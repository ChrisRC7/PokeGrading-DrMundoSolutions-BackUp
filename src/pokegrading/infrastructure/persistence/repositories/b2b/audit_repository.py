from __future__ import annotations

from sqlalchemy.orm import Session
from uuid_extensions import uuid7

from pokegrading.domain.repositories.b2b_audit_repository import (
    IB2BAuditRepository,
    LookupAuditRecord,
)
from pokegrading.infrastructure.persistence.models import B2BLookupAuditORM


class B2BAuditRepositoryImpl(IB2BAuditRepository):
    def __init__(self, db: Session) -> None:
        self._db = db

    def record_lookup(self, record: LookupAuditRecord) -> None:
        row = B2BLookupAuditORM(
            id=uuid7(),
            api_key_id=record.api_key_id,
            customer_id=record.customer_id,
            request_id=record.request_id,
            trace_id=record.trace_id,
            card_count=record.card_count,
            covered=record.covered,
            multiple=record.multiple,
            not_covered=record.not_covered,
            invalid=record.invalid,
        )
        self._db.add(row)
        self._db.commit()
