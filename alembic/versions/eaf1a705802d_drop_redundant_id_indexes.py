"""drop redundant id indexes

Revision ID: eaf1a705802d
Revises: 3c8a1f0e2d94
Create Date: 2026-07-06 19:46:01.132059

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'eaf1a705802d'
down_revision: Union[str, Sequence[str], None] = '3c8a1f0e2d94'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_index('ix_products_id', table_name='products')
    op.drop_index('ix_price_records_id', table_name='price_records')
    op.drop_index('ix_users_id', table_name='users')
    op.drop_index('ix_user_products_id', table_name='user_products')
    op.drop_index('ix_alerts_id', table_name='alerts')


def downgrade() -> None:
    """Downgrade schema."""
    op.create_index(op.f('ix_alerts_id'), 'alerts', ['id'], unique=False)
    op.create_index(op.f('ix_user_products_id'), 'user_products', ['id'], unique=False)
    op.create_index(op.f('ix_users_id'), 'users', ['id'], unique=False)
    op.create_index(op.f('ix_price_records_id'), 'price_records', ['id'], unique=False)
    op.create_index(op.f('ix_products_id'), 'products', ['id'], unique=False)
