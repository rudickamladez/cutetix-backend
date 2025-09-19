from pydantic import BaseModel
from uuid import UUID
from datetime import datetime
from app.schemas.user import UserFromDB


class AuthRefreshTokenResponse(BaseModel):
    refresh_token: str
    token_type: str = "bearer"

class AuthTokenResponse(AuthRefreshTokenResponse):
    access_token: str


class AuthTokenData(BaseModel):
    username: str | None = None
    scopes: list[str] = []


class AuthTokenFamilyRevoked(BaseModel):
    uuid: UUID | None = None # if not set will be created by SQLAlchemy
    delete_date: datetime


class AuthTokenFamily(AuthTokenFamilyRevoked):
    last_refresh_token: UUID
    user: UserFromDB | None = None
    user_uuid: UUID
