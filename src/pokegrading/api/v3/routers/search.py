from __future__ import annotations

import re as _re

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from pokegrading.api.v3.dependencies import get_current_user, get_db
from pokegrading.api.v3.schemas.search import (
    CardCandidateResponse,
    OcrDetectedFields,
    OcrExtractResponse,
    QuickSearchResponse,
)
from pokegrading.application.ports.card_matching_service import ICardMatchingService
from pokegrading.application.ports.image_hash_service import IImageHashService
from pokegrading.application.use_cases.quick_search_by_phash import (
    QuickSearchByPHashInput,
    QuickSearchByPHashUseCase,
)
from pokegrading.application.use_cases.quick_search_card import (
    QuickSearchCardUseCase,
    QuickSearchInput,
)
from pokegrading.domain.entities.user import User
from pokegrading.domain.exceptions import ImageNotIdentifiableError, NoMatchFoundError
from pokegrading.infrastructure.matching.easyocr_card_matching_service import EasyOCRCardMatchingService
from pokegrading.infrastructure.matching.phash_image_hash_service import PHashImageHashService
from pokegrading.infrastructure.matching.stub_card_matching_service import StubCardMatchingService
from pokegrading.infrastructure.persistence.repositories.card.card_repository import (
    CardRepositoryImpl,
)
from pokegrading.infrastructure.services.pillow_image_quality_service import PillowImageQualityService

router = APIRouter(prefix="/search", tags=["search"])

_matching_svc = EasyOCRCardMatchingService()
_hash_svc = PHashImageHashService()

_JPEG_MAGIC = b"\xff\xd8\xff"
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

# ── Patrones para parsear campos de cartas Pokémon TCG desde tokens OCR ──────
_CARD_NUM_RE = _re.compile(r"\b(\d{1,3}/\d{1,3})\b")
_NUMERIC_RE = _re.compile(r"^\d+$")
_STAGE_RE = _re.compile(r"^(basic|stage\s*\d+|restored|v-union|break)$", _re.IGNORECASE)


def _parse_card_tokens(tokens: list[str]) -> dict:
    """Extrae campos estructurados de la lista de tokens devuelta por EasyOCR.

    Campos detectables:
    - ``card_number``: patrón ``\\d+/\\d+`` (ej. "025/185")
    - ``hp``: número adyacente a un token "HP"
    - ``name``: primeros tokens significativos antes del HP/número

    Retorna un dict con las claves detectadas (omite las no encontradas).
    """
    # El parser intenta quedarse con señales útiles para matching y descartar ruido OCR.
    result: dict = {}

    # 1. Número de carta: buscar patrón NN/NNN en el texto completo
    joined = " ".join(tokens)
    m = _CARD_NUM_RE.search(joined)
    if m:
        result["card_number"] = m.group(1)

    # 2. HP: número inmediatamente antes o después del token "HP"
    for i, tok in enumerate(tokens):
        if tok.upper() == "HP":
            if i > 0 and _NUMERIC_RE.match(tokens[i - 1]):
                result["hp"] = int(tokens[i - 1])
                break
            if i < len(tokens) - 1 and _NUMERIC_RE.match(tokens[i + 1]):
                result["hp"] = int(tokens[i + 1])
                break

    # 3. Nombre: primeros tokens significativos (máx. 3 palabras)
    #    Salta indicadores de stage y números puros.
    name_parts: list[str] = []
    for tok in tokens:
        if _STAGE_RE.match(tok):
            if name_parts:  # stage aparece DESPUÉS del nombre → parar
                break
            continue
        if _NUMERIC_RE.match(tok):
            if name_parts:  # número tras nombre → fin del nombre
                break
            continue
        if tok.upper() == "HP":
            break
        if _CARD_NUM_RE.match(tok):
            break
        if len(tok) < 2:
            continue
        name_parts.append(tok)
        if len(name_parts) >= 3:  # "Tapu Koko GX" ya son 3 partes
            break
    if name_parts:
        result["name"] = " ".join(name_parts)

    return result


