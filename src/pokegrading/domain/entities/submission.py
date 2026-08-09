from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from pokegrading.domain.value_objects.submission_status import SubmissionStatus


@dataclass
class Submission:
    """Envío de una carta física para evaluación de grado.

    Contiene los bytes binarios de las imágenes frente y reverso capturadas
    por el Submitter. Se almacenan como BYTEA en PostgreSQL (Sprint 2).
    """

    id: UUID
    user_id: UUID                   # FK al submitter que generó el envío
    image_front_data: bytes         # imagen de frente embebida en el agregado
    image_back_data: bytes          # imagen de reverso embebida en el agregado
    status: SubmissionStatus
    created_at: datetime
    card_id: UUID | None = None             # FK a catálogo; puede ser None si aún no se identifica
    image_quality_score: float | None = None
    rejection_reason: str | None = None
