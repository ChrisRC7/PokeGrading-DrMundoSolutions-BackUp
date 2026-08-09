from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class SearchResult:
    """Candidate card returned by a quick-search operation.

    Attributes
    ----------
    candidate_card_id:
        The UUID of the matching catalog card.
    confidence_score:
        Normalised match confidence in [0.0, 1.0].
        1.0 = exact name match; 0.5 = partial / fallback match.
    rank:
        1-based position in the result list (1 = best match).
    name, set_name, card_number, language:
        Denormalised card fields surfaced to the API without a second DB call.
    rarity, pokemon_type, hp:
        Optional descriptive fields.
    """

    # La respuesta del caso de uso ya viene ordenada; rank es parte del contrato API,
    # no solo un dato derivado de la lista.
    candidate_card_id: UUID
    confidence_score: float
    rank: int
    name: str
    set_name: str
    card_number: str
    language: str
    rarity: str | None = None
    pokemon_type: str | None = None
    hp: int | None = None
