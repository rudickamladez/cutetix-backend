import os
from datetime import datetime
from uuid import UUID

import pytest
from fastapi import HTTPException, status
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("SQLALCHEMY_DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("CORS_ORIGINS", '["*"]')
os.environ.setdefault("JWT_SECRET_LOCATION", "/tmp/cutetix-test-private.pem")
os.environ.setdefault("JWT_PUBLIC_LOCATION", "/tmp/cutetix-test-public.pem")
os.environ.setdefault("SMTP_FROM", "test@example.com")
os.environ.setdefault("SMTP_HOST", "localhost")
os.environ.setdefault("SMTP_PORT", "25")
os.environ.setdefault("SMTP_USER", "test")
os.environ.setdefault("SMTP_PASSWORD", "test")

from app import models  # noqa: E402
from app.auth_scopes import AuthScope  # noqa: E402
from app.database import BaseModelMixin  # noqa: E402
from app.middleware.auth import (  # noqa: E402
    get_event_ids_with_scope,
    require_event_scope,
    require_event_scope_for_ticket,
)
from app.schemas.user import UserFromDB  # noqa: E402


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:")
    BaseModelMixin.metadata.create_all(bind=engine)
    testing_session = sessionmaker(bind=engine, expire_on_commit=False)
    db = testing_session()
    try:
        yield db
    finally:
        db.close()
        BaseModelMixin.metadata.drop_all(bind=engine)


def _event(event_id: int) -> models.Event:
    timestamp = datetime(2026, 1, 1)
    return models.Event(
        id=event_id,
        name=f"Event {event_id}",
        tickets_sales_start=timestamp,
        tickets_sales_end=timestamp,
        smtp_mail_from="tickets@example.com",
        mail_text_new_ticket="new ticket",
        mail_html_new_ticket="<p>new ticket</p>",
        mail_text_cancelled_ticket="cancelled ticket",
        mail_html_cancelled_ticket="<p>cancelled ticket</p>",
    )


def _user(user_uuid: UUID) -> models.User:
    return models.User(
        uuid=user_uuid.bytes,
        username=f"user-{user_uuid}",
        full_name="Test User",
        email="test@example.com",
        hashed_password="hash",
        disabled=False,
        scopes=[],
    )


def _current_user(user_uuid: UUID) -> UserFromDB:
    return UserFromDB(
        uuid=user_uuid,
        username=f"user-{user_uuid}",
        full_name="Test User",
        email="test@example.com",
        disabled=False,
        scopes=[],
        favorite_events=[],
    )


def test_require_event_scope_allows_user_with_event_local_scope(db_session):
    user_uuid = UUID("12345678-1234-5678-1234-567812345678")
    db_session.add_all([
        _event(1),
        _user(user_uuid),
        models.EventUserScope(
            event_id=1,
            user_uuid=user_uuid.bytes,
            scope=AuthScope.EVENTS_EDIT.value,
        ),
    ])
    db_session.commit()

    require_event_scope(
        event_id=1,
        current_user=_current_user(user_uuid),
        scope=AuthScope.EVENTS_EDIT,
        db=db_session,
    )


def test_require_event_scope_rejects_missing_event_local_scope(db_session):
    user_uuid = UUID("12345678-1234-5678-1234-567812345678")
    db_session.add_all([_event(1), _user(user_uuid)])
    db_session.commit()

    with pytest.raises(HTTPException) as exc:
        require_event_scope(
            event_id=1,
            current_user=_current_user(user_uuid),
            scope=AuthScope.EVENTS_EDIT,
            db=db_session,
        )

    assert exc.value.status_code == status.HTTP_403_FORBIDDEN


def test_require_event_scope_returns_404_for_missing_event(db_session):
    user_uuid = UUID("12345678-1234-5678-1234-567812345678")
    db_session.add(_user(user_uuid))
    db_session.commit()

    with pytest.raises(HTTPException) as exc:
        require_event_scope(
            event_id=404,
            current_user=_current_user(user_uuid),
            scope=AuthScope.EVENTS_EDIT,
            db=db_session,
        )

    assert exc.value.status_code == status.HTTP_404_NOT_FOUND


def test_require_event_scope_for_ticket_uses_ticket_group_event(db_session):
    user_uuid = UUID("12345678-1234-5678-1234-567812345678")
    db_session.add_all([
        _event(1),
        _user(user_uuid),
        models.TicketGroup(
            id=1,
            name="Group",
            capacity=10,
            event_id=1,
        ),
        models.Ticket(
            id=1,
            email="buyer@example.com",
            firstname="Buyer",
            lastname="Example",
            order_date=datetime(2026, 1, 1),
            status=models.TicketStatusEnum.new,
            description="",
            group_id=1,
        ),
        models.EventUserScope(
            event_id=1,
            user_uuid=user_uuid.bytes,
            scope=AuthScope.TICKETS_READ.value,
        ),
    ])
    db_session.commit()

    ticket = require_event_scope_for_ticket(
        ticket_id=1,
        current_user=_current_user(user_uuid),
        scope=AuthScope.TICKETS_READ,
        db=db_session,
    )

    assert ticket.id == 1


def test_get_event_ids_with_scope_returns_only_matching_event_ids(db_session):
    user_uuid = UUID("12345678-1234-5678-1234-567812345678")
    db_session.add_all([
        _event(1),
        _event(2),
        _user(user_uuid),
        models.EventUserScope(
            event_id=1,
            user_uuid=user_uuid.bytes,
            scope=AuthScope.TICKETS_EDIT.value,
        ),
        models.EventUserScope(
            event_id=2,
            user_uuid=user_uuid.bytes,
            scope=AuthScope.TICKETS_READ.value,
        ),
    ])
    db_session.commit()

    assert get_event_ids_with_scope(
        current_user=_current_user(user_uuid),
        scope=AuthScope.TICKETS_READ,
        db=db_session,
    ) == [2]
