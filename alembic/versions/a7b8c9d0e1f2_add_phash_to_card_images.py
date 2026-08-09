"""add_phash_to_card_images

Columna pHash perceptual para la búsqueda rápida (US-004 / Sprint 3,
ver Sprint3/DOC/busqueda-phash-ocr.md §4).

Revision ID: a7b8c9d0e1f2
Revises: f1a2b3c4d5e6
Create Date: 2026-06-13 12:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7b8c9d0e1f2'
down_revision: Union[str, None] = 'f1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'card_images',
        sa.Column('phash', sa.String(length=16), nullable=True),
    )
    op.create_index(
        op.f('ix_card_images_phash'), 'card_images', ['phash'], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_card_images_phash'), table_name='card_images')
    op.drop_column('card_images', 'phash')
