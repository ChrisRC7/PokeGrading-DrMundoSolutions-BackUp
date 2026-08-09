from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from pokegrading.domain.value_objects.role import UserRole


@dataclass
class User:
    """User entity. Represents a registered account in PokéGrading.

    Invariant: password is always stored hashed — plain text is never persisted.
    Role determines the access scope for every write operation (RNF SP1).
    """

    id: UUID
    email: str
    hashed_password: str
    alias: str
    role: UserRole
    accepted_disclosure: bool
    is_active: bool
    created_at: datetime
    country: str = "CR"
    preferred_language: str = "es"

    def __post_init__(self) -> None:
        # El dominio no acepta usuarios con email o alias vacíos, incluso si
        # alguna capa externa omitió validaciones.
        if not self.email or "@" not in self.email:
            raise ValueError("User email must be a valid email address")
        if not self.alias or not self.alias.strip():
            raise ValueError("User alias cannot be empty")

    def is_admin(self) -> bool:
        # Ruta rápida para decisiones de autorización en use cases y routers.
        return self.role == UserRole.ADMIN

    def is_reviewer(self) -> bool:
        # Algunos flujos distinguen reviewer de admin para permisos más finos.
        return self.role == UserRole.REVIEWER

    def has_role(self, role: UserRole) -> bool:
        # Helper genérico para comparaciones de rol sin repetir lógica.
        return self.role == role
