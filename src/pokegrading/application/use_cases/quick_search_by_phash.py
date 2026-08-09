from __future__ import annotations

from dataclasses import dataclass

from pokegrading.application.ports.image_hash_service import IImageHashService
from pokegrading.application.use_cases.quick_search_card import (
    QuickSearchOutput,
)
from pokegrading.domain.entities.search_result import SearchResult
from pokegrading.domain.exceptions import ImageNotIdentifiableError, NoMatchFoundError
from pokegrading.domain.repositories.card_repository import ICardRepository

# pHash de 64 bits → la confianza se deriva de la distancia de Hamming.
_PHASH_BITS = 64

# Umbrales por defecto (configurables por llamada).
DEFAULT_AUTO_ACCEPT_MAX_HAMMING = 6
DEFAULT_MAX_HAMMING = 12


@dataclass(frozen=True)
class QuickSearchByPHashInput:
    image_front_data: bytes
    auto_accept_max_hamming: int = DEFAULT_AUTO_ACCEPT_MAX_HAMMING
    max_hamming: int = DEFAULT_MAX_HAMMING
    limit: int = 3


class QuickSearchByPHashUseCase:
    """US-004 — Búsqueda RÁPIDA por pHash (Sprint 3).

    Primer intento, barato: compara la imagen del usuario con las imágenes de
    referencia del catálogo por similitud visual.

    - Imagen no decodificable → ``ImageNotIdentifiableError``.
    - Sin candidatos cercanos → ``NoMatchFoundError``.
    Ambas señalan al caller que debe escalar a la búsqueda especializada (OCR).
    """

    def __init__(
        self,
        card_repo: ICardRepository,
        hash_svc: IImageHashService,
    ) -> None:
        self._card_repo = card_repo
        self._hash_svc = hash_svc

    def execute(self, inp: QuickSearchByPHashInput) -> QuickSearchOutput:
        phash = self._hash_svc.compute_phash(inp.image_front_data)
        if not phash:
            raise ImageNotIdentifiableError()

        raw = self._card_repo.find_by_phash_near(
            phash, max_hamming=inp.max_hamming, limit=inp.limit
        )
        if not raw:
            raise NoMatchFoundError(f"phash:{phash}")

        candidates = [
            SearchResult(
                candidate_card_id=card.id,
                confidence_score=round(1.0 - distance / _PHASH_BITS, 4),
                rank=rank,
                name=card.name,
                set_name=card.identity.set_name,
                card_number=card.identity.card_number,
                language=card.identity.language,
                rarity=card.rarity,
                pokemon_type=card.pokemon_type,
                hp=card.hp,
            )
            for rank, (card, distance) in enumerate(raw, start=1)
        ]

        auto_accepted = raw[0][1] <= inp.auto_accept_max_hamming
        return QuickSearchOutput(candidates=candidates, auto_accepted=auto_accepted)
