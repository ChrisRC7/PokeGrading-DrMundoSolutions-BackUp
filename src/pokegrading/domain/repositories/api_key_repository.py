from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from uuid import UUID

from pokegrading.domain.entities.api_key import ApiKey


class IApiKeyRepository(ABC):
    """Puerto de persistencia de API keys B2B (Repository pattern, DoD.md)."""

    @abstractmethod
    def find_by_prefix(self, key_prefix: str) -> ApiKey | None:
        ...

    @abstractmethod
    def save(self, api_key: ApiKey) -> ApiKey:
        ...

    @abstractmethod
    def touch_last_used(self, api_key_id: UUID, when: datetime) -> None:
        """Actualiza `last_used_at` sin reemplazar el resto de la fila."""
        ...
