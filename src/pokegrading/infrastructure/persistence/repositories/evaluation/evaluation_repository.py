from __future__ import annotations

from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from pokegrading.domain.entities.card_evaluation import CardEvaluation, Subgrade
from pokegrading.domain.repositories.evaluation_repository import IEvaluationRepository
from pokegrading.domain.value_objects.grading_region import GradingRegion
from pokegrading.infrastructure.persistence.models import (
    CardEvaluationORM,
    EvaluationSubgradeORM,
)


def _row_to_entity(row: CardEvaluationORM) -> CardEvaluation:
    subgrades = tuple(
        Subgrade(
            region=GradingRegion(sg.region),
            score=sg.score,
            hamming_distance=sg.hamming_distance,
            confidence=sg.confidence,
        )
        for sg in row.subgrades
    )
    return CardEvaluation(
        id=row.id,
        submission_id=row.submission_id,
        card_id=row.card_id,
        subgrades=subgrades,
        final_grade=row.final_grade,
        uncertainty=row.uncertainty,
        algorithm_version=row.algorithm_version,
        baseline_ref=row.baseline_ref,
        created_at=row.created_at,
    )


class EvaluationRepositoryImpl(IEvaluationRepository):
    def __init__(self, db: Session) -> None:
        self._db = db

    def find_by_submission_and_version(
        self, submission_id: UUID, algorithm_version: str
    ) -> CardEvaluation | None:
        row = (
            self._db.query(CardEvaluationORM)
            .filter(
                CardEvaluationORM.submission_id == submission_id,
                CardEvaluationORM.algorithm_version == algorithm_version,
            )
            .first()
        )
        return _row_to_entity(row) if row else None

    def save(self, evaluation: CardEvaluation) -> CardEvaluation:
        """INSERT-only (append-only). Ante violación de unicidad por carrera,
        devuelve la fila ya existente en vez de lanzar (idempotencia AC-G6)."""
        try:
            row = CardEvaluationORM(
                id=evaluation.id,
                submission_id=evaluation.submission_id,
                card_id=evaluation.card_id,
                final_grade=evaluation.final_grade,
                uncertainty=evaluation.uncertainty,
                algorithm_version=evaluation.algorithm_version,
                baseline_ref=evaluation.baseline_ref,
                created_at=evaluation.created_at,
            )
            self._db.add(row)
            self._db.flush()  # flush para detectar IntegrityError antes de agregar subgrades

            for sg in evaluation.subgrades:
                self._db.add(
                    EvaluationSubgradeORM(
                        evaluation_id=row.id,
                        region=sg.region.value,
                        score=sg.score,
                        hamming_distance=sg.hamming_distance,
                        confidence=sg.confidence,
                    )
                )
            self._db.commit()
            self._db.refresh(row)
            return _row_to_entity(row)

        except IntegrityError:
            self._db.rollback()
            # La fila ya existe (carrera de requests): devolver la existente
            existing = (
                self._db.query(CardEvaluationORM)
                .filter(
                    CardEvaluationORM.submission_id == evaluation.submission_id,
                    CardEvaluationORM.algorithm_version == evaluation.algorithm_version,
                )
                .first()
            )
            return _row_to_entity(existing)  # type: ignore[arg-type]
