"""Integration tests for POST /api/v3/submissions (US-003)."""
from __future__ import annotations

import io
import uuid

import pytest
from fastapi.testclient import TestClient

from pokegrading.api.v3.routers.submissions import _get_quality_svc
from pokegrading.application.ports.image_quality_service import IImageQualityService
from pokegrading.infrastructure.persistence.repositories.submission_repository import (
    SubmissionRepositoryImpl,
)
from pokegrading.main import app
from tests.conftest import _make_active_card, _token_for

_JPEG_BYTES = b"\xff\xd8\xff" + b"\x00" * 100
_PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100


class _AlwaysGoodQualityService(IImageQualityService):
    def evaluate(self, image_data: bytes) -> float:
        return 0.85


def test_submit_without_token_returns_401(client: TestClient):
    """AC-09: sin token → 401."""
    resp = client.post(
        "/api/v3/submissions",
        files={
            "image_front": ("front.jpg", io.BytesIO(_JPEG_BYTES), "image/jpeg"),
            "image_back": ("back.png", io.BytesIO(_PNG_BYTES), "image/png"),
        },
    )
    assert resp.status_code == 401


def test_submit_valid_returns_201(client: TestClient, submitter_token: str):
    """AC-01: imágenes válidas → 201 con evaluation_id."""
    app.dependency_overrides[_get_quality_svc] = lambda: _AlwaysGoodQualityService()
    try:
        resp = client.post(
            "/api/v3/submissions",
            headers={"Authorization": f"Bearer {submitter_token}"},
            files={
                "image_front": ("front.jpg", io.BytesIO(_JPEG_BYTES), "image/jpeg"),
                "image_back": ("back.png", io.BytesIO(_PNG_BYTES), "image/png"),
            },
        )
    finally:
        app.dependency_overrides.pop(_get_quality_svc, None)

    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert "evaluation_id" in data
    assert data["status"] == "pending"
    assert "received_at" in data


def test_submit_persists_card_id_from_form(client: TestClient, db, submitter_user):
    """Regresión: `card_id` viaja en el cuerpo multipart (Form), no en el query string.

    Si el endpoint lo declarara sin `Form(...)`, FastAPI lo leería del query string
    y siempre llegaría None, dejando el envío sin vínculo con la carta del catálogo
    — lo que rompía la calificación (la derivaba siempre a manual, AC-G7).
    """
    card = _make_active_card(db, submitter_user.id)
    token = _token_for(submitter_user)

    app.dependency_overrides[_get_quality_svc] = lambda: _AlwaysGoodQualityService()
    try:
        resp = client.post(
            "/api/v3/submissions",
            headers={"Authorization": f"Bearer {token}"},
            files={
                "image_front": ("front.jpg", io.BytesIO(_JPEG_BYTES), "image/jpeg"),
                "image_back": ("back.png", io.BytesIO(_PNG_BYTES), "image/png"),
            },
            data={"card_id": str(card.id)},
        )
    finally:
        app.dependency_overrides.pop(_get_quality_svc, None)

    assert resp.status_code == 201, resp.text
    # 1) La respuesta refleja el card_id recibido (no None).
    assert resp.json()["card_id"] == str(card.id)
    # 2) Quedó realmente persistido en el envío (no solo eco del router).
    saved = SubmissionRepositoryImpl(db).find_by_id(uuid.UUID(resp.json()["evaluation_id"]))
    assert saved is not None
    assert str(saved.card_id) == str(card.id)
