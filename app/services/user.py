from uuid import UUID
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app import models
from app.schemas.user import (
    UserFromDB,
    UserInDB,
    UserRegister,
    UserSearchResult,
)
from app.schemas.user_favorite_events import UserFavoriteEvent
from app.services.passwords import get_password_hash

# A picker is filled by a human typing a few characters; anything past the
# cap is unreadable there anyway, and the cap is what keeps a short query
# from returning a large slice of the table.
SEARCH_LIMIT = 20


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


def _escape_like(value: str) -> str:
    """Quote the LIKE wildcards so a literal ``_`` or ``%`` stays literal."""
    return (
        value.replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )


def search(q: str, db: Session) -> list[UserSearchResult]:
    """Look users up by exact e-mail or username prefix, for a scope-grant picker.

    ``email`` is matched exactly (case-insensitively) and only ``username`` gets
    a prefix match. Exact-only on e-mail is the load-bearing choice: it keeps
    this endpoint from being a way to enumerate addresses. A leading wildcard on
    either column, or any match on the unindexed ``full_name``, would turn the
    query into a table scan and this endpoint into a directory walk.

    Returns a list because e-mail is indexed but not unique, so several accounts
    can share an address.
    """
    return (
        db.query(models.User)
        .filter(
            or_(
                func.lower(models.User.email) == func.lower(q),
                models.User.username.ilike(
                    f"{_escape_like(q)}%",
                    escape="\\",
                ),
            )
        )
        .order_by(models.User.username)
        .limit(SEARCH_LIMIT)
        .all()
    )


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
