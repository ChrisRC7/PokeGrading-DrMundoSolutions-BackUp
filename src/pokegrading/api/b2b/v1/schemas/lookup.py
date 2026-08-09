from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class LookupItemRequest(BaseModel):
    """Una carta dentro de la consulta B2B. `set` y `number` son obligatorios.

    Los nombres JSON externos son `set`/`number`; internamente se mapean a
    `set_name`/`card_number` para alinear con la identidad del catálogo.
    """

    model_config = ConfigDict(populate_by_name=True)

    set_name: str | None = Field(default=None, alias="set")
    card_number: str | None = Field(default=None, alias="number")
    edition: str | None = None
    language: str | None = None
    finish: str | None = None


class LookupRequest(BaseModel):
    request_id: str | None = None
    cards: list[LookupItemRequest] = Field(default_factory=list)


class OfficialIdentitySchema(BaseModel):
    """Identidad oficial de catálogo (solo metadata; nunca datos de evaluación)."""

    model_config = ConfigDict(populate_by_name=True)

    card_id: str
    set_name: str = Field(serialization_alias="set")
    card_number: str = Field(serialization_alias="number")
    edition: str
    language: str
    finish: str


class LookupItemResultSchema(BaseModel):
    index: int
    status: str
    query: dict
    card: OfficialIdentitySchema | None = None
    candidates: list[OfficialIdentitySchema] | None = None
    reason: dict | None = None


class LookupResponseSchema(BaseModel):
    request_id: str | None
    etag: str
    summary: dict
    results: list[LookupItemResultSchema]


class B2BErrorDetail(BaseModel):
    code: str
    message: str
    field: str | None = None
    card_ref: str | None = None
    trace_id: str


class B2BErrorResponse(BaseModel):
    error: B2BErrorDetail
