from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from pokegrading.domain.entities.card_image import CardImage


class ICardImageRepository(ABC):
    """Puerto de dominio para almacenar y recuperar imágenes binarias de cartas."""

    @abstractmethod
    def save(self, image: CardImage) -> CardImage:
        """Persiste una imagen nueva o actualiza la existente (mismo card_id + side)."""

    @abstractmethod
    def find_by_card_and_side(self, card_id: UUID, side: str) -> CardImage | None:
        """Retorna la imagen para una carta y cara específica, o None si no existe."""

    @abstractmethod
    def has_front(self, card_id: UUID) -> bool:
        """Retorna True si la carta tiene imagen de frente almacenada."""

    @abstractmethod
    def has_back(self, card_id: UUID) -> bool:
        """Retorna True si la carta tiene imagen de reverso almacenada."""
