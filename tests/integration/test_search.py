"""Integration tests for POST /api/v3/search/quick (US-004)."""
from __future__ import annotations

import io
import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from pokegrading.api.v3.routers.search import _get_matching_svc
from pokegrading.application.ports.card_matching_service import ICardMatchingService
from pokegrading.domain.value_objects.card_status import CardStatus
from pokegrading.infrastructure.persistence.models import CardORM, UserORM
from pokegrading.main import app

_JPEG = b"\xff\xd8\xff" + b"\x00" * 50
_NOT_IMAGE = b"NOTIMAGE" + b"\x00" * 50


# ── Fake matching service ─────────────────────────────────────────────────────


class _QueryFeedingMatchingService(ICardMatchingService):
    """Devuelve un query fijo en lugar de extraer features de la imagen."""

    def __init__(self, features: str) -> None:
        self._features = features

    def extract_features(self, image_data: bytes) -> str:
        return self._features


# ── Helpers ───────────────────────────────────────────────────────────────────


def _insert_active_card(
    db: Session,
    creator_id: uuid.UUID,
    *,
    name: str = "Pikachu",
    set_name: str = "Vivid Voltage",
    card_number: str = "025/185",
    language: str = "en",
    rarity: str = "Common",
    hp: int = 60,
    pokemon_type: str = "Lightning",
    status: CardStatus = CardStatus.ACTIVE,
) -> CardORM:
    row = CardORM(
        id=uuid.uuid4(),
        name=name,
        set_name=set_name,
        card_number=card_number,
        edition="1st",
        language=language,
        finish="normal",
        status=status,
        version=1,
        description=None,
        rarity=rarity,
        pokemon_type=pokemon_type,
        hp=hp,
        illustrator=None,
        print_year=None,
        created_by=creator_id,
        created_at=datetime.now(tz=timezone.utc),
    )
    db.add(row)
    db.flush()
    return row


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_quick_search_without_token_returns_401(client: TestClient):
    """AC-05: sin token >> 401."""
    resp = client.post(
        "/api/v3/search/quick",
        files={"image_front": ("card.jpg", io.BytesIO(_JPEG), "image/jpeg")},
        data={"q": "pikachu"},
    )
    assert resp.status_code == 401


def test_quick_search_no_features_no_query_returns_422(
    client: TestClient, submitter_token: str
):
    """AC-04: imagen que EasyOCR no puede leer texto + sin q → 422 ImageNotIdentifiable.

    Se envía un JPEG mínimo (53 bytes, imagen corrupta). PIL no puede decodificarlo
    correctamente, EasyOCRCardMatchingService.extract_features() captura la excepción
    y retorna '' → effective_q = None → ImageNotIdentifiableError → 422.
    """
    resp = client.post(
        "/api/v3/search/quick",
        headers={"Authorization": f"Bearer {submitter_token}"},
        files={"image_front": ("card.jpg", io.BytesIO(_JPEG), "image/jpeg")},
    )
    assert resp.status_code == 422
    assert "identified" in resp.json()["detail"].lower()


def test_quick_search_query_no_match_returns_404(
    client: TestClient, db: Session, submitter_user: UserORM, submitter_token: str
):
    """AC-03: query valida sin coincidencias en catalogo >> 404."""
    _insert_active_card(db, submitter_user.id, name="Pikachu")

    resp = client.post(
        "/api/v3/search/quick",
        headers={"Authorization": f"Bearer {submitter_token}"},
        files={"image_front": ("card.jpg", io.BytesIO(_JPEG), "image/jpeg")},
        data={"q": "Charizard"},
    )
    assert resp.status_code == 404
    detail = resp.json()["detail"]
    assert "Charizard" in detail["message"]


