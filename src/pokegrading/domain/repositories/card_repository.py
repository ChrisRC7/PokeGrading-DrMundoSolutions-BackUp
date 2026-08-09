from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from pokegrading.domain.entities.card import Card
from pokegrading.domain.value_objects.card_identity import CardIdentityTuple


class ICardRepository(ABC):
    """Port (interface) for Card catalog persistence.

    The domain never imports SQLAlchemy directly (Repository pattern, DoD.md).
    """

    @abstractmethod
    def find_by_identity(self, identity: CardIdentityTuple) -> Card | None:
        ...

    @abstractmethod
    def find_by_id(self, card_id: UUID) -> Card | None:
        ...

    @abstractmethod
    def save(self, card: Card) -> Card:
        ...

    @abstractmethod
    def find_top_candidates(self, query: str, limit: int = 3) -> list[tuple[Card, float]]:
        """Case-insensitive search returning up to `limit` ACTIVE cards with confidence scores.

        Parameters
        ----------
        query:
            Search string (card name, set name, or card number).
        limit:
            Maximum number of results to return.

        Returns
        -------
        List of (Card, confidence_score) tuples ordered by confidence desc.
        Returns an empty list when `query` is blank or nothing matches.
        """
        ...

    @abstractmethod
    def find_active_by_partial_identity(
        self,
        set_name: str,
        card_number: str,
        edition: str | None = None,
        language: str | None = None,
        finish: str | None = None,
    ) -> list[Card]:
        """B2B lookup (US-005): cartas ACTIVE que coinciden por identidad parcial.

        `set_name` y `card_number` son obligatorios (igualdad exacta,
        case-insensitive). Los opcionales (`edition`, `language`, `finish`),
        si se proveen, restringen el match para desambiguar variantes.

        Devuelve los resultados en orden estable y reproducible (por `id`),
        de modo que dos consultas idénticas producen el mismo orden.
        Solo retorna cartas activas: una carta retirada nunca aparece.
        """
        ...

    @abstractmethod
    def find_by_phash_near(
        self, phash: str, max_hamming: int = 12, limit: int = 3
    ) -> list[tuple[Card, int]]:
        """Búsqueda rápida por pHash (US-004): cartas ACTIVE visualmente cercanas.

        Compara `phash` contra el pHash de la imagen frontal de cada carta
        activa y devuelve hasta `limit` candidatos cuya distancia de Hamming
        sea ``<= max_hamming``, ordenados por distancia ascendente
        (más parecido primero).

        Returns
        -------
        Lista de (Card, hamming_distance). Vacía si no hay imágenes de
        referencia con pHash o nada está suficientemente cerca → el caller
        escala a la búsqueda especializada por OCR.
        """
        ...

    @abstractmethod
    def get_catalog_fingerprint(self) -> str:
        """Huella corta del estado del catálogo activo, para ETag (ADR-004 §5).

        Cambia cuando se altera el conjunto de cartas activas (altas,
        aprobaciones, retiros, ediciones). Permite validación condicional
        (`If-None-Match` → 304) sin retransferir datos sin cambios.
        """
        ...
