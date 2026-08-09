from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, Response, UploadFile, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from pokegrading.api.v3.dependencies import get_current_user, require_admin
from pokegrading.api.v3.schemas.grading import EvaluationResponse, PreprocessResponse, SubgradeSchema
from pokegrading.api.v3.schemas.submission import SubmissionListItem, SubmissionResponse, SubmissionStatusResponse
from pokegrading.application.ports.image_quality_service import IImageQualityService
from pokegrading.application.use_cases.grade_card import GradeCardInput, GradeCardUseCase
from pokegrading.application.use_cases.preprocess_card import PreprocessCardInput, PreprocessCardUseCase
from pokegrading.application.use_cases.submit_card_for_evaluation import (
    SubmitCardForEvaluationUseCase,
    SubmitCardInput,
)
from pokegrading.domain.entities.user import User
from pokegrading.domain.exceptions import (
    BothImagesRequiredError,
    CardNotPreprocessedError,
    FileTooLargeError,
    ImageQualityBelowThresholdError,
    InvalidFileFormatError,
    PolyglotDetectedError,
    SubmissionNotFoundError,
)
from pokegrading.infrastructure.grading.phash_region_grading_service import (
    StructuralRegionGradingService,
)
from pokegrading.infrastructure.matching.phash_image_hash_service import PHashImageHashService
from pokegrading.infrastructure.persistence.database import get_db
from pokegrading.infrastructure.persistence.repositories.evaluation.evaluation_repository import (
    EvaluationRepositoryImpl,
)
from pokegrading.infrastructure.persistence.repositories.grading.grading_baseline_repository import (
    GradingBaselineRepositoryImpl,
)
from pokegrading.infrastructure.persistence.repositories.submission.region_repository import (
    RegionRepositoryImpl,
)
from pokegrading.infrastructure.persistence.repositories.submission_repository import (
    SubmissionRepositoryImpl,
)
from pokegrading.infrastructure.persistence.repositories.card.card_repository import (
    CardRepositoryImpl,
)
from pokegrading.infrastructure.persistence.repositories.card.image_repository import (
    CardImageRepositoryImpl,
)
from pokegrading.infrastructure.preprocessing.pillow_card_preprocessing_service import (
    PillowCardPreprocessingService,
)
from pokegrading.infrastructure.services.pillow_image_quality_service import (
    PillowImageQualityService,
)

router = APIRouter(prefix="/submissions", tags=["submissions"])

_quality_svc = PillowImageQualityService()


def _get_quality_svc() -> IImageQualityService:
    # El evaluador de calidad es stateless, así que se reutiliza como singleton.
    return _quality_svc


