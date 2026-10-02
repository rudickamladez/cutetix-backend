"""add event user scopes

Revision ID: 0006_event_user_scopes
Revises: 0005_merge_heads
Create Date: 2026-09-21
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# Literal on purpose: a migration must keep describing the schema it created
# even after app.auth_scopes.SCOPE_MAX_LENGTH moves on. Keep in step with the
# model while this revision is the head.
SCOPE_LENGTH = 64

revision: str = "0006_event_user_scopes"
down_revision: Union[str, Sequence[str], None] = "0005_merge_heads"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

USER_UUID_INDEX = "ix_event_user_scopes_user_uuid"


def _has_table(name: str) -> bool:
    # A fresh inspector per call: Inspector caches reflection, so one built
    # before create_table would still report the table as missing.
    try:
        return sa.inspect(op.get_bind()).has_table(name)
    except Exception:
        return False


def _has_index(table: str, index_name: str) -> bool:
    if not _has_table(table):
        return False
    try:
        inspector = sa.inspect(op.get_bind())
        return any(ix.get("name") == index_name for ix in inspector.get_indexes(table))
    except Exception:
        return False


def upgrade() -> None:
    if not _has_table("event_user_scopes"):
        # One row represents one concrete event-local scope grant.
        op.create_table(
            "event_user_scopes",
            sa.Column("event_id", sa.Integer(), nullable=False),
            sa.Column("user_uuid", sa.BINARY(length=16), nullable=False),
            # Shorter than the app's other strings on purpose: `scope` is part
            # of the primary key, and a 255-char utf8mb4 column would exceed
            # InnoDB's 767-byte-per-column index limit on the COMPACT row
            # format. Every real scope is under 20 characters.
            sa.Column("scope", sa.String(length=SCOPE_LENGTH), nullable=False),
            sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["user_uuid"], ["users.uuid"], ondelete="CASCADE"),
            # Scope is part of the key to keep grants granular and unique.
            sa.PrimaryKeyConstraint("event_id", "user_uuid", "scope"),
        )

    # The only secondary index worth its keep: get_event_ids_with_scope
    # filters by user_uuid alone, which the primary key (leading with
    # event_id) cannot serve. An index on event_id would duplicate the key's
    # leftmost prefix, and one on `scope` would index six distinct values.
    if not _has_index("event_user_scopes", USER_UUID_INDEX):
        op.create_index(
            USER_UUID_INDEX,
            "event_user_scopes",
            ["user_uuid"],
            unique=False,
        )


def downgrade() -> None:
    if not _has_table("event_user_scopes"):
        return
    # One DROP TABLE is enough - it takes the index and both foreign keys with
    # it. Dropping ix_event_user_scopes_user_uuid first is not merely
    # redundant: MariaDB refuses with errno 1553, because InnoDB needs that
    # index for the user_uuid foreign key while the table still exists.
    op.drop_table("event_user_scopes")
