"""Unit tests for the event-tenancy checks in app.middleware.event_scopes.

The HTTP-level behaviour is covered by tests/test_event_scopes_authz.py; these
exercise the helpers directly, including the token half of the either/or rule,
which needs no event rows at all.
"""
from datetime import datetime
from uuid import UUID

import pytest
from fastapi import HTTPException, status
from sqlalchemy import create_engine, event as sqlalchemy_event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models
from app.auth_scopes import AuthScope
from app.database import BaseModelMixin
from app.middleware.event_scopes import (
    check_event_scope_or_403,
    check_scope_on_new_owner_or_403,
    get_event_ids_with_scope,
    resolve_event_id,
)


@pytest.fixture()
def db_session():
    """A private in-memory DB, so fixed ids below cannot clash with other tests.

    StaticPool keeps every checkout on one connection: sqlite :memory: is
    per-connection, and TestClient would otherwise see an empty database.
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # Mirrors app/database.py - SQLite ignores FKs (and so cascades) unless
    # every connection asks for them.
    @sqlalchemy_event.listens_for(engine, "connect")
    def _enforce_foreign_keys(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    BaseModelMixin.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine, expire_on_commit=False)()
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


def _current_user(user_uuid: UUID, token_scopes=()) -> models.User:
    """Stand-in for what the auth dependency hands the routes.

    `get_current_user` attaches the verified token's scopes to the user object
    it returns, and the authorization helpers read exactly that - never the
    `scopes` column, which login may have narrowed. That assignment only works
    on the flexible ORM instance the dependency actually passes along (a
    pydantic UserFromDB rejects unknown attributes), so use one here.
    """
    user = _user(user_uuid)
    user.token_scopes = list(token_scopes)
    return user


USER_UUID = UUID("12345678-1234-5678-1234-567812345678")


def test_local_grant_authorizes_without_any_token_scope(db_session):
    db_session.add_all([
        _event(1),
        _user(USER_UUID),
        models.EventUserScope(
            event_id=1,
            user_uuid=USER_UUID.bytes,
            scope=AuthScope.EVENTS_EDIT.value,
        ),
    ])
    db_session.commit()

    check_event_scope_or_403(_current_user(USER_UUID), 1, AuthScope.EVENTS_EDIT, db_session)


def test_global_token_scope_authorizes_without_any_grant(db_session):
    """The global half of the rule works against an empty event_user_scopes."""
    db_session.add_all([_event(1), _user(USER_UUID)])
    db_session.commit()

    check_event_scope_or_403(
        _current_user(USER_UUID, token_scopes=[AuthScope.EVENTS_EDIT.value]),
        1,
        AuthScope.EVENTS_EDIT,
        db_session,
    )


def test_missing_grant_and_missing_token_scope_is_403(db_session):
    db_session.add_all([_event(1), _user(USER_UUID)])
    db_session.commit()

    with pytest.raises(HTTPException) as exc:
        check_event_scope_or_403(_current_user(USER_UUID), 1, AuthScope.EVENTS_EDIT, db_session)

    assert exc.value.status_code == status.HTTP_403_FORBIDDEN


def test_a_grant_on_another_event_does_not_help(db_session):
    db_session.add_all([
        _event(1),
        _event(2),
        _user(USER_UUID),
        models.EventUserScope(
            event_id=1,
            user_uuid=USER_UUID.bytes,
            scope=AuthScope.EVENTS_EDIT.value,
        ),
    ])
    db_session.commit()

    with pytest.raises(HTTPException) as exc:
        check_event_scope_or_403(_current_user(USER_UUID), 2, AuthScope.EVENTS_EDIT, db_session)

    assert exc.value.status_code == status.HTTP_403_FORBIDDEN


def test_reparenting_requires_the_destination_event(db_session):
    db_session.add_all([_event(1), _event(2), _user(USER_UUID)])
    db_session.commit()
    user = _current_user(USER_UUID)

    # An unchanged parent is a no-op even with no grants at all.
    check_scope_on_new_owner_or_403(user, 1, 1, AuthScope.EVENTS_EDIT, db_session)

    with pytest.raises(HTTPException) as exc:
        check_scope_on_new_owner_or_403(user, 1, 2, AuthScope.EVENTS_EDIT, db_session)

    assert exc.value.status_code == status.HTTP_403_FORBIDDEN


def test_resolve_event_id_maps_resources_to_their_event(db_session):
    db_session.add_all([
        _event(1),
        _user(USER_UUID),
        models.TicketGroup(id=1, name="Group", capacity=10, event_id=1),
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
    ])
    db_session.commit()

    assert resolve_event_id("event", 1, db_session) == 1
    assert resolve_event_id("ticket_group", 1, db_session) == 1
    assert resolve_event_id("ticket", 1, db_session) == 1


def test_resolve_event_id_returns_none_for_unknown_resources(db_session):
    assert resolve_event_id("event", 404, db_session) is None
    assert resolve_event_id("ticket_group", 404, db_session) is None
    assert resolve_event_id("ticket", 404, db_session) is None


def test_get_event_ids_with_scope_returns_only_matching_event_ids(db_session):
    db_session.add_all([
        _event(1),
        _event(2),
        _user(USER_UUID),
        models.EventUserScope(
            event_id=1,
            user_uuid=USER_UUID.bytes,
            scope=AuthScope.TICKETS_EDIT.value,
        ),
        models.EventUserScope(
            event_id=2,
            user_uuid=USER_UUID.bytes,
            scope=AuthScope.TICKETS_READ.value,
        ),
    ])
    db_session.commit()

    assert get_event_ids_with_scope(
        current_user=_current_user(USER_UUID),
        scope=AuthScope.TICKETS_READ,
        db=db_session,
    ) == [2]


def test_the_database_scopes_column_is_never_the_authority(db_session):
    """`users.scopes` is a registration record, not the request's permissions:
    login and refresh can both narrow it. Only the token and the grants may
    authorize, so a user object carrying no token scopes must fail closed."""
    from app.middleware.event_scopes import token_scopes_of

    db_session.add_all([
        _event(1),
        models.User(
            uuid=USER_UUID.bytes,
            username=f"user-{USER_UUID}",
            full_name="Test User",
            email="test@example.com",
            hashed_password="hash",
            disabled=False,
            # Strongest possible DB scopes - irrelevant to the check.
            scopes=[scope.value for scope in AuthScope],
        ),
    ])
    db_session.commit()

    assert token_scopes_of(_current_user(USER_UUID, token_scopes=[])) == []
    with pytest.raises(HTTPException) as exc:
        check_event_scope_or_403(_current_user(USER_UUID, token_scopes=[]),
                                 1, AuthScope.EVENTS_EDIT, db_session)
    assert exc.value.status_code == status.HTTP_403_FORBIDDEN


def test_a_user_object_carrying_no_token_scopes_fails_closed():
    """token_scopes_of must not fall through to the DB column when the
    attribute is missing entirely (a bare ORM instance, as unit tests build)."""
    from app.middleware.event_scopes import token_scopes_of

    assert token_scopes_of(_user(USER_UUID)) == []


def test_global_scope_means_no_event_filter(db_session):
    """None means "do not filter" - a global holder must not be narrowed to
    the handful of events they happen to hold rows on."""
    db_session.add_all([_event(1), _user(USER_UUID)])
    db_session.commit()

    assert get_event_ids_with_scope(
        current_user=_current_user(USER_UUID, token_scopes=[AuthScope.TICKETS_READ.value]),
        scope=AuthScope.TICKETS_READ,
        db=db_session,
    ) is None
