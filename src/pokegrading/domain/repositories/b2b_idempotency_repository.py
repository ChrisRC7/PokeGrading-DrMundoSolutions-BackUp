from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class IdempotencyRecord:
    """Respuesta almacenada para una `(api_key_id, request_id)` (ADR-004 §3)."""

    api_key_id: UUID
    request_id: str
    request_hash: str
    response_json: str


class IIdempotencyRepository(ABC):
    """Puerto de persistencia de idempotencia de consultas B2B."""

    @abstractmethod
    def find_within_window(
        self, api_key_id: UUID, request_id: str, window_start: datetime
    ) -> IdempotencyRecord | None:
        """Devuelve el registro si existe uno con `created_at >= window_start`."""
        ...

    @abstractmethod
    def save(self, record: IdempotencyRecord) -> None:
        ...
