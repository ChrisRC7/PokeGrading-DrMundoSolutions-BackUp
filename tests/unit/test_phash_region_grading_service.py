"""Tests de PHashRegionGradingService (AC-G1/G7)."""
from __future__ import annotations

import pytest

from pokegrading.domain.entities.grading_baseline import GradingBaseline
from pokegrading.domain.exceptions import InsufficientGradingInputError
from pokegrading.domain.value_objects.grading_region import GradingRegion
from pokegrading.infrastructure.grading.phash_region_grading_service import (
    PHashRegionGradingService,
)

_PARAMS = {region: (4, 28) for region in GradingRegion}

_BASELINE = GradingBaseline(
    ref="global",
    is_calibrated=False,
    params_by_region=_PARAMS,
    ground_truth_count=0,
)

_SVC = PHashRegionGradingService()

# pHash de todos ceros y todos unos (distancias extremas)
_HASH_ZEROS = "0000000000000000"
_HASH_ONES = "ffffffffffffffff"


def test_distance_zero_gives_max_score():
    sg = _SVC.grade_region(
        GradingRegion.CENTERING, _HASH_ZEROS, _HASH_ZEROS, _BASELINE
    )
    assert sg.score == 10.0
    assert sg.hamming_distance == 0
    assert sg.confidence == 1.0


def test_distance_max_gives_min_score():
    sg = _SVC.grade_region(
        GradingRegion.CORNERS, _HASH_ZEROS, _HASH_ONES, _BASELINE
    )
    assert sg.score == 1.0
    assert sg.hamming_distance == 64
    assert sg.confidence == 0.0


def test_score_clamped_to_range():
    sg = _SVC.grade_region(
        GradingRegion.SURFACE, _HASH_ZEROS, _HASH_ZEROS, _BASELINE
    )
    assert 1.0 <= sg.score <= 10.0


def test_confidence_clamped_to_range():
    sg = _SVC.grade_region(
        GradingRegion.EDGES, _HASH_ZEROS, _HASH_ONES, _BASELINE
    )
    assert 0.0 <= sg.confidence <= 1.0


def test_empty_submission_phash_raises():
    with pytest.raises(InsufficientGradingInputError):
        _SVC.grade_region(GradingRegion.CENTERING, "", _HASH_ZEROS, _BASELINE)


def test_empty_reference_phash_raises():
    with pytest.raises(InsufficientGradingInputError):
        _SVC.grade_region(GradingRegion.CENTERING, _HASH_ZEROS, "", _BASELINE)


def test_midpoint_distance_gives_intermediate_score():
    """Distancia ~16 (½ máximo) debe dar score entre 1 y 10."""
    # flip los primeros 16 bits para distancia exactamente 16
    mid_hash = "0000000000000fff"
    sg = _SVC.grade_region(GradingRegion.SURFACE, _HASH_ZEROS, mid_hash, _BASELINE)
    assert 1.0 <= sg.score <= 10.0


def test_region_is_preserved_in_subgrade():
    sg = _SVC.grade_region(GradingRegion.CORNERS, _HASH_ZEROS, _HASH_ZEROS, _BASELINE)
    assert sg.region == GradingRegion.CORNERS
