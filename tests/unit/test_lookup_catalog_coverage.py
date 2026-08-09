from __future__ import annotations

from datetime import datetime, timezone

import pytest
from uuid_extensions import uuid7

from pokegrading.application.ports.rate_limiter import RateLimitVerdict
from pokegrading.application.use_cases.lookup_catalog_coverage import (
    LookupCatalogCoverageUseCase,
)
from pokegrading.domain.entities.api_key import ApiKey
from pokegrading.domain.entities.b2b_customer import B2BCustomer
from pokegrading.domain.entities.card import Card
from pokegrading.domain.entities.card_lookup import CardLookupItem
from pokegrading.domain.exceptions import (
    EmptyLookupQueryError,
    IdempotencyKeyReuseError,
    RateLimitExceededError,
)
from pokegrading.domain.repositories.b2b_idempotency_repository import IdempotencyRecord
from pokegrading.domain.value_objects.api_key_status import ApiKeyStatus
from pokegrading.domain.value_objects.b2b_customer_status import B2BCustomerStatus
from pokegrading.domain.value_objects.card_identity import CardIdentityTuple
from pokegrading.domain.value_objects.card_status import CardStatus

_NOW = datetime.now(tz=timezone.utc)


# ── Fakes (duck-typed, no DB) ─────────────────────────────────────────────────


class FakeCardRepo:
    def __init__(self, cards: list[Card]) -> None:
        self._cards = cards

    def find_active_by_partial_identity(
        self, set_name, card_number, edition=None, language=None, finish=None
    ):
        out = []
        for c in self._cards:
            if c.status != CardStatus.ACTIVE:
                continue
            if c.identity.set_name.lower() != set_name.lower():
                continue
            if c.identity.card_number.lower() != card_number.lower():
                continue
            if edition and c.identity.edition.lower() != edition.lower():
                continue
            if language and c.identity.language.lower() != language.lower():
                continue
            if finish and c.identity.finish.lower() != finish.lower():
                continue
            out.append(c)
        return sorted(out, key=lambda c: str(c.id))

    def get_catalog_fingerprint(self) -> str:
        return "cat-test"


class FakeRateLimiter:
    def __init__(self, allowed: bool = True, retry: int = 60) -> None:
        self._allowed = allowed
        self._retry = retry
        self.calls: list[int] = []

    def check_and_consume(self, api_key, cards):
        self.calls.append(cards)
        return RateLimitVerdict(allowed=self._allowed, retry_after_seconds=self._retry)


class FakeAuditRepo:
    def __init__(self) -> None:
        self.records = []

    def record_lookup(self, record) -> None:
        self.records.append(record)


class FakeIdempotencyRepo:
    def __init__(self) -> None:
        self.store: dict = {}

    def find_within_window(self, api_key_id, request_id, window_start):
        return self.store.get((api_key_id, request_id))

    def save(self, record: IdempotencyRecord) -> None:
        self.store[(record.api_key_id, record.request_id)] = record


# ── Builders ──────────────────────────────────────────────────────────────────


def _card(set_name="Base Set", number="58/102", edition="Unlimited",
          language="en", finish="holo", name="Pikachu",
          status=CardStatus.ACTIVE) -> Card:
    return Card(
        id=uuid7(),
        identity=CardIdentityTuple(set_name, number, edition, language, finish),
        name=name,
        status=status,
        version=1,
        created_by=uuid7(),
        created_at=_NOW,
    )


def _customer() -> B2BCustomer:
    return B2BCustomer(id=uuid7(), name="Tienda", status=B2BCustomerStatus.ACTIVE, created_at=_NOW)


def _api_key() -> ApiKey:
    return ApiKey(
        id=uuid7(),
        customer_id=uuid7(),
        key_prefix="abcd1234",
        hashed_secret="x",
        status=ApiKeyStatus.ACTIVE,
        scopes="catalog:lookup",
        rate_limit_cards_per_window=1000,
        rate_limit_window_seconds=3600,
        created_at=_NOW,
    )


def _use_case(cards, rate=None, audit=None, idem=None):
    return LookupCatalogCoverageUseCase(
        card_repo=FakeCardRepo(cards),
        rate_limiter=rate or FakeRateLimiter(),
        audit_repo=audit or FakeAuditRepo(),
        idempotency_repo=idem or FakeIdempotencyRepo(),
    )


def _run(uc, items, *, customer=None, api_key=None, **kwargs):
    return uc.execute(
        customer=customer or _customer(),
        api_key=api_key or _api_key(),
        items=items,
        trace_id="t-1",
        **kwargs,
    )


# ── Tests por estado de resultado ─────────────────────────────────────────────


def test_covered_single_active_match():
    card = _card()
    resp = _run(_use_case([card]), [CardLookupItem("Base Set", "58/102")])
    assert resp.summary["covered"] == 1
    assert resp.results[0].status == "covered"
    assert resp.results[0].card is not None
    assert resp.results[0].card.card_id == str(card.id)


