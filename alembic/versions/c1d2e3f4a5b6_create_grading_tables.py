"""create_grading_tables

Tablas de preprocesamiento y calificación (Sprint 4):
submission_regions, card_evaluations, evaluation_subgrades, grading_baselines.
Añade los nuevos valores al enum submissionstatus en PostgreSQL.

Revision ID: c1d2e3f4a5b6
Revises: a7b8c9d0e1f2
Create Date: 2026-06-24 10:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c1d2e3f4a5b6"
down_revision: Union[str, None] = "a7b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Añadir los nuevos estados al enum submissionstatus en PostgreSQL.
    # ALTER TYPE … ADD VALUE requiere estar fuera de una transacción explícita,
    # por lo que usamos execute_if para que solo corra en PostgreSQL.
    conn = op.get_bind()
    if conn.dialect.name == "postgresql":
        conn.execute(sa.text(
            "ALTER TYPE submissionstatus ADD VALUE IF NOT EXISTS 'preprocessed'"
        ))
        conn.execute(sa.text(
            "ALTER TYPE submissionstatus ADD VALUE IF NOT EXISTS 'manual_review'"
        ))
        conn.execute(sa.text(
            "ALTER TYPE submissionstatus ADD VALUE IF NOT EXISTS 'needs_recapture'"
        ))

    op.create_table(
        "submission_regions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("submission_id", sa.UUID(), nullable=False),
        sa.Column("region", sa.String(length=12), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column("phash", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["submission_id"], ["submissions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("submission_id", "region", name="uq_submission_region"),
    )
    op.create_index(
        op.f("ix_submission_regions_submission_id"),
        "submission_regions",
        ["submission_id"],
    )

    op.create_table(
        "card_evaluations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("submission_id", sa.UUID(), nullable=False),
        sa.Column("card_id", sa.UUID(), nullable=True),
        sa.Column("final_grade", sa.Float(), nullable=False),
        sa.Column("uncertainty", sa.Float(), nullable=False),
        sa.Column("algorithm_version", sa.String(length=32), nullable=False),
        sa.Column("baseline_ref", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["submission_id"], ["submissions.id"]),
        sa.ForeignKeyConstraint(["card_id"], ["catalog_cards.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "submission_id", "algorithm_version", name="uq_evaluation_version"
        ),
    )
    op.create_index(
        op.f("ix_card_evaluations_submission_id"),
        "card_evaluations",
        ["submission_id"],
    )

    op.create_table(
        "evaluation_subgrades",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("evaluation_id", sa.UUID(), nullable=False),
        sa.Column("region", sa.String(length=12), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("hamming_distance", sa.Integer(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(
            ["evaluation_id"], ["card_evaluations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("evaluation_id", "region", name="uq_subgrade_region"),
    )
    op.create_index(
        op.f("ix_evaluation_subgrades_evaluation_id"),
        "evaluation_subgrades",
        ["evaluation_id"],
    )

    op.create_table(
        "grading_baselines",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("ref", sa.String(length=64), nullable=False),
        sa.Column("is_calibrated", sa.Boolean(), nullable=False),
        sa.Column("ground_truth_count", sa.Integer(), nullable=False),
        sa.Column("params_json", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ref"),
    )


def downgrade() -> None:
    op.drop_table("grading_baselines")
    op.drop_index(
        op.f("ix_evaluation_subgrades_evaluation_id"),
        table_name="evaluation_subgrades",
    )
    op.drop_table("evaluation_subgrades")
    op.drop_index(
        op.f("ix_card_evaluations_submission_id"),
        table_name="card_evaluations",
    )
    op.drop_table("card_evaluations")
    op.drop_index(
        op.f("ix_submission_regions_submission_id"),
        table_name="submission_regions",
    )
    op.drop_table("submission_regions")
    # No se pueden quitar valores de un enum en PostgreSQL sin recrearlo.
