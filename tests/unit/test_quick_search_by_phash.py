from __future__ import annotations

from datetime import datetime, timezone

import pytest
from uuid_extensions import uuid7

from pokegrading.application.use_cases.quick_search_by_phash import (
    QuickSearchByPHashInput,
    QuickSearchByPHashUseCase,
)
from pokegrading.domain.entities.card import Card
from pokegrading.domain.exceptions import ImageNotIdentifiableError, NoMatchFoundError
from pokegrading.domain.value_objects.card_identity import CardIdentityTuple
from pokegrading.domain.value_objects.card_status import CardStatus
from pokegrading.infrastructure.matching.phash_image_hash_service import (
    StubImageHashService,
)

_NOW = datetime.now(tz=timezone.utc)


class FakeCardRepo:
    def __init__(self, near: list[tuple[Card, int]]) -> None:
        self._near = near

    def find_by_phash_near(self, phash, max_hamming=12, limit=3):
        return self._near[:limit]


def _card(name="Pikachu") -> Card:
    return Card(
        id=uuid7(),
        identity=CardIdentityTuple("Base Set", "58/102", "Unlimited", "en", "holo"),
        name=name,
        status=CardStatus.ACTIVE,
        version=1,
        created_by=uuid7(),
        created_at=_NOW,
    )


def _uc(near):
    return QuickSearchByPHashUseCase(FakeCardRepo(near), StubImageHashService())


def test_close_match_is_auto_accepted():
    card = _card()
    out = _uc([(card, 2)]).execute(QuickSearchByPHashInput(b"image-bytes"))
    assert out.candidates[0].candidate_card_id == card.id
    assert out.candidates[0].rank == 1
    assert out.auto_accepted is True  # hamming 2 <= 6


def test_far_match_is_not_auto_accepted():
    out = _uc([(_card(), 10)]).execute(QuickSearchByPHashInput(b"image-bytes"))
    assert out.auto_accepted is False  # hamming 10 > 6


def test_no_candidates_raises_no_match():
    with pytest.raises(NoMatchFoundError):
        _uc([]).execute(QuickSearchByPHashInput(b"image-bytes"))


def test_undecodable_image_raises_not_identifiable():
    # El stub devuelve "" para bytes vacíos → señal de escalar a OCR.
    with pytest.raises(ImageNotIdentifiableError):
        _uc([(_card(), 0)]).execute(QuickSearchByPHashInput(b""))


def test_confidence_decreases_with_distance():
    near = [(_card("A"), 0), (_card("B"), 12)]
    out = _uc(near).execute(QuickSearchByPHashInput(b"x"))
    assert out.candidates[0].confidence_score == 1.0
    assert out.candidates[1].confidence_score < out.candidates[0].confidence_score
