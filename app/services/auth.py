"""Module for user authentication"""
from fastapi import HTTPException
from sqlalchemy.orm import Session
from app import models
from app.database import engine
from app.schemas.auth import UserInDB, UserFromDB, UserRegister
from passlib.context import CryptContext

# Create table if not exists
models.User.__table__.create(bind=engine, checkfirst=True)


# https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/#hash-and-verify-the-passwords
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plaintext_password, hashed_password):
    return pwd_context.verify(plaintext_password, hashed_password)


def get_password_hash(password):
    return pwd_context.hash(password)


def get_user(db, username: str):
    if username in db:
        user_dict = db[username]
        user_dict["username"] = username
        return UserFromDB(**user_dict)

def register(user: UserRegister, db: Session) -> UserFromDB:
    user_dict = get_by_username(user.username, db=db)
    if user_dict:
        raise HTTPException(
            status_code=400, detail="Username already registered"
        )
    user.hashed_password = get_password_hash(user.plaintext_password)
    user.plaintext_password = None
    return create(user, db=db)

def login(username: str, plain_password: str, db: Session) -> UserFromDB | None:
    db_user = get_by_username(username, db=db)
    if not db_user:
        raise HTTPException(
            status_code=400, detail="Incorrect username"
        )

    if not verify_password(plain_password, db_user.hashed_password):
        raise HTTPException(
            status_code=400, detail="Incorrect password"
        )

    user = UserInDB.model_validate(db_user, from_attributes=True)
    return user

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


def get_by_id(user_id: str, db: Session) -> UserFromDB | None:
    return models.User.get_by_id(db_session=db, id=user_id)


def get_by_username(username: str, db: Session) -> UserFromDB | None:
    return (
        db.query(models.User)
        .filter(models.User.username == username)
        .first()
    )


def update(model: UserInDB, db: Session) -> UserFromDB | None:
    return models.User.update(db_session=db, id=model.uuid, **model.model_dump())


def delete(user_id: str, db: Session) -> UserFromDB | None:
    return models.User.delete(db_session=db, id=user_id)
