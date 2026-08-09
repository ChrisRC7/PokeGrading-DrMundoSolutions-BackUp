from __future__ import annotations

import io
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from pokegrading.api.v3.dependencies import get_current_user, require_admin
from pokegrading.api.v3.schemas.catalog import (
    CardDetailResponse,
    CardIdentityResponse,
    CardResponse,
    ImageUploadResponse,
    UpdateCardRequest,
)
from pokegrading.application.use_cases.add_card_to_catalog import (
    AddCardInput,
    AddCardToCatalogUseCase,
)
from pokegrading.domain.entities.card_image import (
    ALLOWED_CONTENT_TYPES,
    MAX_FILE_SIZE_BYTES,
    MIN_HEIGHT_PX,
    MIN_WIDTH_PX,
    CardImage,
)
from pokegrading.domain.entities.user import User
from pokegrading.domain.exceptions import (
    CardAlreadyExistsError,
    InvalidImageError,
    InvalidLanguageError,
    InvalidPokemonTypeError,
    InvalidRarityError,
    UnauthorizedError,
)
from pokegrading.domain.value_objects.card_status import CardStatus
from pokegrading.infrastructure.persistence.database import get_db
from pokegrading.infrastructure.persistence.repositories.card.card_repository import CardRepositoryImpl
from pokegrading.infrastructure.persistence.repositories.card.image_repository import CardImageRepositoryImpl
from pokegrading.infrastructure.persistence.repositories.user.user_repository import UserRepositoryImpl
from pokegrading.infrastructure.matching.phash_image_hash_service import PHashImageHashService
from uuid_extensions import uuid7

router = APIRouter(prefix="/catalog", tags=["catalog"])

_hash_svc = PHashImageHashService()


def _card_to_detail(card, image_repo: CardImageRepositoryImpl | None = None) -> CardDetailResponse:
    card_id = getattr(card, "card_id", None) or getattr(card, "id", None)
    has_front = image_repo.has_front(card_id) if image_repo else getattr(card, "has_image_front", False)
    has_back = image_repo.has_back(card_id) if image_repo else getattr(card, "has_image_back", False)
    return CardDetailResponse(
        card_id=card_id,
        identity=CardIdentityResponse(
            set_name=card.identity.set_name,
            card_number=card.identity.card_number,
            edition=card.identity.edition,
            language=card.identity.language,
            finish=card.identity.finish,
        ),
        name=card.name,
        status=card.status.value,
        version=card.version,
        created_by=card.created_by,
        created_at=card.created_at,
        description=card.description,
        rarity=card.rarity,
        pokemon_type=card.pokemon_type,
        hp=card.hp,
        illustrator=card.illustrator,
        print_year=card.print_year,
        has_image_front=has_front,
        has_image_back=has_back,
        approved_by=getattr(card, "approved_by", None),
        approved_at=getattr(card, "approved_at", None),
    )


async def _read_image(file: UploadFile, *, label: str = "imagen") -> tuple[bytes, str, int, int]:
    """Lee y valida una imagen subida (JPEG/PNG, tamaño, magic bytes, resolución).

    Devuelve (raw_data, content_type, width, height). Lanza HTTPException 422
    si algo no cumple. Reutilizado por `add_card` y `upload_card_image`.
    """
    content_type = file.content_type or ""
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Formato no permitido para '{label}': '{content_type}'. Use image/jpeg o image/png.",
        )

    raw_data = await file.read()
    if len(raw_data) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Imagen '{label}' demasiado grande ({len(raw_data)} bytes). "
                f"Máximo permitido: {MAX_FILE_SIZE_BYTES // (1024 * 1024)} MB."
            ),
        )

    _validate_magic_bytes(raw_data, content_type)

    try:
        from PIL import Image as PILImage

        width, height = PILImage.open(io.BytesIO(raw_data)).size
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"No se pudo leer la imagen '{label}'. Verifique que sea JPEG o PNG válido.",
        )

    if width < MIN_WIDTH_PX or height < MIN_HEIGHT_PX:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Resolución {width}×{height} px insuficiente para '{label}'. "
                f"Mínimo requerido: {MIN_WIDTH_PX}×{MIN_HEIGHT_PX} px."
            ),
        )

    return raw_data, content_type, width, height


