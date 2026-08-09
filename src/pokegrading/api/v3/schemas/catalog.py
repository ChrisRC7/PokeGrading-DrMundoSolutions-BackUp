from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class AddCardRequest(BaseModel):
    # Contrato de entrada para crear una carta del catálogo.
    name: str = Field(min_length=1, max_length=255)
    set_name: str = Field(min_length=1, max_length=100)
    card_number: str = Field(min_length=1, max_length=20)
    edition: str = Field(min_length=1, max_length=100)
    language: str = Field(min_length=1, max_length=10)
    finish: str = Field(min_length=1, max_length=50)
    description: str | None = None
    rarity: str | None = Field(default=None, max_length=50)
    pokemon_type: str | None = Field(default=None, max_length=50)
    hp: int | None = Field(default=None, ge=1)
    illustrator: str | None = Field(default=None, max_length=255)
    print_year: int | None = Field(default=None, ge=1996, le=2100)


class UpdateCardRequest(BaseModel):
    # Actualización parcial del catálogo.
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    status: str | None = Field(default=None, pattern="^(pending|active|retired)$")


class CardIdentityResponse(BaseModel):
    # Identidad de negocio visible para la UI y para detectar variantes.
    set_name: str
    card_number: str
    edition: str
    language: str
    finish: str


class CardResponse(BaseModel):
    # Respuesta resumida tras crear o consultar una carta.
    card_id: UUID
    identity: CardIdentityResponse
    name: str
    status: str
    version: int
    created_by: UUID
    created_at: datetime


class CardDetailResponse(CardResponse):
    # Detalle completo: metadatos, auditoría e indicadores de imágenes.
    description: str | None
    rarity: str | None
    pokemon_type: str | None
    hp: int | None
    illustrator: str | None
    print_year: int | None
    has_image_front: bool
    has_image_back: bool
    approved_by: UUID | None
    approved_at: datetime | None


class ImageUploadResponse(BaseModel):
    # Respuesta mínima tras persistir una imagen de referencia.
    card_id: UUID
    side: str
    content_type: str
    width: int
    height: int
    file_size: int
    uploaded_at: datetime
