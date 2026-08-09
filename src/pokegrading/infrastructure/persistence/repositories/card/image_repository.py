from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from pokegrading.domain.entities.card_image import CardImage
from pokegrading.domain.repositories.image_repository import ICardImageRepository
from pokegrading.infrastructure.persistence.models import CardImageORM


class CardImageRepositoryImpl(ICardImageRepository):
    """Implementación de ICardImageRepository sobre `card_images` (BYTEA + pHash).

    Garantiza una sola imagen por (card_id, side) mediante un upsert manual
    portable (PostgreSQL y SQLite): si ya existe la fila se actualiza, si no
    se inserta.
    """

    def __init__(self, db: Session) -> None:
        self._db = db

    def save(self, image: CardImage) -> CardImage:
        row = (
            self._db.query(CardImageORM)
            .filter(
                CardImageORM.card_id == image.card_id,
                CardImageORM.side == image.side,
            )
            .first()
        )
        if row is None:
            row = CardImageORM(
                id=image.id,
                card_id=image.card_id,
                side=image.side,
                content_type=image.content_type,
                width=image.width,
                height=image.height,
                file_size=image.file_size,
                data=image.data,
                phash=image.phash,
                uploaded_at=image.uploaded_at,
                uploaded_by=image.uploaded_by,
            )
            self._db.add(row)
        else:
            row.content_type = image.content_type
            row.width = image.width
            row.height = image.height
            row.file_size = image.file_size
            row.data = image.data
            row.phash = image.phash
            row.uploaded_at = image.uploaded_at
            row.uploaded_by = image.uploaded_by
        self._db.commit()
        return image

    def find_by_card_and_side(self, card_id: UUID, side: str) -> CardImage | None:
        row = (
            self._db.query(CardImageORM)
            .filter(CardImageORM.card_id == card_id, CardImageORM.side == side)
            .first()
        )
        return self._to_entity(row) if row else None

    def has_front(self, card_id: UUID) -> bool:
        return (
            self._db.query(CardImageORM.id)
            .filter(CardImageORM.card_id == card_id, CardImageORM.side == "front")
            .first()
        ) is not None

    def has_back(self, card_id: UUID) -> bool:
        return (
            self._db.query(CardImageORM.id)
            .filter(CardImageORM.card_id == card_id, CardImageORM.side == "back")
            .first()
        ) is not None

    @staticmethod
    def _to_entity(row: CardImageORM) -> CardImage:
        return CardImage(
            id=row.id,
            card_id=row.card_id,
            side=row.side,
            content_type=row.content_type,
            width=row.width,
            height=row.height,
            file_size=row.file_size,
            data=row.data,
            phash=getattr(row, "phash", None),
            uploaded_at=row.uploaded_at,
            uploaded_by=row.uploaded_by,
        )
