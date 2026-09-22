from typing import Annotated
from fastapi import Path
from pydantic import BaseModel, StringConstraints, field_validator
from uuid import UUID

from app.auth_scopes import (
    SCOPE_MAX_LENGTH,
    ScopeValidationError,
    normalize_event_grantable_scope,
)


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
ScopePath = Annotated[
    str,
    Path(
        min_length=1,
        max_length=SCOPE_MAX_LENGTH,
        pattern=r"\S(.*\S)?",
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
