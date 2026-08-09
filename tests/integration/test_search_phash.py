"""Integration tests para la búsqueda rápida por pHash y escalamiento a OCR (Sprint 3)."""
from __future__ import annotations

import io
import uuid
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy.orm import Session

from pokegrading.infrastructure.matching.phash_image_hash_service import (
    PHashImageHashService,
)
from pokegrading.infrastructure.persistence.models import CardImageORM, UserORM
from tests.conftest import _make_active_card

_QUICK = "/api/v3/search/quick"
_SPECIALIZED = "/api/v3/search/specialized"


def _png(color=(120, 80, 200), size=(200, 280)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


def _attach_front_image(db: Session, card_id, uploader_id, data: bytes) -> None:
    phash = PHashImageHashService().compute_phash(data)
    db.add(
        CardImageORM(
            id=uuid.uuid4(),
            card_id=card_id,
            side="front",
            content_type="image/png",
            width=200,
            height=280,
            file_size=len(data),
            data=data,
            phash=phash,
            uploaded_at=datetime.now(tz=timezone.utc),
            uploaded_by=uploader_id,
        )
    )
    db.commit()


def test_quick_search_matches_by_phash(
    client: TestClient, db: Session, submitter_user: UserORM, submitter_token: str
):
    img = _png()
    card = _make_active_card(db, submitter_user.id, name="Pikachu", card_number="025/185")
    _attach_front_image(db, card.id, submitter_user.id, img)

    resp = client.post(
        _QUICK,
        headers={"Authorization": f"Bearer {submitter_token}"},
        files={"image_front": ("card.png", io.BytesIO(img), "image/png")},
    )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["match_engine"] == "phash"
    assert data["candidates"][0]["candidate_card_id"] == str(card.id)
    assert data["auto_accepted"] is True


def test_quick_search_escalates_to_ocr_when_no_phash_match(
    client: TestClient, db: Session, submitter_user: UserORM, submitter_token: str
):
    # Carta sin imagen de referencia → no hay pHash que coincida → escala a OCR (con q).
    _make_active_card(db, submitter_user.id, name="Pikachu")
    other = _png(color=(10, 240, 10))

    resp = client.post(
        _QUICK,
        headers={"Authorization": f"Bearer {submitter_token}"},
        files={"image_front": ("card.png", io.BytesIO(other), "image/png")},
        data={"q": "Pikachu"},
    )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["match_engine"] == "ocr"
    assert data["candidates"][0]["name"] == "Pikachu"


def test_specialized_search_uses_ocr(
    client: TestClient, db: Session, submitter_user: UserORM, submitter_token: str
):
    _make_active_card(db, submitter_user.id, name="Charizard")

    resp = client.post(
        _SPECIALIZED,
        headers={"Authorization": f"Bearer {submitter_token}"},
        files={"image_front": ("card.png", io.BytesIO(_png()), "image/png")},
        data={"q": "Charizard"},
    )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["match_engine"] == "ocr"
    assert data["candidates"][0]["name"] == "Charizard"


def test_quick_search_without_token_returns_401(client: TestClient):
    resp = client.post(
        _QUICK,
        files={"image_front": ("card.png", io.BytesIO(_png()), "image/png")},
    )
    assert resp.status_code == 401
