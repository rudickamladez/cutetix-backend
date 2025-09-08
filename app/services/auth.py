"""Module for user authentication"""
from jwt import encode
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from passlib.context import CryptContext
from app.schemas.auth import AuthTokenResponse
from app.schemas.settings import settings
import app.services.user as user_service


# https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/#hash-and-verify-the-passwords
pwd_context = CryptContext(
    schemes=["bcrypt"],
    bcrypt__rounds=12,
    deprecated="auto"
)


def verify_password(plaintext_password, hashed_password):
    return pwd_context.verify(plaintext_password, hashed_password)


def get_password_hash(password):
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + \
            timedelta(minutes=settings.access_token_expire_minutes)
    to_encode.update({"exp": expire})
    encoded_jwt = encode(
        payload=to_encode,
        key=settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    return encoded_jwt


def login(username: str, plain_password: str, scopes: list[str] | None, db: Session) -> AuthTokenResponse | None:
    db_user = user_service.get_by_username(username, db=db)
    if not db_user or not verify_password(plain_password, db_user.hashed_password):
        raise Exception("Incorrect credentials")

    if len(list(scopes)) == 0:
        token_scopes = db_user.scopes
    else:
        token_scopes = []
        for scope in scopes:
            if scope in db_user.scopes:
                token_scopes.append(scope)

    access_token = create_access_token(
        data={"sub": db_user.username, "scope": " ".join(token_scopes)}
    )
    return AuthTokenResponse(
        access_token=access_token
    )
