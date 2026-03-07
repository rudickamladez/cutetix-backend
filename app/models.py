from uuid_extensions import uuid7
from sqlalchemy import DateTime, Integer, String, ForeignKey, Enum, JSON, BINARY, Table, Column, Boolean, LargeBinary
from sqlalchemy.orm import Mapped, relationship, mapped_column
from enum import Enum as pythonEnum
from app.database import BaseModelMixin


def generate_uuid() -> bytes:
    return uuid7(as_type="bytes")


user_favorite_events = Table(
    "user_favorite_events",
    BaseModelMixin.metadata,
    Column("user_uuid", BINARY(16), ForeignKey(
        "users.uuid", ondelete="CASCADE"), primary_key=True),
    Column("event_id", Integer, ForeignKey(
        "events.id", ondelete="CASCADE"), primary_key=True),
)


class User(BaseModelMixin):
    __tablename__ = "users"

    uuid: Mapped[str] = mapped_column(
        BINARY(16),
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
    scopes: Mapped[list[str]] = mapped_column(JSON, default=list)

    # Relationships
    favorite_events = relationship(
        "Event",
        secondary=user_favorite_events,
        back_populates="users_favorite",
    )
    passkeys = relationship(
        "WebAuthnCredential",
        back_populates="user",
        passive_deletes=True,
    )


class AuthTokenFamily(BaseModelMixin):
    __tablename__ = "auth_token_families"

    uuid: Mapped[str] = mapped_column(
        BINARY(16),
        primary_key=True,
        index=True,
        default=generate_uuid,
    )
    last_refresh_token: Mapped[str] = mapped_column(
        BINARY(16),
        default=generate_uuid,
    )
    delete_date: Mapped[DateTime] = mapped_column(
        DateTime,
        index=True,
    )
    token_scopes: Mapped[list[str]] = mapped_column(JSON, default=list)

    # Foreign key
    user_uuid: Mapped[str] = mapped_column(
        ForeignKey("users.uuid", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user = relationship("User")


class AuthTokenFamilyRevoked(BaseModelMixin):
    __tablename__ = "auth_token_families_revoked"

    uuid: Mapped[str] = mapped_column(
        BINARY(16),
        primary_key=True,
        index=True,
        default=generate_uuid,
    )
    delete_date: Mapped[DateTime] = mapped_column(
        DateTime,
        index=True,
    )


class WebAuthnCredential(BaseModelMixin):
    __tablename__ = "webauthn_credentials"

    uuid: Mapped[str] = mapped_column(
        BINARY(16),
        primary_key=True,
        index=True,
        default=generate_uuid,
    )
    credential_id: Mapped[bytes] = mapped_column(
        LargeBinary,
        unique=True,
        nullable=False,
    )
    public_key: Mapped[bytes] = mapped_column(
        LargeBinary,
        nullable=False,
    )
    sign_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    transports: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    backed_up: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    device_type: Mapped[str] = mapped_column(String(length=64), default="", nullable=False)
    user_uuid: Mapped[str] = mapped_column(
        ForeignKey("users.uuid", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    user = relationship("User", back_populates="passkeys")


class WebAuthnChallenge(BaseModelMixin):
    __tablename__ = "webauthn_challenges"

    uuid: Mapped[str] = mapped_column(
        BINARY(16),
        primary_key=True,
        index=True,
        default=generate_uuid,
    )
    challenge: Mapped[bytes] = mapped_column(
        LargeBinary,
        nullable=False,
    )
    challenge_type: Mapped[str] = mapped_column(
        String(length=32),
        nullable=False,
        index=True,
    )
    expires_at: Mapped[DateTime] = mapped_column(
        DateTime,
        index=True,
        nullable=False,
    )
    used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    username: Mapped[str | None] = mapped_column(String(length=255), nullable=True)
    user_uuid: Mapped[str | None] = mapped_column(
        ForeignKey("users.uuid", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )


class TicketStatusEnum(pythonEnum):
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
    users_favorite = relationship(
        "User",
        secondary=user_favorite_events,
        back_populates="favorite_events",
    )
