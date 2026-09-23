from typing import Annotated
from fastapi import Path
from pydantic import BaseModel, StringConstraints, field_validator
from uuid import UUID

from app.auth_scopes import (
    SCOPE_MAX_LENGTH,
    ScopeValidationError,
    normalize_event_grantable_scope,
)
from app.schemas.user import UserSearchResult


# The column is shorter than the app's other strings (it is part of a primary
# key); SCOPE_MAX_LENGTH keeps schema, path param and DB in step.
Scope = Annotated[str, StringConstraints(
    strip_whitespace=True,
    min_length=1,
    max_length=SCOPE_MAX_LENGTH,
)]

# Same limits as Scope, for the routes that take the scope in the path.
# Leading/trailing whitespace is rejected outright rather than stripped, so a
# path can never carry a value that differs from its trimmed form only by
# spacing - which would otherwise let two spellings name the same grant.
#
# The anchors are load-bearing, not stylistic: Pydantic matches `pattern` with
# a regex *search*, so an unanchored expression accepts " tickets:read" on the
# strength of its inner substring and the promise above silently goes
# unenforced.
ScopePath = Annotated[
    str,
    Path(
        min_length=1,
        max_length=SCOPE_MAX_LENGTH,
        pattern=r"^\S(.*\S)?$",
    ),
]


class EventUserScopesReplace(BaseModel):
    # Deliberately required (no default): a body that omits `scopes` must 422
    # rather than silently revoke every grant on the event.
    scopes: list[Scope]

    @field_validator("scopes")
    @classmethod
    def check_scope_values(cls, v: list[str]) -> list[str]:
        # Same predicate the service applies, so both scope routes agree.
        # ScopeValidationError is already a ValueError, but re-raising keeps
        # Pydantic from treating the subclass as an unexpected error type.
        try:
            return [normalize_event_grantable_scope(scope) for scope in v]
        except ScopeValidationError as e:
            raise ValueError(str(e)) from e


class EventUserScope(BaseModel):
    event_id: int
    user_uuid: UUID
    scope: Scope

    class Config:
        from_attributes = True


class EventUserScopeWithUser(EventUserScope):
    """A grant plus the grantee, for listing who may work on an event.

    Without the name the response is a table of UUIDs, which the admin UI can
    only print as-is - unhelpful to the event-local organiser it is aimed at,
    who has no way to resolve one (looking a user up needs the global
    `users:read` scope).

    The grantee is `UserSearchResult`, the picker's own projection, rather than
    a look-alike defined here: this list names the very people the picker
    offers, so it must not be able to say more about them than the picker does.
    One class makes that a single decision - a field added for the picker
    cannot silently widen this response, or the reverse. `disabled` earns its
    place because a grant held by a disabled account is a row somebody needs to
    notice and remove.
    """

    user: UserSearchResult

    class Config:
        from_attributes = True
