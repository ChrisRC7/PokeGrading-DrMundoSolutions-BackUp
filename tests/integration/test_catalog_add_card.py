"""Integration tests for POST /api/v3/catalog/cards (US-002, multipart con imagen)."""
from __future__ import annotations

import io

from fastapi.testclient import TestClient
from PIL import Image

_URL = "/api/v3/catalog/cards"

_FIELDS = {
    "name": "Charizard",
    "set_name": "Base Set",
    "card_number": "4/102",
    "edition": "1st Edition",
    "language": "en",
    "finish": "Holo",
}


def _png(color=(200, 80, 40), size=(200, 280)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


def _front_files():
    return {"image_front": ("front.png", io.BytesIO(_png()), "image/png")}


def test_add_card_as_admin(client: TestClient, admin_token: str):
    """AC-01: admin + datos válidos + imagen de frente -> 201 con referencia guardada."""
    resp = client.post(
        _URL,
        data=_FIELDS,
        files=_front_files(),
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["name"] == "Charizard"
    assert data["status"] == "pending"
    assert data["version"] == 1
    assert data["has_image_front"] is True


def test_add_card_as_submitter_is_forbidden(client: TestClient, submitter_token: str):
    """AC-02: submitter -> 403."""
    resp = client.post(
        _URL,
        data=_FIELDS,
        files=_front_files(),
        headers={"Authorization": f"Bearer {submitter_token}"},
    )
    assert resp.status_code == 403


def test_add_card_duplicate_identity(client: TestClient, admin_token: str):
    """AC-04: identidad duplicada -> 409."""
    headers = {"Authorization": f"Bearer {admin_token}"}
    client.post(_URL, data=_FIELDS, files=_front_files(), headers=headers)
    resp = client.post(_URL, data=_FIELDS, files=_front_files(), headers=headers)
    assert resp.status_code == 409


def test_add_card_without_token_is_unauthorized(client: TestClient):
    """Sin token -> 401."""
    resp = client.post(_URL, data=_FIELDS, files=_front_files())
    assert resp.status_code == 401


def test_add_card_missing_required_field(client: TestClient, admin_token: str):
    """Falta 'name' -> 422."""
    fields = {k: v for k, v in _FIELDS.items() if k != "name"}
    resp = client.post(
        _URL,
        data=fields,
        files=_front_files(),
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 422


def test_add_card_without_front_image_is_unprocessable(
    client: TestClient, admin_token: str
):
    """La imagen de frente es obligatoria -> 422 si no se envía."""
    resp = client.post(
        _URL,
        data=_FIELDS,
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 422
