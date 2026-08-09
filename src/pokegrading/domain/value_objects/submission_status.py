from __future__ import annotations

from enum import Enum


class SubmissionStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    PREPROCESSED = "preprocessed"
    GRADED = "graded"
    REJECTED = "rejected"
    MANUAL_REVIEW = "manual_review"
    NEEDS_RECAPTURE = "needs_recapture"
