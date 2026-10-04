"""Module for user authentication"""
from jwt import decode, encode, InvalidTokenError
from datetime import datetime, timedelta, timezone
from sqlalchemy import update
from sqlalchemy.orm import Session
from passlib.context import CryptContext
from uuid import UUID
from app.utils.uuid import to_uuid_bytes
from app.schemas.auth import ApiToken, ApiTokenCreated, AuthTokenResponse
from app.schemas.user import UserFromDB
from app.schemas.settings import settings
from app.models import AuthTokenFamily, AuthTokenFamilyRevoked, generate_uuid
import app.services.user as user_service
from app.schemas.auth import AuthTokenFamily as AuthTokenFamilySchema
# from app.schemas.auth import AuthTokenFamilyRevoked as AuthTokenFamilyRevokedSchema


# https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/#hash-and-verify-the-passwords
pwd_context = CryptContext(
    schemes=["argon2", "bcrypt"],
    bcrypt__rounds=12,
    deprecated="auto"
)


def verify_password(plaintext_password, hashed_password):
    return pwd_context.verify(plaintext_password, hashed_password)

    # pokud bylo původně bcrypt → rehash na argon2
    # if ok and pwd_context.identify(hashed_password) == "bcrypt":
    #     new_hash = pwd_context.hash(plaintext_password)
    #     # TODO: update it in the DB


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
    expires_delta: timedelta
):
    expire = datetime.now(timezone.utc) + expires_delta
    payload.update({
        "exp": expire,
    })
    return encode(
        payload=payload,
        key=settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )


def sign_token_until(payload: dict, expires_at: datetime) -> str:
    """Sign a token with an explicit expiry, used by long-lived API tokens."""
    payload = payload.copy()
    payload["exp"] = expires_at
    return encode(
        payload=payload,
        key=settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )


def create_refresh_token(
    user: UserFromDB,
    db: Session,
    token_scopes: list[str],
    expires_delta: timedelta | None = None
):
    refresh_token_uuid = generate_uuid()
    family = create_refresh_token_family(
        user,
        refresh_token_uuid,
        db,
        token_scopes,
    )
    payload = {
        "jti": str(UUID(bytes=family.last_refresh_token)),  # jwt id
        "rtfid": str(UUID(bytes=family.uuid)),
    }
    if expires_delta is None:
        expires_delta = timedelta(
            minutes=settings.refresh_token_expire_minutes)
    return sign_token(
        payload,
        expires_delta
    ), str(UUID(bytes=family.uuid))


def create_refresh_token_family(
    user: UserFromDB,
    refresh_token_uuid: UUID,
    db: Session,
    token_scopes: list[str],
) -> AuthTokenFamilySchema:
    return AuthTokenFamily.create(
        db,
        delete_date=datetime.now(timezone.utc) +
        timedelta(minutes=settings.refresh_token_expire_minutes),
        last_refresh_token=UUID(bytes=refresh_token_uuid).bytes,
        user_uuid=to_uuid_bytes(user.uuid),
        token_scopes=token_scopes,
    )


def invalidate_refresh_token_family(
    family_uuid: UUID | bytes,
    db: Session,
) -> bool:
    # The lookup may already have autobegun a transaction (for example while
    # checking API-token ownership), so do not unconditionally call begin().
    family_id = family_uuid if isinstance(family_uuid, bytes) else family_uuid.bytes
    family = db.query(AuthTokenFamily).filter(
        AuthTokenFamily.uuid == family_id
    ).first()
    if not family:
        raise InvalidTokenException("Refresh token family not found.")

    revoked = AuthTokenFamilyRevoked(
        uuid=family.uuid,
        delete_date=family.delete_date,
    )
    db.add(revoked)
    db.delete(family)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    return True


def get_refresh_token_family_all(
    db: Session
):
    return AuthTokenFamily.get_all(
        db_session=db,
        order_by=["delete_date", "uuid"],
        descending=True,
    )


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
        order_by=["delete_date", "uuid"],
        descending=True,
    )


def create_access_token(
    username: str,
    refresh_token_family_uuid: UUID,
    token_scopes: list[str],
    expires_delta: timedelta | None = None
) -> str:
    if expires_delta is None:
        expires_delta = timedelta(minutes=settings.access_token_expire_minutes)
    return sign_token(
        {
            "sub": username,
            "rtfid": refresh_token_family_uuid,
            "scope": token_scopes,
        },
        expires_delta
    )


def create_api_token(
    user: UserFromDB,
    name: str,
    expires_at: datetime,
    scopes: list[str],
    db: Session,
) -> ApiTokenCreated:
    """Create one independently revocable, non-refreshable API token.

    The signed JWT is the bearer secret. Only its random identifier is kept
    in the family, so there is no plaintext secret to disclose later.
    """
    token_id = generate_uuid()
    family = AuthTokenFamily(
        delete_date=expires_at,
        last_refresh_token=token_id,
        user_uuid=to_uuid_bytes(user.uuid),
        token_scopes=scopes,
        token_type="api",
        name=name,
    )
    db.add(family)
    db.commit()
    db.refresh(family)
    family_id = UUID(bytes=family.uuid)
    token = sign_token_until(
        {
            "sub": user.username,
            "rtfid": str(family_id),
            "jti": str(UUID(bytes=token_id)),
            "scope": scopes,
        },
        expires_at,
    )
    return ApiTokenCreated(
        id=family_id,
        name=family.name,
        created_at=family.created_at,
        expires_at=family.delete_date,
        scopes=family.token_scopes,
        token=token,
    )


