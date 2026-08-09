from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Request, Response, status
from sqlalchemy.orm import Session
from uuid_extensions import uuid7

from pokegrading.api.b2b.v1.dependencies import B2BClient, get_current_b2b_client
from pokegrading.api.b2b.v1.schemas.lookup import (
    B2BErrorResponse,
    LookupItemResultSchema,
    LookupRequest,
    LookupResponseSchema,
    OfficialIdentitySchema,
)
from pokegrading.application.use_cases.lookup_catalog_coverage import (
    LookupCatalogCoverageUseCase,
    LookupResponse,
)
from pokegrading.config import get_settings
from pokegrading.domain.entities.card_lookup import CardLookupItem
from pokegrading.domain.exceptions import B2BError
from pokegrading.infrastructure.persistence.database import get_db
from pokegrading.infrastructure.persistence.repositories.b2b.audit_repository import (
    B2BAuditRepositoryImpl,
)
from pokegrading.infrastructure.persistence.repositories.b2b.idempotency_repository import (
    IdempotencyRepositoryImpl,
)
from pokegrading.infrastructure.persistence.repositories.card.card_repository import (
    CardRepositoryImpl,
)
from pokegrading.infrastructure.ratelimit.fixed_window_rate_limiter import (
    FixedWindowRateLimiter,
)

router = APIRouter(prefix="/catalog", tags=["b2b"])

# Respuestas de error documentadas en OpenAPI (formato de error único).
_ERROR_RESPONSES = {
    401: {"model": B2BErrorResponse, "description": "API key inválida/revocada/suspendida/expirada"},
    403: {"model": B2BErrorResponse, "description": "Customer B2B suspendido"},
    409: {"model": B2BErrorResponse, "description": "request_id reusado con contenido distinto"},
    422: {"model": B2BErrorResponse, "description": "Consulta vacía o malformada"},
    429: {"model": B2BErrorResponse, "description": "Límite de cartas excedido"},
}


@router.post(
    "/lookup",
    response_model=LookupResponseSchema,
    responses=_ERROR_RESPONSES,
    summary="US-005 — Consultar cobertura de catálogo (lookup de carta)",
    description=(
        "Consulta de solo lectura: indica, por cada carta, si está cubierta, "
        "tiene coincidencia múltiple, no está cubierta o tiene parámetros "
        "inválidos. Nunca descuenta cuota de evaluación ni sube imágenes."
    ),
)
def lookup_catalog_coverage(
    body: LookupRequest,
    request: Request,
    response: Response,
    client: B2BClient = Depends(get_current_b2b_client),
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    if_none_match: str | None = Header(default=None, alias="If-None-Match"),
) -> LookupResponseSchema | Response:
    settings = get_settings()
    trace_id = getattr(request.state, "trace_id", None) or str(uuid7())
    request_id = idempotency_key or body.request_id

    items = [
        CardLookupItem(
            set_name=c.set_name,
            card_number=c.card_number,
            edition=c.edition,
            language=c.language,
            finish=c.finish,
        )
        for c in body.cards
    ]

    use_case = LookupCatalogCoverageUseCase(
        card_repo=CardRepositoryImpl(db),
        rate_limiter=FixedWindowRateLimiter(db),
        audit_repo=B2BAuditRepositoryImpl(db),
        idempotency_repo=IdempotencyRepositoryImpl(db),
        idempotency_window_hours=settings.b2b_idempotency_window_hours,
        max_cards=settings.b2b_max_cards_per_query,
    )

    try:
        result = use_case.execute(
            customer=client.customer,
            api_key=client.api_key,
            items=items,
            trace_id=trace_id,
            request_id=request_id,
            if_none_match=if_none_match,
        )
    except B2BError:
        # Errores B2B esperados (rate limit, idempotencia, etc.) → formato único.
        raise
    except Exception as exc:  # noqa: BLE001 - AC-14: fallo temporal → formato único
        # Cualquier fallo inesperado se envuelve en INTERNAL_ERROR (500) con el
        # formato de error único. La auditoría/idempotencia solo se persisten al
        # final del use case, así que un fallo previo no deja estado parcial.
        raise B2BError(
            "Fallo temporal del sistema. La consulta puede reintentarse."
        ) from exc

    etag_header = f'"{result.etag}"'
    if result.not_modified:
        return Response(
            status_code=status.HTTP_304_NOT_MODIFIED,
            headers={"ETag": etag_header, "X-Trace-Id": trace_id},
        )

    response.headers["ETag"] = etag_header
    return _to_schema(result)


def _to_schema(result: LookupResponse) -> LookupResponseSchema:
    return LookupResponseSchema(
        request_id=result.request_id,
        etag=result.etag,
        summary=result.summary,
        results=[_to_item_schema(item) for item in result.results],
    )


def _to_identity_schema(o) -> OfficialIdentitySchema:
    return OfficialIdentitySchema(
        card_id=o.card_id,
        set_name=o.set_name,
        card_number=o.card_number,
        edition=o.edition,
        language=o.language,
        finish=o.finish,
    )


def _to_item_schema(item) -> LookupItemResultSchema:
    return LookupItemResultSchema(
        index=item.index,
        status=item.status,
        query=item.query,
        card=_to_identity_schema(item.card) if item.card else None,
        candidates=(
            [_to_identity_schema(c) for c in item.candidates]
            if item.candidates
            else None
        ),
        reason=item.reason,
    )
