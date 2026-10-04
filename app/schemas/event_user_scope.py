from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, Field, StringConstraints

from app.auth_scopes import SCOPE_MAX_LENGTH
from app.schemas.user import UserSearchResult


# Keep request validation in step with the database column and normalise input
# before it reaches the service layer.
EventScope = Annotated[str, StringConstraints(
    strip_whitespace=True,
    min_length=1,
    max_length=SCOPE_MAX_LENGTH,
)]


class EventUserScopeBase(BaseModel):
    scope: EventScope


class EventUserScopeCreate(EventUserScopeBase):
    user_uuid: UUID


class EventUserScopesReplace(BaseModel):
    """The complete set of local scopes held by a user for one event."""

    scopes: list[EventScope] = Field(default_factory=list)


class EventUserScope(EventUserScopeBase):
    event_id: int
    user_uuid: UUID
    user: UserSearchResult

    class Config:
        from_attributes = True
