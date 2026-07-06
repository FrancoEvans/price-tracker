"""add telegram_id to users and create alerts table

Revision ID: 3c8a1f0e2d94
Revises: 1e06f4da42d7
Create Date: 2026-05-17 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '3c8a1f0e2d94'
down_revision: Union[str, Sequence[str], None] = '1e06f4da42d7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('telegram_id', sa.BigInteger(), nullable=True))
    op.create_unique_constraint('uq_users_telegram_id', 'users', ['telegram_id'])

    op.create_table(
        'alerts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_product_id', sa.Integer(), nullable=False),
        sa.Column('condition', sa.String(length=50), nullable=False),
        sa.Column('threshold', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_product_id'], ['user_products.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_alerts_id'), 'alerts', ['id'], unique=False)
    op.create_index(op.f('ix_alerts_user_product_id'), 'alerts', ['user_product_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_alerts_user_product_id'), table_name='alerts')
    op.drop_index(op.f('ix_alerts_id'), table_name='alerts')
    op.drop_table('alerts')

    op.drop_constraint('uq_users_telegram_id', 'users', type_='unique')
    op.drop_column('users', 'telegram_id')
