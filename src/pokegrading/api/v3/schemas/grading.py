from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel


class PreprocessResponse(BaseModel):
    submission_id: UUID
    status: str           # "preprocessed" | "manual_review" | "needs_recapture"
    regions_ready: bool
    reason: str | None = None


class SubgradeSchema(BaseModel):
    region: str           # GradingRegion value
    score: float
    hamming_distance: int
    confidence: float


class EvaluationResponse(BaseModel):
    evaluation_id: UUID
    submission_id: UUID
    status: str           # "graded" | "manual_review"
    final_grade: float | None = None
    uncertainty: float | None = None
    subgrades: list[SubgradeSchema]
    algorithm_version: str
    baseline_ref: str | None = None
