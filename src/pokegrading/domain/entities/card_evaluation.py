from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from pokegrading.domain.value_objects.grading_region import GradingRegion


@dataclass(frozen=True)
class Subgrade:
    """Score de una sola dimensión de grading (AC-G1).

    hamming_distance es la distancia pHash entre el recorte del envío y
    el recorte equivalente de la imagen de referencia del catálogo.
    confidence es el insumo principal de la banda de incertidumbre.
    """

    region: GradingRegion
    score: float
    hamming_distance: int
    confidence: float


@dataclass(frozen=True)
class CardEvaluation:
    """Evaluación estimada e INMUTABLE de una carta (AC-G5).

    Una vez creada nunca se modifica: una nueva versión del algoritmo
    genera otra fila, dejando intacta esta (append-only, AC-G5/G6).
    """

    id: UUID
    submission_id: UUID
    card_id: UUID | None
    subgrades: tuple[Subgrade, ...]
    final_grade: float
    uncertainty: float
    algorithm_version: str
    baseline_ref: str
    created_at: datetime
