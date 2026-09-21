from pydantic import BaseModel, Field
from uuid import UUID


class EventUserScopeBase(BaseModel):
    scope: str = Field(min_length=1, max_length=255)


class EventUserScopeCreate(EventUserScopeBase):
    user_uuid: UUID


class EventUserScopesReplace(BaseModel):
    scopes: list[str] = Field(default_factory=list)


class EventUserScope(EventUserScopeBase):
    event_id: int
    user_uuid: UUID

    class Config:
        from_attributes = True
