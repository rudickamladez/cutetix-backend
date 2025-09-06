from fastapi import APIRouter, Depends, HTTPException, Security, status
from sqlalchemy.orm import Session
from typing import Annotated
from fastapi.security import OAuth2PasswordRequestForm
from app.middleware.auth import get_current_active_user
from app.schemas.auth import AuthTokenResponse, UserFromDB, UserLogin, UserRegister
from app.database import get_db
import app.services.auth as auth_service
import uuid

router = APIRouter(
    prefix="/auth",
    tags=["auth"],
    responses={404: {"description": "Not found"}},
)


def check_user_found(user: UserFromDB) -> UserFromDB:
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    return user


@router.post("/register", response_model=UserFromDB)
def register(user: UserLogin, db: Session = Depends(get_db)):
    try:
        return auth_service.register(UserRegister.model_validate(user.model_dump()), db=db)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/token", response_model=AuthTokenResponse)
async def login(form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
                db: Session = Depends(get_db)):
    try:
        return auth_service.login(form_data.username, form_data.password, form_data.scopes, db=db)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get(
    "/users/me",
    response_model=UserFromDB,
    description="Get info about logged in user. Requires 'me:read' scope.",
)
async def read_users_me(
    current_user: Annotated[UserFromDB, Security(get_current_active_user, scopes=["me:read"])],
):
    return current_user


@router.get(
    "/users/all",
    response_model=list[UserFromDB],
    dependencies=[Security(
        get_current_active_user,
        scopes=["users:read"]
    )],
    description="Get info about all users. Requires 'users:read' scope.",
)
async def read_all_users(db: Session = Depends(get_db)):
    return auth_service.get_all(db)


@router.get("/user/{id}", response_model=UserFromDB)
async def read_user_by_id(id: uuid.UUID, db: Session = Depends(get_db)):
    return check_user_found(auth_service.get_by_id(id, db))


@router.get("/user/by-username/{username}", response_model=UserFromDB)
async def read_user_by_username(username: str, db: Session = Depends(get_db)):
    return check_user_found(auth_service.get_by_username(username, db))


@router.patch("/user/", response_model=UserFromDB, description="Returns updated user.")
async def update_user(user: UserFromDB, db: Session = Depends(get_db)):
    return check_user_found(auth_service.update(user, db))


@router.delete("/user/{id}", response_model=UserFromDB, description="Returns deleted user.")
async def delete_user(id: uuid.UUID, db: Session = Depends(get_db)):
    return check_user_found(auth_service.delete(id, db))
