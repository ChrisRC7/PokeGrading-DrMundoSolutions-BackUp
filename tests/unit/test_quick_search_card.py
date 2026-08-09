"""Unit tests for QuickSearchCardUseCase (US-004)."""
from __future__ import annotations

import difflib
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from pokegrading.application.ports.card_matching_service import ICardMatchingService
from pokegrading.application.use_cases.quick_search_card import (
    QuickSearchCardUseCase,
    QuickSearchInput,
)
from pokegrading.domain.entities.card import Card
from pokegrading.domain.exceptions import ImageNotIdentifiableError, NoMatchFoundError
from pokegrading.domain.value_objects.card_identity import CardIdentityTuple
from pokegrading.domain.value_objects.card_status import CardStatus

# ── Imagen mínima válida (JPEG) ───────────────────────────────────────────────

_JPEG = b"\xff\xd8\xff" + b"\x00" * 50

# ── Fakes ─────────────────────────────────────────────────────────────────────


class _StubMatchingService(ICardMatchingService):
    """Stub que no extrae features (simula motor de prod sin ML disponible)."""

    def extract_features(self, image_data: bytes) -> str:
        return ""


class _FakeCardRepo:
    """Repo en memoria con soporte para find_top_candidates."""

    def __init__(self, cards: list[Card]) -> None:
        self._cards = cards

    # Métodos del ABC no usados en este use case
    def find_by_identity(self, identity): ...
    def find_by_id(self, card_id): ...
    def save(self, card): ...

    def find_top_candidates(self, query: str, limit: int = 3) -> list[tuple[Card, float]]:
        q = query.strip().lower()
        if not q:
            return []
        results = []
        for card in self._cards:
            name_l = card.name.lower()
            if name_l == q:
                score = 1.0
            else:
                sim = difflib.SequenceMatcher(None, q, name_l).ratio()
                # Solo incluir si hay algo de similaridad mínima
                if sim < 0.30:
                    continue
                score = round(sim, 4)
            results.append((card, score))
        results.sort(key=lambda t: t[1], reverse=True)
        return results[:limit]


def _make_card(name: str = "Pikachu", language: str = "en") -> Card:
    return Card(
        id=uuid4(),
        identity=CardIdentityTuple(
            set_name="Vivid Voltage",
            card_number="025/185",
            edition="1st",
            language=language,
            finish="normal",
        ),
        name=name,
        status=CardStatus.ACTIVE,
        version=1,
        created_by=uuid4(),
        created_at=datetime.now(tz=timezone.utc),
        hp=60,
        pokemon_type="Lightning",
        rarity="Common",
    )


def _make_use_case(cards: list[Card]) -> QuickSearchCardUseCase:
    return QuickSearchCardUseCase(
        card_repo=_FakeCardRepo(cards),
        matching_svc=_StubMatchingService(),
    )


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_no_query_hint_and_stub_raises_not_identifiable():
    """AC-04: imagen sin features + sin q → ImageNotIdentifiableError."""
    uc = _make_use_case([_make_card("Pikachu")])
    with pytest.raises(ImageNotIdentifiableError):
        uc.execute(QuickSearchInput(image_front_data=_JPEG, query_hint=None))


def test_query_hint_no_match_raises_no_match_found():
    """AC-03: query válida pero ningún candidato → NoMatchFoundError."""
    uc = _make_use_case([_make_card("Pikachu")])
    with pytest.raises(NoMatchFoundError) as exc_info:
        uc.execute(QuickSearchInput(image_front_data=_JPEG, query_hint="Mewtwo"))
    assert "Mewtwo" in str(exc_info.value)


def test_returns_candidates_sorted_by_confidence():
    """AC-01: query con coincidencias → candidatos ordenados por confianza desc."""
    cards = [
        _make_card("Pikachu V"),   # contains "pikachu" → 0.70
        _make_card("Pikachu"),     # exact match → 1.0
        _make_card("Pikachu VMAX"),  # starts with "pikachu" → 0.85
    ]
    uc = _make_use_case(cards)
    result = uc.execute(QuickSearchInput(image_front_data=_JPEG, query_hint="pikachu"))

    assert len(result.candidates) == 3
    scores = [c.confidence_score for c in result.candidates]
    assert scores == sorted(scores, reverse=True), "Candidatos deben estar en orden desc"
    assert result.candidates[0].confidence_score == 1.0
    assert result.candidates[0].name == "Pikachu"


def test_returns_at_most_three_candidates():
    """AC-01: incluso con más matches, devuelve máximo 3."""
    cards = [_make_card(f"Pikachu V{i}") for i in range(10)]
    uc = _make_use_case(cards)
    result = uc.execute(QuickSearchInput(image_front_data=_JPEG, query_hint="pikachu"))
    assert len(result.candidates) <= 3


def test_auto_accepted_when_top_exceeds_threshold():
    """AC-02: confianza del #1 ≥ umbral → auto_accepted = True."""
    uc = _make_use_case([_make_card("Pikachu")])
    result = uc.execute(
        QuickSearchInput(image_front_data=_JPEG, query_hint="pikachu", confidence_threshold=0.90)
    )
    assert result.auto_accepted is True
    assert result.candidates[0].confidence_score == 1.0


def test_not_auto_accepted_when_top_below_threshold():
    """AC-02 inverso: confianza < umbral → auto_accepted = False."""
    uc = _make_use_case([_make_card("Pikachu V")])
    result = uc.execute(
        QuickSearchInput(image_front_data=_JPEG, query_hint="pikachu", confidence_threshold=0.90)
    )
    # "pikachu" in "pikachu v" → 0.70 < 0.90
    assert result.auto_accepted is False


def test_rank_is_correct():
    """Cada SearchResult tiene rank = posición correcta en la lista."""
    cards = [_make_card("Pikachu"), _make_card("Pikachu V"), _make_card("Pikachu VMAX")]
    uc = _make_use_case(cards)
    result = uc.execute(QuickSearchInput(image_front_data=_JPEG, query_hint="pikachu"))
    for expected_rank, candidate in enumerate(result.candidates, start=1):
        assert candidate.rank == expected_rank


def test_search_result_contains_card_metadata():
    """El resultado incluye name, set_name, card_number, language, hp, etc."""
    card = _make_card("Pikachu")
    uc = _make_use_case([card])
    result = uc.execute(QuickSearchInput(image_front_data=_JPEG, query_hint="pikachu"))
    r = result.candidates[0]
    assert r.name == "Pikachu"
    assert r.set_name == "Vivid Voltage"
    assert r.card_number == "025/185"
    assert r.language == "en"
    assert r.hp == 60
    assert r.pokemon_type == "Lightning"
    assert r.rarity == "Common"


def test_spanish_card_found_by_same_name():
    """Cartas en español se encuentran por nombre (los nombres son iguales EN/ES)."""
    es_card = _make_card("Pikachu", language="es")
    uc = _make_use_case([es_card])
    result = uc.execute(QuickSearchInput(image_front_data=_JPEG, query_hint="pikachu"))
    assert result.candidates[0].language == "es"
    assert result.candidates[0].confidence_score == 1.0


def test_without_token_raises_in_integration():
    """(Placeholder) — el test de integración cubre AC-05 (ver test_search.py)."""
    pass
