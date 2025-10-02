from pydantic import BaseModel
from uuid import UUID
from datetime import datetime #, timedelta
from app.schemas.user import UserFromDB


class AuthRefreshTokenRequest(BaseModel):
    refresh_token: str
    # TODO: Add params, but check if user is admin?
    # at_expires_delta: timedelta | None = None
    # rt_expires_delta: timedelta | None = None
    requested_scopes: list[str] | None = None,


class AuthTokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class AuthTokenData(BaseModel):
    username: str | None = None
    scopes: list[str] = []


class AuthTokenFamilyRevoked(BaseModel):
    uuid: UUID | None = None  # if not set will be created by SQLAlchemy
    delete_date: datetime


class AuthTokenFamily(AuthTokenFamilyRevoked):
    last_refresh_token: UUID
    user: UserFromDB | None = None
    token_scopes: list[str]
    user_uuid: UUID
