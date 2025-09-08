from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Annotated
from fastapi.security import OAuth2PasswordRequestForm
from app.middleware.auth import get_current_active_user, oauth2_scheme, verify_token
from app.schemas.auth import AuthTokenResponse
from app.schemas.user import UserFromDB, UserLogin, UserRegister
from app.database import get_db
import app.services.auth as auth_service
import app.services.user as user_service

router = APIRouter(
    prefix="/auth",
    tags=["authentication"],
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "Not found"}
    },
)


@router.post(
    "/register",
    response_model=AuthTokenResponse,
    description="Create user and login them. Server ignores given scopes."
)
async def register(user: UserLogin, db: Session = Depends(get_db)):
    try:
        user_db = user_service.register(
            user=UserRegister.model_validate(user.model_dump()),
            db=db
        )
        return auth_service.login(
            username=user_db.username,
            plain_password=user.plaintext_password,
            db=db
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post(
    "/login",
    response_model=AuthTokenResponse
)
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
    "/me",
    response_model=UserFromDB,
    description="Get info about logged in user. Requires to be logged in.",
)
async def read_users_me(
    current_user: Annotated[UserFromDB, Depends(get_current_active_user)],
):
    return current_user
