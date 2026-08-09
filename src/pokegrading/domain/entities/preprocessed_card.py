from __future__ import annotations

from dataclasses import dataclass

from pokegrading.domain.value_objects.grading_region import GradingRegion
from pokegrading.domain.value_objects.preprocessing_status import PreprocessingStatus


@dataclass(frozen=True)
class RegionImage:
    """Recorte normalizado de una de las 4 regiones de grading.

    El pHash se calcula sobre el recorte para poder compararlo contra
    la región equivalente de la imagen de referencia del catálogo.
    """

    region: GradingRegion
    data: bytes
    phash: str


@dataclass(frozen=True)
class PreprocessedCard:
    """Resultado del preprocesamiento exitoso de una carta.

    Contiene la imagen normalizada (perspectiva corregida, recortada y con
    color balanceado) y los 4 recortes regionales listos para grading.
    """

    normalized_image: bytes
    regions: tuple[RegionImage, ...]


@dataclass(frozen=True)
class PreprocessOutcome:
    """Resultado del pipeline de preprocesamiento (AC-P3/P4/P5).

    Siempre se devuelve un outcome — nunca se lanza para ramas de negocio.
    El use case lee el status y ramifica el flujo.
    """

    status: PreprocessingStatus
    card: PreprocessedCard | None = None
    reason: str | None = None
