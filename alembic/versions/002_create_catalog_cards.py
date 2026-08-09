"""create catalog_cards table

Revision ID: 002
Revises: 001
Create Date: 2025-01-01 00:01:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "catalog_cards",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("set_name", sa.String(length=100), nullable=False),
        sa.Column("card_number", sa.String(length=20), nullable=False),
        sa.Column("edition", sa.String(length=100), nullable=False),
        sa.Column("language", sa.String(length=50), nullable=False),
        sa.Column("finish", sa.String(length=50), nullable=False),
        sa.Column(
            "status",
            sa.Enum("pending", "active", "retired", name="cardstatus"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "reference_image_front_url", sa.String(length=500), nullable=True
        ),
        sa.Column(
            "reference_image_back_url", sa.String(length=500), nullable=True
        ),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("approved_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["approved_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "set_name",
            "card_number",
            "edition",
            "language",
            "finish",
            name="uq_card_identity",
        ),
    )


def downgrade() -> None:
    op.drop_table("catalog_cards")
    sa.Enum(name="cardstatus").drop(op.get_bind(), checkfirst=True)
