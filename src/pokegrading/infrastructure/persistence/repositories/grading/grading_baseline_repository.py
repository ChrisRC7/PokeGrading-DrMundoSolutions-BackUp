from __future__ import annotations

import json

from sqlalchemy.orm import Session

from pokegrading.domain.entities.grading_baseline import GradingBaseline
from pokegrading.domain.repositories.grading_baseline_repository import IGradingBaselineRepository
from pokegrading.domain.value_objects.grading_region import GradingRegion
from pokegrading.infrastructure.persistence.models import GradingBaselineORM

# Umbral de ground truth para considerar un baseline "calibrado"
_MIN_GROUND_TRUTH = 30
_GLOBAL_REF = "global"


def _row_to_entity(row: GradingBaselineORM) -> GradingBaseline:
    params_raw: dict = json.loads(row.params_json)
    params_by_region: dict[GradingRegion, tuple[int, int]] = {
        GradingRegion(region_str): (d_min, d_max)
        for region_str, (d_min, d_max) in params_raw.items()
    }
    return GradingBaseline(
        ref=row.ref,
        is_calibrated=row.is_calibrated,
        params_by_region=params_by_region,
        ground_truth_count=row.ground_truth_count,
    )


class GradingBaselineRepositoryImpl(IGradingBaselineRepository):
    def __init__(self, db: Session) -> None:
        self._db = db

    def get_for(self, set_name: str, finish: str) -> GradingBaseline:
        """Devuelve el baseline calibrado si tiene suficiente ground truth;
        si no, el baseline GLOBAL. Nunca devuelve None (AC-G2)."""
        ref = f"{set_name}:{finish}"

        specific = (
            self._db.query(GradingBaselineORM)
            .filter(
                GradingBaselineORM.ref == ref,
                GradingBaselineORM.ground_truth_count >= _MIN_GROUND_TRUTH,
            )
            .first()
        )
        if specific:
            return _row_to_entity(specific)

        global_row = (
            self._db.query(GradingBaselineORM)
            .filter(GradingBaselineORM.ref == _GLOBAL_REF)
            .first()
        )
        if global_row is None:
            # El baseline global siempre debe existir (sembrado). Si no está,
            # devolver un baseline in-memory de emergencia para no romper el flujo.
            return _build_fallback_global()

        return _row_to_entity(global_row)


def _build_fallback_global() -> GradingBaseline:
    """Baseline global in-memory de emergencia si el seed no se ejecutó."""
    params = {region: (4, 28) for region in GradingRegion}
    return GradingBaseline(
        ref=_GLOBAL_REF,
        is_calibrated=False,
        params_by_region=params,
        ground_truth_count=0,
    )
