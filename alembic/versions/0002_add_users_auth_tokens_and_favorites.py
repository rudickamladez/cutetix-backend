"""add users, auth token tables, and user_favorite_events (M2M)

Revision ID: 0002_add_users_auth_tokens_and_favorites
Revises: 0001_initial_schema
Create Date: 2025-10-02
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# --- Alembic identifiers ---
revision: str = "0002_users_auth_favs"
down_revision: Union[str, Sequence[str], None] = "0001_initial_schema"
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

    # 1) users
    if not _has_table(inspector, "users"):
        op.create_table(
            "users",
            sa.Column("uuid", sa.BINARY(length=16),
                      primary_key=True, nullable=False),
            sa.Column("username", sa.String(length=255), nullable=True),
            sa.Column("full_name", sa.String(length=255), nullable=True),
            sa.Column("email", sa.String(length=255), nullable=True),
            sa.Column("hashed_password", sa.String(length=255), nullable=True),
            sa.Column("disabled", sa.Boolean(), nullable=True),
            sa.Column("scopes", sa.JSON(), nullable=True),
        )
    # místo create_unique_constraint použijeme unikátní index (funguje i na SQLite)
    if not _has_index(inspector, "users", "ix_users_username"):
        op.create_index("ix_users_username", "users",
                        ["username"], unique=True)
    if not _has_index(inspector, "users", "ix_users_email"):
        op.create_index("ix_users_email", "users", ["email"], unique=False)

    # 2) auth_token_families
    if not _has_table(inspector, "auth_token_families"):
        op.create_table(
            "auth_token_families",
            sa.Column("uuid", sa.BINARY(length=16),
                      primary_key=True, nullable=False),
            sa.Column("last_refresh_token", sa.BINARY(
                length=16), nullable=True),
            sa.Column("delete_date", sa.DateTime(), nullable=True),
            sa.Column("token_scopes", sa.JSON(), nullable=True),
            sa.Column(
                "user_uuid",
                sa.BINARY(length=16),
                sa.ForeignKey("users.uuid", ondelete="CASCADE"),
                nullable=False,
            ),
        )
    if not _has_index(inspector, "auth_token_families", "ix_auth_token_families_user_uuid"):
        op.create_index(
            "ix_auth_token_families_user_uuid",
            "auth_token_families",
            ["user_uuid"],
            unique=False,
        )
    if not _has_index(inspector, "auth_token_families", "ix_auth_token_families_delete_date"):
        op.create_index(
            "ix_auth_token_families_delete_date",
            "auth_token_families",
            ["delete_date"],
            unique=False,
        )

    # 3) auth_token_families_revoked
    if not _has_table(inspector, "auth_token_families_revoked"):
        op.create_table(
            "auth_token_families_revoked",
            sa.Column("uuid", sa.BINARY(length=16),
                      primary_key=True, nullable=False),
            sa.Column("delete_date", sa.DateTime(), nullable=True),
        )
    if not _has_index(inspector, "auth_token_families_revoked", "ix_auth_token_families_revoked_delete_date"):
        op.create_index(
            "ix_auth_token_families_revoked_delete_date",
            "auth_token_families_revoked",
            ["delete_date"],
            unique=False,
        )

    # 4) user_favorite_events (M2M)
    if not _has_table(inspector, "user_favorite_events"):
        op.create_table(
            "user_favorite_events",
            sa.Column(
                "user_uuid",
                sa.BINARY(length=16),
                sa.ForeignKey("users.uuid", ondelete="CASCADE"),
                primary_key=True,
                nullable=False,
            ),
            sa.Column(
                "event_id",
                sa.Integer(),
                sa.ForeignKey("events.id", ondelete="CASCADE"),
                primary_key=True,
                nullable=False,
            ),
        )
    if not _has_index(inspector, "user_favorite_events", "ix_user_favorite_events_user_uuid"):
        op.create_index(
            "ix_user_favorite_events_user_uuid",
            "user_favorite_events",
            ["user_uuid"],
            unique=False,
        )
    if not _has_index(inspector, "user_favorite_events", "ix_user_favorite_events_event_id"):
        op.create_index(
            "ix_user_favorite_events_event_id",
            "user_favorite_events",
            ["event_id"],
            unique=False,
        )


def downgrade() -> None:
    # drop indexes before tables (SQLite OK)
    op.drop_index("ix_user_favorite_events_event_id",
                  table_name="user_favorite_events")
    op.drop_index("ix_user_favorite_events_user_uuid",
                  table_name="user_favorite_events")
    op.drop_table("user_favorite_events")

    op.drop_index("ix_auth_token_families_revoked_delete_date",
                  table_name="auth_token_families_revoked")
    op.drop_table("auth_token_families_revoked")

    op.drop_index("ix_auth_token_families_delete_date",
                  table_name="auth_token_families")
    op.drop_index("ix_auth_token_families_user_uuid",
                  table_name="auth_token_families")
    op.drop_table("auth_token_families")

    op.drop_index("ix_users_email", table_name="users")
    op.drop_index("ix_users_username", table_name="users")
    op.drop_table("users")
