from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session
from uuid_extensions import uuid7

from pokegrading.domain.repositories.b2b_idempotency_repository import (
    IdempotencyRecord,
    IIdempotencyRepository,
)
from pokegrading.infrastructure.persistence.models import B2BIdempotencyORM


class IdempotencyRepositoryImpl(IIdempotencyRepository):
    def __init__(self, db: Session) -> None:
        self._db = db

    def find_within_window(
        self, api_key_id: UUID, request_id: str, window_start: datetime
    ) -> IdempotencyRecord | None:
        row = (
            self._db.query(B2BIdempotencyORM)
            .filter(
                B2BIdempotencyORM.api_key_id == api_key_id,
                B2BIdempotencyORM.request_id == request_id,
                B2BIdempotencyORM.created_at >= window_start,
            )
            .order_by(B2BIdempotencyORM.created_at.desc())
            .first()
        )
        if row is None:
            return None
        return IdempotencyRecord(
            api_key_id=row.api_key_id,
            request_id=row.request_id,
            request_hash=row.request_hash,
            response_json=row.response_json,
        )

    def save(self, record: IdempotencyRecord) -> None:
        row = B2BIdempotencyORM(
            id=uuid7(),
            api_key_id=record.api_key_id,
            request_id=record.request_id,
            request_hash=record.request_hash,
            response_json=record.response_json,
        )
        self._db.add(row)
        self._db.commit()