def _api_token_schema(family: AuthTokenFamily) -> ApiToken:
    return ApiToken(
        id=UUID(bytes=family.uuid),
        name=family.name,
        created_at=family.created_at,
        expires_at=family.delete_date,
        scopes=family.token_scopes or [],
    )


def get_api_tokens_for_user(user_uuid: UUID, db: Session) -> list[ApiToken]:
    families = db.query(AuthTokenFamily).filter(
        AuthTokenFamily.user_uuid == to_uuid_bytes(user_uuid),
        AuthTokenFamily.token_type == "api",
    ).order_by(AuthTokenFamily.created_at.desc(), AuthTokenFamily.uuid.desc()).all()
    return [_api_token_schema(family) for family in families]


def get_api_token_for_user(
    token_id: UUID, user_uuid: UUID, db: Session,
) -> ApiToken | None:
    family = db.query(AuthTokenFamily).filter(
        AuthTokenFamily.uuid == token_id.bytes,
        AuthTokenFamily.user_uuid == to_uuid_bytes(user_uuid),
        AuthTokenFamily.token_type == "api",
    ).first()
    return _api_token_schema(family) if family else None


def revoke_api_token_for_user(token_id: UUID, user_uuid: UUID, db: Session) -> bool:
    family = db.query(AuthTokenFamily).filter(
        AuthTokenFamily.uuid == token_id.bytes,
        AuthTokenFamily.user_uuid == to_uuid_bytes(user_uuid),
        AuthTokenFamily.token_type == "api",
    ).first()
    if family is None:
        return False
    invalidate_refresh_token_family(token_id, db)
    return True


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
        db_user,
        db,
        token_scopes
    )

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


def refresh(
    refresh_token: str,
    db: Session,
    requested_scopes: list[str] | None = None,
):
    rt_payload = decode_token(refresh_token)
    rtf = AuthTokenFamily.get_by_id(UUID(rt_payload["rtfid"]).bytes, db)
    if rtf is None:
        raise InvalidTokenException("Refresh token family does not exist.")
    if rtf.token_type == "api":
        raise InvalidTokenException("API tokens cannot be refreshed.")
    if str(UUID(bytes=rtf.last_refresh_token)) != str(rt_payload["jti"]):
        raise InvalidTokenException(
            "Refresh token family has been refreshed mean time.")

    if rtf.user is None:
        raise InvalidTokenException("User not found.")

    if rtf.user.disabled:
        raise InvalidTokenException("User is disabled.")

    family_scopes: set[str] = set(rtf.token_scopes or [])
    if requested_scopes:
        eff_scopes = sorted(set(rtf.user.scopes).intersection(
            family_scopes.intersection(requested_scopes)
        ))
    else:
        eff_scopes = sorted(family_scopes)

    new_access_token = create_access_token(
        username=rtf.user.username,
        # str(UUID(...)), not rtf.uuid (raw bytes PyJWT cannot serialize) and
        # not str(rtf.uuid) either - that renders b'\\x06...' rather than a
        # uuid, so an access token would carry an unusable rtfid claim.
        refresh_token_family_uuid=str(UUID(bytes=rtf.uuid)),
        token_scopes=eff_scopes,
    )
    new_refresh_token_uuid = UUID(bytes=generate_uuid())
    new_refresh_token = sign_token(
        {
            "jti": str(new_refresh_token_uuid),
            "rtfid": str(UUID(bytes=rtf.uuid)),
        },
        timedelta(minutes=settings.refresh_token_expire_minutes)
    )
    # TODO: Missing family expiry extension on refresh.
    db.execute(
        update(AuthTokenFamily)
        .where(AuthTokenFamily.uuid == rtf.uuid)
        .values(last_refresh_token=new_refresh_token_uuid.bytes)
    )
    db.commit()

    return AuthTokenResponse(
        access_token=new_access_token,
        refresh_token=new_refresh_token,
    )


def verify_access_token(
    access_token: str,
    db: Session,
) -> AuthTokenFamily:
    try:
        at_payload = decode_token(access_token)
        rtfr_id = UUID(str(at_payload["rtfid"]))
    except (InvalidTokenError, KeyError, TypeError, ValueError) as e:
        raise InvalidTokenException(f"Invalid token. {str(e)}.")

    if get_refresh_token_family_revoked_by_id(rtfr_id, db):
        raise InvalidTokenException("Token revoked.")
    family = get_refresh_token_family_by_id(rtfr_id, db)
    if family is None:
        # A family can disappear without a matching revoked-record (for
        # example through expiry cleanup). Its old access tokens are invalid.
        raise InvalidTokenException("Refresh token family does not exist.")
    if family.delete_date is not None:
        expires_at = family.delete_date
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at <= datetime.now(timezone.utc):
            raise InvalidTokenException("Token expired.")
    return family


class InvalidTokenException(InvalidTokenError):
    pass


def has_access_token_required_scopes(
    access_token: str,
    required_scopes: list[str],
    db: Session,
) -> bool:
    try:
        at_payload = decode_token(access_token)
    except InvalidTokenError as e:
        raise InvalidTokenException(f"Invalid token. {str(e)}.")

    try:
        family = verify_access_token(access_token, db)
    except (KeyError, TypeError, ValueError) as e:
        raise InvalidTokenException(f"Invalid token. {str(e)}.")

    token_scopes = at_payload.get("scope", [])

    # Check if all required scopes are present in the token scopes
    if not set(required_scopes).issubset(set(token_scopes)):
        return False
    # API family scopes are the persisted source of truth as well as a
    # ceiling on the signed token's scopes. Session-family behaviour remains
    # compatible with the existing login/refresh tokens.
    if family.token_type == "api":
        return set(required_scopes).issubset(set(family.token_scopes or []))
    return True
