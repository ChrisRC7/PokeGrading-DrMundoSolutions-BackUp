"""Implementación de IImageQualityService usando Pillow.

Evalúa tres dimensiones:
  1. Nitidez   — varianza del Laplaciano sobre la imagen en escala de grises.
                 Valores bajos → imagen borrosa o movida.
  2. Exposición — media del brillo (canal L en modo HSV/L).
                 Valores extremos (< 20 o > 235) → subexpuesta/sobreexpuesta.
  3. Resolución — penaliza imágenes por debajo de 150×150 px.

El score final es la media ponderada de los tres componentes, normalizada a [0, 1].
"""
from __future__ import annotations

import io
import math

from PIL import Image, ImageFilter

from pokegrading.application.ports.image_quality_service import IImageQualityService

# ── Umbrales de referencia ────────────────────────────────────────────────────

# Varianza del Laplaciano (via FIND_EDGES de Pillow):
# Imágenes con bordes claros (texto, marcos) → sqrt(variance) ≈ 10–20.
# Imágenes completamente borrosas o sólidas → sqrt(variance) ≈ 0–3.
# Se satura a _SHARP_MAX para normalizar a [0, 1].
_SHARP_MAX = 20.0

# Brillo medio en [0, 255].  Rango aceptable: [30, 225].
_BRIGHT_LOW = 30.0
_BRIGHT_HIGH = 225.0

# Resolución mínima recomendada (lado menor).
_MIN_SIDE = 150

# Pesos de cada componente
_W_SHARP = 0.55
_W_BRIGHT = 0.30
_W_RES = 0.15


class PillowImageQualityService(IImageQualityService):
    """Evalúa calidad de imagen con heurísticas basadas en Pillow.

    Suficiente para Sprint 2; en producción se puede reemplazar por un
    modelo de visión (CLIP, BRISQUE, etc.) sin cambiar el puerto.
    """

    def evaluate(self, image_data: bytes) -> float:
        try:
            img = Image.open(io.BytesIO(image_data)).convert("RGB")
        except Exception:
            return 0.0

        sharpness_score = _sharpness(img)
        brightness_score = _brightness(img)
        resolution_score = _resolution(img)

        score = (
            _W_SHARP * sharpness_score
            + _W_BRIGHT * brightness_score
            + _W_RES * resolution_score
        )
        return round(max(0.0, min(1.0, score)), 4)


# ── Métricas auxiliares ────────────────────────────────────────────────────────

def _sharpness(img: Image.Image) -> float:
    """Varianza del Laplaciano normalizada a [0, 1].

    El filtro FIND_EDGES de Pillow aproxima el Laplaciano.
    Se calcula sobre una versión reducida (máx. 512 px) para velocidad.
    """
    # Reducir para acelerar sin perder detalle estadístico
    thumb = img.copy()
    thumb.thumbnail((512, 512), Image.LANCZOS)
    gray = thumb.convert("L")
    edges = gray.filter(ImageFilter.FIND_EDGES)

    pixels = list(edges.getdata())
    n = len(pixels)
    if n == 0:
        return 0.0

    mean = sum(pixels) / n
    variance = sum((p - mean) ** 2 for p in pixels) / n

    # Normalizar: varianza de FIND_EDGES es aproximadamente Laplaciano²
    normalized = math.sqrt(variance) / _SHARP_MAX
    return min(1.0, normalized)


def _brightness(img: Image.Image) -> float:
    """Score de exposición basado en el canal L (luminancia).

    Retorna 1.0 si el brillo medio está en el rango aceptable [30, 225].
    Decrece linealmente hacia 0 solo en los extremos (sub/sobreexpuestos).
    La mayoría de fotos reales de cartas caen en el rango aceptable → 1.0.
    """
    thumb = img.copy()
    thumb.thumbnail((256, 256), Image.LANCZOS)
    l_channel = thumb.convert("L")

    pixels = list(l_channel.getdata())
    mean_brightness = sum(pixels) / len(pixels)

    if mean_brightness < _BRIGHT_LOW:
        # Subexpuesta: ramp 0→1 entre 0 y _BRIGHT_LOW
        return mean_brightness / _BRIGHT_LOW
    if mean_brightness > _BRIGHT_HIGH:
        # Sobreexpuesta: ramp 1→0 entre _BRIGHT_HIGH y 255
        return max(0.0, 1.0 - (mean_brightness - _BRIGHT_HIGH) / (255.0 - _BRIGHT_HIGH))
    return 1.0


def _resolution(img: Image.Image) -> float:
    """Penaliza imágenes con resolución inferior a _MIN_SIDE px en el lado menor.

    - Imágenes ≥ _MIN_SIDE × _MIN_SIDE → 1.0
    - Imágenes muy pequeñas → decrece linealmente hasta 0
    """
    w, h = img.size
    short_side = min(w, h)
    if short_side >= _MIN_SIDE:
        return 1.0
    return max(0.0, short_side / _MIN_SIDE)