@router.get(
    "",
    response_model=list[SubmissionListItem],
    summary="Listar todos los envíos (solo admin)",
)
def list_submissions(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> list[SubmissionListItem]:
    """Retorna todos los envíos ordenados por fecha descendente. Requiere rol admin."""
    # Solo admins necesitan ver el historial completo de evaluaciones.
    submissions = SubmissionRepositoryImpl(db).find_all()
    return [
        SubmissionListItem(
            evaluation_id=s.id,
            user_id=s.user_id,
            status=s.status.value,
            received_at=s.created_at,
            card_id=s.card_id,
            image_quality_score=s.image_quality_score,
            rejection_reason=s.rejection_reason,
        )
        for s in submissions
    ]


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=SubmissionResponse,
    summary="Enviar carta para evaluación (US-003)",
)
async def submit_card(
    image_front: UploadFile | None = None,
    image_back: UploadFile | None = None,
    # card_id viaja en el cuerpo multipart (FormData del frontend). Sin Form(),
    # FastAPI lo leería del query string y siempre llegaría None, rompiendo la
    # vinculación con la carta del catálogo necesaria para calificar (Sprint 4).
    card_id: UUID | None = Form(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    quality_svc: IImageQualityService = Depends(_get_quality_svc),
) -> SubmissionResponse:
    """Acepta las imágenes de frente y reverso de una carta física para evaluación.

    - Requiere token válido (cualquier rol).
    - Formato: multipart/form-data con `image_front` e `image_back`.
    - Validaciones: formato JPEG/PNG, tamaño ≤ 10 MB, calidad de imagen, polyglot.
    """
    # El router solo lee bytes y arma el input; la validación real vive en el use case.
    front_data = await image_front.read() if image_front else None
    back_data = await image_back.read() if image_back else None

    inp = SubmitCardInput(
        user_id=current_user.id,
        image_front_data=front_data,
        image_back_data=back_data,
        card_id=card_id,
    )

    try:
        result = SubmitCardForEvaluationUseCase(
            submission_repo=SubmissionRepositoryImpl(db),
            quality_svc=quality_svc,
        ).execute(inp)
    except BothImagesRequiredError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    except InvalidFileFormatError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    except FileTooLargeError as exc:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=str(exc))
    except PolyglotDetectedError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    except ImageQualityBelowThresholdError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    except SQLAlchemyError:
        # Fallo de persistencia (BD caída, timeout, constraint). Se revierte la
        # transacción para no dejar la sesión en estado inconsistente y se
        # responde 503 en vez de filtrar un 500 genérico con el stack interno.
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No se pudo registrar el envío por un problema de almacenamiento. Intente nuevamente.",
        )

    return SubmissionResponse(
        evaluation_id=result.evaluation_id,
        status=result.status,
        received_at=result.received_at,
        card_id=card_id,
        image_quality_score=result.image_quality_score,
    )


@router.get(
    "/{evaluation_id}",
    response_model=SubmissionStatusResponse,
    summary="Consultar estado de un envío (US-003)",
)
def get_submission(
    evaluation_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SubmissionStatusResponse:
    """Retorna el estado actual del envío identificado por `evaluation_id`."""
    # La consulta de estado no modifica nada; es una lectura pura del agregado.
    submission = SubmissionRepositoryImpl(db).find_by_id(evaluation_id)
    if submission is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Submission '{evaluation_id}' not found.",
        )
    return SubmissionStatusResponse(
        evaluation_id=submission.id,
        status=submission.status.value,
        received_at=submission.created_at,
        card_id=submission.card_id,
        image_quality_score=submission.image_quality_score,
        rejection_reason=submission.rejection_reason,
    )


