from __future__ import annotations

import hashlib
import time
from datetime import datetime, timezone
from uuid import uuid4

from pokegrading.application.use_cases.quick_search_by_phash import (
    QuickSearchByPHashInput,
    QuickSearchByPHashUseCase,
)
from pokegrading.application.use_cases.quick_search_card import (
    QuickSearchCardUseCase,
    QuickSearchInput,
)
from pokegrading.domain.entities.card import Card
from pokegrading.domain.value_objects.card_identity import CardIdentityTuple
from pokegrading.domain.value_objects.card_status import CardStatus


_JPEG = b"\xff\xd8\xff" + b"\x00" * 50


class _FakeCardRepo:
    def __init__(self, card: Card) -> None:
        self._card = card

    def find_by_identity(self, identity): ...
    def find_by_id(self, card_id): ...
    def save(self, card): ...

    def find_by_phash_near(self, phash, max_hamming=12, limit=3):
        return [(self._card, 2)]

    def find_top_candidates(self, query: str, limit: int = 3):
        return [(self._card, 1.0)]


class _FakePHashService:
    def compute_phash(self, image_data: bytes) -> str:
        return hashlib.sha256(image_data).hexdigest()[:16]


class _FakeMatchingService:
    def extract_features(self, image_data: bytes) -> str:
        payload = image_data.lower()
        features = [chr(byte) for byte in payload if 97 <= byte <= 122]
        return "".join(features[:32]) or "pikachu"


def _make_card(name: str = "Pikachu") -> Card:
    return Card(
        id=uuid4(),
        identity=CardIdentityTuple(
            set_name="Vivid Voltage",
            card_number="025/185",
            edition="1st",
            language="en",
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


def test_phash_is_faster_than_ocr_for_same_image() -> None:
    """Benchmark natural y determinista para documentar el ADR de pHash vs OCR."""
    card = _make_card("Pikachu")
    repo = _FakeCardRepo(card)

    phash_use_case = QuickSearchByPHashUseCase(
        card_repo=repo,
        hash_svc=_FakePHashService(),
    )
    ocr_use_case = QuickSearchCardUseCase(
        card_repo=repo,
        matching_svc=_FakeMatchingService(),
    )

    image_payload = _JPEG + b"pikachu" * 5000
    repetitions = 200

    phash_started = time.perf_counter()
    for _ in range(repetitions):
        phash_result = phash_use_case.execute(QuickSearchByPHashInput(image_front_data=image_payload))
    phash_elapsed = time.perf_counter() - phash_started

    ocr_started = time.perf_counter()
    for _ in range(repetitions):
        ocr_result = ocr_use_case.execute(QuickSearchInput(image_front_data=image_payload))
    ocr_elapsed = time.perf_counter() - ocr_started

    print(
        "Benchmark pHash vs OCR: "
        f"pHash={phash_elapsed:.6f}s | OCR={ocr_elapsed:.6f}s | ratio={ocr_elapsed / phash_elapsed:.2f}x"
    )

    assert phash_result.candidates[0].candidate_card_id == card.id
    assert ocr_result.candidates[0].candidate_card_id == card.id
    assert phash_elapsed < ocr_elapsed, (
        "Benchmark pHash vs OCR falló: "
        f"pHash={phash_elapsed:.6f}s, OCR={ocr_elapsed:.6f}s, ratio={ocr_elapsed / phash_elapsed:.2f}x"
    )
