from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from uuid_extensions import uuid7

from pokegrading.domain.entities.card import Card
from pokegrading.domain.exceptions import CardAlreadyExistsError, InvalidLanguageError, InvalidPokemonTypeError, InvalidRarityError, UnauthorizedError
from pokegrading.domain.repositories.card_repository import ICardRepository
from pokegrading.domain.repositories.user_repository import IUserRepository
from pokegrading.domain.value_objects.card_identity import CardIdentityTuple
from pokegrading.domain.value_objects.card_status import CardStatus
from pokegrading.domain.value_objects.language import SupportedLanguage
from pokegrading.domain.value_objects.pokemon_type import PokemonType
from pokegrading.domain.value_objects.rarity import CardRarity


@dataclass(frozen=True)
class AddCardInput:
    name: str
    set_name: str
    card_number: str
    edition: str
    language: str
    finish: str
    created_by: UUID
    description: str | None = None
    rarity: str | None = None
    pokemon_type: str | None = None
    hp: int | None = None
    illustrator: str | None = None
    print_year: int | None = None


@dataclass(frozen=True)
class AddCardOutput:
    card_id: UUID
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


class AddCardToCatalogUseCase:
    """US-002 — Agregar carta al catálogo.

    AC-01: Valid card data + Admin token -> 201, card in PENDING status.
    AC-02: Non-admin user -> raises UnauthorizedError.
    AC-04: Duplicate CardIdentityTuple -> raises CardAlreadyExistsError.
    AC-05: Card starts in PENDING (dual validation required for ACTIVE).
    AC-06: created_by, created_at, version=1 set automatically.
    """

    def __init__(
        self,
        card_repo: ICardRepository,
        user_repo: IUserRepository,
    ) -> None:
        self._card_repo = card_repo
        self._user_repo = user_repo

    def execute(self, input_data: AddCardInput) -> AddCardOutput:
        # Seguridad: el use case no asume que el router ya filtró correctamente el rol.
        creator = self._user_repo.find_by_id(input_data.created_by)

        # Si no es admin, la carta no puede entrar al catálogo de referencia.
        if creator is None or not creator.is_admin():
            raise UnauthorizedError(
                "Only administrators can add cards to the reference catalog"
            )

        # Se normalizan campos de identidad para evitar duplicados por espacios o formato.
        name = input_data.name.strip()
        set_name = input_data.set_name.strip()
        card_number = input_data.card_number.strip()
        edition = input_data.edition.strip()
        language = input_data.language.strip()
        finish = input_data.finish.strip()

        for field, value in (
            ("name", name),
            ("set_name", set_name),
            ("card_number", card_number),
            ("edition", edition),
            ("language", language),
            ("finish", finish),
        ):
            if not value:
                raise ValueError(f"El campo '{field}' no puede estar vacío")

        # Validate language against canonical list
        # El idioma se valida contra el catálogo canónico antes de construir la identidad.
        try:
            SupportedLanguage(language)
        except ValueError:
            raise InvalidLanguageError(language)

        # La identidad define unicidad de negocio, no solo la PK técnica.
        identity = CardIdentityTuple(
            set_name=set_name,
            card_number=card_number,
            edition=edition,
            language=language,
            finish=finish,
        )

        if self._card_repo.find_by_identity(identity) is not None:
            raise CardAlreadyExistsError(str(identity))

        # Validate optional display fields
        # Estos campos son opcionales, pero cuando llegan deben respetar enums y rangos.
        rarity: str | None = None
        if input_data.rarity is not None:
            try:
                rarity = CardRarity(input_data.rarity).value
            except ValueError:
                raise InvalidRarityError(input_data.rarity)

        pokemon_type: str | None = None
        if input_data.pokemon_type is not None:
            try:
                pokemon_type = PokemonType(input_data.pokemon_type).value
            except ValueError:
                raise InvalidPokemonTypeError(input_data.pokemon_type)

        hp: int | None = None
        if input_data.hp is not None:
            if input_data.hp <= 0:
                raise ValueError("HP must be a positive integer")
            hp = input_data.hp

        # La carta nace en PENDING para que otra persona la apruebe después.
        card = Card(
            id=uuid7(),
            identity=identity,
            name=name,
            status=CardStatus.PENDING,
            version=1,
            created_by=input_data.created_by,
            created_at=datetime.now(tz=timezone.utc),
            description=input_data.description,
            rarity=rarity,
            pokemon_type=pokemon_type,
            hp=hp,
            illustrator=input_data.illustrator,
            print_year=input_data.print_year,
        )

        # Persistir devuelve la versión canonical y permite que la BD asigne/ajuste lo necesario.
        saved = self._card_repo.save(card)

        return AddCardOutput(
            card_id=saved.id,
            identity=saved.identity,
            name=saved.name,
            status=saved.status,
            version=saved.version,
            created_by=saved.created_by,
            created_at=saved.created_at,
            description=saved.description,
            rarity=saved.rarity,
            pokemon_type=saved.pokemon_type,
            hp=saved.hp,
            illustrator=saved.illustrator,
            print_year=saved.print_year,
        )
