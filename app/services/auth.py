"""Module for user authentication"""
import os
import jwt
import uuid
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from app import models
from app.database import engine
from app.schemas.auth import UserInDB, UserFromDB, UserRegister, AuthTokenResponse
from passlib.context import CryptContext


SECRET_KEY = os.getenv("JWT_SECRET")
ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(
    os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30")
)

# Create table if not exists
models.User.__table__.create(bind=engine, checkfirst=True)


# https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/#hash-and-verify-the-passwords
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plaintext_password, hashed_password):
    return pwd_context.verify(plaintext_password, hashed_password)


def get_password_hash(password):
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + \
            timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(
        payload=to_encode, key=SECRET_KEY, algorithm=ALGORITHM
    )
    return encoded_jwt


def get_user(db, username: str):
    if username in db:
        user_dict = db[username]
        user_dict["username"] = username
        return UserFromDB(**user_dict)


def register(user: UserRegister, db: Session) -> UserFromDB:
    user_dict = get_by_username(user.username, db=db)
    if user_dict:
        raise Exception("Username already registered")
    user.hashed_password = get_password_hash(user.plaintext_password)
    user.plaintext_password = None
    user_db = create(user, db=db)
    # TODO: send e-mail to user?
    return user_db


def login(username: str, plain_password: str, db: Session) -> AuthTokenResponse | None:
    db_user = get_by_username(username, db=db)
    if not db_user or not verify_password(plain_password, db_user.hashed_password):
        raise Exception("Incorrect credentials")

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": db_user.username}, expires_delta=access_token_expires
    )
    return AuthTokenResponse(access_token=access_token, token_type="bearer")


def create(model: UserInDB, db: Session) -> UserFromDB:
    return models.User.create(
        db_session=db,
        **model.model_dump(
            exclude_unset=True,
            exclude_none=True,
        )
    )


def get_all(db: Session) -> list[UserFromDB]:
    return models.User.get_all(db_session=db)


def get_by_id(user_id: uuid.UUID, db: Session) -> UserFromDB | None:
    return models.User.get_by_id(db_session=db, id=user_id)


def get_by_username(username: str, db: Session) -> UserFromDB | None:
    return (
        db.query(models.User)
        .filter(models.User.username == username)
        .first()
    )


def update(model: UserInDB, db: Session) -> UserFromDB | None:
    return models.User.update(
        db_session=db, id=model.uuid, **model.model_dump()
    )


def delete(user_id: str, db: Session) -> UserFromDB | None:
    return models.User.delete(db_session=db, id=user_id)
