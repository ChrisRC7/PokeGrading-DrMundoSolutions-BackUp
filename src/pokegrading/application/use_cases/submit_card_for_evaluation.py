from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from uuid_extensions import uuid7

from pokegrading.application.ports.image_quality_service import IImageQualityService
from pokegrading.domain.entities.submission import Submission
from pokegrading.domain.exceptions import (
    BothImagesRequiredError,
    FileTooLargeError,
    ImageQualityBelowThresholdError,
    InvalidFileFormatError,
    PolyglotDetectedError,
)
from pokegrading.domain.repositories.submission_repository import ISubmissionRepository
from pokegrading.domain.value_objects.submission_status import SubmissionStatus

# ── Constantes de validación ──────────────────────────────────────────────────

SUBMISSION_MAX_FILE_SIZE_BYTES: int = 10 * 1024 * 1024   # 10 MB
SUBMISSION_IQS_THRESHOLD: float = 0.60

_JPEG_MAGIC: bytes = b"\xff\xd8\xff"
_PNG_MAGIC: bytes = b"\x89PNG\r\n\x1a\n"

# Firmas de archivos incrustados (políglotas)
_POLYGLOT_SIGNATURES: tuple[bytes, ...] = (
    b"PK\x05\x06",   # ZIP — end of central directory record
    b"%PDF-",         # PDF embebido
    b"\x7fELF",       # Ejecutable ELF (Linux)
    b"MZ",            # Ejecutable PE (Windows) — sólo en posición 0 es válida
)


# ── DTOs ──────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class SubmitCardInput:
    user_id: UUID
    image_front_data: bytes | None
    image_back_data: bytes | None
    card_id: UUID | None = None


@dataclass(frozen=True)
class SubmitCardOutput:
    evaluation_id: UUID
    status: str           # "pending"
    received_at: datetime
    image_quality_score: float  # promedio IQS frente+reverso, [0.0, 1.0]


# ── Helpers privados ──────────────────────────────────────────────────────────

def _detect_content_type(data: bytes) -> str | None:
    # La detección por magic bytes evita confiar en extensiones o headers manipulables.
    if data[:3] == _JPEG_MAGIC:
        return "image/jpeg"
    if data[:8] == _PNG_MAGIC:
        return "image/png"
    return None


def _has_polyglot(data: bytes) -> bool:
    """Detecta firmas de archivos no-imagen en las zonas donde se insertan en ataques reales.

    Los ataques políglotas colocan la firma secundaria:
    - Al inicio del archivo (antes o solapado con el header de imagen).
    - Al final del archivo (ZIP se lee desde el final, por eso JPEG+ZIP es el
      vector más común).

    Buscar en TODO el cuerpo produce falsos positivos: los datos DEFLATE/Huffman
    de imágenes reales pueden contener casualmente cualquier secuencia de 4 bytes.
    """
    # Primeros 256 bytes (encabezado de posibles formatos alternativos)
    head = data[:256]
    # Últimos 4096 bytes (zona de End-of-Central-Directory de ZIP y trailers de PDF)
    tail = data[-4096:] if len(data) > 4096 else data
    zone = head + tail
    return any(sig in zone for sig in _POLYGLOT_SIGNATURES)


def _validate_image(side: str, data: bytes | None) -> None:
    """Valida presencia, formato, tamaño y polyglot de una imagen de envío."""
    # No hay envío válido con una de las dos imágenes ausente.
    if not data:
        raise BothImagesRequiredError(side)

    # Solo se aceptan formatos que el pipeline conoce y puede inspeccionar.
    if _detect_content_type(data) is None:
        raise InvalidFileFormatError(side)

    # Evita almacenar imágenes demasiado pesadas para el flujo operativo.
    if len(data) > SUBMISSION_MAX_FILE_SIZE_BYTES:
        raise FileTooLargeError(side, len(data), SUBMISSION_MAX_FILE_SIZE_BYTES)

    # Defensa extra contra archivos camuflados como imágenes.
    if _has_polyglot(data):
        raise PolyglotDetectedError(side)


# ── Use case ──────────────────────────────────────────────────────────────────

class SubmitCardForEvaluationUseCase:
    """US-003: Enviar carta física para evaluación de grado.

    Flujo de validación (orden determinista):
    1. Ambas imágenes presentes  → BothImagesRequiredError
    2. Formato JPEG/PNG           → InvalidFileFormatError
    3. Tamaño ≤ 10 MB             → FileTooLargeError
    4. Sin datos políglotas       → PolyglotDetectedError
    5. IQS ≥ umbral (0.60)        → ImageQualityBelowThresholdError
    """

    def __init__(
        self,
        submission_repo: ISubmissionRepository,
        quality_svc: IImageQualityService,
    ) -> None:
        self._submission_repo = submission_repo
        self._quality_svc = quality_svc

    def execute(self, inp: SubmitCardInput) -> SubmitCardOutput:
        # Pasos 1–4: valida cada imagen
        # La validación se hace por lado para reportar el error exacto al usuario.
        _validate_image("front", inp.image_front_data)
        _validate_image("back", inp.image_back_data)

        # Paso 5: calidad de imagen
        # El score no es una calificación de la carta, sino una medida de legibilidad.
        front_score = self._quality_svc.evaluate(inp.image_front_data)  # type: ignore[arg-type]
        if front_score < SUBMISSION_IQS_THRESHOLD:
            raise ImageQualityBelowThresholdError("front", front_score, SUBMISSION_IQS_THRESHOLD)

        back_score = self._quality_svc.evaluate(inp.image_back_data)  # type: ignore[arg-type]
        if back_score < SUBMISSION_IQS_THRESHOLD:
            raise ImageQualityBelowThresholdError("back", back_score, SUBMISSION_IQS_THRESHOLD)

        # Se guarda el promedio, porque el envío completo depende de ambas imágenes.
        avg_score = (front_score + back_score) / 2
        now = datetime.now(tz=timezone.utc)

        # La entidad submission encapsula ambos binarios y el metadata de evaluación.
        submission = Submission(
            id=uuid7(),
            user_id=inp.user_id,
            card_id=inp.card_id,
            image_front_data=inp.image_front_data,  # type: ignore[arg-type]
            image_back_data=inp.image_back_data,    # type: ignore[arg-type]
            status=SubmissionStatus.PENDING,
            image_quality_score=avg_score,
            rejection_reason=None,
            created_at=now,
        )

        # La persistencia devuelve la versión final guardada del agregado.
        saved = self._submission_repo.save(submission)

        return SubmitCardOutput(
            evaluation_id=saved.id,
            status=saved.status.value,
            received_at=saved.created_at,
            image_quality_score=avg_score,
        )
