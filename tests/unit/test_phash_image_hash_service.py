from __future__ import annotations

import io

from PIL import Image

from pokegrading.infrastructure.matching.phash_image_hash_service import (
    PHashImageHashService,
    StubImageHashService,
)


def _png(color=(120, 80, 200), size=(200, 280)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


def test_phash_has_16_hex_chars_and_zero_self_distance():
    svc = PHashImageHashService()
    data = _png()
    h = svc.compute_phash(data)
    assert len(h) == 16
    assert svc.hamming_distance(h, h) == 0


def test_phash_invalid_image_returns_empty():
    assert PHashImageHashService().compute_phash(b"not-an-image") == ""


def test_stub_is_deterministic_and_zero_self_distance():
    svc = StubImageHashService()
    a = svc.compute_phash(b"same-bytes")
    b = svc.compute_phash(b"same-bytes")
    assert a == b
    assert svc.hamming_distance(a, b) == 0


def test_stub_empty_returns_empty():
    assert StubImageHashService().compute_phash(b"") == ""
