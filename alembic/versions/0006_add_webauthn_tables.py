"""add webauthn credentials and challenges tables

Revision ID: 0006_add_webauthn_tables
Revises: 0005_merge_heads
Create Date: 2026-02-24
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0006_add_webauthn_tables"
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

    if not _has_table(inspector, "webauthn_credentials"):
        op.create_table(
            "webauthn_credentials",
            sa.Column("uuid", sa.BINARY(length=16), primary_key=True, nullable=False),
            sa.Column("credential_id", sa.LargeBinary(), nullable=False),
            sa.Column("public_key", sa.LargeBinary(), nullable=False),
            sa.Column("sign_count", sa.Integer(), nullable=False),
            sa.Column("transports", sa.JSON(), nullable=False),
            sa.Column("backed_up", sa.Boolean(), nullable=False),
            sa.Column("device_type", sa.String(length=64), nullable=False),
            sa.Column(
                "user_uuid",
                sa.BINARY(length=16),
                sa.ForeignKey("users.uuid", ondelete="CASCADE"),
                nullable=False,
            ),
        )
    if not _has_index(inspector, "webauthn_credentials", "ix_webauthn_credentials_uuid"):
        op.create_index("ix_webauthn_credentials_uuid", "webauthn_credentials", ["uuid"], unique=False)
    if not _has_index(inspector, "webauthn_credentials", "ix_webauthn_credentials_credential_id"):
        op.create_index(
            "ix_webauthn_credentials_credential_id",
            "webauthn_credentials",
            ["credential_id"],
            unique=True,
        )
    if not _has_index(inspector, "webauthn_credentials", "ix_webauthn_credentials_user_uuid"):
        op.create_index(
            "ix_webauthn_credentials_user_uuid",
            "webauthn_credentials",
            ["user_uuid"],
            unique=False,
        )

    if not _has_table(inspector, "webauthn_challenges"):
        op.create_table(
            "webauthn_challenges",
            sa.Column("uuid", sa.BINARY(length=16), primary_key=True, nullable=False),
            sa.Column("challenge", sa.LargeBinary(), nullable=False),
            sa.Column("challenge_type", sa.String(length=32), nullable=False),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
            sa.Column("used", sa.Boolean(), nullable=False),
            sa.Column("username", sa.String(length=255), nullable=True),
            sa.Column(
                "user_uuid",
                sa.BINARY(length=16),
                sa.ForeignKey("users.uuid", ondelete="CASCADE"),
                nullable=True,
            ),
        )
    if not _has_index(inspector, "webauthn_challenges", "ix_webauthn_challenges_uuid"):
        op.create_index("ix_webauthn_challenges_uuid", "webauthn_challenges", ["uuid"], unique=False)
    if not _has_index(inspector, "webauthn_challenges", "ix_webauthn_challenges_challenge_type"):
        op.create_index(
            "ix_webauthn_challenges_challenge_type",
            "webauthn_challenges",
            ["challenge_type"],
            unique=False,
        )
    if not _has_index(inspector, "webauthn_challenges", "ix_webauthn_challenges_expires_at"):
        op.create_index(
            "ix_webauthn_challenges_expires_at",
            "webauthn_challenges",
            ["expires_at"],
            unique=False,
        )
    if not _has_index(inspector, "webauthn_challenges", "ix_webauthn_challenges_used"):
        op.create_index(
            "ix_webauthn_challenges_used",
            "webauthn_challenges",
            ["used"],
            unique=False,
        )
    if not _has_index(inspector, "webauthn_challenges", "ix_webauthn_challenges_user_uuid"):
        op.create_index(
            "ix_webauthn_challenges_user_uuid",
            "webauthn_challenges",
            ["user_uuid"],
            unique=False,
        )


def downgrade() -> None:
    op.drop_index("ix_webauthn_challenges_user_uuid", table_name="webauthn_challenges")
    op.drop_index("ix_webauthn_challenges_used", table_name="webauthn_challenges")
    op.drop_index("ix_webauthn_challenges_expires_at", table_name="webauthn_challenges")
    op.drop_index("ix_webauthn_challenges_challenge_type", table_name="webauthn_challenges")
    op.drop_index("ix_webauthn_challenges_uuid", table_name="webauthn_challenges")
    op.drop_table("webauthn_challenges")

    op.drop_index("ix_webauthn_credentials_user_uuid", table_name="webauthn_credentials")
    op.drop_index("ix_webauthn_credentials_credential_id", table_name="webauthn_credentials")
    op.drop_index("ix_webauthn_credentials_uuid", table_name="webauthn_credentials")
    op.drop_table("webauthn_credentials")
