from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CardIdentityTuple:
    """Value object that uniquely identifies a Pokémon card as a collectible asset.

    The tuple (set_name, card_number, edition, language, finish) is the stable
    identity key used throughout the system and for integrating with PokéMarket's
    price API.
    """

    set_name: str
    card_number: str
    edition: str
    language: str
    finish: str

    def __post_init__(self) -> None:
        for field_name in ("set_name", "card_number", "edition", "language", "finish"):
            value = getattr(self, field_name)
            if not value or not value.strip():
                raise ValueError(f"CardIdentityTuple.{field_name} cannot be empty")

    def __str__(self) -> str:
        return (
            f"{self.set_name}/{self.card_number}/{self.edition}"
            f"/{self.language}/{self.finish}"
        )
