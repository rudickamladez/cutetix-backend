"""Module for user authentication"""
from jwt import encode
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from passlib.context import CryptContext
from uuid import UUID
from app.schemas.auth import AuthTokenResponse
from app.schemas.user import UserFromDB
from app.schemas.settings import settings
from app.models import AuthTokenFamily, AuthTokenFamilyRevoked, generate_uuid
from app.database import engine
import app.services.user as user_service
from app.schemas.auth import AuthTokenFamily as AuthTokenFamilySchema
from app.schemas.auth import AuthTokenFamilyRevoked as AuthTokenFamilyRevokedSchema


# https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/#hash-and-verify-the-passwords
pwd_context = CryptContext(
    schemes=["bcrypt"],
    bcrypt__rounds=12,
    deprecated="auto"
)

# Create table if not exists
AuthTokenFamily.__table__.create(bind=engine, checkfirst=True)
AuthTokenFamilyRevoked.__table__.create(bind=engine, checkfirst=True)


def verify_password(plaintext_password, hashed_password):
    return pwd_context.verify(plaintext_password, hashed_password)


def get_password_hash(password):
    return pwd_context.hash(password)


def sign_token(
    payload: dict,
    expires_delta: timedelta | None = None
):
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + \
            timedelta(minutes=settings.access_token_expire_minutes)
    # TODO: JWI, etc.
    payload.update({
        "exp": expire,
    })
    return encode(
        payload=payload,
        key=settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )


def create_refresh_token(
    user: UserFromDB,
    db: Session,
    expires_delta: timedelta | None = None
):
    refresh_token_uuid = generate_uuid()
    family = create_refresh_token_family(
        user,
        refresh_token_uuid,
        db
    )
    payload = {
        "jti": str(UUID(bytes=family.last_refresh_token)),  # jwt id
        "token_family": str(UUID(bytes=family.uuid)),
    }
    return sign_token(
        payload,
        expires_delta
    )


def create_refresh_token_family(
    user: UserFromDB,
    refresh_token_uuid: UUID,
    db: Session,
) -> AuthTokenFamilySchema:
    return AuthTokenFamily.create(
        db,
        delete_date=datetime.now(timezone.utc) +
        timedelta(minutes=settings.access_token_expire_minutes),
        last_refresh_token=UUID(bytes=refresh_token_uuid).bytes,
        user_uuid=bytes(user.uuid),
    )


def invalidate_refresh_token_family(
    uuid: UUID,
    db: Session,
):
    # TODO: Transaction?
    # https://docs.sqlalchemy.org/en/20/orm/session_transaction.html
    deleted_token: AuthTokenFamilyRevoked = AuthTokenFamily.get_by_id(uuid, db)
    AuthTokenFamilyRevoked.create(
        db,
        **deleted_token.model_dump(
            exclude_unset=True,
            exclude_none=True,
        )
    )


def get_refresh_token_family_all(
    db: Session
):
    return AuthTokenFamily.get_all(db)


def get_refresh_token_family_by_id(
    uuid: UUID,
    db: Session
):
    return AuthTokenFamily.get_by_id(uuid, db)


def get_refresh_token_family_by_user_id(
    user_uuid: UUID,
    db: Session
):
    return AuthTokenFamily.get_by_param(
        db_session=db,
        param_name="user",
        param_value=user_uuid,
    )


def create_access_token(
    payload: dict,
    expires_delta: timedelta | None = None
) -> str:
    return sign_token(
        payload,
        expires_delta
    )


def login(
    username: str,
    plain_password: str,
    db: Session,
    scopes: list[str] | None = None,
) -> AuthTokenResponse | None:
    db_user = user_service.get_by_username(username, db=db)
    if not db_user or not verify_password(plain_password, db_user.hashed_password):
        raise Exception("Incorrect credentials")

    if scopes is None or len(list(scopes)) == 0:
        token_scopes = db_user.scopes
    else:
        token_scopes = []
        for scope in scopes:
            if scope in db_user.scopes:
                token_scopes.append(scope)

    access_token = create_access_token(payload={
        "sub": db_user.username, "scope": " ".join(token_scopes)
    })
    refresh_token = create_refresh_token(db_user, db)
    return AuthTokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
    )
