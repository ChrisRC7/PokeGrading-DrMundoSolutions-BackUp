from __future__ import annotations

from dataclasses import dataclass

from pokegrading.domain.value_objects.grading_region import GradingRegion


@dataclass(frozen=True)
class GradingBaseline:
    """Parámetros de calibración del mapeo distancia-pHash → grado por región.

    Puede ser calibrado (ground truth real de un set+finish específico) o
    global (valores por defecto sembrados). El use case registra cuál usó
    en CardEvaluation.baseline_ref (AC-G2).
    """

    ref: str
    is_calibrated: bool
    params_by_region: dict[GradingRegion, tuple[int, int]]
    ground_truth_count: int

    def score_for(self, region: GradingRegion, d: int) -> float:
        """Mapea distancia de Hamming [0..64] a score [1.0..10.0].

        La interpolación es lineal entre d_min (→ 10.0) y d_max (→ 1.0).
        Fuera de rango se satura: por debajo de d_min siempre es 10.0,
        por encima de d_max siempre es 1.0.
        """
        d_min, d_max = self.params_by_region[region]
        if d <= d_min:
            return 10.0
        if d >= d_max:
            return 1.0
        return 10.0 - 9.0 * (d - d_min) / (d_max - d_min)
