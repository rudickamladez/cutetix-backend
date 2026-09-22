from uuid import UUID

# The test environment (database, JWT keys, SMTP) is configured once, at conftest
# import time - before app.settings builds its cached Settings.

# Importing user first mirrors the application import path and avoids the
# auth/user circular import edge in this legacy module layout.
import app.services.user  # noqa: F401, E402
import app.services.auth as auth_service  # noqa: E402
from app.auth_scopes import AuthScope  # noqa: E402


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


def test_known_token_scopes_keep_global_and_event_permissions():
    """A token may carry event-local scopes.

    The two tiers are an either/or in require_event_scope, so a token is only
    narrowed to what the API does not know - dropping the event scopes here
    would make the per-event grants in event_user_scopes the sole way to reach
    an event, and minting the first grant needs events:edit on the token.
    """
    assert auth_service._known_token_scopes([
        AuthScope.USERS_READ.value,
        AuthScope.EVENTS_EDIT.value,
        AuthScope.TICKETS_READ.value,
        AuthScope.TOKEN_FAMILY_READ.value,
    ]) == [
        AuthScope.USERS_READ.value,
        AuthScope.EVENTS_EDIT.value,
        AuthScope.TICKETS_READ.value,
        AuthScope.TOKEN_FAMILY_READ.value,
    ]


def test_known_token_scopes_drop_values_the_api_does_not_know():
    """A typo in users.scopes must not be re-issued forever by refreshing."""
    assert auth_service._known_token_scopes([
        AuthScope.EVENTS_READ.value,
        "event:read",
        "admin",
    ]) == [AuthScope.EVENTS_READ.value]


def test_known_token_scopes_keep_the_given_order():
    """The scope string is user-visible (and hashed into token families), so
    the filter must not shuffle it."""
    assert auth_service._known_token_scopes([
        AuthScope.EVENTS_EDIT.value,
        AuthScope.TICKETS_READ.value,
        "unknown:scope",
        AuthScope.EVENTS_READ.value,
    ]) == [
        AuthScope.EVENTS_EDIT.value,
        AuthScope.TICKETS_READ.value,
        AuthScope.EVENTS_READ.value,
    ]
