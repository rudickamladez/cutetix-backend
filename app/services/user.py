from uuid import UUID
from sqlalchemy.orm import Session

from app import models
from app.schemas.user import UserFromDB, UserInDB, UserRegister
from app.schemas.user_favorite_events import UserFavoriteEvent
from app.services.auth import get_password_hash


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


def get_favorite_events(user: UserFromDB, db: Session) -> list[UserFavoriteEvent]:
    return db.query(models.Event).join(
        models.user_favorite_events,
        models.Event.id == models.user_favorite_events.c.event_id
    ).filter(
        models.user_favorite_events.c.user_uuid == user.uuid
    ).order_by(models.Event.tickets_sales_end).all()


def add_favorite_event(user: UserFromDB, event_id: int, db: Session) -> UserFavoriteEvent:
    event = db.get(models.Event, event_id)
    if event is None:
        raise ValueError(f"Event with ID '{event_id}' not found")

    # Do not add duplicate
    if event not in user.favorite_events:
        user.favorite_events.append(event)
        db.commit()
    else:
        raise Exception("Favorite event already exists")


def delete_favorite_event(user: UserFromDB, event_id: int, db: Session) -> bool:
    ct_db = db.execute(
        models.user_favorite_events.delete().where(
            models.user_favorite_events.c.user_uuid == user.uuid,
            models.user_favorite_events.c.event_id == event_id
        )
    ).rowcount
    db.commit()
    if ct_db == 0:
        raise Exception(
            "Favorite event not found",
        )
    if ct_db == 1:
        return not not ct_db

    raise Exception(
        "Database integrity error.",
    )
