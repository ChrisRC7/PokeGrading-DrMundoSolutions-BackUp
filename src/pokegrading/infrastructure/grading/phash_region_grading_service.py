from __future__ import annotations

import io

from pokegrading.application.ports.region_grading_service import IRegionGradingService
from pokegrading.domain.entities.card_evaluation import Subgrade
from pokegrading.domain.entities.grading_baseline import GradingBaseline
from pokegrading.domain.exceptions import InsufficientGradingInputError
from pokegrading.domain.value_objects.grading_region import GradingRegion


def _hamming_distance(a: str, b: str) -> int:
    """Distancia de Hamming entre dos hashes hex de 64 bits (máx 64)."""
    if not a or not b:
        return 64  # insumo vacío = distancia máxima
    try:
        x = int(a, 16) ^ int(b, 16)
        return bin(x).count("1")
    except ValueError:
        return 64


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


class PHashRegionGradingService(IRegionGradingService):
    """Subgrade por región usando distancia de Hamming entre pHashes (AC-G1).

    Fórmula:
        d         = hamming_distance(submission_phash, reference_phash)  [0..64]
        s         = baseline.score_for(region, d)                        [1.0..10.0]
        score     = clamp(round(s, 1), 1.0, 10.0)
        confidence= 1.0 - d / 64

    Si alguno de los pHashes está vacío → InsufficientGradingInputError (AC-G7).
    """

    def grade_region(
        self,
        region: GradingRegion,
        submission_region_phash: str,
        reference_region_phash: str,
        baseline: GradingBaseline,
        *,
        submission_region_data: bytes = b"",
        reference_region_data: bytes = b"",
    ) -> Subgrade:
        if not submission_region_phash or not reference_region_phash:
            raise InsufficientGradingInputError(region.value)

        d = _hamming_distance(submission_region_phash, reference_region_phash)
        s = baseline.score_for(region, d)
        score = _clamp(round(s, 1), 1.0, 10.0)
        confidence = _clamp(1.0 - d / 64, 0.0, 1.0)

        return Subgrade(
            region=region,
            score=score,
            hamming_distance=d,
            confidence=confidence,
        )


# ── Constantes de detección de daño (StructuralRegionGradingService) ──────────
# Son perillas de "cuánto penaliza el daño". Subir PHASH_WEIGHT da más peso al
# parecido estructural (más indulgente con marcas); bajarlo castiga más el daño.
# peso del score por pHash; (1 - w) es el peso del daño
DEFAULT_PHASH_WEIGHT = 0.35
# delta de color por píxel para contar el píxel como "marca"
DAMAGE_COLOR_THRESHOLD = 40
# fracción de píxeles alterados que ya implica daño total (score 1.0)
DAMAGE_FULL_FRACTION = 0.12
# resolución a la que se comparan los recortes
_DAMAGE_GRID = 128


def _altered_fraction(a_data: bytes, b_data: bytes) -> float | None:
    """Fracción de píxeles del recorte cuyo color difiere por encima del umbral.

    Sensible a marcas locales (rayones, manchas) que el pHash ignora por diseño.
    Devuelve None si algún recorte no se puede decodificar (sin señal de daño).
    """
    try:
        import numpy as np
        from PIL import Image

        size = (_DAMAGE_GRID, _DAMAGE_GRID)
        a = Image.open(io.BytesIO(a_data)).convert("RGB").resize(size)
        b = Image.open(io.BytesIO(b_data)).convert("RGB").resize(size)
    except Exception:
        return None

    arr_a = np.asarray(a, dtype=np.int16)
    arr_b = np.asarray(b, dtype=np.int16)
    # Máxima diferencia por canal en cada píxel: una marca roja sobre fondo azul
    # produce un delta alto aunque la luminancia apenas cambie.
    per_pixel = np.abs(arr_a - arr_b).max(axis=2)
    return float((per_pixel > DAMAGE_COLOR_THRESHOLD).mean())


class StructuralRegionGradingService(IRegionGradingService):
    """Subgrade que combina pHash (parecido estructural) con detección de daño local.

    El pHash reconoce que es la carta correcta y penaliza diferencias estructurales
    grandes, pero es robusto a marcas locales (rayones) por diseño. Para que el daño
    superficial baje la nota, se añade una diferencia de píxeles región-contra-región
    que sí detecta esas marcas. Score final = mezcla ponderada de ambos.

    Pertenece a la etapa de CALIFICAR; no interviene en la identificación de la carta.
    """

    def __init__(self, phash_weight: float = DEFAULT_PHASH_WEIGHT) -> None:
        self._w = _clamp(phash_weight, 0.0, 1.0)

    def grade_region(
        self,
        region: GradingRegion,
        submission_region_phash: str,
        reference_region_phash: str,
        baseline: GradingBaseline,
        *,
        submission_region_data: bytes = b"",
        reference_region_data: bytes = b"",
    ) -> Subgrade:
        if not submission_region_phash or not reference_region_phash:
            raise InsufficientGradingInputError(region.value)

        d = _hamming_distance(submission_region_phash, reference_region_phash)
        score_phash = baseline.score_for(region, d)

        altered = _altered_fraction(submission_region_data, reference_region_data)
        if altered is None:
            # Sin recortes comparables → se cae a pHash puro (comportamiento previo).
            score = _clamp(round(score_phash, 1), 1.0, 10.0)
            return Subgrade(region=region, score=score, hamming_distance=d,
                            confidence=_clamp(1.0 - d / 64, 0.0, 1.0))

        # Daño: 0.0 (limpio) → 10.0; DAMAGE_FULL_FRACTION o más → 1.0.
        damage_ratio = _clamp(altered / DAMAGE_FULL_FRACTION, 0.0, 1.0)
        score_damage = 10.0 - 9.0 * damage_ratio

        score = self._w * score_phash + (1.0 - self._w) * score_damage
        score = _clamp(round(score, 1), 1.0, 10.0)
        # La confianza baja cuando hay daño detectado (insumo de la banda AC-G4).
        confidence = _clamp((1.0 - d / 64) * (1.0 - damage_ratio), 0.0, 1.0)

        return Subgrade(
            region=region,
            score=score,
            hamming_distance=d,
            confidence=confidence,
        )


class StubRegionGradingService(IRegionGradingService):
    """Stub determinista para tests: distancia 0 → score 10.0, 64 → score 1.0."""

    def __init__(self, fixed_distance: int = 0) -> None:
        self._d = fixed_distance

    def grade_region(
        self,
        region: GradingRegion,
        submission_region_phash: str,
        reference_region_phash: str,
        baseline: GradingBaseline,
        *,
        submission_region_data: bytes = b"",
        reference_region_data: bytes = b"",
    ) -> Subgrade:
        if not submission_region_phash or not reference_region_phash:
            raise InsufficientGradingInputError(region.value)

        d = self._d
        score = _clamp(round(baseline.score_for(region, d), 1), 1.0, 10.0)
        confidence = _clamp(1.0 - d / 64, 0.0, 1.0)
        return Subgrade(
            region=region,
            score=score,
            hamming_distance=d,
            confidence=confidence,
        )
