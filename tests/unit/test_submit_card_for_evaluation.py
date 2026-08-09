"""Unit tests for SubmitCardForEvaluationUseCase (US-003)."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from pokegrading.application.ports.image_quality_service import IImageQualityService
from pokegrading.application.use_cases.submit_card_for_evaluation import (
    SUBMISSION_IQS_THRESHOLD,
    SubmitCardForEvaluationUseCase,
    SubmitCardInput,
)
from pokegrading.domain.entities.submission import Submission
from pokegrading.domain.exceptions import (
    BothImagesRequiredError,
    FileTooLargeError,
    ImageQualityBelowThresholdError,
    InvalidFileFormatError,
    PolyglotDetectedError,
)
from pokegrading.domain.value_objects.submission_status import SubmissionStatus

# ── Fixtures de imagen ────────────────────────────────────────────────────────

_JPEG_HEADER = b"\xff\xd8\xff" + b"\x00" * 100          # JPEG mínimo válido
_PNG_HEADER = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100       # PNG mínimo válido
_INVALID_BYTES = b"NOTANIMAGE" + b"\x00" * 100
_POLYGLOT_JPEG = b"\xff\xd8\xff" + b"\x00" * 50 + b"PK\x05\x06" + b"\x00" * 18  # firma ZIP al final
_10MB_PLUS = _JPEG_HEADER + b"\x00" * (10 * 1024 * 1024)  # > 10 MB

# ── Fakes ─────────────────────────────────────────────────────────────────────


class FakeSubmissionRepo:
    def __init__(self) -> None:
        self._store: dict = {}

    def save(self, submission: Submission) -> Submission:
        self._store[submission.id] = submission
        return submission

    def find_by_id(self, submission_id):
        return self._store.get(submission_id)

    def find_by_user(self, user_id):
        return [s for s in self._store.values() if s.user_id == user_id]


class GoodQualityService(IImageQualityService):
    def evaluate(self, image_data: bytes) -> float:
        return 0.85


class LowQualityService(IImageQualityService):
    def evaluate(self, image_data: bytes) -> float:
        return 0.30


def _make_use_case(quality_svc: IImageQualityService | None = None) -> SubmitCardForEvaluationUseCase:
    return SubmitCardForEvaluationUseCase(
        submission_repo=FakeSubmissionRepo(),
        quality_svc=quality_svc or GoodQualityService(),
    )


def _base_input(**overrides) -> SubmitCardInput:
    return SubmitCardInput(
        user_id=uuid4(),
        image_front_data=overrides.get("image_front_data", _JPEG_HEADER),
        image_back_data=overrides.get("image_back_data", _PNG_HEADER),
    )


# ── Tests ──────────────────────────────────────────────────────────────────────

def test_submit_without_front_image_raises():
    """AC-02: falta imagen de frente → BothImagesRequiredError."""
    with pytest.raises(BothImagesRequiredError) as exc_info:
        _make_use_case().execute(_base_input(image_front_data=None))
    assert "front" in str(exc_info.value)


def test_submit_without_back_image_raises():
    """AC-02: falta imagen de reverso → BothImagesRequiredError."""
    with pytest.raises(BothImagesRequiredError) as exc_info:
        _make_use_case().execute(_base_input(image_back_data=None))
    assert "back" in str(exc_info.value)


def test_submit_with_invalid_front_format_raises():
    """AC-03: formato no JPEG/PNG en frente → InvalidFileFormatError."""
    with pytest.raises(InvalidFileFormatError) as exc_info:
        _make_use_case().execute(_base_input(image_front_data=_INVALID_BYTES))
    assert "front" in str(exc_info.value)


def test_submit_with_invalid_back_format_raises():
    """AC-03: formato no JPEG/PNG en reverso → InvalidFileFormatError."""
    with pytest.raises(InvalidFileFormatError) as exc_info:
        _make_use_case().execute(_base_input(image_back_data=_INVALID_BYTES))
    assert "back" in str(exc_info.value)


def test_submit_exceeding_size_raises():
    """AC-04: imagen > 10 MB → FileTooLargeError."""
    with pytest.raises(FileTooLargeError) as exc_info:
        _make_use_case().execute(_base_input(image_front_data=_10MB_PLUS))
    assert "front" in str(exc_info.value)


def test_submit_polyglot_raises():
    """AC-05: archivo políglotas → PolyglotDetectedError."""
    with pytest.raises(PolyglotDetectedError) as exc_info:
        _make_use_case().execute(_base_input(image_front_data=_POLYGLOT_JPEG))
    assert "front" in str(exc_info.value)


def test_submit_low_quality_raises():
    """AC-06: IQS < umbral → ImageQualityBelowThresholdError."""
    with pytest.raises(ImageQualityBelowThresholdError) as exc_info:
        _make_use_case(LowQualityService()).execute(_base_input())
    assert "front" in str(exc_info.value)
    assert exc_info.value.score == pytest.approx(0.30)


def test_submit_valid_returns_pending_submission():
    """AC-01: imágenes válidas, calidad OK → evaluation_id + status PENDING."""
    result = _make_use_case().execute(_base_input())

    assert result.evaluation_id is not None
    assert result.status == SubmissionStatus.PENDING.value
    assert isinstance(result.received_at, datetime)
