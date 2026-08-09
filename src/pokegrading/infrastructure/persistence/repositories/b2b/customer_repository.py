from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from pokegrading.domain.entities.b2b_customer import B2BCustomer
from pokegrading.domain.repositories.b2b_customer_repository import (
    IB2BCustomerRepository,
)
from pokegrading.domain.value_objects.b2b_customer_status import B2BCustomerStatus
from pokegrading.infrastructure.persistence.models import B2BCustomerORM


class B2BCustomerRepositoryImpl(IB2BCustomerRepository):
    def __init__(self, db: Session) -> None:
        self._db = db

    def find_by_id(self, customer_id: UUID) -> B2BCustomer | None:
        row = (
            self._db.query(B2BCustomerORM)
            .filter(B2BCustomerORM.id == customer_id)
            .first()
        )
        return self._to_entity(row) if row else None

    def save(self, customer: B2BCustomer) -> B2BCustomer:
        row = (
            self._db.query(B2BCustomerORM)
            .filter(B2BCustomerORM.id == customer.id)
            .first()
        )
        if row is None:
            row = B2BCustomerORM(
                id=customer.id,
                name=customer.name,
                status=customer.status,
                created_at=customer.created_at,
            )
            self._db.add(row)
        else:
            row.name = customer.name
            row.status = customer.status
        self._db.commit()
        self._db.refresh(row)
        return self._to_entity(row)

    @staticmethod
    def _to_entity(row: B2BCustomerORM) -> B2BCustomer:
        return B2BCustomer(
            id=row.id,
            name=row.name,
            status=B2BCustomerStatus(row.status)
            if isinstance(row.status, str)
            else row.status,
            created_at=row.created_at,
        )
