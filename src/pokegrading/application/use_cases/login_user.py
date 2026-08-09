from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from pokegrading.application.ports.password_service import IPasswordService
from pokegrading.domain.exceptions import InvalidCredentialsError
from pokegrading.domain.repositories.user_repository import IUserRepository
from pokegrading.domain.value_objects.role import UserRole


@dataclass(frozen=True)
class LoginUserInput:
    email: str
    password: str


@dataclass(frozen=True)
class LoginUserOutput:
    user_id: UUID
    email: str
    alias: str
    role: UserRole


class LoginUserUseCase:
    def __init__(
        self,
        user_repo: IUserRepository,
        password_service: IPasswordService,
    ) -> None:
        self._user_repo = user_repo
        self._password_service = password_service

    def execute(self, inp: LoginUserInput) -> LoginUserOutput:
        # Normaliza email antes de buscarlo; el login no debe depender de mayúsculas
        # o espacios accidentales escritos por el usuario.
        user = self._user_repo.find_by_email(inp.email.lower().strip())

        # Credenciales inválidas y usuario inactivo se tratan igual para no filtrar
        # información sobre qué parte falló.
        if user is None or not self._password_service.verify(
            inp.password, user.hashed_password
        ):
            raise InvalidCredentialsError()

        # Un usuario desactivado no puede entrar aunque su contraseña sea correcta.
        if not user.is_active:
            raise InvalidCredentialsError()

        # La respuesta solo expone datos de sesión y autorización, no el hash.
        return LoginUserOutput(
            user_id=user.id,
            email=user.email,
            alias=user.alias,
            role=user.role,
        )
