"""Module for user authentication"""
from jwt import decode, encode, InvalidTokenError
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
# from app.schemas.auth import AuthTokenFamilyRevoked as AuthTokenFamilyRevokedSchema


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


def decode_token(
    token: str
):
    return decode(
        token,
        settings.jwt_public,
        algorithms=[settings.jwt_algorithm]
    )


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
        "rtfid": str(UUID(bytes=family.uuid)),
    }
    return sign_token(
        payload,
        expires_delta
    ), str(UUID(bytes=family.uuid))


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
    family_uuid: UUID,
    db: Session,
) -> bool:
    with db.begin():
        # Find refresh token family
        family = db.query(AuthTokenFamily).filter(
            AuthTokenFamily.uuid == family_uuid
        ).first()
        if not family:
            # return False
            raise InvalidTokenException("Refresh token family not found.")

        # Create simplified copy in revoked db table
        revoked = AuthTokenFamilyRevoked(
            uuid=family.uuid,
            delete_date=family.delete_date,
        )
        db.add(revoked)

        # Delete the original db row
        db.delete(family)

    return True


def get_refresh_token_family_all(
    db: Session
):
    return AuthTokenFamily.get_all(db)


def get_refresh_token_family_by_id(
    uuid: UUID,
    db: Session
):
    return AuthTokenFamily.get_by_id(
        id=uuid.bytes,
        db_session=db
    )


def get_refresh_token_family_revoked_by_id(
    uuid: UUID,
    db: Session
):
    return AuthTokenFamilyRevoked.get_by_id(
        id=uuid.bytes,
        db_session=db
    )


def get_refresh_token_family_by_user_id(
    user_uuid: UUID,
    db: Session
):
    return AuthTokenFamily.get_list_by_param(
        db_session=db,
        param_name="user_uuid",
        param_value=user_uuid.bytes,
    )


def create_access_token(
    username: str,
    refresh_token_family_uuid: UUID,
    token_scopes: list[str],
    expires_delta: timedelta | None = None
) -> str:
    return sign_token(
        {
            "sub": username,
            "rtfid": refresh_token_family_uuid,
            "scope": token_scopes,
        },
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

    refresh_token, refresh_token_family_uuid = create_refresh_token(
        db_user, db)
    access_token = create_access_token(
        username=db_user.username,
        refresh_token_family_uuid=refresh_token_family_uuid,
        token_scopes=token_scopes,
    )
    return AuthTokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
    )


def logout(
    access_token: str,
    db: Session
):
    at_payload = decode_token(access_token)
    invalidate_refresh_token_family(
        family_uuid=UUID(at_payload["rtfid"]).bytes,
        db=db,
    )


class InvalidTokenException(Exception):
    pass


def verify_acces_token(
    access_token: str,
    db: Session,
):
    try:
        at_payload = decode_token(access_token)
    except InvalidTokenError as e:
        raise InvalidTokenException(f"Invalid token. {str(e)}.")

    rtfr_id = UUID(at_payload["rtfid"])
    if get_refresh_token_family_revoked_by_id(rtfr_id, db):
        raise InvalidTokenException("Token revoked.")
