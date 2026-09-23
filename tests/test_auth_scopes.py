import pytest

from app.auth_scopes import (
    AUTH_SCOPE_DESCRIPTIONS,
    AUTH_SCOPE_VALUES,
    AuthScope,
    EVENT_GRANTABLE_SCOPE_VALUES,
    GLOBAL_AUTH_SCOPE_VALUES,
    OAUTH2_SCOPES,
    ScopeValidationError,
    normalize_event_grantable_scope,
)


def test_oauth2_scope_map_advertises_every_auth_scope():
    """A token may carry any scope, so the docs must advertise all of them.

    The event-local tier lives in event_user_scopes, but the token half of the
    either/or check still needs the scope to be issuable and documented.
    """
    assert set(OAUTH2_SCOPES) == set(AUTH_SCOPE_VALUES)
    assert GLOBAL_AUTH_SCOPE_VALUES < set(AUTH_SCOPE_VALUES)
    assert AuthScope.EVENTS_READ.value in OAUTH2_SCOPES
    assert AuthScope.TICKETS_EDIT.value in OAUTH2_SCOPES


def test_every_scope_value_has_a_description():
    """A new AuthScope with no description is a silent gap in the docs."""
    assert set(AUTH_SCOPE_DESCRIPTIONS) == set(AUTH_SCOPE_VALUES)
    assert all(OAUTH2_SCOPES.values())


def test_event_grantable_scopes_are_an_explicit_safe_subset():
    assert set(EVENT_GRANTABLE_SCOPE_VALUES) == {
        AuthScope.EVENTS_READ.value,
        AuthScope.EVENTS_EDIT.value,
        AuthScope.TICKET_GROUPS_READ.value,
        AuthScope.TICKET_GROUPS_EDIT.value,
        AuthScope.TICKETS_READ.value,
        AuthScope.TICKETS_EDIT.value,
    }
    assert AuthScope.USERS_EDIT.value not in EVENT_GRANTABLE_SCOPE_VALUES
    assert AuthScope.TOKEN_FAMILY_READ.value not in EVENT_GRANTABLE_SCOPE_VALUES


def test_event_scope_normalization_strips_valid_scope_values():
    assert normalize_event_grantable_scope(" events:edit ") == "events:edit"


@pytest.mark.parametrize("scope", ["", "   ", "not-a-real-scope"])
def test_event_scope_normalization_rejects_unknown_or_empty_scope_values(scope):
    with pytest.raises(ScopeValidationError):
        normalize_event_grantable_scope(scope)


def test_event_scope_normalization_rejects_global_only_scope_values():
    with pytest.raises(ScopeValidationError):
        normalize_event_grantable_scope("users:edit")
