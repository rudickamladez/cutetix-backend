from pydantic import BaseModel
import uuid


class TokenResponse(BaseModel):
    access_token: str
    token_type: str


class User(BaseModel):
    email: str
    username: str
    full_name: str
    disabled: bool = False


class UserLogin(User):
    plaintext_password: str


class UserRegister(UserLogin):
    hashed_password: str | None = None


class UserFromDB(User):
    uuid: uuid.UUID


class UserInDB(UserFromDB):
    hashed_password: str
