"""Module for user authentication"""
from sqlalchemy.orm import Session
from app import models
from app.database import engine
from app.schemas.auth import UserInDB, UserFromDB

# Create table if not exists
models.User.__table__.create(bind=engine, checkfirst=True)


def fake_hash_password(password: str):
    return "fakehashed" + password


def get_user(db, username: str):
    if username in db:
        user_dict = db[username]
        user_dict["username"] = username
        return UserFromDB(**user_dict)


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
