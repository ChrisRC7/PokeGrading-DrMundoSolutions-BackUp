"""create_b2b_tables

Tablas del API B2B de cobertura de catálogo (US-005, ADR-004 §7):
b2b_customers, api_keys, b2b_lookup_audit, b2b_idempotency,
b2b_rate_limit_counters.

Revision ID: f1a2b3c4d5e6
Revises: e269249ec3a9
Create Date: 2026-06-13 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, None] = 'e269249ec3a9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'b2b_customers',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=150), nullable=False),
        sa.Column(
            'status',
            sa.Enum('active', 'suspended', name='b2bcustomerstatus'),
            nullable=False,
        ),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'api_keys',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('customer_id', sa.UUID(), nullable=False),
        sa.Column('key_prefix', sa.String(length=32), nullable=False),
        sa.Column('hashed_secret', sa.String(length=128), nullable=False),
        sa.Column(
            'status',
            sa.Enum('active', 'suspended', 'revoked', 'expired', name='apikeystatus'),
            nullable=False,
        ),
        sa.Column('scopes', sa.String(length=255), nullable=False),
        sa.Column('rate_limit_cards_per_window', sa.Integer(), nullable=False),
        sa.Column('rate_limit_window_seconds', sa.Integer(), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('grace_period_until', sa.DateTime(timezone=True), nullable=True),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['customer_id'], ['b2b_customers.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('key_prefix'),
    )
    op.create_index(op.f('ix_api_keys_customer_id'), 'api_keys', ['customer_id'])
    op.create_index(op.f('ix_api_keys_key_prefix'), 'api_keys', ['key_prefix'])

    op.create_table(
        'b2b_lookup_audit',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('api_key_id', sa.UUID(), nullable=False),
        sa.Column('customer_id', sa.UUID(), nullable=False),
        sa.Column('request_id', sa.String(length=100), nullable=True),
        sa.Column('trace_id', sa.String(length=64), nullable=False),
        sa.Column('card_count', sa.Integer(), nullable=False),
        sa.Column('covered', sa.Integer(), nullable=False),
        sa.Column('multiple', sa.Integer(), nullable=False),
        sa.Column('not_covered', sa.Integer(), nullable=False),
        sa.Column('invalid', sa.Integer(), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['api_key_id'], ['api_keys.id'], ),
        sa.ForeignKeyConstraint(['customer_id'], ['b2b_customers.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_b2b_lookup_audit_api_key_id'), 'b2b_lookup_audit', ['api_key_id']
    )

    op.create_table(
        'b2b_idempotency',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('api_key_id', sa.UUID(), nullable=False),
        sa.Column('request_id', sa.String(length=100), nullable=False),
        sa.Column('request_hash', sa.String(length=64), nullable=False),
        sa.Column('response_json', sa.Text(), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['api_key_id'], ['api_keys.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('api_key_id', 'request_id', name='uq_b2b_idempotency'),
    )

    op.create_table(
        'b2b_rate_limit_counters',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('api_key_id', sa.UUID(), nullable=False),
        sa.Column('window_start', sa.DateTime(timezone=True), nullable=False),
        sa.Column('cards_consumed', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['api_key_id'], ['api_keys.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('api_key_id', 'window_start', name='uq_b2b_rate_window'),
    )
    op.create_index(
        op.f('ix_b2b_rate_limit_counters_api_key_id'),
        'b2b_rate_limit_counters',
        ['api_key_id'],
    )


def downgrade() -> None:
    op.drop_index(
        op.f('ix_b2b_rate_limit_counters_api_key_id'),
        table_name='b2b_rate_limit_counters',
    )
    op.drop_table('b2b_rate_limit_counters')
    op.drop_table('b2b_idempotency')
    op.drop_index(
        op.f('ix_b2b_lookup_audit_api_key_id'), table_name='b2b_lookup_audit'
    )
    op.drop_table('b2b_lookup_audit')
    op.drop_index(op.f('ix_api_keys_key_prefix'), table_name='api_keys')
    op.drop_index(op.f('ix_api_keys_customer_id'), table_name='api_keys')
    op.drop_table('api_keys')
    op.drop_table('b2b_customers')
    sa.Enum(name='apikeystatus').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='b2bcustomerstatus').drop(op.get_bind(), checkfirst=True)
