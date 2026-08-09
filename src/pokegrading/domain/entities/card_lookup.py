from __future__ import annotations

from dataclasses import dataclass, field

from pokegrading.domain.entities.card import Card
from pokegrading.domain.value_objects.lookup_result_status import LookupResultStatus


@dataclass(frozen=True)
class CardLookupItem:
    """Una carta solicitada en una consulta B2B (US-005).

    Solo transporta los valores tal cual llegan de la tienda; NO valida
    en construcción, porque "parámetros inválidos" es un estado de
    resultado por carta (no una excepción que aborte el batch).

    Obligatorios: ``set_name`` y ``card_number``.
    Opcionales: ``edition``, ``language``, ``finish`` (desambiguan variantes).
    """

    set_name: str | None
    card_number: str | None
    edition: str | None = None
    language: str | None = None
    finish: str | None = None


@dataclass(frozen=True)
class InvalidReason:
    """Motivo de un resultado ``invalid_params`` para una carta concreta."""

    code: str
    field: str | None
    message: str


@dataclass
class CardLookupResult:
    """Resultado independiente de una carta dentro de la consulta.

    - ``COVERED``: ``matches`` tiene exactamente 1 carta.
    - ``MULTIPLE_MATCH``: ``matches`` tiene N cartas en orden estable.
    - ``NOT_COVERED``: ``matches`` vacío.
    - ``INVALID_PARAMS``: ``reason`` indica el motivo.
    """

    index: int
    status: LookupResultStatus
    query: CardLookupItem
    matches: list[Card] = field(default_factory=list)
    reason: InvalidReason | None = None
