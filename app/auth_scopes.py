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

GLOBAL_AUTH_SCOPES = (
    AuthScope.USERS_READ,
    AuthScope.USERS_EDIT,
    AuthScope.TOKEN_FAMILY_READ,
)
GLOBAL_AUTH_SCOPE_VALUES = frozenset(scope.value for scope in GLOBAL_AUTH_SCOPES)

OAUTH2_SCOPES = {
    scope.value: description
    for scope, description in AUTH_SCOPE_DESCRIPTIONS.items()
    if scope in GLOBAL_AUTH_SCOPES
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


class ScopeValidationError(ValueError):
    pass


def normalize_event_grantable_scope(scope: str) -> str:
    scope = scope.strip()
    if len(scope) == 0:
        raise ScopeValidationError("Scope cannot be empty")
    if scope not in AUTH_SCOPE_VALUES:
        raise ScopeValidationError(f"Unknown scope '{scope}'")
    if scope not in EVENT_GRANTABLE_SCOPE_SET:
        raise ScopeValidationError(
            f"Scope '{scope}' cannot be granted for a single event"
        )
    return scope
