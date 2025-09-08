from fastapi import APIRouter, Depends, HTTPException, Security, status
from sqlalchemy.orm import Session
from typing import Annotated
from fastapi.security import OAuth2PasswordRequestForm
from app.middleware.auth import get_current_active_user, oauth2_scheme, verify_token
from app.schemas.auth import AuthTokenResponse, UserFromDB, UserLogin, UserRegister
from app.database import get_db
import app.services.auth as auth_service
from uuid import UUID

router = APIRouter(
    prefix="/auth",
    tags=["authentication"],
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


@router.post("/register", response_model=UserFromDB)
async def register(user: UserLogin, db: Session = Depends(get_db)):
    try:
        return auth_service.register(UserRegister.model_validate(user.model_dump()), db=db)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/login", response_model=AuthTokenResponse)
async def login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Session = Depends(get_db)
):
    try:
        return auth_service.login(form_data.username, form_data.password, form_data.scopes, db=db)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/verify_token")
async def verify(token: str = Depends(oauth2_scheme)):
    return verify_token(token)


@router.get(
    "/users/me",
    response_model=UserFromDB,
    description="Get info about logged in user. Requires to be logged in.",
)
async def read_users_me(
    current_user: Annotated[UserFromDB, Depends(get_current_active_user)],
):
    return current_user


@router.get(
    "/users/",
    response_model=list[UserFromDB],
    dependencies=[Security(
        get_current_active_user,
        scopes=["users:read"]
    )],
    description="Get info about all users. Requires 'users:read' scope.",
)
async def read_all_users(db: Session = Depends(get_db)):
    return auth_service.get_all(db)


@router.get(
    "/users/{id}",
    response_model=UserFromDB,
    dependencies=[Security(
        get_current_active_user,
        scopes=["users:read"]
    )],
    description="Get info about user by ID. Requires 'user:read' scope.",
)
async def read_user_by_id(id: UUID, db: Session = Depends(get_db)):
    return check_user_found(auth_service.get_by_id(id, db))


@router.get(
    "/users/by-username/{username}",
    response_model=UserFromDB,
    dependencies=[Security(
        get_current_active_user,
        scopes=["users:read"]
    )],
    description="Get info about user by username. Requires 'user:read' scope.",
)
async def read_user_by_username(username: str, db: Session = Depends(get_db)):
    return check_user_found(auth_service.get_by_username(username, db))


@router.put(
    "/users/{id}",
    response_model=UserFromDB,
    dependencies=[Security(
        get_current_active_user,
        scopes=["users:edit"]
    )],
    description="Returns updated user. Requires 'users:edit' scope.",
)
async def update_user(user: UserFromDB, db: Session = Depends(get_db)):
    return check_user_found(auth_service.update(user, db))


@router.delete(
    "/users/{id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Security(
        get_current_active_user,
        scopes=["users:edit"]
    )],
    description="Returns 204 if successful. Requires 'users:delete' scope.",
)
async def delete_user(id: UUID, db: Session = Depends(get_db)):
    if not auth_service.delete(id, db):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User does not exist, nothing to delete."
        )
    return
