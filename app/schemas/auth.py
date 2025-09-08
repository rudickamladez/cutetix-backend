from pydantic import BaseModel
from uuid import UUID


class AuthTokenResponse(BaseModel):
    access_token: str
    token_type: str


class AuthTokenData(BaseModel):
    username: str | None = None
    scopes: list[str] = []


class User(BaseModel):
    email: str
    username: str
    full_name: str
    disabled: bool = False
    scopes: list[str] = []


class UserLogin(User):
    plaintext_password: str


class UserRegister(UserLogin):
    hashed_password: str | None = None


class UserFromDB(User):
    uuid: UUID


class UserInDB(UserFromDB):
    """
    Model for user in database
    I don't want to send hashed_password to the client, but I need it for authentication and registration
    """
    hashed_password: str
