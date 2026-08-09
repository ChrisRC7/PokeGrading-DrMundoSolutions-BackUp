from __future__ import annotations

from abc import ABC, abstractmethod

from pokegrading.domain.entities.card_evaluation import Subgrade
from pokegrading.domain.entities.grading_baseline import GradingBaseline
from pokegrading.domain.value_objects.grading_region import GradingRegion


class IRegionGradingService(ABC):
    @abstractmethod
    def grade_region(
        self,
        region: GradingRegion,
        submission_region_phash: str,
        reference_region_phash: str,
        baseline: GradingBaseline,
        *,
        submission_region_data: bytes = b"",
        reference_region_data: bytes = b"",
    ) -> Subgrade:
        """Calcula el subgrade de una región.

        Devuelve un Subgrade con score en 1.0–10.0. Si los insumos son
        insuficientes (p. ej. pHash de referencia ausente / región ilegible),
        lanza InsufficientGradingInputError para que el use case derive a
        calificación manual (AC-G7).

        `submission_region_data` / `reference_region_data` son los bytes de los
        recortes normalizados. Son opcionales (default vacío) para no romper a las
        implementaciones que solo usan pHash; las implementaciones sensibles al
        daño (rayones, marcas) comparan los píxeles de ambos recortes.

        Nota de alcance: este puerto pertenece a la etapa de CALIFICAR. La etapa de
        IDENTIFICAR carta (búsqueda pHash) no usa este puerto y no se ve afectada.
        """
