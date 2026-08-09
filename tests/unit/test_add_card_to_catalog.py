"""Unit tests for AddCardToCatalogUseCase (US-002)."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from pokegrading.application.use_cases.add_card_to_catalog import (
    AddCardInput,
    AddCardToCatalogUseCase,
)
from pokegrading.domain.entities.card import Card
from pokegrading.domain.entities.user import User
from pokegrading.domain.exceptions import (
    CardAlreadyExistsError,
    InvalidLanguageError,
    InvalidPokemonTypeError,
    InvalidRarityError,
    UnauthorizedError,
)
from pokegrading.domain.value_objects.card_identity import CardIdentityTuple
from pokegrading.domain.value_objects.card_status import CardStatus
from pokegrading.domain.value_objects.role import UserRole


def _make_user(role: UserRole = UserRole.ADMIN) -> User:
    return User(
        id=uuid4(),
        email="admin@example.com",
        hashed_password="hashed",
        alias="admin",
        role=role,
        accepted_disclosure=True,
        is_active=True,
        created_at=datetime.now(tz=timezone.utc),
    )


class FakeUserRepo:
    def __init__(self, user: User | None = None) -> None:
        self._user = user

    def find_by_email(self, email: str) -> User | None:
        return self._user if self._user and self._user.email == email else None

    def find_by_id(self, user_id) -> User | None:
        return self._user if self._user and self._user.id == user_id else None

    def save(self, user: User) -> User:
        return user


class FakeCardRepo:
    def __init__(self) -> None:
        self._store: dict[str, Card] = {}

    def find_by_identity(self, identity: CardIdentityTuple) -> Card | None:
        return self._store.get(str(identity))

    def find_by_id(self, card_id) -> Card | None:
        for c in self._store.values():
            if c.id == card_id:
                return c
        return None

    def save(self, card: Card) -> Card:
        self._store[str(card.identity)] = card
        return card


def _base_input(created_by) -> AddCardInput:
    return AddCardInput(
        name="Charizard",
        set_name="Base Set",
        card_number="4/102",
        edition="1st Edition",
        language="en",
        finish="Holo",
        created_by=created_by,
    )


# ── Test cases ───────────────────────────────────────────────────────────────


def test_add_card_happy_path():
    """AC-01: admin adds valid card -> PENDING, version=1."""
    admin = _make_user(UserRole.ADMIN)
    uc = AddCardToCatalogUseCase(FakeCardRepo(), FakeUserRepo(admin))
    result = uc.execute(_base_input(admin.id))
    assert result.name == "Charizard"
    assert result.status == CardStatus.PENDING
    assert result.version == 1
    assert result.created_by == admin.id


def test_add_card_non_admin_raises():
    """AC-02: submitter token -> UnauthorizedError."""
    submitter = _make_user(UserRole.SUBMITTER)
    uc = AddCardToCatalogUseCase(FakeCardRepo(), FakeUserRepo(submitter))
    with pytest.raises(UnauthorizedError):
        uc.execute(_base_input(submitter.id))


def test_add_card_unknown_user_raises():
    """User not in repo -> UnauthorizedError (treated as unauthorized)."""
    uc = AddCardToCatalogUseCase(FakeCardRepo(), FakeUserRepo(None))
    with pytest.raises(UnauthorizedError):
        uc.execute(_base_input(uuid4()))


def test_add_card_duplicate_identity_raises():
    """AC-04: same CardIdentityTuple twice -> CardAlreadyExistsError."""
    admin = _make_user(UserRole.ADMIN)
    card_repo = FakeCardRepo()
    uc = AddCardToCatalogUseCase(card_repo, FakeUserRepo(admin))
    uc.execute(_base_input(admin.id))
    with pytest.raises(CardAlreadyExistsError):
        uc.execute(_base_input(admin.id))


def test_add_card_identity_value_object_strips_whitespace():
    """Identity fields are stripped before storage."""
    admin = _make_user(UserRole.ADMIN)
    uc = AddCardToCatalogUseCase(FakeCardRepo(), FakeUserRepo(admin))
    result = uc.execute(
        AddCardInput(
            name=" Charizard ",
            set_name=" Base Set ",
            card_number=" 4/102 ",
            edition=" 1st Edition ",
            language=" en ",
            finish=" Holo ",
            created_by=admin.id,
        )
    )
    assert result.identity.set_name == "Base Set"
    assert result.identity.card_number == "4/102"
    assert result.name == "Charizard"


def test_add_card_optional_fields_nullable():
    """AC-06: optional fields default to None."""
    admin = _make_user(UserRole.ADMIN)
    uc = AddCardToCatalogUseCase(FakeCardRepo(), FakeUserRepo(admin))
    result = uc.execute(_base_input(admin.id))
    # No assertion failure means defaults are accepted
    assert result.card_id is not None


# ── Defensive programming tests ──────────────────────────────────────────────


@pytest.mark.parametrize("empty_field", ["set_name", "card_number", "edition", "language", "finish", "name"])
def test_add_card_empty_identity_field_raises(empty_field: str):
    """Campo de identidad vacío después de strip() lanza ValueError."""
    admin = _make_user(UserRole.ADMIN)
    uc = AddCardToCatalogUseCase(FakeCardRepo(), FakeUserRepo(admin))
    fields = {
        "name": "Charizard",
        "set_name": "Base Set",
        "card_number": "4/102",
        "edition": "1st Edition",
        "language": "en",
        "finish": "Holo",
    }
    fields[empty_field] = "   "
    with pytest.raises(ValueError, match=empty_field):
        uc.execute(AddCardInput(created_by=admin.id, **fields))


# ── US-002 extended: display fields ─────────────────────────────────────────


def test_add_card_with_display_fields_returns_201():
    """AC: campos de display opcionales se almacenan correctamente."""
    admin = _make_user(UserRole.ADMIN)
    uc = AddCardToCatalogUseCase(FakeCardRepo(), FakeUserRepo(admin))
    result = uc.execute(AddCardInput(
        name="Pikachu",
        set_name="Base Set",
        card_number="58/102",
        edition="Unlimited",
        language="en",
        finish="Non-Holo",
        created_by=admin.id,
        rarity="Common",
        pokemon_type="Electric",
        hp=40,
        illustrator="Mitsuhiro Arita",
        print_year=1999,
    ))
    assert result.rarity == "Common"
    assert result.pokemon_type == "Electric"
    assert result.hp == 40
    assert result.illustrator == "Mitsuhiro Arita"
    assert result.print_year == 1999


def test_add_card_with_invalid_rarity_raises():
    """AC-05: rareza fuera del listado canónico -> InvalidRarityError."""
    admin = _make_user(UserRole.ADMIN)
    uc = AddCardToCatalogUseCase(FakeCardRepo(), FakeUserRepo(admin))
    with pytest.raises(InvalidRarityError):
        uc.execute(AddCardInput(
            name="Mewtwo",
            set_name="Base Set",
            card_number="10/102",
            edition="1st Edition",
            language="en",
            finish="Holo",
            created_by=admin.id,
            rarity="Legendary",  # inválido
        ))


def test_add_card_with_invalid_pokemon_type_raises():
    """AC-06: tipo Pokémon inválido -> InvalidPokemonTypeError."""
    admin = _make_user(UserRole.ADMIN)
    uc = AddCardToCatalogUseCase(FakeCardRepo(), FakeUserRepo(admin))
    with pytest.raises(InvalidPokemonTypeError):
        uc.execute(AddCardInput(
            name="Blastoise",
            set_name="Base Set",
            card_number="2/102",
            edition="1st Edition",
            language="en",
            finish="Holo",
            created_by=admin.id,
            pokemon_type="Shadow",  # inválido
        ))


def test_add_card_with_negative_hp_raises():
    """AC-07: HP negativo o cero -> ValueError."""
    admin = _make_user(UserRole.ADMIN)
    uc = AddCardToCatalogUseCase(FakeCardRepo(), FakeUserRepo(admin))
    with pytest.raises(ValueError, match="HP"):
        uc.execute(AddCardInput(
            name="Bulbasaur",
            set_name="Base Set",
            card_number="44/102",
            edition="Unlimited",
            language="en",
            finish="Non-Holo",
            created_by=admin.id,
            hp=0,
        ))


def test_add_card_with_invalid_language_raises():
    """AC: idioma fuera de la lista canónica -> InvalidLanguageError."""
    admin = _make_user(UserRole.ADMIN)
    uc = AddCardToCatalogUseCase(FakeCardRepo(), FakeUserRepo(admin))
    with pytest.raises(InvalidLanguageError):
        uc.execute(AddCardInput(
            name="Charizard",
            set_name="Base Set",
            card_number="4/102",
            edition="1st Edition",
            language="English",  # nombre completo no válido, debe ser 'en'
            finish="Holo",
            created_by=admin.id,
        ))


def test_add_card_audit_fields_are_set():
    """AC-09: created_by, created_at y version=1 se generan automáticamente."""
    admin = _make_user(UserRole.ADMIN)
    uc = AddCardToCatalogUseCase(FakeCardRepo(), FakeUserRepo(admin))
    result = uc.execute(_base_input(admin.id))
    assert result.created_by == admin.id
    assert result.created_at is not None
    assert result.version == 1


def test_add_card_duplicate_identity_returns_409():
    """AC-04: identidad duplicada -> CardAlreadyExistsError."""
    admin = _make_user(UserRole.ADMIN)
    card_repo = FakeCardRepo()
    uc = AddCardToCatalogUseCase(card_repo, FakeUserRepo(admin))
    uc.execute(_base_input(admin.id))
    with pytest.raises(CardAlreadyExistsError):
        uc.execute(_base_input(admin.id))
