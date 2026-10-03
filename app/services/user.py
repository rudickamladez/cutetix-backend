from uuid import UUID
from sqlalchemy import case, or_
from sqlalchemy.orm import Session

from app import models
from app.schemas.user import UserFromDB, UserInDB, UserRegister, UserSearchResult
from app.schemas.user_favorite_events import UserFavoriteEvent
from app.services.auth import get_password_hash

SEARCH_RESULT_LIMIT = 20


class FavoriteEventNotFoundException(Exception):
    """The user does not have the given event in their favorites."""


def register(user: UserRegister, db: Session) -> UserFromDB:
    if len(user.username) == 0:
        raise Exception("Username cannot be empty")
    user_dict = get_by_username(user.username, db=db)
    if user_dict:
        raise Exception("Username already registered")
    user.hashed_password = get_password_hash(user.plaintext_password)
    user.plaintext_password = None
    user.scopes = []
    user_db = create(user, db=db)
    # TODO: send e-mail to user?
    return user_db


def create(user: UserInDB, db: Session) -> UserFromDB:
    user_dict = get_by_username(user.username, db=db)
    if user_dict:
        raise Exception("Username already registered")
    return models.User.create(
        db_session=db,
        **user.model_dump(
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


def search_users(query: str, db: Session) -> list[UserSearchResult]:
    terms = query.split()
    if not terms:
        return []

    def escape_like(value: str) -> str:
        return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

    filters = [
        or_(
            models.User.username.ilike(f"%{escape_like(term)}%", escape="\\"),
            models.User.email.ilike(f"%{escape_like(term)}%", escape="\\"),
            models.User.full_name.ilike(f"%{escape_like(term)}%", escape="\\"),
        )
        for term in terms
    ]
    exact = escape_like(" ".join(terms))
    return db.query(models.User).filter(*filters).order_by(
        case(
            (models.User.username.ilike(exact, escape="\\"), 0),
            (models.User.email.ilike(exact, escape="\\"), 1),
            (models.User.full_name.ilike(exact, escape="\\"), 2),
            (models.User.username.ilike(f"{exact}%", escape="\\"), 3),
            (models.User.email.ilike(f"{exact}%", escape="\\"), 4),
            (models.User.full_name.ilike(f"{exact}%", escape="\\"), 5),
            else_=6,
        ),
        models.User.username,
    ).limit(SEARCH_RESULT_LIMIT).all()


def update(model: UserInDB, db: Session) -> UserFromDB | None:
    return models.User.update(
        db_session=db, id=model.uuid, **model.model_dump()
    )


def delete(user_id: UUID, db: Session) -> UserFromDB | None:
    return models.User.delete(db_session=db, id=user_id.bytes)


def get_favorite_events(user: UserFromDB, db: Session) -> list[UserFavoriteEvent]:
    return db.query(models.Event).join(
        models.user_favorite_events,
        models.Event.id == models.user_favorite_events.c.event_id
    ).filter(
        models.user_favorite_events.c.user_uuid == user.uuid
    ).order_by(
        models.Event.tickets_sales_end,
        models.Event.id,
    ).all()


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
        raise FavoriteEventNotFoundException(
            "Favorite event not found",
        )
    if ct_db == 1:
        return not not ct_db

    raise Exception(
        "Database integrity error.",
    )
