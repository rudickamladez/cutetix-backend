"""add event user scopes

Revision ID: 0006_event_user_scopes
Revises: 0005_merge_heads
Create Date: 2026-09-21
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0006_event_user_scopes"
down_revision: Union[str, Sequence[str], None] = "0005_merge_heads"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(inspector, name: str) -> bool:
    try:
        return inspector.has_table(name)
    except Exception:
        return False


def _has_index(inspector, table: str, index_name: str) -> bool:
    if not _has_table(inspector, table):
        return False
    try:
        return any(ix.get("name") == index_name for ix in inspector.get_indexes(table))
    except Exception:
        return False


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _has_table(inspector, "event_user_scopes"):
        # One row represents one concrete event-local scope grant.
        op.create_table(
            "event_user_scopes",
            sa.Column("event_id", sa.Integer(), nullable=False),
            sa.Column("user_uuid", sa.BINARY(length=16), nullable=False),
            sa.Column("scope", sa.String(length=255), nullable=False),
            sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["user_uuid"], ["users.uuid"], ondelete="CASCADE"),
            # Scope is part of the key to keep grants granular and unique.
            sa.PrimaryKeyConstraint("event_id", "user_uuid", "scope"),
        )

    if not _has_index(inspector, "event_user_scopes", "ix_event_user_scopes_event_id"):
        op.create_index(
            "ix_event_user_scopes_event_id",
            "event_user_scopes",
            ["event_id"],
            unique=False,
        )
    if not _has_index(inspector, "event_user_scopes", "ix_event_user_scopes_user_uuid"):
        op.create_index(
            "ix_event_user_scopes_user_uuid",
            "event_user_scopes",
            ["user_uuid"],
            unique=False,
        )
    if not _has_index(inspector, "event_user_scopes", "ix_event_user_scopes_scope"):
        op.create_index(
            "ix_event_user_scopes_scope",
            "event_user_scopes",
            ["scope"],
            unique=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _has_index(inspector, "event_user_scopes", "ix_event_user_scopes_scope"):
        op.drop_index("ix_event_user_scopes_scope", table_name="event_user_scopes")
    if _has_index(inspector, "event_user_scopes", "ix_event_user_scopes_user_uuid"):
        op.drop_index("ix_event_user_scopes_user_uuid", table_name="event_user_scopes")
    if _has_index(inspector, "event_user_scopes", "ix_event_user_scopes_event_id"):
        op.drop_index("ix_event_user_scopes_event_id", table_name="event_user_scopes")
    if _has_table(inspector, "event_user_scopes"):
        op.drop_table("event_user_scopes")
