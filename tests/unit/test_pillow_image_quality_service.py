"""Unit tests for PillowImageQualityService."""
from __future__ import annotations

import io

import pytest
from PIL import Image, ImageFilter

from pokegrading.infrastructure.services.pillow_image_quality_service import (
    PillowImageQualityService,
)

_svc = PillowImageQualityService()


def _make_jpeg(width: int = 500, height: int = 500, color: tuple = (128, 128, 128)) -> bytes:
    """Genera un JPEG con bordes que simula el contenido de una carta real
    (texto, ilustración, marco) para obtener sharpness no nula.
    """
    from PIL import ImageDraw

    img = Image.new("RGB", (width, height), color=(240, 240, 240))
    draw = ImageDraw.Draw(img)
    # Borde de carta
    draw.rectangle([10, 10, width - 10, height - 10], outline=(0, 0, 0), width=6)
    draw.rectangle([25, 25, width - 25, height - 25], outline=(30, 60, 180), width=3)
    # Líneas simulando texto
    for y in range(80, height - 80, 18):
        draw.line([40, y, width - 40, y], fill=(20, 20, 20), width=1)
    # Bloque de color que simula la ilustración
    draw.rectangle([40, 40, width - 40, height // 2], fill=color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def _make_jpeg_solid(width: int = 500, height: int = 500, color: tuple = (128, 128, 128)) -> bytes:
    """Genera un JPEG de color sólido uniforme (sin bordes ni texto)."""
    img = Image.new("RGB", (width, height), color=color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def _make_blurry_jpeg(width: int = 500, height: int = 500) -> bytes:
    """Genera un JPEG con desenfoque extremo (filtro BLUR repetido)."""
    img = Image.new("RGB", (width, height), color=(100, 150, 200))
    # Aplicar blur agresivo para bajar la varianza del Laplaciano
    for _ in range(20):
        img = img.filter(ImageFilter.BLUR)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def _make_png(width: int = 500, height: int = 500, color: tuple = (128, 128, 128)) -> bytes:
    img = Image.new("RGB", (width, height), color=color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ── Tests ──────────────────────────────────────────────────────────────────────

def test_good_image_returns_score_above_threshold():
    """Imagen bien expuesta y con resolución suficiente → score ≥ 0.60."""
    data = _make_jpeg(500, 500, color=(128, 128, 128))
    score = _svc.evaluate(data)
    assert score >= 0.60, f"Se esperaba score ≥ 0.60, obtuvo {score}"


def test_score_is_bounded_0_to_1():
    """El score siempre está en [0.0, 1.0]."""
    data = _make_jpeg(800, 800)
    score = _svc.evaluate(data)
    assert 0.0 <= score <= 1.0


def test_small_image_penalized():
    """Imagen 100×100 px (< 400 px) → penalización de resolución."""
    data_small = _make_jpeg(100, 100)
    data_good = _make_jpeg(500, 500)
    score_small = _svc.evaluate(data_small)
    score_good = _svc.evaluate(data_good)
    assert score_small < score_good, "Imagen pequeña debería tener score menor"


def test_overexposed_image_penalized():
    """Imagen sobreexpuesta (blanca sólida, sin contenido) → score menor que imagen normal con bordes."""
    data_overexp = _make_jpeg_solid(500, 500, color=(255, 255, 255))
    data_normal = _make_jpeg(500, 500)
    score_overexp = _svc.evaluate(data_overexp)
    score_normal = _svc.evaluate(data_normal)
    assert score_overexp < score_normal, "Imagen sobreexpuesta debería tener score menor"


def test_underexposed_image_penalized():
    """Imagen subexpuesta (negra sólida, sin contenido) → score menor que imagen normal con bordes."""
    data_underexp = _make_jpeg_solid(500, 500, color=(0, 0, 0))
    data_normal = _make_jpeg(500, 500)
    score_underexp = _svc.evaluate(data_underexp)
    score_normal = _svc.evaluate(data_normal)
    assert score_underexp < score_normal, "Imagen subexpuesta debería tener score menor"


def test_png_image_evaluated():
    """PNG válido también es evaluado correctamente."""
    data = _make_png(500, 500)
    score = _svc.evaluate(data)
    assert 0.0 <= score <= 1.0


def test_invalid_bytes_returns_zero():
    """Bytes que no son imagen → score 0.0."""
    score = _svc.evaluate(b"NOT_AN_IMAGE" * 50)
    assert score == 0.0
