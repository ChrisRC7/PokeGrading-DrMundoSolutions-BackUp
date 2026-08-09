from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from pokegrading.domain.entities.card_evaluation import CardEvaluation


class IEvaluationRepository(ABC):
    @abstractmethod
    def find_by_submission_and_version(
        self, submission_id: UUID, algorithm_version: str
    ) -> CardEvaluation | None: ...

    @abstractmethod
    def save(self, evaluation: CardEvaluation) -> CardEvaluation:
        """INSERT-only. Si hay violación de unicidad por carrera de requests,
        devuelve la fila ya existente en vez de lanzar (idempotencia AC-G6)."""
