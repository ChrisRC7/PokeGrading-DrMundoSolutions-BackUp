"""Tests de GradeCardUseCase (AC-G1..G8)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from pokegrading.application.use_cases.grade_card import (
    GRADING_ALGORITHM_VERSION,
    GradeCardInput,
    GradeCardUseCase,
)
from pokegrading.domain.entities.card_evaluation import CardEvaluation, Subgrade
from pokegrading.domain.entities.grading_baseline import GradingBaseline
from pokegrading.domain.entities.preprocessed_card import RegionImage
from pokegrading.domain.entities.submission import Submission
from pokegrading.domain.exceptions import CardNotPreprocessedError, SubmissionNotFoundError
from pokegrading.domain.value_objects.grading_region import GradingRegion
from pokegrading.domain.value_objects.submission_status import SubmissionStatus
from pokegrading.infrastructure.grading.phash_region_grading_service import (
    StubRegionGradingService,
)

_HASH_A = "aabbccddeeff0011"
_HASH_B = "aabbccddeeff0011"  # mismos → distancia 0 → score 10.0

_PARAMS = {region: (4, 28) for region in GradingRegion}
_BASELINE = GradingBaseline(
    ref="global",
    is_calibrated=False,
    params_by_region=_PARAMS,
    ground_truth_count=0,
)


def _make_submission(status: SubmissionStatus = SubmissionStatus.PREPROCESSED) -> Submission:
    return Submission(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        image_front_data=b"front",
        image_back_data=b"back",
        status=status,
        created_at=datetime.now(tz=timezone.utc),
        card_id=None,
        image_quality_score=0.9,
    )


def _make_regions(phash: str = _HASH_A) -> list[RegionImage]:
    return [
        RegionImage(region=r, data=b"bytes", phash=phash)
        for r in GradingRegion
    ]


def _make_uc(
    submission: Submission | None = None,
    regions: list[RegionImage] | None = None,
    existing_eval: CardEvaluation | None = None,
    fixed_distance: int = 0,
) -> GradeCardUseCase:
    sub = submission or _make_submission()

    submission_repo = MagicMock()
    submission_repo.find_by_id.return_value = sub
    submission_repo.save.side_effect = lambda s: s

    region_repo = MagicMock()
    region_repo.find_by_submission.return_value = regions or _make_regions()

    evaluation_repo = MagicMock()
    evaluation_repo.find_by_submission_and_version.return_value = existing_eval
    evaluation_repo.save.side_effect = lambda e: e

    baseline_repo = MagicMock()
    baseline_repo.get_for.return_value = _BASELINE

    card_repo = MagicMock()
    card_repo.find_by_id.return_value = None  # sin carta de referencia → phash vacío

    image_repo = MagicMock()
    image_repo.find_by_card_and_side.return_value = None  # sin imagen de referencia

    preprocessing_svc = MagicMock()  # no se invoca cuando no hay imagen de referencia
    hash_svc = MagicMock()

    return GradeCardUseCase(
        submission_repo=submission_repo,
        region_repo=region_repo,
        evaluation_repo=evaluation_repo,
        baseline_repo=baseline_repo,
        card_repo=card_repo,
        image_repo=image_repo,
        preprocessing_svc=preprocessing_svc,
        hash_svc=hash_svc,
        grading_svc=StubRegionGradingService(fixed_distance=fixed_distance),
    )


# ── Pruebas de casos exitosos ──────────────────────────────────────────────────

def test_grade_without_reference_returns_manual_review():
    """Sin pHash de referencia (carta de catálogo sin imagen) → MANUAL_REVIEW (AC-G7)."""
    uc = _make_uc()
    result = uc.execute(GradeCardInput(submission_id=_make_submission().id))
    # La submission del mock devuelve PREPROCESSED pero card_id=None→sin ref phash
    # → el use case detecta ref vacío y devuelve manual_review
    assert result.status == "manual_review"


def test_grade_not_found_raises():
    """submission_id desconocido → SubmissionNotFoundError."""
    uc_obj = _make_uc()
    # Reemplazar el submission_repo para devolver None
    uc_obj._submission_repo.find_by_id.return_value = None
    with pytest.raises(SubmissionNotFoundError):
        uc_obj.execute(GradeCardInput(submission_id=uuid.uuid4()))


def test_grade_not_preprocessed_raises():
    """Submission en estado PENDING → CardNotPreprocessedError (409)."""
    sub = _make_submission(status=SubmissionStatus.PENDING)
    uc = _make_uc(submission=sub)
    with pytest.raises(CardNotPreprocessedError):
        uc.execute(GradeCardInput(submission_id=sub.id))


def test_idempotence_returns_existing_evaluation():
    """Si ya existe evaluación con la misma versión, se devuelve sin recalcular (AC-G6)."""
    sub = _make_submission()
    existing = CardEvaluation(
        id=uuid.uuid4(),
        submission_id=sub.id,
        card_id=None,
        subgrades=(
            Subgrade(GradingRegion.CENTERING, 9.0, 2, 0.9),
            Subgrade(GradingRegion.CORNERS, 8.5, 3, 0.85),
            Subgrade(GradingRegion.EDGES, 8.0, 4, 0.8),
            Subgrade(GradingRegion.SURFACE, 8.2, 3, 0.82),
        ),
        final_grade=8.5,
        uncertainty=0.5,
        algorithm_version=GRADING_ALGORITHM_VERSION,
        baseline_ref="global",
        created_at=datetime.now(tz=timezone.utc),
    )
    uc = _make_uc(submission=sub, existing_eval=existing)
    result = uc.execute(GradeCardInput(submission_id=sub.id))
    assert result.evaluation_id == existing.id
    assert result.status == "graded"


def test_coherence_rule_grade_not_exceed_worst_plus_half():
    """El grado final no excede el subgrade más bajo + 0.5 (AC-G3)."""
    from pokegrading.application.use_cases.grade_card import _compute_final_grade, PESOS

    subgrades = [
        Subgrade(GradingRegion.CENTERING, 9.5, 1, 0.99),
        Subgrade(GradingRegion.CORNERS, 9.0, 2, 0.95),
        Subgrade(GradingRegion.EDGES, 2.0, 30, 0.1),   # peor subgrade
        Subgrade(GradingRegion.SURFACE, 8.5, 5, 0.9),
    ]
    final = _compute_final_grade(subgrades)
    min_sub = 2.0
    assert final <= min_sub + 0.5 + 1e-9  # tolerancia de float


def test_uncertainty_band_present():
    """El output de grade incluye la banda de incertidumbre (AC-G4)."""
    from pokegrading.application.use_cases.grade_card import _compute_uncertainty

    subgrades = [
        Subgrade(GradingRegion.CENTERING, 8.0, 5, 0.9),
        Subgrade(GradingRegion.CORNERS, 8.0, 5, 0.9),
        Subgrade(GradingRegion.EDGES, 8.0, 5, 0.9),
        Subgrade(GradingRegion.SURFACE, 8.0, 5, 0.9),
    ]
    band = _compute_uncertainty(subgrades, is_calibrated=True, image_quality_score=0.9)
    assert band >= 0.0


def test_uncalibrated_baseline_widens_band():
    """Baseline no calibrado (global) produce banda mayor (AC-G4)."""
    from pokegrading.application.use_cases.grade_card import _compute_uncertainty

    subgrades = [
        Subgrade(GradingRegion.CENTERING, 8.0, 5, 0.9),
        Subgrade(GradingRegion.CORNERS, 8.0, 5, 0.9),
        Subgrade(GradingRegion.EDGES, 8.0, 5, 0.9),
        Subgrade(GradingRegion.SURFACE, 8.0, 5, 0.9),
    ]
    band_global = _compute_uncertainty(subgrades, is_calibrated=False, image_quality_score=0.9)
    band_calibrated = _compute_uncertainty(subgrades, is_calibrated=True, image_quality_score=0.9)
    assert band_global > band_calibrated


def test_algorithm_version_in_output():
    """El output incluye el identificador exacto de versión del algoritmo (AC-G5)."""
    sub = _make_submission()
    existing = CardEvaluation(
        id=uuid.uuid4(),
        submission_id=sub.id,
        card_id=None,
        subgrades=(),
        final_grade=8.0,
        uncertainty=0.5,
        algorithm_version=GRADING_ALGORITHM_VERSION,
        baseline_ref="global",
        created_at=datetime.now(tz=timezone.utc),
    )
    uc = _make_uc(submission=sub, existing_eval=existing)
    result = uc.execute(GradeCardInput(submission_id=sub.id))
    assert result.algorithm_version == GRADING_ALGORITHM_VERSION