def test_not_covered_when_no_match():
    resp = _run(_use_case([]), [CardLookupItem("Nope", "999")])
    assert resp.results[0].status == "not_covered"
    assert resp.summary["not_covered"] == 1


def test_retired_card_is_not_covered():
    retired = _card(status=CardStatus.RETIRED)
    resp = _run(_use_case([retired]), [CardLookupItem("Base Set", "58/102")])
    assert resp.results[0].status == "not_covered"


def test_multiple_match_returns_candidates_in_stable_order():
    c1 = _card(finish="holo")
    c2 = _card(finish="reverse holo")
    uc = _use_case([c1, c2])
    item = [CardLookupItem("Base Set", "58/102")]  # sin finish → ambas coinciden
    resp1 = _run(uc, item)
    resp2 = _run(uc, item)
    assert resp1.results[0].status == "multiple_match"
    ids1 = [c.card_id for c in resp1.results[0].candidates]
    ids2 = [c.card_id for c in resp2.results[0].candidates]
    assert ids1 == ids2  # orden estable y reproducible
    assert len(ids1) == 2


def test_invalid_params_missing_set():
    resp = _run(_use_case([]), [CardLookupItem("", "58/102")])
    assert resp.results[0].status == "invalid_params"
    assert resp.results[0].reason["field"] == "set"


def test_invalid_params_missing_number():
    resp = _run(_use_case([]), [CardLookupItem("Base Set", None)])
    assert resp.results[0].status == "invalid_params"
    assert resp.results[0].reason["field"] == "number"


def test_invalid_params_non_canonical_language():
    resp = _run(_use_case([]), [CardLookupItem("Base Set", "58/102", language="xx")])
    assert resp.results[0].status == "invalid_params"
    assert resp.results[0].reason["code"] == "NON_CANONICAL_VALUE"
    assert resp.results[0].reason["field"] == "language"


def test_mixed_batch_is_resolved_independently():
    card = _card()
    items = [
        CardLookupItem("Base Set", "58/102"),   # covered
        CardLookupItem("Nope", "1"),            # not_covered
        CardLookupItem("", "1"),                # invalid_params
    ]
    resp = _run(_use_case([card]), items)
    assert resp.summary == {
        "total": 3, "covered": 1, "multiple_match": 0,
        "not_covered": 1, "invalid_params": 1,
    }


# ── Reglas de la consulta ─────────────────────────────────────────────────────


def test_empty_query_raises():
    with pytest.raises(EmptyLookupQueryError):
        _run(_use_case([]), [])


def test_rate_limit_exceeded_raises_with_retry():
    rate = FakeRateLimiter(allowed=False, retry=42)
    with pytest.raises(RateLimitExceededError) as exc:
        _run(_use_case([], rate=rate), [CardLookupItem("Base Set", "58/102")])
    assert exc.value.retry_after_seconds == 42


def test_rate_limit_counts_cards_not_calls():
    rate = FakeRateLimiter()
    items = [CardLookupItem("Base Set", "58/102") for _ in range(5)]
    _run(_use_case([], rate=rate), items)
    assert rate.calls == [5]  # una llamada de 5 cartas → consume 5


# ── Idempotencia ──────────────────────────────────────────────────────────────


def test_idempotent_replay_returns_same_response_without_recounting():
    card = _card()
    rate = FakeRateLimiter()
    audit = FakeAuditRepo()
    idem = FakeIdempotencyRepo()
    uc = _use_case([card], rate=rate, audit=audit, idem=idem)
    items = [CardLookupItem("Base Set", "58/102")]
    customer, api_key = _customer(), _api_key()

    first = _run(uc, items, customer=customer, api_key=api_key, request_id="r-1")
    second = _run(uc, items, customer=customer, api_key=api_key, request_id="r-1")

    assert second.etag == first.etag
    assert second.results[0].status == "covered"
    assert rate.calls == [1]        # no se reconsumió rate limit
    assert len(audit.records) == 1  # no se reauditó


def test_idempotency_reuse_with_different_content_raises():
    idem = FakeIdempotencyRepo()
    uc = _use_case([], idem=idem)
    customer, api_key = _customer(), _api_key()
    _run(uc, [CardLookupItem("Base Set", "58/102")],
         customer=customer, api_key=api_key, request_id="r-1")
    with pytest.raises(IdempotencyKeyReuseError):
        _run(uc, [CardLookupItem("Other Set", "1")],
             customer=customer, api_key=api_key, request_id="r-1")


# ── Validación condicional (ETag) ─────────────────────────────────────────────


def test_if_none_match_returns_not_modified():
    resp = _run(_use_case([]), [CardLookupItem("Base Set", "58/102")],
                if_none_match='"cat-test"')
    assert resp.not_modified is True


def test_audit_recorded_on_normal_response():
    audit = FakeAuditRepo()
    _run(_use_case([_card()], audit=audit), [CardLookupItem("Base Set", "58/102")])
    assert len(audit.records) == 1
    assert audit.records[0].trace_id == "t-1"
