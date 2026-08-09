from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class SubmissionResponse(BaseModel):
    evaluation_id: UUID
    status: str
    received_at: datetime
    card_id: UUID | None = None
    image_quality_score: float | None = None


class SubmissionStatusResponse(BaseModel):
    evaluation_id: UUID
    status: str
    received_at: datetime
    card_id: UUID | None = None
    image_quality_score: float | None = None
    rejection_reason: str | None = None


class SubmissionListItem(BaseModel):
    evaluation_id: UUID
    user_id: UUID
    status: str
    received_at: datetime
    card_id: UUID | None = None
    image_quality_score: float | None = None
    rejection_reason: str | None = None
