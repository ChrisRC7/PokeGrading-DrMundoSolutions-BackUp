from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from pokegrading.domain.entities.submission import Submission
from pokegrading.domain.repositories.submission_repository import ISubmissionRepository
from pokegrading.domain.value_objects.submission_status import SubmissionStatus
from pokegrading.infrastructure.persistence.models import SubmissionORM


class SubmissionRepositoryImpl(ISubmissionRepository):
    def __init__(self, db: Session) -> None:
        self._db = db

    def save(self, submission: Submission) -> Submission:
        row = SubmissionORM(
            id=submission.id,
            user_id=submission.user_id,
            card_id=submission.card_id,
            image_front_data=submission.image_front_data,
            image_back_data=submission.image_back_data,
            status=submission.status,
            image_quality_score=submission.image_quality_score,
            rejection_reason=submission.rejection_reason,
            created_at=submission.created_at,
        )
        self._db.merge(row)
        self._db.commit()
        return self._to_entity(self._db.get(SubmissionORM, submission.id))  # type: ignore[arg-type]

    def find_by_id(self, submission_id: UUID) -> Submission | None:
        row = self._db.get(SubmissionORM, submission_id)
        return self._to_entity(row) if row else None

    def find_by_user(self, user_id: UUID) -> list[Submission]:
        rows = (
            self._db.query(SubmissionORM)
            .filter(SubmissionORM.user_id == user_id)
            .order_by(SubmissionORM.created_at.desc())
            .all()
        )
        return [self._to_entity(r) for r in rows]

    def find_all(self) -> list[Submission]:
        rows = (
            self._db.query(SubmissionORM)
            .order_by(SubmissionORM.created_at.desc())
            .all()
        )
        return [self._to_entity(r) for r in rows]

    @staticmethod
    def _to_entity(row: SubmissionORM) -> Submission:
        return Submission(
            id=row.id,
            user_id=row.user_id,
            card_id=row.card_id,
            image_front_data=row.image_front_data,
            image_back_data=row.image_back_data,
            status=SubmissionStatus(row.status),
            image_quality_score=row.image_quality_score,
            rejection_reason=row.rejection_reason,
            created_at=row.created_at,
        )
