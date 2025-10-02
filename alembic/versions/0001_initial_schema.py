"""initial schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2025-10-02
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# --- Alembic identifiers ---
revision: str = "0001_initial_schema"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Jméno DB typu pro enum (stabilní mezi migracemi)
TICKET_STATUS_TYPE = "ticketstatusenum"


def upgrade() -> None:
    bind = op.get_bind()

    # 1) Enum pro Ticket.status
    ticket_status = sa.Enum(
        "new", "confirmed", "paid", "cancelled",
        name=TICKET_STATUS_TYPE,
        # na SQLite se použije CHECK constraint; na PG/MySQL nativní typ
        native_enum=(bind.dialect.name != "sqlite"),
        create_constraint=(bind.dialect.name == "sqlite"),
        validate_strings=True,
    )
    ticket_status.create(bind=bind, checkfirst=True)

    # 2) events
    op.create_table(
        "events",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("name", sa.String(length=250), nullable=True),
        sa.Column("tickets_sales_start", sa.DateTime(), nullable=True),
        sa.Column("tickets_sales_end", sa.DateTime(), nullable=True),
        sa.Column("smtp_mail_from", sa.String(length=250), nullable=True),
        sa.Column("mail_text_new_ticket", sa.String(length=1024), nullable=True),
        sa.Column("mail_html_new_ticket", sa.String(length=2048), nullable=True),
        sa.Column("mail_text_cancelled_ticket", sa.String(length=1024), nullable=True),
        sa.Column("mail_html_cancelled_ticket", sa.String(length=2048), nullable=True),
    )

    # 3) ticket_groups
    op.create_table(
        "ticket_groups",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("name", sa.String(length=250), nullable=True),
        sa.Column("capacity", sa.Integer(), nullable=True),
        sa.Column(
            "event_id",
            sa.Integer(),
            sa.ForeignKey("events.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )

    # 4) tickets
    op.create_table(
        "tickets",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("email", sa.String(length=250), nullable=True),
        sa.Column("firstname", sa.String(length=250), nullable=True),
        sa.Column("lastname", sa.String(length=250), nullable=True),
        sa.Column("order_date", sa.DateTime(), nullable=True),
        sa.Column("status", ticket_status, nullable=True),
        sa.Column("description", sa.String(length=250), nullable=True),
        sa.Column(
            "group_id",
            sa.Integer(),
            sa.ForeignKey("ticket_groups.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )

    # Pozn.: index na PK `id` se vytváří implicitně; zvláštní `ix_tickets_id` není potřeba.


def downgrade() -> None:
    # rušit v obráceném pořadí kvůli FK závislostem
    op.drop_table("tickets")
    op.drop_table("ticket_groups")
    op.drop_table("events")

    # enum až nakonec
    bind = op.get_bind()
    ticket_status = sa.Enum(
        "new", "confirmed", "paid", "cancelled",
        name=TICKET_STATUS_TYPE,
        native_enum=(bind.dialect.name != "sqlite"),
        create_constraint=(bind.dialect.name == "sqlite"),
    )
    ticket_status.drop(bind=bind, checkfirst=True)
