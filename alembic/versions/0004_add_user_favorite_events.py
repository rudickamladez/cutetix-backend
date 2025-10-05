"""add user_favorite_events

Revision ID: 42e96ddc41ad
Revises: 0002_users_auth_favs
Create Date: 2025-10-04 21:06:58.411239

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '0004_add_user_favorite_events'
down_revision: Union[str, Sequence[str], None] = '0002_users_auth_favs'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('user_favorite_events',
                    sa.Column('user_uuid', sa.BINARY(
                        length=16), nullable=False),
                    sa.Column('event_id', sa.Integer(), nullable=False),
                    sa.ForeignKeyConstraint(
                        ['event_id'], ['events.id'], ondelete='CASCADE'),
                    sa.ForeignKeyConstraint(
                        ['user_uuid'], ['users.uuid'], ondelete='CASCADE'),
                    sa.PrimaryKeyConstraint('user_uuid', 'event_id')
                    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('user_favorite_events')
