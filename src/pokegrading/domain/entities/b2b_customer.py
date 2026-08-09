from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from pokegrading.domain.value_objects.b2b_customer_status import B2BCustomerStatus


@dataclass
class B2BCustomer:
    """Customer B2B (tienda) que consume el API de cobertura de catálogo (US-005)."""

    id: UUID
    name: str
    status: B2BCustomerStatus
    created_at: datetime

    def is_active(self) -> bool:
        return self.status == B2BCustomerStatus.ACTIVE
