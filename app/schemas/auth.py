from pydantic import BaseModel, Field, field_validator
from uuid import UUID
from datetime import datetime, timezone #, timedelta
from app.schemas.user import UserFromDB
from app.auth_scopes import AuthScopes


class AuthRefreshTokenRequest(BaseModel):
    refresh_token: str
    # TODO: Add params, but check if user is admin?
    # at_expires_delta: timedelta | None = None
    # rt_expires_delta: timedelta | None = None
    requested_scopes: list[str] | None = None


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


class ApiTokenCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255, pattern=r".*\S.*")
    expires_at: datetime
    scopes: list[str] = Field(min_length=1)

    @field_validator("expires_at")
    @classmethod
    def expiration_must_be_in_the_future(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("expires_at must include a timezone")
        if value <= datetime.now(timezone.utc):
            raise ValueError("expires_at must be in the future")
        # DateTime columns in the supported databases do not reliably retain
        # tzinfo; storing UTC keeps their later expiry check unambiguous.
        return value.astimezone(timezone.utc)

    @field_validator("scopes")
    @classmethod
    def scopes_must_be_known_and_unique(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("scopes must not contain duplicates")
        unknown = set(value).difference(AuthScopes.all_values())
        if unknown:
            raise ValueError(f"Unknown scopes: {', '.join(sorted(unknown))}")
        return value


class ApiToken(BaseModel):
    id: UUID
    name: str
    created_at: datetime
    expires_at: datetime
    scopes: list[str]


class ApiTokenCreated(ApiToken):
    token: str
