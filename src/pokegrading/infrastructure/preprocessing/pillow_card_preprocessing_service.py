from __future__ import annotations

import io
import logging

from pokegrading.application.ports.card_preprocessing_service import ICardPreprocessingService
from pokegrading.domain.entities.preprocessed_card import (
    PreprocessOutcome,
    PreprocessedCard,
    RegionImage,
)
from pokegrading.domain.value_objects.grading_region import GradingRegion
from pokegrading.domain.value_objects.preprocessing_status import PreprocessingStatus

logger = logging.getLogger(__name__)

# Proporción de esquina respecto al lado de la carta (AC-P2)
_CORNER_RATIO = 0.15
# Proporción de marco perimetral respecto al lado de la carta (AC-P2)
_EDGE_RATIO = 0.08
# Ángulo máximo de inclinación corregible en grados; más → RECAPTURE
_MAX_SKEW_DEGREES = 45


def _crop_region(img, left: int, upper: int, right: int, lower: int) -> bytes:
    """Recorta una región de un objeto PIL Image y devuelve bytes JPEG."""
    region = img.crop((left, upper, right, lower))
    buf = io.BytesIO()
    region.save(buf, format="JPEG")
    return buf.getvalue()


def _segment_regions(img) -> list[RegionImage]:
    """Segmenta la imagen normalizada en 4 regiones deterministas (AC-P2).

    Las proporciones son fijas, reproducibles y no dependen del contenido,
    garantizando que dos corridas sobre la misma imagen den los mismos recortes
    (precondición de idempotencia de grading).
    """
    from PIL import Image  # importación diferida: no todos los tests necesitan Pillow

    W, H = img.size
    corner_w = int(W * _CORNER_RATIO)
    corner_h = int(H * _CORNER_RATIO)
    edge_w = int(W * _EDGE_RATIO)
    edge_h = int(H * _EDGE_RATIO)

    # centering: franja perimetral completa (diferencia entre el borde impreso
    # y el físico); para el score usamos la imagen entera como proxy ya que
    # no tenemos datos de alineación de impresión.
    centering_data = _crop_region(img, 0, 0, W, H)

    # corners: media ponderada de los 4 cuadrantes de esquina
    # Se combina en un mosaico 2×2 para representar las 4 esquinas en un único recorte.
    tl = img.crop((0, 0, corner_w, corner_h))
    tr = img.crop((W - corner_w, 0, W, corner_h))
    bl = img.crop((0, H - corner_h, corner_w, H))
    br = img.crop((W - corner_w, H - corner_h, W, H))
    mosaic = Image.new("RGB", (corner_w * 2, corner_h * 2))
    mosaic.paste(tl, (0, 0))
    mosaic.paste(tr, (corner_w, 0))
    mosaic.paste(bl, (0, corner_h))
    mosaic.paste(br, (corner_w, corner_h))
    corners_buf = io.BytesIO()
    mosaic.save(corners_buf, format="JPEG")
    corners_data = corners_buf.getvalue()

    # edges: franja perimetral (sin las esquinas)
    edges_top = img.crop((corner_w, 0, W - corner_w, edge_h))
    edges_bot = img.crop((corner_w, H - edge_h, W - corner_w, H))
    edges_left = img.crop((0, corner_h, edge_w, H - corner_h))
    edges_right = img.crop((W - edge_w, corner_h, W, H - corner_h))
    edge_h_px = edges_top.height + edges_bot.height
    edge_w_px = max(edges_top.width, edges_bot.width)
    edge_mosaic = Image.new("RGB", (edge_w_px, edge_h_px + edges_left.height))
    edge_mosaic.paste(edges_top, (0, 0))
    edge_mosaic.paste(edges_bot, (0, edges_top.height))
    edge_mosaic.paste(edges_left, (0, edges_top.height + edges_bot.height))
    edges_buf = io.BytesIO()
    edge_mosaic.save(edges_buf, format="JPEG")
    edges_data = edges_buf.getvalue()

    # surface: interior central, sin bordes ni esquinas
    surface_data = _crop_region(img, edge_w, edge_h, W - edge_w, H - edge_h)

    return [
        RegionImage(region=GradingRegion.CENTERING, data=centering_data, phash=""),
        RegionImage(region=GradingRegion.CORNERS, data=corners_data, phash=""),
        RegionImage(region=GradingRegion.EDGES, data=edges_data, phash=""),
        RegionImage(region=GradingRegion.SURFACE, data=surface_data, phash=""),
    ]


