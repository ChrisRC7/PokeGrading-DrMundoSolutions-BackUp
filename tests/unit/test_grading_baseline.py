"""Tests de GradingBaseline (AC-G2, score_for monótona decreciente)."""
from __future__ import annotations

import pytest

from pokegrading.domain.entities.grading_baseline import GradingBaseline
from pokegrading.domain.value_objects.grading_region import GradingRegion

_PARAMS = {region: (4, 28) for region in GradingRegion}


def _make_baseline(is_calibrated: bool = True, count: int = 30) -> GradingBaseline:
    return GradingBaseline(
        ref="Base Set:holo",
        is_calibrated=is_calibrated,
        params_by_region=_PARAMS,
        ground_truth_count=count,
    )


def test_score_at_dmin_is_10():
    bl = _make_baseline()
    assert bl.score_for(GradingRegion.CENTERING, 4) == 10.0


def test_score_at_dmax_is_1():
    bl = _make_baseline()
    assert bl.score_for(GradingRegion.CENTERING, 28) == 1.0


def test_score_below_dmin_is_10():
    bl = _make_baseline()
    assert bl.score_for(GradingRegion.CENTERING, 0) == 10.0


def test_score_above_dmax_is_1():
    bl = _make_baseline()
    assert bl.score_for(GradingRegion.CORNERS, 64) == 1.0


def test_score_is_monotone_decreasing():
    """score_for debe ser monótona no-creciente en d (AC-G2)."""
    bl = _make_baseline()
    prev = bl.score_for(GradingRegion.SURFACE, 0)
    for d in range(1, 65):
        curr = bl.score_for(GradingRegion.SURFACE, d)
        assert curr <= prev, f"Not decreasing at d={d}: prev={prev}, curr={curr}"
        prev = curr


def test_midpoint_score_is_between_1_and_10():
    bl = _make_baseline()
    score = bl.score_for(GradingRegion.EDGES, 16)
    assert 1.0 <= score <= 10.0


def test_all_regions_are_covered():
    """El baseline debe tener parámetros para todas las regiones."""
    bl = _make_baseline()
    for region in GradingRegion:
        score = bl.score_for(region, 10)
        assert 1.0 <= score <= 10.0
