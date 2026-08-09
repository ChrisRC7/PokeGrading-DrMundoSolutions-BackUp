from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from pokegrading.domain.value_objects.card_identity import CardIdentityTuple
from pokegrading.domain.value_objects.card_status import CardStatus


@dataclass
class Card:
    """Card entity representing an entry in PokéGrading's reference catalog.

    Invariants (RNF R11):
    - Cannot be deleted if evaluations are associated with it.
    - New entries start in PENDING status (dual validation required).
    - Approver cannot be the same person as the creator.
    - Modifications to reference images or identity attributes preserve history.
    """

    id: UUID
    identity: CardIdentityTuple
    name: str
    status: CardStatus
    version: int
    created_by: UUID
    created_at: datetime
    description: str | None = None
    rarity: str | None = None
    pokemon_type: str | None = None
    hp: int | None = None
    illustrator: str | None = None
    print_year: int | None = None
    has_image_front: bool = False
    has_image_back: bool = False
    approved_by: UUID | None = None
    approved_at: datetime | None = None

    def __post_init__(self) -> None:
        # Validaciones mínimas para evitar que el dominio quede con datos absurdos
        # incluso si la entidad se crea fuera de la capa HTTP.
        if not self.name or not self.name.strip():
            raise ValueError("Card name cannot be empty")
        if self.version < 1:
            raise ValueError("Card version must be >= 1")

    def is_active(self) -> bool:
        # Atajo semántico para filtros y reglas de negocio del catálogo público.
        return self.status == CardStatus.ACTIVE

    def is_pending(self) -> bool:
        # Útil para saber si una carta aún requiere segunda validación.
        return self.status == CardStatus.PENDING

    def approve(self, approver_id: UUID, approved_at: datetime) -> None:
        """Transition card from PENDING to ACTIVE (second admin validates).

        Raises ValueError if approver is the same user who created the card,
        enforcing the dual-validation requirement (RNF R11).
        """
        # La aprobación no puede ser realizada por el mismo usuario que creó la carta.
        if approver_id == self.created_by:
            raise ValueError(
                "The approver must be different from the card creator (dual validation)"
            )
        # Solo las cartas pendientes pueden moverse a ACTIVE.
        if self.status != CardStatus.PENDING:
            raise ValueError(
                f"Only PENDING cards can be approved. Current status: {self.status}"
            )
        # La transición finaliza el flujo de validación y deja trazabilidad de quién aprobó.
        self.status = CardStatus.ACTIVE
        self.approved_by = approver_id
        self.approved_at = approved_at

    def reset_to_pending(self) -> None:
        """Reset card back to PENDING, clearing any approval data."""
        # Se usa cuando una validación posterior detecta que la carta debe revisarse de nuevo.
        self.status = CardStatus.PENDING
        self.approved_by = None
        self.approved_at = None
