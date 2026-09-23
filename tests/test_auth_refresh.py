"""POST /auth/refresh must return a usable token, and keep the family's scopes.

The endpoint shipped broken and no test covered it: refresh() handed the
token-family uuid to PyJWT as raw bytes (400 on every call), and behind that
the request model's trailing-comma default narrowed a default-body refresh to
zero scopes.

Self-contained on purpose - no conftest, file-backed SQLite (SQLite's
:memory: database is per-connection, which TestClient's worker thread would
not see), keys generated at import time because app.settings builds its
cached Settings the moment the package is imported.
"""
import os
import tempfile
from datetime import datetime, timezone
from uuid import UUID

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

_TMP = tempfile.mkdtemp(prefix="cutetix-auth-refresh-")
_PRIVATE = os.path.join(_TMP, "jwt-private.pem")
_PUBLIC = os.path.join(_TMP, "jwt-public.pem")

_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
with open(_PRIVATE, "wb") as f:
    f.write(_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ))
with open(_PUBLIC, "wb") as f:
    f.write(_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ))
os.chmod(_PRIVATE, 0o600)

os.environ.update(
    SQLALCHEMY_DATABASE_URL=f"sqlite:///{os.path.join(_TMP, 'test.db')}",
    CORS_ORIGINS='["*"]',
    JWT_SECRET_LOCATION=_PRIVATE,
    JWT_PUBLIC_LOCATION=_PUBLIC,
    SMTP_FROM="tests@example.invalid",
    SMTP_HOST="localhost",
    SMTP_PORT="25",
    SMTP_USER="tests",
    SMTP_PASSWORD="tests",
)

# Importing user first mirrors the application's own import path, which keeps
# the auth/user cycle from tripping over a partially initialized module.
import app.services.user  # noqa: E402,F401
from fastapi.testclient import TestClient  # noqa: E402

from app import database, models  # noqa: E402
from app.schemas.auth import AuthRefreshTokenRequest  # noqa: E402
from app.services import auth as auth_service  # noqa: E402


@pytest.fixture(scope="module")
def client():
    database.BaseModelMixin.metadata.create_all(bind=database.engine)
    from app.main import app
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def db():
    session = database.SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def user(db):
    from uuid import uuid4

    name = f"refresh-{uuid4().hex[:10]}"
    user = models.User(
        username=name,
        full_name=name,
        email=f"{name}@example.invalid",
        hashed_password=auth_service.get_password_hash("hunter2"),
        disabled=False,
        scopes=["events:read", "events:edit", "tickets:read"],
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _login(client, user):
    # /auth/login consumes an OAuth2PasswordRequestForm, not JSON.
    return client.post("/auth/login", data={
        "username": user.username,
        "password": "hunter2",
    })


def _public_key():
    with open(_PUBLIC) as f:
        return f.read()


def _private_key():
    with open(_PRIVATE) as f:
        return f.read()


def _claims(token):
    return jwt.decode(token, _public_key(), algorithms=["RS256"])


class TestRefreshSucceeds:
    def test_default_body_returns_a_new_token_pair(self, client, user):
        login = _login(client, user)
        assert login.status_code == 200, login.text

        response = client.post("/auth/refresh", json={
            "refresh_token": login.json()["refresh_token"],
        })

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["access_token"]
        assert body["refresh_token"] != login.json()["refresh_token"]

    def test_the_access_token_verifies_and_names_its_family(self, client, user):
        """The rtfid claim is what logout and /auth/verify_acces_token parse
        back with UUID(), so it has to be a uuid string - not raw bytes (which
        is what made every refresh 400) and not str() of bytes."""
        login = _login(client, user).json()
        body = client.post("/auth/refresh", json={
            "refresh_token": login["refresh_token"],
        }).json()

        claims = _claims(body["access_token"])
        family = UUID(claims["rtfid"])
        assert claims["sub"] == user.username

        # The claim resolves to the family login created.
        login_claims = _claims(login["access_token"])
        assert UUID(login_claims["rtfid"]) == family

    def test_logout_accepts_a_refreshed_access_token(self, client, user, db):
        """Regression for the claim's *shape*: str(bytes) serializes fine but
        yields "b'\\\\x06...' ", so UUID() inside logout would blow up."""
        login = _login(client, user).json()
        refreshed = client.post("/auth/refresh", json={
            "refresh_token": login["refresh_token"],
        }).json()

        response = client.post("/auth/logout", headers={
            "Authorization": f"Bearer {refreshed['access_token']}",
        })

        assert response.status_code == 204, response.text


class TestRefreshKeepsScopes:
    def test_a_default_body_keeps_the_family_scopes(self, client, user):
        """The bug: `requested_scopes ... = None,` makes the model's default
        the tuple (None,), which is truthy, so an ordinary refresh intersected
        against (None,) and issued a token that could do nothing."""
        login = _login(client, user).json()

        body = client.post("/auth/refresh", json={
            "refresh_token": login["refresh_token"],
        }).json()

        assert sorted(_claims(body["access_token"])["scope"]) == [
            "events:edit", "events:read", "tickets:read",
        ]

    def test_requested_scopes_still_narrow(self, client, user):
        """Narrowing on refresh is the intended behaviour; only the *default*
        was broken."""
        login = _login(client, user).json()

        body = client.post("/auth/refresh", json={
            "refresh_token": login["refresh_token"],
            "requested_scopes": ["events:read"],
        }).json()

        assert _claims(body["access_token"])["scope"] == ["events:read"]

    def test_the_model_default_is_none_not_a_tuple(self):
        """The whole defect is one comma."""
        default = AuthRefreshTokenRequest.model_fields["requested_scopes"].default
        assert default is None


class TestRefreshRejectsBadTokens:
    def test_a_stale_refresh_token_is_rejected(self, client, user):
        """Rotating last_refresh_token must keep the reuse check: the first
        refresh token stops working once a second has been issued."""
        first = _login(client, user).json()["refresh_token"]
        assert client.post(
            "/auth/refresh", json={"refresh_token": first}).status_code == 200

        response = client.post("/auth/refresh", json={"refresh_token": first})

        assert response.status_code == 400
        assert "refreshed" in response.text.lower()

    def test_a_token_naming_an_unknown_family_is_rejected(self, client, user):
        """Well-formed and correctly signed, but no such family exists - so
        the claim has to survive UUID() and then miss the lookup."""
        token = jwt.encode(
            {
                "sub": user.username,
                "rtfid": str(UUID(int=0)),
                "jti": str(UUID(int=0)),
                "exp": datetime(2099, 1, 1, tzinfo=timezone.utc),
            },
            _private_key(), algorithm="RS256",
        )

        response = client.post("/auth/refresh", json={"refresh_token": token})

        assert response.status_code == 400
        assert "family" in response.text.lower()

    def test_a_token_signed_with_another_key_is_rejected(self, client, user):
        from cryptography.hazmat.primitives.asymmetric import rsa

        attacker = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        forged = jwt.encode(
            {
                "sub": user.username,
                "rtfid": str(UUID(int=0)),
                "jti": str(UUID(int=0)),
                "exp": datetime(2099, 1, 1, tzinfo=timezone.utc),
            },
            attacker.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            ),
            algorithm="RS256",
        )

        response = client.post("/auth/refresh", json={"refresh_token": forged})

        assert response.status_code == 400
