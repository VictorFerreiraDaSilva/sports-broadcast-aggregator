"""game tier and gender

Revision ID: 0002_game_tier_and_gender
Revises: 0001_schema_inicial
Create Date: 2026-09-08

Adds the aggregator's own canonical classification of a game's competition
(ADR 0008). Existing rows land on `unknown`/`none`: the classification is
resolved at ingestion (app/core/classification.py), so games still inside the collection
window reclassify themselves on the next run, and everything older is covered
by `python -m app.main reclassify`.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '0002_game_tier_and_gender'
down_revision: Union[str, None] = '0001_schema_inicial'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'game',
        sa.Column('tier', sa.String(length=16), nullable=False, server_default='unknown'),
    )
    op.add_column(
        'game',
        sa.Column('tier_method', sa.String(length=16), nullable=False, server_default='none'),
    )
    op.add_column(
        'game',
        sa.Column('gender', sa.String(length=16), nullable=False, server_default='unknown'),
    )
    op.add_column(
        'game',
        sa.Column('gender_method', sa.String(length=16), nullable=False, server_default='none'),
    )
    op.create_index('ix_game_tier', 'game', ['tier'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_game_tier', table_name='game')
    op.drop_column('game', 'gender_method')
    op.drop_column('game', 'gender')
    op.drop_column('game', 'tier_method')
    op.drop_column('game', 'tier')
