"""Shared fixtures: a throwaway SQLite DB, throwaway JWT keys, real tokens.

Everything here runs against the real app and the real auth pipeline -
the point of these tests is that a token's scope claim is honoured end to
end, so stubbing auth out would test nothing.

The environment is configured *at import time*, before any test module can
import app.database: its engine and settings are built during that import, so
a later fixture is too late to influence them. The DB is a file rather than
sqlite :memory:, which is per-connection and would give the TestClient's
worker thread a different database from the fixtures' thread.
"""
import os
import shutil
import sys
import tempfile
from datetime import datetime, timedelta
from uuid import uuid4

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_TMP_DIR = tempfile.mkdtemp(prefix="cutetix-tests-")
_TEST_DB = os.path.join(_TMP_DIR, "test.db")
_PRIVATE_KEY = os.path.join(_TMP_DIR, "test_private.pem")
_PUBLIC_KEY = os.path.join(_TMP_DIR, "test_public.pem")


def _generate_jwt_keys() -> None:
    """A keypair generated per session; never shared with a real deployment."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with open(_PRIVATE_KEY, "wb") as f:
        f.write(key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ))
    with open(_PUBLIC_KEY, "wb") as f:
        # A private key object only hands out private_bytes(); the public half
        # has to come off public_key() first.
        f.write(key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ))
    os.chmod(_PRIVATE_KEY, 0o600)


_generate_jwt_keys()
os.environ.update({
    "SQLALCHEMY_DATABASE_URL": f"sqlite:///{_TEST_DB}",
    "CORS_ORIGINS": '["*"]',
    "JWT_SECRET_LOCATION": _PRIVATE_KEY,
    "JWT_PUBLIC_LOCATION": _PUBLIC_KEY,
    "JWT_ALGORITHM": "RS256",
    "SMTP_FROM": "tests@example.invalid",
    "SMTP_HOST": "localhost",
    "SMTP_PORT": "25",
    "SMTP_USER": "tests",
    "SMTP_PASSWORD": "tests",
})


def pytest_sessionfinish(session, exitstatus):
    shutil.rmtree(_TMP_DIR, ignore_errors=True)


ALL_SCOPES = (
    "users:read",
    "users:edit",
    "events:read",
    "events:edit",
    "token_family:read",
    "ticket_groups:read",
    "ticket_groups:edit",
    "tickets:read",
    "tickets:edit",
)


@pytest.fixture(scope="session")
def _app():
    # Imported here (not at module top): settings and the engine are built at
    # import time, and the environment above has to be in place first.
    from app.database import BaseModelMixin, engine
    import app.models  # noqa: F401  (registers every table on the metadata)
    BaseModelMixin.metadata.create_all(bind=engine)
    from app.main import app
    return app


@pytest.fixture
def client(_app):
    from fastapi.testclient import TestClient
    with TestClient(_app) as test_client:
        yield test_client


@pytest.fixture
def db(_app):
    # Depends on _app so the environment is configured before app.database
    # is imported (its settings and engine are built at import time).
    from app.database import SessionLocal
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def make_user(db):
    """Create a user holding the given *global* (DB column) scopes."""
    def _make(scopes=()):
        from app import models
        name = f"user-{uuid4().hex[:12]}"
        user = models.User(
            username=name,
            full_name=name,
            email=f"{name}@example.invalid",
            hashed_password="not-a-real-hash",
            disabled=False,
            scopes=list(scopes),
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    return _make


@pytest.fixture
def token_for(db):
    """Mint an access token for a user carrying exactly ``scopes``.

    Scope narrowing is reachable in production - /auth/login intersects
    the requested scopes with the user's DB scopes, and /auth/refresh
    narrows the family's scopes further - which is why tests must be able
    to produce a token weaker than the user's DB row.
    """
    from app.services.auth import create_refresh_token, sign_token

    def _token(user, scopes=None):
        carried = list(user.scopes if scopes is None else scopes)
        _, family_uuid = create_refresh_token(user, db, carried)
        return sign_token(
            {"sub": user.username, "rtfid": family_uuid, "scope": carried},
            timedelta(minutes=5),
        )

    return _token


@pytest.fixture
def auth():
    """Authorization header for a raw token."""
    def _auth(token):
        return {"Authorization": f"Bearer {token}"}
    return _auth


@pytest.fixture
def make_event(db):
    """Create an event, and delete it (with its children) afterwards."""
    created = []

    def _make(name="Test event"):
        from app import models
        event = models.Event(
            name=name,
            tickets_sales_start=datetime(2026, 1, 1),
            tickets_sales_end=datetime(2026, 12, 31),
            smtp_mail_from="events@example.invalid",
            mail_text_new_ticket="text",
            mail_html_new_ticket="<p>html</p>",
            mail_text_cancelled_ticket="text",
            mail_html_cancelled_ticket="<p>html</p>",
        )
        db.add(event)
        db.commit()
        db.refresh(event)
        created.append(event.id)
        return event

    yield _make
    from app import models
    # A test that deleted its event leaves the instance stale in the identity
    # map; without expiring first, db.delete() below reads back attributes for
    # a row that is already gone and the DELETE matches nothing.
    db.expire_all()
    for event_id in created:
        event = db.get(models.Event, event_id)
        if event is not None:
            db.delete(event)
    db.commit()


@pytest.fixture
def make_group(db):
    def _make(event, name="Group", capacity=10):
        from app import models
        group = models.TicketGroup(name=name, capacity=capacity, event_id=event.id)
        db.add(group)
        db.commit()
        db.refresh(group)
        return group

    return _make


@pytest.fixture
def make_ticket(db):
    def _make(group, email="attendee@example.invalid"):
        from app import models
        ticket = models.Ticket(
            email=email,
            firstname="Attendee",
            lastname="One",
            order_date=datetime(2026, 1, 1),
            status=models.TicketStatusEnum.new,
            group_id=group.id,
        )
        db.add(ticket)
        db.commit()
        db.refresh(ticket)
        return ticket

    return _make


@pytest.fixture
def uid():
    """Render a user's id for use in a URL.

    ``users.uuid`` is stored as BINARY(16), so the ORM hands back raw
    bytes; interpolating those into a path yields ``b'...'`` and a 422.
    """
    from uuid import UUID

    def _uid(user_or_bytes):
        raw = getattr(user_or_bytes, "uuid", user_or_bytes)
        return str(raw if isinstance(raw, UUID) else UUID(bytes=raw))

    return _uid


@pytest.fixture
def grant(db):
    """Give a user event-local grants directly, bypassing the API."""
    from app.services import event_user_scopes as service

    def _grant(event, user, *scopes):
        service.grant_scopes(
            event_id=event.id,
            user_uuid=user.uuid,
            scopes=list(scopes),
            db=db,
        )

    return _grant
