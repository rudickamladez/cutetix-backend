from fastapi import APIRouter, Depends, HTTPException, Security, status
from fastapi.responses import PlainTextResponse, FileResponse
from sqlalchemy.orm import Session
from uuid import UUID
from typing import Annotated
from fastapi.security import OAuth2PasswordRequestForm
from app.middleware.auth import get_current_active_user, oauth2_scheme
from app.schemas.auth import AuthTokenResponse, AuthTokenFamily, AuthRefreshTokenRequest
from app.schemas.passkey import (
    PasskeyLoginOptionsRequest,
    PasskeyLoginVerifyRequest,
    PasskeyOptionsResponse,
    PasskeyRegisterVerifyRequest,
    PasskeyVerifyResponse,
)
from app.schemas.user import UserFromDB, UserLogin, UserRegister
from app.schemas.settings import settings
from app.database import get_db
import app.services.auth as auth_service
import app.services.passkey as passkey_service
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
    description="Creates user and log him/her in. Server ignores given scopes."
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
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e)
        )


@router.post(
    "/login",
    response_model=AuthTokenResponse,
    summary="Get access and refresh tokens"
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


@router.post(
    "/passkeys/register/options",
    response_model=PasskeyOptionsResponse,
    summary="Start passkey registration",
    description="Creates WebAuthn registration options for logged in user.",
)
async def passkey_register_options(
    current_user: Annotated[UserFromDB, Depends(get_current_active_user)],
    db: Session = Depends(get_db),
):
    try:
        return passkey_service.begin_registration(current_user, db)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post(
    "/passkeys/register/verify",
    response_model=PasskeyVerifyResponse,
    summary="Finish passkey registration",
    description="Verifies WebAuthn registration response and stores passkey.",
)
async def passkey_register_verify(
    payload: PasskeyRegisterVerifyRequest,
    current_user: Annotated[UserFromDB, Depends(get_current_active_user)],
    db: Session = Depends(get_db),
):
    try:
        credential_id = passkey_service.finish_registration(
            user=current_user,
            challenge_id=payload.challenge_id,
            credential=payload.credential,
            db=db,
        )
        return PasskeyVerifyResponse(credential_id=credential_id)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post(
    "/passkeys/login/options",
    response_model=PasskeyOptionsResponse,
    summary="Start passkey authentication",
    description="Creates WebAuthn authentication options. Username is optional.",
)
async def passkey_login_options(
    payload: PasskeyLoginOptionsRequest,
    db: Session = Depends(get_db),
):
    try:
        return passkey_service.begin_authentication(payload.username, db)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post(
    "/passkeys/login/verify",
    response_model=AuthTokenResponse,
    summary="Finish passkey authentication",
    description="Verifies passkey assertion and returns access/refresh token pair.",
)
async def passkey_login_verify(
    payload: PasskeyLoginVerifyRequest,
    db: Session = Depends(get_db),
):
    try:
        return passkey_service.finish_authentication(
            challenge_id=payload.challenge_id,
            credential=payload.credential,
            requested_scopes=payload.requested_scopes,
            db=db,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post(
    "/refresh",
    response_model=AuthTokenResponse,
)
async def refresh(
    payload: AuthRefreshTokenRequest,
    db: Session = Depends(get_db),
):
    try:
        return auth_service.refresh(
            payload.refresh_token,
            db,
            payload.requested_scopes,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Logout user",
    description="Logout current user. Requires to be logged in.",
)
async def logout(
    access_token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    try:
        auth_service.logout(
            access_token,
            db
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
        )


@router.get(
    "/jwt/public_key",
    response_class=PlainTextResponse,
    summary="Get JWT public key as plaintext",
)
async def read_public_key():
    return settings.jwt_public


@router.get(
    "/jwt/public_key.pem",
    response_class=FileResponse,
    summary="Get JWT public key as PEM file",
)
async def get_public_key_file():
    return FileResponse(
        path=settings.jwt_public_location,
        filename="public_key.pem",
        media_type="application/x-pem-file"
    )


@router.get(
    "/tokens/me",
    response_model=list[AuthTokenFamily],
    summary="Get current user refresh token families",
    description="Returns list of logged user token families. Requires to be logged in.",
)
async def read_users_token_families(
    current_user: Annotated[UserFromDB, Depends(get_current_active_user)],
    db: Session = Depends(get_db)
):
    return auth_service.get_refresh_token_family_by_user_id(
        user_uuid=current_user.uuid,
        db=db
    )


@router.get(
    "/tokens",
    response_model=list[AuthTokenFamily],
    dependencies=[Security(
        get_current_active_user,
        scopes=["token_family:read"]
    )],
    summary="Get all refresh token families",
    description="Returns list of all token families. Requires `token_family:read` scope.",
)
async def read_all_refresh_token_families(
    db: Session = Depends(get_db),
):
    return auth_service.get_refresh_token_family_all(db)


@router.get(
    "/tokens/{family_id}",
    response_model=AuthTokenFamily,
    dependencies=[Security(
        get_current_active_user,
        scopes=["token_family:read"]
    )],
    summary="Get refresh token family by ID",
    description="Returns token family with ID, otherwise 404. Requires `token_family:read` scope.",
)
async def read_tokens_id(
    family_id: UUID,
    db: Session = Depends(get_db),
):
    return auth_service.get_refresh_token_family_by_id(family_id, db)


@router.get(
    "/tokens/user/{user_id}",
    response_model=list[AuthTokenFamily],
    dependencies=[Security(
        get_current_active_user,
        scopes=["token_family:read"]
    )],
    summary="Get refresh token families by user ID",
    description="Returns list of refresh token families for given `user_id`. Requires `token_family:read` scope.",
)
async def read_tokens_user_id(
    user_id: UUID,
    db: Session = Depends(get_db),
):
    return auth_service.get_refresh_token_family_by_user_id(user_id, db)


# TODO: Maybe set better name
@router.get(
    "/verify_acces_token",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Check if token is valid",
    description="Check if token is valid. Requires to be logged in.",
)
async def verify_acces_token(
    access_token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    try:
        auth_service.verify_acces_token(access_token, db)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
        )

# TODO: Refresh tokenu (dastanu refresh token, zkontroluju si ho v DB, vegenuruju novej access a refresh token v rodine a poslu je klientovi)
# TODO: (Automatic ‒ Cron) Deleting of normal and invalid families
# https://pypi.org/project/python-crontab/
