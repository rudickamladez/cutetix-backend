from uuid import uuid4
from sqlalchemy import DateTime, Integer, String, ForeignKey, Enum, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, relationship, mapped_column
import enum
from app.database import BaseModelMixin


def generate_uuid() -> str:
    return str(uuid4())


class User(BaseModelMixin):
    __tablename__ = "users"

    uuid: Mapped[str] = mapped_column(
        UUID(as_uuid=True).with_variant(String(36), "sqlite"),
        primary_key=True,
        index=True,
        default=generate_uuid,
    )
    username: Mapped[str] = mapped_column(
        String(length=255), unique=True, index=True
    )
    full_name: Mapped[str] = mapped_column(String(length=255), default="")
    email: Mapped[str] = mapped_column(String(length=255), index=True)
    hashed_password: Mapped[str] = mapped_column(String(length=255))
    disabled: Mapped[bool] = mapped_column(default=False)
    scopes: Mapped[list[str]] = mapped_column(JSON, default=["me:read"])


class TicketStatusEnum(enum.Enum):
    new = 0
    confirmed = 1
    paid = 2
    cancelled = 3


class Ticket(BaseModelMixin):
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(length=255))
    firstname: Mapped[str] = mapped_column(String(length=255))
    lastname: Mapped[str] = mapped_column(String(length=255))
    order_date: Mapped[DateTime] = mapped_column(DateTime)
    status: Mapped[TicketStatusEnum] = mapped_column(Enum(TicketStatusEnum))
    description: Mapped[str] = mapped_column(String(length=255), default="")
    # maybe there should be an attribute for ticket cancellation

    # Relationships
    group_id: Mapped[int] = mapped_column(
        ForeignKey("ticket_groups.id", ondelete="CASCADE")
    )
    group = relationship("TicketGroup", back_populates="tickets")


class TicketGroup(BaseModelMixin):
    __tablename__ = "ticket_groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(length=255))
    capacity: Mapped[int] = mapped_column(Integer)

    # Relationships
    event_id: Mapped[int] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"))
    tickets = relationship(
        "Ticket", back_populates="group", passive_deletes=True)
    event = relationship("Event", back_populates="ticket_groups")


class Event(BaseModelMixin):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(length=255))
    tickets_sales_start: Mapped[DateTime] = mapped_column(DateTime)
    tickets_sales_end: Mapped[DateTime] = mapped_column(DateTime)
    smtp_mail_from: Mapped[str] = mapped_column(String(length=255))
    mail_text_new_ticket: Mapped[str] = mapped_column(String(length=1024))
    mail_html_new_ticket: Mapped[str] = mapped_column(String(length=2048))
    mail_text_cancelled_ticket: Mapped[str] = mapped_column(
        String(length=1024))
    mail_html_cancelled_ticket: Mapped[str] = mapped_column(
        String(length=2048))

    # Relationships
    ticket_groups = relationship(
        "TicketGroup", back_populates="event", passive_deletes=True
    )
