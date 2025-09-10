from fastapi import APIRouter, Depends, HTTPException, Security, status
from sqlalchemy.orm import Session
from typing import Annotated
from uuid import UUID
from app.middleware.auth import get_current_active_user
from app.schemas.user import UserFromDB
from app.database import get_db
import app.services.user as user_service

router = APIRouter(
    prefix="/users",
    tags=["users"],
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "Not found"}
    },
)


def check_user_found(user: UserFromDB) -> UserFromDB:
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    return user


@router.get(
    "/",
    response_model=list[UserFromDB],
    dependencies=[Security(
        get_current_active_user,
        scopes=["users:read"]
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
    "/{id}",
    response_model=UserFromDB,
    dependencies=[Security(
        get_current_active_user,
        scopes=["users:read"]
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
        scopes=["users:read"]
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
        scopes=["users:edit"]
    )],
    description="Returns updated user. Requires `users:edit` scope.",
)
async def update_user(user: UserFromDB, db: Session = Depends(get_db)):
    return check_user_found(user_service.update(user, db))


@router.delete(
    "/{id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Security(
        get_current_active_user,
        scopes=["users:edit"]
    )],
    description="Returns 204 if successful. Requires `users:delete` scope.",
)
async def delete_user(id: UUID, db: Session = Depends(get_db)):
    if not user_service.delete(id, db):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User does not exist, nothing to delete."
        )
    return
