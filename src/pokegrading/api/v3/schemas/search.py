from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field


class OcrDetectedFields(BaseModel):
    """Campos de una carta Pokémon detectados automáticamente por OCR."""

    name: str | None = Field(None, description="Nombre de la carta (ej. 'Charizard VMAX')")
    hp: int | None = Field(None, description="HP detectado (ej. 120)")
    card_number: str | None = Field(None, description="Número de carta (ej. '025/185')")


class OcrExtractResponse(BaseModel):
    """Respuesta del endpoint POST /search/ocr-extract."""

    raw_text: str = Field(..., description="Texto completo extraído por EasyOCR")
    detected: OcrDetectedFields = Field(..., description="Campos identificados automáticamente")


class CardCandidateResponse(BaseModel):
    """Un candidato individual retornado por la búsqueda rápida."""

    rank: int = Field(..., ge=1, le=3, description="Posición en el ranking (1 = mejor coincidencia)")
    candidate_card_id: UUID = Field(..., description="UUID de la carta en el catálogo")
    confidence_score: float = Field(..., ge=0.0, le=1.0, description="Confianza de la coincidencia (0–1)")
    name: str = Field(..., description="Nombre de la carta (igual en EN y ES)")
    set_name: str = Field(..., description="Nombre del set / colección")
    card_number: str = Field(..., description="Número impreso en la carta, ej. '025/185'")
    language: str = Field(..., description="Idioma de la carta: 'en' (inglés) o 'es' (español)")
    rarity: str | None = Field(None, description="Rareza: Common, Uncommon, Rare, Holo Rare, etc.")
    pokemon_type: str | None = Field(None, description="Tipo de energía: Fire, Water, Grass…")
    hp: int | None = Field(None, description="Puntos de vida impresos en la carta")


class QuickSearchResponse(BaseModel):
    """Respuesta del endpoint POST /search/quick (US-004)."""

    candidates: list[CardCandidateResponse] = Field(..., description="Hasta 3 candidatos ordenados por confianza")
    auto_accepted: bool = Field(
        ...,
        description=(
            "True si el candidato #1 supera el umbral de confianza configurado "
            "y puede avanzar automáticamente al siguiente paso del flujo."
        ),
    )
    total: int = Field(..., description="Número de candidatos devueltos")
    match_engine: str | None = Field(
        None,
        description=(
            "Motor que resolvió la búsqueda: 'phash' (rápida por similitud "
            "visual) u 'ocr' (especializada por texto). "
            "Permite saber qué etapa identificó la carta."
        ),
    )
    ocr_text: str | None = Field(
        None,
        description=(
            "Texto extraído de la imagen por EasyOCR (solo disponible cuando "
            "la búsqueda fue por imagen, no por 'q' manual). "
            "Útil para depuración: muestra exactamente qué leyó el modelo."
        ),
    )
    image_quality_score: float | None = Field(
        None,
        ge=0.0,
        le=1.0,
        description=(
            "Calidad de la imagen de frente [0.0–1.0], calculada con PillowImageQualityService "
            "(55% nitidez + 30% brillo + 15% resolución). "
            "Se devuelve siempre que la imagen sea JPEG/PNG válida, independientemente de si hubo OCR."
        ),
    )
