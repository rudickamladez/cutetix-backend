from typing import Annotated
from pydantic import BaseModel, Field, StringConstraints
from uuid import UUID


Scope = Annotated[str, StringConstraints(
    strip_whitespace=True,
    min_length=1,
    max_length=255,
)]


class EventUserScopeBase(BaseModel):
    scope: Scope


class EventUserScopeCreate(EventUserScopeBase):
    user_uuid: UUID


class EventUserScopesReplace(BaseModel):
    scopes: list[Scope] = Field()


class EventUserScope(EventUserScopeBase):
    event_id: int
    user_uuid: UUID

    class Config:
        from_attributes = True
