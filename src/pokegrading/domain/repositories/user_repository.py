from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from pokegrading.domain.entities.user import User


class IUserRepository(ABC):
    """Port (interface) for User persistence.

    The domain never imports SQLAlchemy directly — all DB access goes through
    this abstraction (Repository pattern, DoD.md).
    """

    @abstractmethod
    def find_by_email(self, email: str) -> User | None:
        ...

    @abstractmethod
    def find_by_id(self, user_id: UUID) -> User | None:
        ...

    @abstractmethod
    def save(self, user: User) -> User:
        ...
