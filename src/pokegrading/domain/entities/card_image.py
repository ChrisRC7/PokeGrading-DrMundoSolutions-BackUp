from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


ALLOWED_CONTENT_TYPES: frozenset[str] = frozenset({"image/jpeg", "image/png"})
MIN_WIDTH_PX: int = 150
MIN_HEIGHT_PX: int = 150
MAX_FILE_SIZE_BYTES: int = 10 * 1024 * 1024  # 10 MB


@dataclass
class CardImage:
    """Imagen de referencia de una carta almacenada como binario en la base de datos.

    Invariantes:
    - `side` must be 'front' or 'back'.
    - `content_type` must be 'image/jpeg' or 'image/png'.
    - `width` and `height` >= 150 px.
    - `file_size` <= 10 MB.
    - `data` contiene el binario completo de la imagen.
    """

    id: UUID
    card_id: UUID
    side: str           # 'front' | 'back'
    content_type: str   # 'image/jpeg' | 'image/png'
    width: int
    height: int
    file_size: int      # bytes
    data: bytes
    uploaded_at: datetime
    uploaded_by: UUID
    phash: str | None = None  # pHash perceptual (hex 16) — solo relevante en 'front'

    def __post_init__(self) -> None:
        # La entidad protege sus invariantes aunque se construya fuera del router.
        if self.side not in ("front", "back"):
            raise ValueError(f"Invalid image side '{self.side}': must be 'front' or 'back'")
        if self.content_type not in ALLOWED_CONTENT_TYPES:
            raise ValueError(
                f"Content type '{self.content_type}' not allowed. "
                "Use image/jpeg or image/png."
            )
        # Requisito mínimo para OCR y para evitar almacenar thumbnails inútiles.
        if self.width < MIN_WIDTH_PX or self.height < MIN_HEIGHT_PX:
            raise ValueError(
                f"Image resolution {self.width}×{self.height} is below the minimum "
                f"{MIN_WIDTH_PX}×{MIN_HEIGHT_PX} px required."
            )
        # Evita que el repositorio persista archivos demasiado grandes en BYTEA.
        if self.file_size > MAX_FILE_SIZE_BYTES:
            raise ValueError(
                f"File size {self.file_size} bytes exceeds the maximum "
                f"{MAX_FILE_SIZE_BYTES // (1024 * 1024)} MB."
            )
