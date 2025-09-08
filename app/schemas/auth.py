from pydantic import BaseModel


class AuthTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class AuthTokenData(BaseModel):
    username: str | None = None
    scopes: list[str] = []