def test_quick_search_returns_candidates(
    client: TestClient, db: Session, submitter_user: UserORM, submitter_token: str
):
    """AC-01: query con coincidencias >> lista de candidatos con card_id y confidence."""
    _insert_active_card(db, submitter_user.id, name="Pikachu", card_number="025/185")
    _insert_active_card(db, submitter_user.id, name="Pikachu V", card_number="043/185")

    resp = client.post(
        "/api/v3/search/quick",
        headers={"Authorization": f"Bearer {submitter_token}"},
        files={"image_front": ("card.jpg", io.BytesIO(_JPEG), "image/jpeg")},
        data={"q": "pikachu"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["total"] >= 1
    assert len(data["candidates"]) >= 1
    first = data["candidates"][0]
    assert "candidate_card_id" in first
    assert "confidence_score" in first
    assert first["rank"] == 1


def test_quick_search_auto_accepted_when_exact_match(
    client: TestClient, db: Session, submitter_user: UserORM, submitter_token: str
):
    """AC-02: match exacto (confidence=1.0) y umbral=0.6 >> auto_accepted=True."""
    _insert_active_card(db, submitter_user.id, name="Pikachu")

    resp = client.post(
        "/api/v3/search/quick",
        headers={"Authorization": f"Bearer {submitter_token}"},
        files={"image_front": ("card.jpg", io.BytesIO(_JPEG), "image/jpeg")},
        data={"q": "Pikachu", "confidence_threshold": "0.60"},
    )
    assert resp.status_code == 200
    assert resp.json()["auto_accepted"] is True


def test_quick_search_not_auto_accepted_when_partial_match_high_threshold(
    client: TestClient, db: Session, submitter_user: UserORM, submitter_token: str
):
    """AC-02 inverso: match parcial (confidence=0.70) con umbral=0.9 >> auto_accepted=False."""
    _insert_active_card(db, submitter_user.id, name="Pikachu V")

    resp = client.post(
        "/api/v3/search/quick",
        headers={"Authorization": f"Bearer {submitter_token}"},
        files={"image_front": ("card.jpg", io.BytesIO(_JPEG), "image/jpeg")},
        data={"q": "pikachu", "confidence_threshold": "0.90"},
    )
    assert resp.status_code == 200
    assert resp.json()["auto_accepted"] is False


def test_quick_search_not_jpeg_or_png_returns_422(
    client: TestClient, submitter_token: str
):
    """Imagen invalida (no JPEG/PNG) >> 422."""
    resp = client.post(
        "/api/v3/search/quick",
        headers={"Authorization": f"Bearer {submitter_token}"},
        files={"image_front": ("card.txt", io.BytesIO(_NOT_IMAGE), "application/octet-stream")},
        data={"q": "pikachu"},
    )
    assert resp.status_code == 422


def test_quick_search_missing_image_returns_422(
    client: TestClient, submitter_token: str
):
    """Sin image_front >> 422."""
    resp = client.post(
        "/api/v3/search/quick",
        headers={"Authorization": f"Bearer {submitter_token}"},
        data={"q": "pikachu"},
    )
    assert resp.status_code == 422


def test_quick_search_with_ml_features_override(
    client: TestClient, db: Session, submitter_user: UserORM, submitter_token: str
):
    """Simula motor ML que extrae features >> usa features en lugar de q."""
    _insert_active_card(db, submitter_user.id, name="Charizard")

    app.dependency_overrides[_get_matching_svc] = lambda: _QueryFeedingMatchingService("Charizard")
    try:
        resp = client.post(
            "/api/v3/search/quick",
            headers={"Authorization": f"Bearer {submitter_token}"},
            files={"image_front": ("card.jpg", io.BytesIO(_JPEG), "image/jpeg")},
        )
    finally:
        app.dependency_overrides.pop(_get_matching_svc, None)

    assert resp.status_code == 200
    data = resp.json()
    assert data["candidates"][0]["name"] == "Charizard"


def test_quick_search_only_returns_active_cards(
    client: TestClient, db: Session, submitter_user: UserORM, submitter_token: str
):
    """Solo se devuelven cartas ACTIVE; las PENDING no aparecen en busqueda."""
    _insert_active_card(db, submitter_user.id, name="Mewtwo", status=CardStatus.PENDING)

    resp = client.post(
        "/api/v3/search/quick",
        headers={"Authorization": f"Bearer {submitter_token}"},
        files={"image_front": ("card.jpg", io.BytesIO(_JPEG), "image/jpeg")},
        data={"q": "mewtwo"},
    )
    assert resp.status_code == 404
