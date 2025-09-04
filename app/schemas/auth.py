from pydantic import BaseModel


class AuthTokenResponse(BaseModel):
    access_token: str
    token_type: str


class AuthTokenData(BaseModel):
    username: str | None = None


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
    # There is not used uuid.UUID, becuase there is problem with SQLite queries
    uuid: str


class UserInDB(UserFromDB):
    hashed_password: str
