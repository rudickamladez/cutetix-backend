from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import PlainTextResponse, FileResponse
from sqlalchemy.orm import Session
from typing import Annotated
from fastapi.security import OAuth2PasswordRequestForm
from app.middleware.auth import get_current_active_user, oauth2_scheme, verify_token
from app.schemas.auth import AuthTokenResponse
from app.schemas.user import UserFromDB, UserLogin, UserRegister
from app.schemas.settings import settings
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
        return auth_service.login(
            username=form_data.username,
            plain_password=form_data.password,
            scopes=form_data.scopes,
            db=db
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/jwt/public_key", response_class=PlainTextResponse)
async def read_public_key():
    return settings.jwt_public


@router.get("/auth/jwt/public_key.pem", response_class=FileResponse)
async def get_public_key_file():
    return FileResponse(
        path=settings.jwt_public_location,
        filename="public_key.pem",
        media_type="application/x-pem-file"
    )


@router.get("/tokens/family")
async def read_tokens(
    db: Session = Depends(get_db),
):
    return auth_service.get_refresh_token_family_all(db)


@router.get("/tokens/family/{id}")
async def read_tokens_id(
    id: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
):
    return auth_service.get_refresh_token_family_by_id(id, db)


@router.get("/tokens/family/user/{user_id}")
async def read_tokens_user_id(
    user_id: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
):
    return auth_service.get_refresh_token_family_by_user_id(user_id, db)


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
