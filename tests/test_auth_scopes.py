import pytest

from app.auth_scopes import (
    AuthScope,
    EVENT_GRANTABLE_SCOPE_VALUES,
    OAUTH2_SCOPES,
    ScopeValidationError,
    normalize_event_grantable_scope,
)


def test_oauth2_scope_map_covers_every_auth_scope():
    assert set(OAUTH2_SCOPES) == {scope.value for scope in AuthScope}


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