@router.get(
    "/{evaluation_id}/images/{side}",
    summary="Obtener imagen de un envío (solo admin)",
    response_class=Response,
)
def get_submission_image(
    evaluation_id: UUID,
    side: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Response:
    """Retorna la imagen (front|back) de un envío en binario. Requiere rol admin."""
    # Ruta de inspección administrativa para revisar lo que el submitter subió.
    if side not in ("front", "back"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="side must be 'front' or 'back'")

    submission = SubmissionRepositoryImpl(db).find_by_id(evaluation_id)
    if submission is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Submission not found")

    data = submission.image_front_data if side == "front" else submission.image_back_data

    # Detectar content-type por magic bytes
    # El media type se infiere desde el contenido real y no desde el cliente.
    if data[:3] == b"\xff\xd8\xff":
        media_type = "image/jpeg"
    elif data[:8] == b"\x89PNG\r\n\x1a\n":
        media_type = "image/png"
    else:
        media_type = "application/octet-stream"

    return Response(content=data, media_type=media_type)


# ── Sprint 4: Preprocesar y Calificar carta ───────────────────────────────────

_preprocessing_svc = PillowCardPreprocessingService()
_hash_svc = PHashImageHashService()
# Servicio de calificación sensible al daño local (pHash + diferencia estructural).
# La identificación de carta usa otro camino (búsqueda pHash) y no se ve afectada.
_grading_svc = StructuralRegionGradingService()


@router.post(
    "/{evaluation_id}/preprocess",
    response_model=PreprocessResponse,
    summary="Preprocesar carta de un envío (Sprint 4)",
)
def preprocess_submission(
    evaluation_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PreprocessResponse:
    """Corrige perspectiva, recorta y normaliza la imagen; segmenta en 4 regiones.

    - 200 status=preprocessed: regiones guardadas, listo para calificar.
    - 200 status=manual_review: no se pudo aislar la carta del fondo (AC-P4).
    - 200 status=needs_recapture: distorsión incorregible (AC-P5).
    - 404: submission no encontrada.
    """
    try:
        result = PreprocessCardUseCase(
            submission_repo=SubmissionRepositoryImpl(db),
            region_repo=RegionRepositoryImpl(db),
            preprocessing_svc=_preprocessing_svc,
            hash_svc=_hash_svc,
        ).execute(PreprocessCardInput(submission_id=evaluation_id))
    except SubmissionNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    return PreprocessResponse(
        submission_id=result.submission_id,
        status=result.status,
        regions_ready=result.regions_ready,
        reason=result.reason,
    )


@router.post(
    "/{evaluation_id}/grade",
    response_model=EvaluationResponse,
    summary="Calificar carta de un envío (Sprint 4)",
)
def grade_submission(
    evaluation_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> EvaluationResponse:
    """Calcula el grado estimado por pHash sobre las 4 regiones preprocesadas.

    - 200 status=graded (idempotente): evaluación con grado final y banda.
    - 200 status=manual_review: insumos insuficientes o incoherencia interna.
    - 404: submission no encontrada.
    - 409: submission no está en estado PREPROCESSED.
    """
    try:
        result = GradeCardUseCase(
            submission_repo=SubmissionRepositoryImpl(db),
            region_repo=RegionRepositoryImpl(db),
            evaluation_repo=EvaluationRepositoryImpl(db),
            baseline_repo=GradingBaselineRepositoryImpl(db),
            card_repo=CardRepositoryImpl(db),
            image_repo=CardImageRepositoryImpl(db),
            preprocessing_svc=_preprocessing_svc,
            hash_svc=_hash_svc,
            grading_svc=_grading_svc,
        ).execute(GradeCardInput(submission_id=evaluation_id))
    except SubmissionNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except CardNotPreprocessedError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))

    return EvaluationResponse(
        evaluation_id=result.evaluation_id,
        submission_id=result.submission_id,
        status=result.status,
        final_grade=result.final_grade,
        uncertainty=result.uncertainty,
        subgrades=[
            SubgradeSchema(
                region=sg.region.value,
                score=sg.score,
                hamming_distance=sg.hamming_distance,
                confidence=sg.confidence,
            )
            for sg in result.subgrades
        ],
        algorithm_version=result.algorithm_version,
        baseline_ref=result.baseline_ref,
    )


@router.get(
    "/{evaluation_id}/evaluation",
    response_model=EvaluationResponse,
    summary="Obtener evaluación de un envío (Sprint 4)",
)
def get_evaluation(
    evaluation_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> EvaluationResponse:
    """Retorna la evaluación más reciente del envío (por versión de algoritmo).

    - 200: evaluación existente.
    - 404: no existe evaluación para este envío.
    """
    from pokegrading.application.use_cases.grade_card import GRADING_ALGORITHM_VERSION

    evaluation = EvaluationRepositoryImpl(db).find_by_submission_and_version(
        evaluation_id, GRADING_ALGORITHM_VERSION
    )
    if evaluation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No evaluation found for submission '{evaluation_id}'.",
        )

    return EvaluationResponse(
        evaluation_id=evaluation.id,
        submission_id=evaluation.submission_id,
        status="graded",
        final_grade=evaluation.final_grade,
        uncertainty=evaluation.uncertainty,
        subgrades=[
            SubgradeSchema(
                region=sg.region.value,
                score=sg.score,
                hamming_distance=sg.hamming_distance,
                confidence=sg.confidence,
            )
            for sg in evaluation.subgrades
        ],
        algorithm_version=evaluation.algorithm_version,
        baseline_ref=evaluation.baseline_ref,
    )
