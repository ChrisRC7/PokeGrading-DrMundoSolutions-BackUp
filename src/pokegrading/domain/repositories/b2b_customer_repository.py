from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from pokegrading.domain.entities.b2b_customer import B2BCustomer


class IB2BCustomerRepository(ABC):
    """Puerto de persistencia de Customers B2B."""

    @abstractmethod
    def find_by_id(self, customer_id: UUID) -> B2BCustomer | None:
        ...

    @abstractmethod
    def save(self, customer: B2BCustomer) -> B2BCustomer:
        ...
