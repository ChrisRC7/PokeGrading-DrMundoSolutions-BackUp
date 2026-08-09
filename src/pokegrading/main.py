from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from uuid_extensions import uuid7

from pokegrading.api.b2b.v1.routers import lookup as b2b_lookup
from pokegrading.api.v3.routers import auth, catalog, search, submissions
from pokegrading.config import get_settings
from pokegrading.domain.exceptions import (
    B2BError,
    BothImagesRequiredError,
    CardAlreadyExistsError,
    CardNotFoundError,
    CardNotPreprocessedError,
    DisclosureNotAcceptedError,
    EmailAlreadyExistsError,
    FileTooLargeError,
    ImageNotIdentifiableError,
    ImageQualityBelowThresholdError,
    InvalidCredentialsError,
    InvalidFileFormatError,
    NoMatchFoundError,
    PokegradingError,
    PolyglotDetectedError,
    RateLimitExceededError,
    SubmissionNotFoundError,
    UnauthorizedError,
    UserNotFoundError,
)

_settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    yield


app = FastAPI(
    title=_settings.app_title,
    version=_settings.app_version,
    debug=_settings.app_debug,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    swagger_ui_parameters={"persistAuthorization": True},
    openapi_tags=[
        {"name": "auth", "description": "Registro e inicio de sesión"},
        {"name": "catalog", "description": "Gestión del catálogo de cartas"},
        {"name": "submissions", "description": "Envío de cartas para evaluación de grado"},
        {"name": "search", "description": "Búsqueda rápida de carta en el catálogo (US-004)"},
        {"name": "b2b", "description": "API B2B de cobertura de catálogo (US-005)"},
        {"name": "ops", "description": "Estado del servicio"},
    ],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def trace_id_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
    """Asigna un trace_id por request y lo propaga en `X-Trace-Id`.

    Permite correlacionar logs, auditoría y el formato de error único
    (ver Sprint3/DOC/diseno-datos-sensibles.md §5).
    """
    trace_id = str(uuid7())
    request.state.trace_id = trace_id
    response = await call_next(request)
    response.headers["X-Trace-Id"] = trace_id
    return response

# ── Domain exception → HTTP status mapping ──────────────────────────────────

_DOMAIN_STATUS_MAP: dict[type[PokegradingError], int] = {
    EmailAlreadyExistsError: 409,
    CardAlreadyExistsError: 409,
    DisclosureNotAcceptedError: 400,
    UnauthorizedError: 403,
    InvalidCredentialsError: 401,
    UserNotFoundError: 404,
    CardNotFoundError: 404,
    BothImagesRequiredError: 422,
    InvalidFileFormatError: 422,
    FileTooLargeError: 413,
    PolyglotDetectedError: 422,
    ImageQualityBelowThresholdError: 422,
    ImageNotIdentifiableError: 422,
    NoMatchFoundError: 404,
    # Sprint 4
    SubmissionNotFoundError: 404,
    CardNotPreprocessedError: 409,
}


@app.exception_handler(B2BError)
async def b2b_error_handler(request: Request, exc: B2BError) -> JSONResponse:
    """Formato de error único del API B2B (ADR-004 §6).

    Registrado para `B2BError`: por el orden de MRO, tiene precedencia sobre
    el handler de `PokegradingError` para cualquier excepción B2B.
    """
    trace_id = getattr(request.state, "trace_id", "")
    headers = {"X-Trace-Id": trace_id}
    if isinstance(exc, RateLimitExceededError):
        headers["Retry-After"] = str(exc.retry_after_seconds)
    return JSONResponse(
        status_code=exc.http_status,
        headers=headers,
        content={
            "error": {
                "code": exc.code,
                "message": str(exc),
                "field": exc.field,
                "card_ref": exc.card_ref,
                "trace_id": trace_id,
            }
        },
    )


@app.exception_handler(PokegradingError)
async def domain_exception_handler(
    request: Request, exc: PokegradingError
) -> JSONResponse:
    status_code = _DOMAIN_STATUS_MAP.get(type(exc), 400)
    return JSONResponse(status_code=status_code, content={"detail": str(exc)})


# ── Routers ──────────────────────────────────────────────────────────────────

app.include_router(auth.router, prefix="/api/v3")
app.include_router(catalog.router, prefix="/api/v3")
app.include_router(submissions.router, prefix="/api/v3")
app.include_router(search.router, prefix="/api/v3")
app.include_router(b2b_lookup.router, prefix="/api/b2b/v1")


@app.get("/health", tags=["ops"])
def health_check() -> dict:
    return {"status": "ok", "version": _settings.app_version}


def custom_openapi() -> dict:
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(
        title=app.title,
        version=app.version,
        routes=app.routes,
    )
    schema.setdefault("components", {})
    schema["components"].setdefault("securitySchemes", {})
    schema["components"]["securitySchemes"]["HTTPBearer"] = {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT",
        "description": (
            "Token JWT obtenido en `POST /api/v3/auth/login`. "
            "Pega solo el valor del campo `access_token`, sin la palabra Bearer."
        ),
    }
    schema["security"] = [{"HTTPBearer": []}]
    app.openapi_schema = schema
    return schema


app.openapi = custom_openapi  # type: ignore[method-assign]
