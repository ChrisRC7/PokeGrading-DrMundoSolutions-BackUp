"""Unit tests for RegisterUserUseCase (US-001)."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from pokegrading.application.use_cases.register_user import (
    RegisterUserInput,
    RegisterUserUseCase,
)
from pokegrading.domain.entities.user import User
from pokegrading.domain.exceptions import (
    BlockedEmailDomainError,
    CountryNotSupportedError,
    DisclosureNotAcceptedError,
    EmailAlreadyExistsError,
    PasswordTooWeakError,
)
from pokegrading.domain.value_objects.role import UserRole


def _make_mock_user(email: str = "test@example.com") -> User:
    return User(
        id=uuid4(),
        email=email,
        hashed_password="hashed",
        alias="tester",
        role=UserRole.SUBMITTER,
        accepted_disclosure=True,
        is_active=True,
        created_at=datetime.now(tz=timezone.utc),
    )


class FakeUserRepo:
    def __init__(self, existing_email: str | None = None) -> None:
        self._store: dict[str, User] = {}
        if existing_email:
            u = _make_mock_user(existing_email)
            self._store[existing_email] = u

    def find_by_email(self, email: str) -> User | None:
        return self._store.get(email)

    def find_by_id(self, user_id):  # type: ignore[override]
        for u in self._store.values():
            if u.id == user_id:
                return u
        return None

    def save(self, user: User) -> User:
        self._store[user.email] = user
        return user


class FakePasswordService:
    def hash(self, plain: str) -> str:
        return f"hashed:{plain}"

    def verify(self, plain: str, hashed: str) -> bool:
        return hashed == f"hashed:{plain}"


# ── Test cases ───────────────────────────────────────────────────────────────


def test_register_happy_path():
    """AC-01: valid input -> user created with SUBMITTER role."""
    uc = RegisterUserUseCase(FakeUserRepo(), FakePasswordService())
    result = uc.execute(
        RegisterUserInput(
            email="new@example.com",
            password="Password1!",
            alias="NewUser",
            accept_disclosure=True,
        )
    )
    assert result.email == "new@example.com"
    assert result.role == UserRole.SUBMITTER
    assert result.alias == "NewUser"
    assert result.user_id is not None


def test_register_normalizes_email():
    """Email is stored lowercase and stripped."""
    uc = RegisterUserUseCase(FakeUserRepo(), FakePasswordService())
    result = uc.execute(
        RegisterUserInput(
            email="  User@EXAMPLE.COM  ",
            password="Password1!",
            alias="u",
            accept_disclosure=True,
        )
    )
    assert result.email == "user@example.com"


def test_register_duplicate_email_raises():
    """AC-02: duplicate email -> EmailAlreadyExistsError."""
    repo = FakeUserRepo(existing_email="dup@example.com")
    uc = RegisterUserUseCase(repo, FakePasswordService())
    with pytest.raises(EmailAlreadyExistsError):
        uc.execute(
            RegisterUserInput(
                email="dup@example.com",
                password="Password1!",
                alias="dup",
                accept_disclosure=True,
            )
        )


def test_register_disclosure_not_accepted_raises():
    """AC-05: accept_disclosure=False -> DisclosureNotAcceptedError."""
    uc = RegisterUserUseCase(FakeUserRepo(), FakePasswordService())
    with pytest.raises(DisclosureNotAcceptedError):
        uc.execute(
            RegisterUserInput(
                email="ok@example.com",
                password="Password1!",
                alias="ok",
                accept_disclosure=False,
            )
        )


def test_password_is_hashed():
    """Password stored hashed, not plain-text."""
    repo = FakeUserRepo()
    uc = RegisterUserUseCase(repo, FakePasswordService())
    uc.execute(
        RegisterUserInput(
            email="hash@example.com",
            password="MyPlainPass1",
            alias="h",
            accept_disclosure=True,
        )
    )
    saved_user = repo.find_by_email("hash@example.com")
    assert saved_user is not None
    assert saved_user.hashed_password != "MyPlainPass1"
    assert "hashed:" in saved_user.hashed_password


# ── Defensive programming tests ──────────────────────────────────────────────


def test_register_empty_email_after_strip_raises():
    """Email vacío después de strip() lanza ValueError."""
    uc = RegisterUserUseCase(FakeUserRepo(), FakePasswordService())
    with pytest.raises(ValueError, match="email"):
        uc.execute(
            RegisterUserInput(
                email="   ",
                password="Password1!",
                alias="tester",
                accept_disclosure=True,
            )
        )


def test_register_empty_alias_after_strip_raises():
    """Alias vacío después de strip() lanza ValueError."""
    uc = RegisterUserUseCase(FakeUserRepo(), FakePasswordService())
    with pytest.raises(ValueError, match="alias"):
        uc.execute(
            RegisterUserInput(
                email="valid@example.com",
                password="Password1!",
                alias="   ",
                accept_disclosure=True,
            )
        )


# ── US-001 extendida: country, language, password rules, blocked domains ─────


def test_register_with_valid_country_and_language():
    """AC-01 extendido: país y idioma válidos retornan en el output."""
    uc = RegisterUserUseCase(FakeUserRepo(), FakePasswordService())
    result = uc.execute(
        RegisterUserInput(
            email="tico@example.com",
            password="Password1!",
            alias="tico",
            accept_disclosure=True,
            country="CR",
            preferred_language="es",
        )
    )
    assert result.country == "CR"
    assert result.preferred_language == "es"


def test_register_default_language_is_spanish():
    """AC-08: idioma preferido default es 'es'."""
    uc = RegisterUserUseCase(FakeUserRepo(), FakePasswordService())
    result = uc.execute(
        RegisterUserInput(
            email="default@example.com",
            password="Password1!",
            alias="default",
            accept_disclosure=True,
        )
    )
    assert result.preferred_language == "es"


def test_register_with_unsupported_country_raises():
    """AC-06: país fuera del listado soportado lanza CountryNotSupportedError."""
    uc = RegisterUserUseCase(FakeUserRepo(), FakePasswordService())
    with pytest.raises(CountryNotSupportedError):
        uc.execute(
            RegisterUserInput(
                email="us@example.com",
                password="Password1!",
                alias="gringo",
                accept_disclosure=True,
                country="US",
            )
        )


def test_register_with_blocked_email_domain_raises():
    """AC-07: dominio descartable lanza BlockedEmailDomainError."""
    uc = RegisterUserUseCase(FakeUserRepo(), FakePasswordService())
    with pytest.raises(BlockedEmailDomainError):
        uc.execute(
            RegisterUserInput(
                email="test@mailinator.com",
                password="Password1!",
                alias="spammer",
                accept_disclosure=True,
            )
        )


def test_register_password_too_short_raises():
    """AC-04: contraseña con menos de 8 caracteres lanza PasswordTooWeakError."""
    uc = RegisterUserUseCase(FakeUserRepo(), FakePasswordService())
    with pytest.raises(PasswordTooWeakError):
        uc.execute(
            RegisterUserInput(
                email="short@example.com",
                password="Ab1!",
                alias="user",
                accept_disclosure=True,
            )
        )


def test_register_password_no_uppercase_raises():
    """AC-04: contraseña sin mayúscula lanza PasswordTooWeakError."""
    uc = RegisterUserUseCase(FakeUserRepo(), FakePasswordService())
    with pytest.raises(PasswordTooWeakError):
        uc.execute(
            RegisterUserInput(
                email="lower@example.com",
                password="password1!",
                alias="user",
                accept_disclosure=True,
            )
        )


def test_register_password_no_digit_raises():
    """AC-04: contraseña sin dígito lanza PasswordTooWeakError."""
    uc = RegisterUserUseCase(FakeUserRepo(), FakePasswordService())
    with pytest.raises(PasswordTooWeakError):
        uc.execute(
            RegisterUserInput(
                email="nodig@example.com",
                password="Password!",
                alias="user",
                accept_disclosure=True,
            )
        )


def test_register_country_case_insensitive():
    """País en minúsculas se normaliza a mayúsculas correctamente."""
    uc = RegisterUserUseCase(FakeUserRepo(), FakePasswordService())
    result = uc.execute(
        RegisterUserInput(
            email="mx@example.com",
            password="Password1!",
            alias="mx",
            accept_disclosure=True,
            country="mx",
        )
    )
    assert result.country == "MX"
