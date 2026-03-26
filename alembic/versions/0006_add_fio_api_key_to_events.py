"""add fio_api_key to events

Revision ID: 0006_add_fio_api_key_to_events
Revises: 0005_merge_heads
Create Date: 2026-03-26
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0006_add_fio_api_key_to_events"
down_revision: Union[str, Sequence[str], None] = "0005_merge_heads"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "events",
        sa.Column("fio_api_key", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("events", "fio_api_key")
