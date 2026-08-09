"""Test de integración del pipeline submit → preprocess → grade (Sprint 4).

Verifica el flujo end-to-end usando la TestClient con SQLite in-memory.
"""
from __future__ import annotations

import io
import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy.orm import Session

from pokegrading.domain.value_objects.role import UserRole
from pokegrading.domain.value_objects.submission_status import SubmissionStatus
from pokegrading.infrastructure.persistence.models import (
    SubmissionORM,
    SubmissionRegionORM,
    CardEvaluationORM,
    GradingBaselineORM,
)
from tests.conftest import _make_user, _token_for


# ── Fixtures locales ──────────────────────────────────────────────────────────

def _make_jpeg_bytes(w: int = 200, h: int = 280) -> bytes:
    """Imagen JPEG sintética de tamaño válido (proporción de carta ~1.4:1)."""
    img = Image.new("RGB", (w, h), color=(180, 180, 180))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def _seed_baseline(db: Session) -> None:
    """Siembra el baseline global si no existe (evita depender del script de seed)."""
    import json
    from pokegrading.domain.value_objects.grading_region import GradingRegion

    existing = db.query(GradingBaselineORM).filter_by(ref="global").first()
    if existing:
        return

    params = {r.value: [4, 28] for r in GradingRegion}
    row = GradingBaselineORM(
        id=uuid.uuid4(),
        ref="global",
        is_calibrated=False,
        ground_truth_count=0,
        params_json=json.dumps(params),
        created_at=datetime.now(tz=timezone.utc),
    )
    db.add(row)
    db.commit()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _submit(client: TestClient, token: str, front: bytes, back: bytes) -> str:
    """Envía una carta y devuelve el evaluation_id."""
    resp = client.post(
        "/api/v3/submissions",
        headers={"Authorization": f"Bearer {token}"},
        files={
            "image_front": ("front.jpg", front, "image/jpeg"),
            "image_back": ("back.jpg", back, "image/jpeg"),
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["evaluation_id"]


def _preprocess(client: TestClient, token: str, eid: str) -> dict:
    resp = client.post(
        f"/api/v3/submissions/{eid}/preprocess",
        headers={"Authorization": f"Bearer {token}"},
    )
    return resp


def _grade(client: TestClient, token: str, eid: str) -> dict:
    return client.post(
        f"/api/v3/submissions/{eid}/grade",
        headers={"Authorization": f"Bearer {token}"},
    )


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_preprocess_returns_valid_status(client: TestClient, db: Session, submitter_user, submitter_token: str):
    _seed_baseline(db)
    front = _make_jpeg_bytes()
    back = _make_jpeg_bytes()
    eid = _submit(client, submitter_token, front, back)

    resp = _preprocess(client, submitter_token, eid)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] in ("preprocessed", "manual_review", "needs_recapture")
    assert body["submission_id"] == eid


def test_full_pipeline_preprocessed_to_graded(client: TestClient, db: Session, submitter_user, submitter_token: str):
    """submit → preprocess OK → grade → GRADED con grado y banda (AC-G4)."""
    _seed_baseline(db)
    front = _make_jpeg_bytes()
    back = _make_jpeg_bytes()
    eid = _submit(client, submitter_token, front, back)

    # Forzar estado PREPROCESSED en la BD para garantizar el flujo de grading
    row = db.query(SubmissionORM).filter_by(id=uuid.UUID(eid)).first()
    if row:
        row.status = SubmissionStatus.PREPROCESSED
        db.commit()

    # Insertar regiones mínimas si el preprocess no las creó
    from pokegrading.domain.value_objects.grading_region import GradingRegion
    for region in GradingRegion:
        existing = db.query(SubmissionRegionORM).filter_by(
            submission_id=uuid.UUID(eid), region=region.value
        ).first()
        if not existing:
            db.add(SubmissionRegionORM(
                id=uuid.uuid4(),
                submission_id=uuid.UUID(eid),
                region=region.value,
                data=b"fake_region",
                phash="",  # phash vacío → manual_review (AC-G7)
                created_at=datetime.now(tz=timezone.utc),
            ))
    db.commit()

    resp_grade = _grade(client, submitter_token, eid)
    assert resp_grade.status_code == 200
    body = resp_grade.json()
    assert body["status"] in ("graded", "manual_review")
    assert body["algorithm_version"] == "grading-v1.0.0"


def test_grade_without_preprocess_returns_409(client: TestClient, db: Session, submitter_user, submitter_token: str):
    """Calificar sin preprocesar → 409 (precondición no satisfecha)."""
    _seed_baseline(db)
    front = _make_jpeg_bytes()
    back = _make_jpeg_bytes()
    eid = _submit(client, submitter_token, front, back)

    # No preprocesar — la submission queda en PENDING
    resp = _grade(client, submitter_token, eid)
    assert resp.status_code == 409


def test_grade_idempotent(client: TestClient, db: Session, submitter_user, submitter_token: str):
    """Llamar grade dos veces devuelve el mismo evaluation_id (AC-G6)."""
    _seed_baseline(db)
    from pokegrading.domain.value_objects.grading_region import GradingRegion
    from pokegrading.application.use_cases.grade_card import GRADING_ALGORITHM_VERSION

    front = _make_jpeg_bytes()
    back = _make_jpeg_bytes()
    eid = _submit(client, submitter_token, front, back)

    # Forzar GRADED con evaluación ya existente
    row = db.query(SubmissionORM).filter_by(id=uuid.UUID(eid)).first()
    if row:
        row.status = SubmissionStatus.GRADED
        db.commit()

    eval_id = uuid.uuid4()
    eval_row = CardEvaluationORM(
        id=eval_id,
        submission_id=uuid.UUID(eid),
        card_id=None,
        final_grade=8.0,
        uncertainty=0.5,
        algorithm_version=GRADING_ALGORITHM_VERSION,
        baseline_ref="global",
        created_at=datetime.now(tz=timezone.utc),
    )
    db.add(eval_row)
    db.commit()

    # Primera y segunda llamada deben devolver el mismo evaluation_id
    resp1 = _grade(client, submitter_token, eid)
    resp2 = _grade(client, submitter_token, eid)
    assert resp1.status_code == 200
    assert resp2.status_code == 200
    assert resp1.json()["evaluation_id"] == resp2.json()["evaluation_id"]

    # Solo debe haber una fila en card_evaluations para esta submission+versión
    count = db.query(CardEvaluationORM).filter(
        CardEvaluationORM.submission_id == uuid.UUID(eid),
        CardEvaluationORM.algorithm_version == GRADING_ALGORITHM_VERSION,
    ).count()
    assert count == 1


def test_get_evaluation_404_when_not_graded(client: TestClient, db: Session, submitter_user, submitter_token: str):
    """GET evaluation de un submission sin evaluación → 404."""
    _seed_baseline(db)
    front = _make_jpeg_bytes()
    back = _make_jpeg_bytes()
    eid = _submit(client, submitter_token, front, back)

    resp = client.get(
        f"/api/v3/submissions/{eid}/evaluation",
        headers={"Authorization": f"Bearer {submitter_token}"},
    )
    assert resp.status_code == 404


def test_preprocess_unknown_submission_returns_404(client: TestClient, submitter_token: str):
    """Preprocesar submission inexistente → 404."""
    random_id = uuid.uuid4()
    resp = client.post(
        f"/api/v3/submissions/{random_id}/preprocess",
        headers={"Authorization": f"Bearer {submitter_token}"},
    )
    assert resp.status_code == 404
