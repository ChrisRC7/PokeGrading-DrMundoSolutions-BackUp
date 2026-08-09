"""Tests de PreprocessCardUseCase (AC-P3/P4/P5)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from pokegrading.application.use_cases.preprocess_card import (
    PreprocessCardInput,
    PreprocessCardUseCase,
)
from pokegrading.domain.entities.submission import Submission
from pokegrading.domain.exceptions import SubmissionNotFoundError
from pokegrading.domain.value_objects.submission_status import SubmissionStatus
from pokegrading.infrastructure.matching.phash_image_hash_service import StubImageHashService
from pokegrading.infrastructure.preprocessing.pillow_card_preprocessing_service import (
    StubCardPreprocessingService,
)


def _make_submission(
    image_front: bytes = b"fake_image",
    status: SubmissionStatus = SubmissionStatus.PENDING,
) -> Submission:
    return Submission(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        image_front_data=image_front,
        image_back_data=b"back",
        status=status,
        created_at=datetime.now(tz=timezone.utc),
    )


def _make_use_case(submission: Submission | None):
    submission_repo = MagicMock()
    submission_repo.find_by_id.return_value = submission
    submission_repo.save.side_effect = lambda s: s

    region_repo = MagicMock()
    region_repo.save.return_value = None

    return (
        PreprocessCardUseCase(
            submission_repo=submission_repo,
            region_repo=region_repo,
            preprocessing_svc=StubCardPreprocessingService(),
            hash_svc=StubImageHashService(),
        ),
        submission_repo,
        region_repo,
    )


def test_ok_path_returns_preprocessed(tmp_path):
    """Stub sin señal especial → PREPROCESSED + 4 regiones guardadas (AC-P3)."""
    sub = _make_submission(b"normal image")
    uc, sub_repo, reg_repo = _make_use_case(sub)

    result = uc.execute(PreprocessCardInput(submission_id=sub.id))

    assert result.status == "preprocessed"
    assert result.regions_ready is True
    assert result.reason is None
    reg_repo.save.assert_called_once()
    _, regions = reg_repo.save.call_args.args
    assert len(regions) == 4


def test_manual_review_when_isolation_fails():
    """Stub recibe señal MANUAL: → MANUAL_REVIEW (AC-P4)."""
    sub = _make_submission(b"MANUAL:cant_isolate")
    uc, sub_repo, reg_repo = _make_use_case(sub)

    result = uc.execute(PreprocessCardInput(submission_id=sub.id))

    assert result.status == "manual_review"
    assert result.regions_ready is False
    reg_repo.save.assert_not_called()


def test_needs_recapture_when_distortion_fails():
    """Stub recibe señal RECAPTURE: → NEEDS_RECAPTURE (AC-P5)."""
    sub = _make_submission(b"RECAPTURE:bad_angle")
    uc, sub_repo, reg_repo = _make_use_case(sub)

    result = uc.execute(PreprocessCardInput(submission_id=sub.id))

    assert result.status == "needs_recapture"
    assert result.regions_ready is False
    reg_repo.save.assert_not_called()


def test_submission_not_found_raises():
    """submission_id desconocido → SubmissionNotFoundError (404)."""
    uc, _, _ = _make_use_case(None)
    with pytest.raises(SubmissionNotFoundError):
        uc.execute(PreprocessCardInput(submission_id=uuid.uuid4()))


def test_phash_computed_for_all_regions():
    """El use case recomputa pHash por región con el hash service (no usa el del stub)."""
    sub = _make_submission(b"normal image")
    uc, _, reg_repo = _make_use_case(sub)

    uc.execute(PreprocessCardInput(submission_id=sub.id))

    _, regions = reg_repo.save.call_args.args
    # StubImageHashService siempre devuelve un hash no vacío para datos no vacíos
    for r in regions:
        assert r.phash != ""
