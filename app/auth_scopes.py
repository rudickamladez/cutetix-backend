from enum import Enum


class AuthScope(str, Enum):
    USERS_READ = "users:read"
    USERS_EDIT = "users:edit"
    EVENTS_READ = "events:read"
    EVENTS_EDIT = "events:edit"
    TOKEN_FAMILY_READ = "token_family:read"
    TICKET_GROUPS_READ = "ticket_groups:read"
    TICKET_GROUPS_EDIT = "ticket_groups:edit"
    TICKETS_READ = "tickets:read"
    TICKETS_EDIT = "tickets:edit"


# OAuth2 scopes need human-readable descriptions for the OpenAPI security UI.
AUTH_SCOPE_DESCRIPTIONS = {
    AuthScope.USERS_READ: "Read information about users.",
    AuthScope.USERS_EDIT: "Edit information about users.",
    AuthScope.EVENTS_READ: "Read information about events.",
    AuthScope.EVENTS_EDIT: "Edit information about events.",
    AuthScope.TOKEN_FAMILY_READ: "Read all token families from DB",
    AuthScope.TICKET_GROUPS_READ: "Read information about ticket groups.",
    AuthScope.TICKET_GROUPS_EDIT: "Edit information about ticket groups.",
    AuthScope.TICKETS_READ: "Read information about tickets.",
    AuthScope.TICKETS_EDIT: "Edit information about tickets.",
}

AUTH_SCOPE_VALUES = frozenset(scope.value for scope in AuthScope)

# Scopes that carry no event meaning, so they can only ever be held globally.
GLOBAL_AUTH_SCOPES = (
    AuthScope.USERS_READ,
    AuthScope.USERS_EDIT,
    AuthScope.TOKEN_FAMILY_READ,
)
GLOBAL_AUTH_SCOPE_VALUES = frozenset(scope.value for scope in GLOBAL_AUTH_SCOPES)

# Every scope is advertised and every scope may be carried by a token. A
# token scope is a *global* grant: it authorizes its holder on every event.
# The per-event alternative lives in event_user_scopes and is checked by
# app.middleware.event_scopes; a request passes on either one.
OAUTH2_SCOPES = {
    scope.value: description
    for scope, description in AUTH_SCOPE_DESCRIPTIONS.items()
}

# Event-local scopes must not include global administration powers such as
# users:edit. Keep the allowlist explicit so new global scopes are not
# automatically grantable for one event.
EVENT_GRANTABLE_SCOPES = (
    AuthScope.EVENTS_READ,
    AuthScope.EVENTS_EDIT,
    AuthScope.TICKET_GROUPS_READ,
    AuthScope.TICKET_GROUPS_EDIT,
    AuthScope.TICKETS_READ,
    AuthScope.TICKETS_EDIT,
)
EVENT_GRANTABLE_SCOPE_VALUES = tuple(
    scope.value for scope in EVENT_GRANTABLE_SCOPES
)
EVENT_GRANTABLE_SCOPE_SET = frozenset(EVENT_GRANTABLE_SCOPE_VALUES)

# Must match the `scope` column in event_user_scopes (model and migration
# 0006) so a value that passes validation can never be truncated by the DB.
# Shorter than the app's other strings because the column is part of a
# composite primary key; the longest real scope is 18 characters.
SCOPE_MAX_LENGTH = 64


class ScopeValidationError(ValueError):
    pass


def normalize_event_grantable_scope(scope: str) -> str:
    scope = scope.strip()
    if len(scope) == 0:
        raise ScopeValidationError("Scope cannot be empty")
    if len(scope) > SCOPE_MAX_LENGTH:
        raise ScopeValidationError(
            f"Scope cannot be longer than {SCOPE_MAX_LENGTH} characters"
        )
    if scope not in AUTH_SCOPE_VALUES:
        raise ScopeValidationError(f"Unknown scope '{scope}'")
    if scope not in EVENT_GRANTABLE_SCOPE_SET:
        raise ScopeValidationError(
            f"Scope '{scope}' cannot be granted for a single event"
        )
    return scope
