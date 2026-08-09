from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from uuid_extensions import uuid7

from pokegrading.application.ports.password_service import IPasswordService
from pokegrading.domain.entities.user import User
from pokegrading.domain.exceptions import (
    BlockedEmailDomainError,
    CountryNotSupportedError,
    DisclosureNotAcceptedError,
    EmailAlreadyExistsError,
    PasswordTooWeakError,
)
from pokegrading.domain.repositories.user_repository import IUserRepository
from pokegrading.domain.value_objects.blocked_domains import BLOCKED_DOMAINS
from pokegrading.domain.value_objects.country import SupportedCountry
from pokegrading.domain.value_objects.language import SupportedLanguage
from pokegrading.domain.value_objects.role import UserRole

# Minimum password requirements: length ≥ 8, ≥ 1 uppercase, ≥ 1 digit
_RE_UPPERCASE = re.compile(r"[A-Z]")
_RE_DIGIT = re.compile(r"\d")
_MIN_PASSWORD_LENGTH = 8


@dataclass(frozen=True)
class RegisterUserInput:
    email: str
    password: str
    alias: str
    accept_disclosure: bool
    country: str = "CR"
    preferred_language: str = "es"


@dataclass(frozen=True)
class RegisterUserOutput:
    user_id: UUID
    email: str
    alias: str
    role: UserRole
    created_at: datetime
    country: str
    preferred_language: str


class RegisterUserUseCase:
    """US-001 — Registrar cuenta.

    AC-01: Valid email + password + alias + country + disclosure accepted -> creates account.
    AC-02: Duplicate email -> raises EmailAlreadyExistsError.
    AC-04: Weak password -> raises PasswordTooWeakError.
    AC-05: accept_disclosure = False -> raises DisclosureNotAcceptedError.
    AC-06: Country not supported -> raises CountryNotSupportedError.
    AC-07: Blocked email domain -> raises BlockedEmailDomainError.
    """

    def __init__(
        self,
        user_repo: IUserRepository,
        password_service: IPasswordService,
    ) -> None:
        self._user_repo = user_repo
        self._password_service = password_service

    def execute(self, input_data: RegisterUserInput) -> RegisterUserOutput:
        # AC-05: disclosure
        # El alta se bloquea si el usuario no acepta el aviso legal primero.
        if not input_data.accept_disclosure:
            raise DisclosureNotAcceptedError()

        # Empty field guards
        # El use case no confía en que la capa HTTP ya haya limpiado el input.
        normalized_email = input_data.email.lower().strip()
        if not normalized_email:
            raise ValueError("El email no puede estar vacío")

        alias = input_data.alias.strip()
        if not alias:
            raise ValueError("El alias no puede estar vacío")

        # AC-07: blocked domain
        # Evita registros con dominios descartables o usados para abuso.
        domain = normalized_email.split("@")[-1]
        if domain in BLOCKED_DOMAINS:
            raise BlockedEmailDomainError(domain)

        # AC-04: password strength
        # La contraseña se valida antes de hashearla para devolver mensajes claros.
        pwd = input_data.password
        if len(pwd) < _MIN_PASSWORD_LENGTH:
            raise PasswordTooWeakError(f"mínimo {_MIN_PASSWORD_LENGTH} caracteres")
        if not _RE_UPPERCASE.search(pwd):
            raise PasswordTooWeakError("debe contener al menos una letra mayúscula")
        if not _RE_DIGIT.search(pwd):
            raise PasswordTooWeakError("debe contener al menos un dígito")

        # AC-06: country
        # El país se normaliza para que "cr" y "CR" sean equivalentes.
        country = input_data.country.strip().upper()
        try:
            SupportedCountry(country)
        except ValueError:
            raise CountryNotSupportedError(country)

        # AC-08: language
        # Si el idioma viene fuera del catálogo soportado, se usa español por defecto.
        lang = input_data.preferred_language.strip().lower()
        try:
            SupportedLanguage(lang)
        except ValueError:
            lang = SupportedLanguage.ES.value

        # AC-02: duplicate email
        # Antes de generar hash y persistir, se comprueba si el email ya existe.
        if self._user_repo.find_by_email(normalized_email) is not None:
            raise EmailAlreadyExistsError(normalized_email)

        # El hash vive fuera del dominio; el use case solo orquesta la operación.
        hashed = self._password_service.hash(input_data.password)

        # La entidad se construye ya normalizada y lista para persistencia.
        user = User(
            id=uuid7(),
            email=normalized_email,
            hashed_password=hashed,
            alias=alias,
            role=UserRole.SUBMITTER,
            accepted_disclosure=True,
            is_active=True,
            created_at=datetime.now(tz=timezone.utc),
            country=country,
            preferred_language=lang,
        )

        # Persistir devuelve la versión canonical del agregado tal como quedó en BD.
        saved = self._user_repo.save(user)

        return RegisterUserOutput(
            user_id=saved.id,
            email=saved.email,
            alias=saved.alias,
            role=saved.role,
            created_at=saved.created_at,
            country=saved.country,
            preferred_language=saved.preferred_language,
        )
