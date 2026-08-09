from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from pokegrading.domain.value_objects.api_key_status import ApiKeyStatus
from pokegrading.domain.value_objects.b2b_customer_status import B2BCustomerStatus
from pokegrading.domain.value_objects.card_status import CardStatus
from pokegrading.infrastructure.persistence.models import B2BLookupAuditORM, UserORM
from tests.conftest import _make_active_card, _make_b2b_key

_URL = "/api/b2b/v1/catalog/lookup"


def _creator(db: Session) -> UserORM:
    from tests.conftest import _make_user

    return _make_user(db, email="b2b-creator@example.com", alias="creator")


def test_lookup_covered_returns_200(client: TestClient, db: Session) -> None:
    creator = _creator(db)
    _make_active_card(db, creator.id, set_name="Vivid Voltage", card_number="025/185")
    key, _, _ = _make_b2b_key(db)

    resp = client.post(
        _URL,
        json={"cards": [{"set": "Vivid Voltage", "number": "025/185"}]},
        headers={"X-API-Key": key},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["summary"]["covered"] == 1
    assert body["results"][0]["status"] == "covered"
    assert body["results"][0]["card"]["set"] == "Vivid Voltage"
    assert resp.headers.get("ETag")


def test_lookup_isolation_only_exposes_catalog_metadata(
    client: TestClient, db: Session
) -> None:
    creator = _creator(db)
    _make_active_card(db, creator.id, set_name="Vivid Voltage", card_number="025/185")
    key, _, _ = _make_b2b_key(db)

    resp = client.post(
        _URL,
        json={"cards": [{"set": "Vivid Voltage", "number": "025/185"}]},
        headers={"X-API-Key": key},
    )
    card = resp.json()["results"][0]["card"]
    assert set(card.keys()) == {"card_id", "set", "number", "edition", "language", "finish"}


def test_lookup_mixed_batch(client: TestClient, db: Session) -> None:
    creator = _creator(db)
    _make_active_card(db, creator.id, set_name="Base Set", card_number="58/102")
    key, _, _ = _make_b2b_key(db)

    resp = client.post(
        _URL,
        json={
            "cards": [
                {"set": "Base Set", "number": "58/102"},  # covered
                {"set": "Ghost", "number": "1"},          # not_covered
                {"set": "", "number": "9"},               # invalid_params
            ]
        },
        headers={"X-API-Key": key},
    )
    assert resp.status_code == 200
    assert resp.json()["summary"] == {
        "total": 3, "covered": 1, "multiple_match": 0,
        "not_covered": 1, "invalid_params": 1,
    }


def test_lookup_without_api_key_returns_401(client: TestClient) -> None:
    resp = client.post(_URL, json={"cards": [{"set": "X", "number": "1"}]})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "INVALID_API_KEY"
    assert resp.json()["error"]["trace_id"]


def test_lookup_with_invalid_api_key_returns_401(client: TestClient) -> None:
    resp = client.post(
        _URL,
        json={"cards": [{"set": "X", "number": "1"}]},
        headers={"X-API-Key": "pkg_live_deadbeef_nopenope"},
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "INVALID_API_KEY"


def test_lookup_suspended_customer_returns_403(client: TestClient, db: Session) -> None:
    key, _, _ = _make_b2b_key(db, customer_status=B2BCustomerStatus.SUSPENDED)
    resp = client.post(
        _URL,
        json={"cards": [{"set": "X", "number": "1"}]},
        headers={"X-API-Key": key},
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "CUSTOMER_SUSPENDED"


def test_lookup_revoked_key_returns_401(client: TestClient, db: Session) -> None:
    key, _, _ = _make_b2b_key(db, status=ApiKeyStatus.REVOKED)
    resp = client.post(
        _URL,
        json={"cards": [{"set": "X", "number": "1"}]},
        headers={"X-API-Key": key},
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "API_KEY_REVOKED"


def test_lookup_empty_query_returns_422(client: TestClient, db: Session) -> None:
    key, _, _ = _make_b2b_key(db)
    resp = client.post(_URL, json={"cards": []}, headers={"X-API-Key": key})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "EMPTY_QUERY"


def test_lookup_idempotent_replay_not_recounted(client: TestClient, db: Session) -> None:
    creator = _creator(db)
    _make_active_card(db, creator.id, set_name="Base Set", card_number="58/102")
    key, _, _ = _make_b2b_key(db)
    payload = {"request_id": "req-1", "cards": [{"set": "Base Set", "number": "58/102"}]}

    first = client.post(_URL, json=payload, headers={"X-API-Key": key})
    second = client.post(_URL, json=payload, headers={"X-API-Key": key})

    assert first.status_code == second.status_code == 200
    assert first.json()["results"] == second.json()["results"]
    # La auditoría solo registró la primera consulta (el replay no reaudita).
    assert db.query(B2BLookupAuditORM).count() == 1


def test_lookup_conditional_request_returns_304(client: TestClient, db: Session) -> None:
    creator = _creator(db)
    _make_active_card(db, creator.id, set_name="Base Set", card_number="58/102")
    key, _, _ = _make_b2b_key(db)
    payload = {"cards": [{"set": "Base Set", "number": "58/102"}]}

    first = client.post(_URL, json=payload, headers={"X-API-Key": key})
    etag = first.headers["ETag"]

    second = client.post(
        _URL, json=payload, headers={"X-API-Key": key, "If-None-Match": etag}
    )
    assert second.status_code == 304


def test_lookup_unexpected_failure_returns_single_error_format(
    client: TestClient, db: Session, monkeypatch
) -> None:
    """AC-14: fallo temporal → formato de error único INTERNAL_ERROR, sin estado parcial."""
    key, _, _ = _make_b2b_key(db)

    def _boom(self, *args, **kwargs):
        raise RuntimeError("db caída")

    monkeypatch.setattr(
        "pokegrading.application.use_cases.lookup_catalog_coverage."
        "LookupCatalogCoverageUseCase.execute",
        _boom,
    )

    resp = client.post(
        _URL,
        json={"cards": [{"set": "X", "number": "1"}]},
        headers={"X-API-Key": key},
    )
    assert resp.status_code == 500
    assert resp.json()["error"]["code"] == "INTERNAL_ERROR"
    assert resp.json()["error"]["trace_id"]


def test_lookup_rate_limit_returns_429(client: TestClient, db: Session) -> None:
    key, _, _ = _make_b2b_key(db, rate_cards=1)
    resp = client.post(
        _URL,
        json={"cards": [{"set": "A", "number": "1"}, {"set": "B", "number": "2"}]},
        headers={"X-API-Key": key},
    )
    assert resp.status_code == 429
    assert resp.json()["error"]["code"] == "RATE_LIMIT_EXCEEDED"
    assert resp.headers.get("Retry-After")
