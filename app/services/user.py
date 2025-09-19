from uuid import UUID
from sqlalchemy.orm import Session

from app import models
from app.database import engine
from app.schemas.user import UserFromDB, UserInDB, UserRegister
from app.services.auth import get_password_hash


# Create table if not exists
models.User.__table__.create(bind=engine, checkfirst=True)


def register(user: UserRegister, db: Session) -> UserFromDB:
    user_dict = get_by_username(user.username, db=db)
    if user_dict:
        raise Exception("Username already registered")
    user.hashed_password = get_password_hash(user.plaintext_password)
    user.plaintext_password = None
    user.scopes = []
    user_db = create(user, db=db)
    # TODO: send e-mail to user?
    return user_db


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


def get_by_id(user_id: UUID, db: Session) -> UserFromDB | None:
    return models.User.get_by_id(db_session=db, id=user_id.bytes)


def get_by_username(username: str, db: Session) -> UserFromDB | None:
    return models.User.get_one_by_param(
        db_session=db,
        param_name="username",
        param_value=username
    )


def update(model: UserInDB, db: Session) -> UserFromDB | None:
    return models.User.update(
        db_session=db, id=model.uuid, **model.model_dump()
    )


def delete(user_id: UUID, db: Session) -> bool:
    user = models.User.delete(db_session=db, id=user_id.bytes)
    return not not user