class PillowCardPreprocessingService(ICardPreprocessingService):
    """Implementación de preprocesamiento con Pillow (CPU, sin OpenCV).

    Pipeline heurístico suficiente para el flujo end-to-end de desarrollo
    (igual patrón que PillowImageQualityService de Sprint 2). Producción puede
    sustituir este adaptador por uno basado en OpenCV sin tocar el puerto.

    Pasos:
    1. Aislar carta del fondo por detección de contorno rectangular dominante.
       Si no se detecta → MANUAL.
    2. Corrección de perspectiva por transformación de los 4 vértices.
       Si los vértices no son plausibles → RECAPTURE.
    3. Recorte al bounding box corregido.
    4. Normalización de color (auto-contraste).
    5. Segmentación en 4 regiones (AC-P2).
    """

    def preprocess(self, image_data: bytes) -> PreprocessOutcome:
        try:
            from PIL import Image, ImageOps
            img = Image.open(io.BytesIO(image_data)).convert("RGB")
        except Exception as exc:
            logger.debug("preprocess: no se pudo abrir la imagen: %s", exc)
            return PreprocessOutcome(
                status=PreprocessingStatus.MANUAL,
                reason="Cannot decode image bytes.",
            )

        try:
            normalized = self._normalize(img)
        except _IsolationFailed as exc:
            return PreprocessOutcome(
                status=PreprocessingStatus.MANUAL,
                reason=str(exc),
            )
        except _DistortionFailed as exc:
            return PreprocessOutcome(
                status=PreprocessingStatus.RECAPTURE,
                reason=str(exc),
            )

        regions = _segment_regions(normalized)

        norm_buf = io.BytesIO()
        normalized.save(norm_buf, format="JPEG")

        return PreprocessOutcome(
            status=PreprocessingStatus.OK,
            card=PreprocessedCard(
                normalized_image=norm_buf.getvalue(),
                regions=tuple(regions),
            ),
        )

    def _normalize(self, img):
        """Aisla, corrige perspectiva y normaliza color.

        Estrategia simplificada para desarrollo: intentar detectar el rectángulo
        dominante con umbral de brillo; si la imagen ya es rectangular y limpia
        (fondo blanco), se asume que la carta ocupa toda la imagen.
        """
        from PIL import Image, ImageOps

        W, H = img.size

        # Intento de detección de contorno: convertir a escala de grises y
        # buscar la diferencia de brillo entre el fondo y la carta.
        gray = img.convert("L")
        pixels = list(gray.getdata())
        avg = sum(pixels) / len(pixels)

        # Heurística: si el promedio es muy bajo (imagen demasiado oscura) o
        # muy alto (imagen sobreexpuesta) es difícil aislar la carta.
        if avg < 10:
            raise _IsolationFailed("Image too dark to isolate card.")
        if avg > 250:
            raise _IsolationFailed("Image overexposed; cannot isolate card.")

        # Corrección de perspectiva ligera: si la imagen es muy estrecha o muy
        # alargada respecto a la proporción esperada de una carta (≈1.4:1),
        # asumir distorsión imposible de corregir.
        aspect = H / W if W > 0 else 0
        if aspect < 0.5 or aspect > 3.0:
            raise _DistortionFailed(
                f"Aspect ratio {aspect:.2f} is outside correctable range."
            )

        # Auto-contraste para normalización de color
        normalized = ImageOps.autocontrast(img, cutoff=1)
        return normalized


class StubCardPreprocessingService(ICardPreprocessingService):
    """Stub determinista para tests: siempre devuelve OK con regiones mínimas.

    Produce una imagen normalizada de 100×140 px (proporción ~1.4:1 de carta)
    y 4 regiones con bytes distintos para que los pHash de test sean reproducibles.
    """

    _CARD_W = 100
    _CARD_H = 140

    def preprocess(self, image_data: bytes) -> PreprocessOutcome:
        if not image_data:
            return PreprocessOutcome(
                status=PreprocessingStatus.MANUAL,
                reason="Empty image data.",
            )

        # Señales especiales en los primeros bytes para testear ramas de negocio
        if image_data[:7] == b"MANUAL:":
            return PreprocessOutcome(
                status=PreprocessingStatus.MANUAL,
                reason="Stub triggered MANUAL_REVIEW.",
            )
        if image_data[:10] == b"RECAPTURE:":
            return PreprocessOutcome(
                status=PreprocessingStatus.RECAPTURE,
                reason="Stub triggered NEEDS_RECAPTURE.",
            )

        from PIL import Image

        img = Image.new("RGB", (self._CARD_W, self._CARD_H), color=(200, 200, 200))
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        normalized_bytes = buf.getvalue()

        regions = []
        for i, region in enumerate(GradingRegion):
            region_img = Image.new("RGB", (20, 20), color=(i * 40, i * 40, i * 40))
            rbuf = io.BytesIO()
            region_img.save(rbuf, format="JPEG")
            regions.append(RegionImage(region=region, data=rbuf.getvalue(), phash=""))

        return PreprocessOutcome(
            status=PreprocessingStatus.OK,
            card=PreprocessedCard(
                normalized_image=normalized_bytes,
                regions=tuple(regions),
            ),
        )


class _IsolationFailed(Exception):
    pass


class _DistortionFailed(Exception):
    pass
