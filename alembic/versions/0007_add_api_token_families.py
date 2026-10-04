"""add API token family metadata

Revision ID: 0007_api_token_families
Revises: 0006_event_user_scopes
Create Date: 2026-10-04
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0007_api_token_families"
down_revision: Union[str, Sequence[str], None] = "0006_event_user_scopes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "auth_token_families",
        sa.Column("token_type", sa.String(length=16), nullable=False, server_default="session"),
    )
    op.add_column(
        "auth_token_families",
        sa.Column("name", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "auth_token_families",
        sa.Column(
            "created_at", sa.DateTime(), nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )


def downgrade() -> None:
    op.drop_column("auth_token_families", "created_at")
    op.drop_column("auth_token_families", "name")
    op.drop_column("auth_token_families", "token_type")
