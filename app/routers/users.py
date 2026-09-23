from fastapi import APIRouter, Depends, HTTPException, Query, Response, Security, status
from sqlalchemy.orm import Session
from typing import Annotated
from uuid import UUID
from app.auth_scopes import AuthScope
from app.middleware.auth import get_current_active_user
from app.middleware.event_scopes import get_event_ids_with_scope
from app.schemas.user import UserFromDB, UserLogin, UserRegister, UserSearchResult
from app.schemas.event import Event
from app.database import get_db
from app.services.passwords import get_password_hash
import app.services.user as user_service


router = APIRouter(
    prefix="/users",
    tags=["users"],
    responses={
        status.HTTP_400_BAD_REQUEST: {"description": "Bad request"},
        status.HTTP_404_NOT_FOUND: {"description": "Not found"},
    },
)


def check_user_found(user: UserFromDB) -> UserFromDB:
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    return user


@router.post(
    "/",
    dependencies=[Security(
        get_current_active_user,
        scopes=[AuthScope.USERS_EDIT.value]
    )],
    status_code=status.HTTP_201_CREATED,
    description="Create new user. Requires `users:edit` scope."
)
async def create_user(user: UserLogin, db: Session = Depends(get_db)):
    try:
        user = user.model_dump()
        user["hashed_password"] = get_password_hash(user["plaintext_password"])
        user = UserRegister.model_validate(user)
        if user.favorite_events is None:
            user.favorite_events = []
        user_service.create(
            user=user,
            db=db
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get(
    "/",
    response_model=list[UserFromDB],
    dependencies=[Security(
        get_current_active_user,
        scopes=[AuthScope.USERS_READ.value]
    )],
    description="Get info about all users. Requires `users:read` scope.",
)
async def read_all_users(db: Session = Depends(get_db)):
    return user_service.get_all(db)


@router.get(
    "/me",
    response_model=UserFromDB,
    summary="Get current user info",
    description="Get info about logged in user. Requires to be logged in.",
)
async def read_users_me(
    current_user: Annotated[UserFromDB, Depends(get_current_active_user)],
):
    return current_user


@router.get(
    "/me/favorite_events",
    response_model=list[Event],
    description="Get all favorite events for logged in user. Requires to be logged in.",
)
async def read_user_favorite_events(
    current_user: Annotated[UserFromDB, Depends(get_current_active_user)],
    db: Session = Depends(get_db)
):
    return user_service.get_favorite_events(current_user, db)


@router.post(
    "/me/favorite_events/{event_id}",
    status_code=status.HTTP_201_CREATED,
    description="Add event to favorites for logged in user. Requires to be logged in.",
)
async def create_user_favorite_events(
    current_user: Annotated[UserFromDB, Depends(get_current_active_user)],
    event_id: int,
    db: Session = Depends(get_db)
):
    try:
        user_service.add_favorite_event(current_user, event_id, db)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.delete(
    "/me/favorite_events/{event_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    description="Returns 204 if successful. Delete event to favorites for logged in user. Requires to be logged in.",
)
async def delete_user_favorite_events(
    current_user: Annotated[UserFromDB, Depends(get_current_active_user)],
    event_id: int,
    db: Session = Depends(get_db)
):
    try:
        user_service.delete_favorite_event(current_user, event_id, db)
    except user_service.FavoriteEventNotFoundException:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Favorite event not found"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


# Declared above "/{id}" on purpose: FastAPI takes the first matching route, so
# a later declaration would have "{id}" swallow /users/search and answer 422.
@router.get(
    "/search",
    response_model=list[UserSearchResult],
    summary="Search users for a scope-grant picker",
    description=(
        "Minimal user projection for filling a scope-grant form. Requires "
        "authentication and `events:edit` on at least one event; deliberately "
        "does not require the global `users:read` scope."
    ),
)
async def search_users(
    q: Annotated[str, Query(min_length=3, max_length=255)],
    current_user: Annotated[UserFromDB, Depends(get_current_active_user)],
    db: Session = Depends(get_db),
):
    # Not the global `users:read` scope - that is the wall this endpoint exists
    # to get around. `== []` means the caller holds neither the global
    # `events:edit` scope (which would give None) nor a single local grant.
    if get_event_ids_with_scope(current_user, AuthScope.EVENTS_EDIT, db) == []:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Requires an events:edit grant on some event",
        )

    # Deliberately not UserFromDB: that model carries email, scopes and
    # favorite_events, none of which a picker needs. `scopes` in particular
    # would tell the caller who else holds global powers.
    #
    # What this does disclose is bounded: an exact e-mail confirms the address
    # has an account and reveals the display name behind it. An organiser
    # already holds that address from an order. That trade holds only while
    # e-mail matching stays exact - with substring matching this becomes a
    # scraping tool for the whole user table.
    return user_service.search(q, db)


@router.get(
    "/{id}",
    response_model=UserFromDB,
    dependencies=[Security(
        get_current_active_user,
        scopes=[AuthScope.USERS_READ.value]
    )],
    description="Get info about user by ID. Requires `user:read` scope.",
)
async def read_user_by_id(id: UUID, db: Session = Depends(get_db)):
    return check_user_found(user_service.get_by_id(id, db))


@router.get(
    "/by-username/{username}",
    response_model=UserFromDB,
    dependencies=[Security(
        get_current_active_user,
        scopes=[AuthScope.USERS_READ.value]
    )],
    description="Get info about user by username. Requires `user:read` scope.",
)
async def read_user_by_username(username: str, db: Session = Depends(get_db)):
    return check_user_found(user_service.get_by_username(username, db))


@router.put(
    "/{id}",
    response_model=UserFromDB,
    dependencies=[Security(
        get_current_active_user,
        scopes=[AuthScope.USERS_EDIT.value]
    )],
    description="Returns updated user. Requires `users:edit` scope.",
)
async def update_user(
    id: UUID,
    user: UserFromDB,
    db: Session = Depends(get_db)
):
    if id != user.uuid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ID in path does not match ID in user's body."
        )
    user.uuid = user.uuid.bytes
    return check_user_found(user_service.update(user, db))


@router.delete(
    "/{id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    dependencies=[Security(
        get_current_active_user,
        scopes=[AuthScope.USERS_EDIT.value]
    )],
    description="Returns 204 if successful. Requires `users:edit` scope.",
)
async def delete_user(id: UUID, db: Session = Depends(get_db)):
    if user_service.delete(id, db) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