def _get_matching_svc() -> ICardMatchingService:
    # Singleton de proceso: el servicio OCR se comparte entre requests.
    return _matching_svc


def _get_hash_svc() -> IImageHashService:
    return _hash_svc


@router.post(
    "/ocr-extract",
    response_model=OcrExtractResponse,
    summary="Extraer campos de una carta por OCR (US-004 / admin)",
    description=(
        "Recibe la imagen de frente de una carta, ejecuta EasyOCR y devuelve:\n\n"
        "- **raw_text**: todo el texto reconocido en la imagen\n"
        "- **detected**: campos parseados automáticamente (nombre, HP, número de carta)\n\n"
        "Diseñado para pre-rellenar el formulario de alta de carta en el panel de administración."
    ),
)
async def ocr_extract(
    image_front: UploadFile | None = None,
    current_user: User = Depends(get_current_user),
    matching_svc: ICardMatchingService = Depends(_get_matching_svc),
) -> OcrExtractResponse:
    # Endpoint auxiliar para admin: extrae texto y campos, pero no persiste nada.
    if image_front is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="image_front is required.",
        )

    front_data = await image_front.read()

    _JPEG_MAGIC = b"\xff\xd8\xff"
    _PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
    if not (front_data[:3] == _JPEG_MAGIC or front_data[:8] == _PNG_MAGIC):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="image_front must be a JPEG or PNG image.",
        )

    # Tokens sin filtrar (necesarios para detectar "HP" y el número)
    from pokegrading.infrastructure.matching.easyocr_card_matching_service import (
        EasyOCRCardMatchingService as _EOCR,
    )
    if isinstance(matching_svc, _EOCR):
        # OCR real: se conservan tokens crudos para detectar HP y número de carta.
        tokens: list[str] = matching_svc.extract_tokens_raw(front_data)
    else:
        # Fallback con stub: degradamos a texto plano para no romper el contrato.
        # Stub u otro servicio: no hay tokens raw, usamos features como fallback
        raw = matching_svc.extract_features(front_data)
        tokens = raw.split() if raw else []

    raw_text = " ".join(tokens)
    parsed = _parse_card_tokens(tokens)

    return OcrExtractResponse(
        raw_text=raw_text,
        detected=OcrDetectedFields(**parsed),
    )


async def _read_image_or_422(image_front: UploadFile | None) -> bytes:
    """Lee la imagen subida y valida que sea JPEG o PNG (magic bytes)."""
    if image_front is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="image_front is required.",
        )
    data = await image_front.read()
    if not (data[:3] == _JPEG_MAGIC or data[:8] == _PNG_MAGIC):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="image_front must be a JPEG or PNG image.",
        )
    return data


def _to_candidates(results) -> list[CardCandidateResponse]:
    return [
        CardCandidateResponse(
            rank=r.rank,
            candidate_card_id=r.candidate_card_id,
            confidence_score=r.confidence_score,
            name=r.name,
            set_name=r.set_name,
            card_number=r.card_number,
            language=r.language,
            rarity=r.rarity,
            pokemon_type=r.pokemon_type,
            hp=r.hp,
        )
        for r in results
    ]


