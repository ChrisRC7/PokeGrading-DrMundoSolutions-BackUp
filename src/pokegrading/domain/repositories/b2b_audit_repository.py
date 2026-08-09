from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class LookupAuditRecord:
    """Registro de auditoría de una consulta B2B (US-005, AC-15).

    Nunca contiene el secreto de la API key (solo el id de la llave) ni
    datos de evaluación.
    """

    api_key_id: UUID
    customer_id: UUID
    trace_id: str
    card_count: int
    covered: int
    multiple: int
    not_covered: int
    invalid: int
    request_id: str | None = None


class IB2BAuditRepository(ABC):
    """Puerto de persistencia de la auditoría de consultas B2B."""

    @abstractmethod
    def record_lookup(self, record: LookupAuditRecord) -> None:
        ...
