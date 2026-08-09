from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from pokegrading.domain.entities.preprocessed_card import RegionImage
from pokegrading.domain.repositories.region_repository import IRegionRepository
from pokegrading.domain.value_objects.grading_region import GradingRegion
from pokegrading.infrastructure.persistence.models import SubmissionRegionORM


class RegionRepositoryImpl(IRegionRepository):
    def __init__(self, db: Session) -> None:
        self._db = db

    def save(self, submission_id: UUID, regions: list[RegionImage]) -> None:
        for region_img in regions:
            # merge garantiza idempotencia: si ya existe la fila (submission_id, region)
            # la actualiza; si no, la crea. Esto permite reejecutar preprocesamiento.
            existing = (
                self._db.query(SubmissionRegionORM)
                .filter(
                    SubmissionRegionORM.submission_id == submission_id,
                    SubmissionRegionORM.region == region_img.region.value,
                )
                .first()
            )
            if existing:
                existing.data = region_img.data
                existing.phash = region_img.phash
            else:
                row = SubmissionRegionORM(
                    submission_id=submission_id,
                    region=region_img.region.value,
                    data=region_img.data,
                    phash=region_img.phash,
                )
                self._db.add(row)
        self._db.commit()

    def find_by_submission(self, submission_id: UUID) -> list[RegionImage]:
        rows = (
            self._db.query(SubmissionRegionORM)
            .filter(SubmissionRegionORM.submission_id == submission_id)
            .all()
        )
        return [
            RegionImage(
                region=GradingRegion(row.region),
                data=row.data,
                phash=row.phash,
            )
            for row in rows
        ]