def _specialized_search(
    front_data: bytes,
    q: str | None,
    confidence_threshold: float,
    db: Session,
    matching_svc: ICardMatchingService,
) -> QuickSearchResponse:
    """Búsqueda especializada/detallada por OCR (EasyOCR + matching de texto)."""
    ocr_text: str | None = None
    effective_q = (q or "").strip() or None
    if not effective_q:
        # Mismo parsing que /ocr-extract: solo nombre + número, no todo el texto OCR.
        if isinstance(matching_svc, EasyOCRCardMatchingService):
            tokens = matching_svc.extract_tokens_raw(front_data)
        else:
            raw = matching_svc.extract_features(front_data)
            tokens = raw.split() if raw else []
        parsed = _parse_card_tokens(tokens)
        parts = [p for p in [parsed.get("name"), parsed.get("card_number")] if p]
        ocr_text = " ".join(tokens)
        effective_q = " ".join(parts).strip() or None

    inp = QuickSearchInput(
        image_front_data=front_data,
        query_hint=effective_q,
        confidence_threshold=confidence_threshold,
    )
    try:
        result = QuickSearchCardUseCase(
            card_repo=CardRepositoryImpl(db),
            matching_svc=matching_svc,
        ).execute(inp)
    except ImageNotIdentifiableError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        )
    except NoMatchFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": str(exc), "ocr_text": ocr_text, "focused_q": effective_q},
        )

    candidates = _to_candidates(result.candidates)
    return QuickSearchResponse(
        candidates=candidates,
        auto_accepted=result.auto_accepted,
        total=len(candidates),
        match_engine="ocr",
        ocr_text=ocr_text,
        image_quality_score=None,
    )


@router.post(
    "/quick",
    response_model=QuickSearchResponse,
    summary="Búsqueda rápida de carta — pHash con escalamiento a OCR (US-004)",
    description=(
        "Recibe la imagen de frente de una carta y devuelve hasta 3 candidatos.\n\n"
        "**Etapa 1 — pHash (rápida):** compara la imagen con las imágenes de "
        "referencia del catálogo por similitud visual. Si encuentra candidatos "
        "cercanos, los devuelve (`match_engine = 'phash'`).\n\n"
        "**Etapa 2 — OCR (escalamiento):** si el pHash no resuelve (sin imágenes "
        "de referencia, imagen muy distinta o ilegible), escala a la búsqueda "
        "especializada por texto (`match_engine = 'ocr'`). En modo desarrollo "
        "puede usarse `q` para la etapa OCR."
    ),
)
async def quick_search(
    image_front: UploadFile | None = None,
    q: str | None = Form(None, description="Texto de búsqueda para la etapa OCR — modo dev"),
    confidence_threshold: float = Form(0.60, ge=0.0, le=1.0, description="Umbral de auto-aceptación (OCR)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    matching_svc: ICardMatchingService = Depends(_get_matching_svc),
    hash_svc: IImageHashService = Depends(_get_hash_svc),
) -> QuickSearchResponse:
    # AC-05: sin token → 401 (manejado por get_current_user)
    front_data = await _read_image_or_422(image_front)

    # Etapa 1 — pHash. Si no resuelve, se escala a OCR (etapa 2).
    try:
        ph_result = QuickSearchByPHashUseCase(
            card_repo=CardRepositoryImpl(db),
            hash_svc=hash_svc,
        ).execute(QuickSearchByPHashInput(image_front_data=front_data))
        candidates = _to_candidates(ph_result.candidates)
        return QuickSearchResponse(
            candidates=candidates,
            auto_accepted=ph_result.auto_accepted,
            total=len(candidates),
            match_engine="phash",
            ocr_text=None,
        )
    except (NoMatchFoundError, ImageNotIdentifiableError):
        pass  # escalar a búsqueda especializada por OCR

    return _specialized_search(front_data, q, confidence_threshold, db, matching_svc)


@router.post(
    "/specialized",
    response_model=QuickSearchResponse,
    summary="Búsqueda especializada/detallada por OCR (US-004)",
    description=(
        "Búsqueda detallada por OCR (EasyOCR). Úsese cuando la búsqueda rápida "
        "por pHash no identifica la carta. En modo desarrollo, incluir `q` con "
        "el nombre o número de la carta."
    ),
)
async def specialized_search(
    image_front: UploadFile | None = None,
    q: str | None = Form(None, description="Texto de búsqueda (nombre/número) — modo dev"),
    confidence_threshold: float = Form(0.60, ge=0.0, le=1.0, description="Umbral de auto-aceptación"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    matching_svc: ICardMatchingService = Depends(_get_matching_svc),
) -> QuickSearchResponse:
    front_data = await _read_image_or_422(image_front)
    return _specialized_search(front_data, q, confidence_threshold, db, matching_svc)
