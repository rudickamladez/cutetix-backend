import os
from uuid import UUID


os.environ.setdefault("SQLALCHEMY_DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("CORS_ORIGINS", '["*"]')
os.environ.setdefault("JWT_SECRET_LOCATION", "/tmp/cutetix-test-private.pem")
os.environ.setdefault("JWT_PUBLIC_LOCATION", "/tmp/cutetix-test-public.pem")
os.environ.setdefault("SMTP_FROM", "test@example.com")
os.environ.setdefault("SMTP_HOST", "localhost")
os.environ.setdefault("SMTP_PORT", "25")
os.environ.setdefault("SMTP_USER", "test")
os.environ.setdefault("SMTP_PASSWORD", "test")

# Importing user first mirrors the application import path and avoids the
# auth/user circular import edge in this legacy module layout.
import app.services.user  # noqa: F401, E402
import app.services.auth as auth_service  # noqa: E402


def _capture_token_family_lookup(monkeypatch):
    captured = {}

    def fake_get_list_by_param(**kwargs):
        captured.update(kwargs)
        return ["token-family"]

    monkeypatch.setattr(
        auth_service.AuthTokenFamily,
        "get_list_by_param",
        staticmethod(fake_get_list_by_param),
    )
    return captured


def test_get_refresh_token_family_by_user_id_accepts_uuid(monkeypatch):
    captured = _capture_token_family_lookup(monkeypatch)
    user_uuid = UUID("12345678-1234-5678-1234-567812345678")
    db = object()

    result = auth_service.get_refresh_token_family_by_user_id(user_uuid, db)

    assert result == ["token-family"]
    assert captured["db_session"] is db
    assert captured["param_name"] == "user_uuid"
    assert captured["param_value"] == user_uuid.bytes


def test_get_refresh_token_family_by_user_id_accepts_bytes(monkeypatch):
    captured = _capture_token_family_lookup(monkeypatch)
    user_uuid = UUID("12345678-1234-5678-1234-567812345678")
    db = object()

    result = auth_service.get_refresh_token_family_by_user_id(user_uuid.bytes, db)

    assert result == ["token-family"]
    assert captured["db_session"] is db
    assert captured["param_name"] == "user_uuid"
    assert captured["param_value"] == user_uuid.bytes
