"""merge parallel heads 0003 and 0004

Revision ID: 0005_merge_heads
Revises: 0003_change_length, 0004_add_user_favorite_events
Create Date: 2026-02-06
"""
from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = "0005_merge_heads"
down_revision: Union[str, Sequence[str], None] = (
    "0003_change_length",
    "0004_add_user_favorite_events",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Merge only; no schema changes."""


def downgrade() -> None:
    """Unmerge only; no schema changes."""