def _store_card_image(
    db: Session,
    card_id: UUID,
    side: str,
    raw_data: bytes,
    content_type: str,
    width: int,
    height: int,
    uploaded_by: UUID,
) -> CardImage:
    """Construye y persiste una CardImage calculando su pHash (US-004)."""
    phash = _hash_svc.compute_phash(raw_data) or None
    try:
        card_image = CardImage(
            id=uuid7(),
            card_id=card_id,
            side=side,
            content_type=content_type,
            width=width,
            height=height,
            file_size=len(raw_data),
            data=raw_data,
            phash=phash,
            uploaded_at=datetime.now(tz=timezone.utc),
            uploaded_by=uploaded_by,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return CardImageRepositoryImpl(db).save(card_image)


@router.post(
    "/cards",
    response_model=CardDetailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="US-002 — Agregar carta al catálogo (con imagen de frente)",
    description=(
        "Crea la carta y guarda su imagen de **frente** (obligatoria) como "
        "referencia, calculando el pHash para la búsqueda rápida. La misma "
        "imagen se usa antes en `POST /search/ocr-extract` para pre-rellenar "
        "el formulario. El reverso es opcional. Petición `multipart/form-data`."
    ),
)
async def add_card(
    image_front: UploadFile = File(
        ..., description="Imagen de frente (JPEG/PNG, requerida) — referencia + pHash."
    ),
    set_name: str = Form(...),
    card_number: str = Form(...),
    edition: str = Form(...),
    language: str = Form(...),
    finish: str = Form(...),
    name: str = Form(...),
    description: str | None = Form(None),
    rarity: str | None = Form(None),
    pokemon_type: str | None = Form(None),
    hp: int | None = Form(None),
    illustrator: str | None = Form(None),
    print_year: int | None = Form(None),
    image_back: UploadFile | None = File(None, description="Imagen de reverso (opcional)."),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> CardDetailResponse:
    # 1) Validar imágenes ANTES de crear la carta (no dejar cartas sin imagen).
    front = await _read_image(image_front, label="frente")
    back = await _read_image(image_back, label="reverso") if image_back is not None else None

    # 2) Crear la carta en el catálogo.
    use_case = AddCardToCatalogUseCase(
        card_repo=CardRepositoryImpl(db),
        user_repo=UserRepositoryImpl(db),
    )
    try:
        result = use_case.execute(
            AddCardInput(
                name=name,
                set_name=set_name,
                card_number=card_number,
                edition=edition,
                language=language,
                finish=finish,
                created_by=current_user.id,
                description=description,
                rarity=rarity,
                pokemon_type=pokemon_type,
                hp=hp,
                illustrator=illustrator,
                print_year=print_year,
            )
        )
    except UnauthorizedError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)
        ) from exc
    except (InvalidRarityError, InvalidPokemonTypeError, InvalidLanguageError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except CardAlreadyExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc

    # 3) Guardar imágenes de referencia + pHash usando el id de la carta creada.
    _store_card_image(db, result.card_id, "front", *front, current_user.id)
    if back is not None:
        _store_card_image(db, result.card_id, "back", *back, current_user.id)

    # 4) Detalle con has_image_front=True.
    return _card_to_detail(result, CardImageRepositoryImpl(db))


@router.get(
    "/cards",
    response_model=list[CardDetailResponse],
    summary="Listar todas las cartas del catálogo",
)
def list_cards(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[CardDetailResponse]:
    image_repo = CardImageRepositoryImpl(db)
    cards = CardRepositoryImpl(db).find_all()
    return [_card_to_detail(c, image_repo) for c in cards]


@router.get(
    "/cards/{card_id}",
    response_model=CardDetailResponse,
    summary="Obtener carta por ID",
)
def get_card(
    card_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> CardDetailResponse:
    card = CardRepositoryImpl(db).find_by_id(card_id)
    if card is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Card not found")
    return _card_to_detail(card, CardImageRepositoryImpl(db))


@router.put(
    "/cards/{card_id}",
    response_model=CardDetailResponse,
    summary="Actualizar carta (admin)",
)
def update_card(
    card_id: UUID,
    body: UpdateCardRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> CardDetailResponse:
    repo = CardRepositoryImpl(db)
    card = repo.find_by_id(card_id)
    if card is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Card not found")

    if body.name is not None:
        card.name = body.name
    if body.description is not None:
        card.description = body.description
    if body.status is not None:
        try:
            new_status = CardStatus(body.status)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Estado inválido: '{body.status}'. Valores permitidos: pending, active, retired",
            )
        if new_status == CardStatus.ACTIVE:
            from datetime import datetime, timezone
            try:
                card.approve(current_user.id, datetime.now(timezone.utc))
            except ValueError as exc:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
                ) from exc
        elif new_status == CardStatus.PENDING:
            card.reset_to_pending()
        else:
            card.status = new_status

    saved = repo.save(card)
    return _card_to_detail(saved, CardImageRepositoryImpl(db))


@router.delete(
    "/cards/{card_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="Eliminar carta del catálogo (admin)",
)
def delete_card(
    card_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> None:
    deleted = CardRepositoryImpl(db).delete(card_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Card not found")


@router.post(
    "/cards/{card_id}/images/{side}",
    response_model=ImageUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="US-002 — Subir imagen de referencia (binario, frente o reverso)",
    description=(
        "Acepta imagen en formato JPEG o PNG con resolución mínima 150×150 px "
        "y tamaño máximo 10 MB. La imagen se almacena como binario (BYTEA) "
        "en la tabla `card_images`. "
        "Si ya existe una imagen para ese `side`, se reemplaza."
    ),
)
async def upload_card_image(
    card_id: UUID,
    side: str,
    file: UploadFile,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> ImageUploadResponse:
    if side not in ("front", "back"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="El parámetro 'side' debe ser 'front' o 'back'.",
        )

    card = CardRepositoryImpl(db).find_by_id(card_id)
    if card is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Card not found")

    raw_data, content_type, width, height = await _read_image(file, label=side)
    saved = _store_card_image(
        db, card_id, side, raw_data, content_type, width, height, current_user.id
    )

    return ImageUploadResponse(
        card_id=card_id,
        side=saved.side,
        content_type=saved.content_type,
        width=saved.width,
        height=saved.height,
        file_size=saved.file_size,
        uploaded_at=saved.uploaded_at,
    )


@router.get(
    "/cards/{card_id}/images/{side}",
    summary="Obtener imagen de referencia binaria (frente o reverso)",
    response_class=Response,
    responses={
        200: {"content": {"image/jpeg": {}, "image/png": {}}},
        404: {"description": "Carta o imagen no encontrada"},
    },
)
def get_card_image(
    card_id: UUID,
    side: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> Response:
    if side not in ("front", "back"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="El parámetro 'side' debe ser 'front' o 'back'.",
        )
    image = CardImageRepositoryImpl(db).find_by_card_and_side(card_id, side)
    if image is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No hay imagen de '{side}' para la carta {card_id}.",
        )
    return Response(content=image.data, media_type=image.content_type)


def _validate_magic_bytes(data: bytes, declared_content_type: str) -> None:
    """Verifica que los bytes de la imagen coincidan con el content-type declarado."""
    is_jpeg = data[:3] == b"\xff\xd8\xff"
    is_png = data[:8] == b"\x89PNG\r\n\x1a\n"

    if declared_content_type == "image/jpeg" and not is_jpeg:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="El archivo no es un JPEG válido (magic bytes incorrectos).",
        )
    if declared_content_type == "image/png" and not is_png:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="El archivo no es un PNG válido (magic bytes incorrectos).",
        )
