"""Module for user authentication"""
from jwt import decode, encode, InvalidTokenError
from datetime import datetime, timedelta, timezone
from sqlalchemy import update
from sqlalchemy.orm import Session
from uuid import UUID
from app.auth_scopes import AUTH_SCOPE_VALUES
from app.schemas.auth import AuthTokenResponse
from app.schemas.user import UserFromDB
from app.schemas.settings import settings
from app.models import AuthTokenFamily, AuthTokenFamilyRevoked, generate_uuid
from app.services.passwords import verify_password
from app.uuid_utils import to_uuid_bytes
import app.services.user as user_service
from app.schemas.auth import AuthTokenFamily as AuthTokenFamilySchema
# from app.schemas.auth import AuthTokenFamilyRevoked as AuthTokenFamilyRevokedSchema


def _known_token_scopes(scopes: list[str] | set[str] | tuple[str, ...]) -> list[str]:
    """Drop anything that is not a scope the application knows about.

    A token scope grants access on *every* event; access limited to a single
    event comes from event_user_scopes instead. Unknown values are dropped so
    a typo or a stale client request cannot linger in a token family and be
    re-issued indefinitely by /auth/refresh.
    """
    return [
        scope
        for scope in scopes
        if scope in AUTH_SCOPE_VALUES
    ]


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
        user_uuid=bytes(user.uuid),
        token_scopes=token_scopes,
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
    user_uuid: UUID | bytes,
    db: Session
):
    return AuthTokenFamily.get_list_by_param(
        db_session=db,
        param_name="user_uuid",
        param_value=to_uuid_bytes(user_uuid),
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
        token_scopes = _known_token_scopes(db_user.scopes)
    else:
        token_scopes = _known_token_scopes([
            scope
            for scope in scopes
            if scope in db_user.scopes
        ])

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
    if str(UUID(bytes=rtf.last_refresh_token)) != str(rt_payload["jti"]):
        raise InvalidTokenException(
            "Refresh token family has been refreshed mean time.")

    if rtf.user is None:
        raise InvalidTokenException("User not found.")

    if rtf.user.disabled:
        raise InvalidTokenException("User is disabled.")

    family_scopes: set[str] = set(rtf.token_scopes or [])
    if requested_scopes:
        eff_scopes = _known_token_scopes(sorted(
            set(rtf.user.scopes).intersection(
                family_scopes.intersection(requested_scopes)
            )
        ))
    else:
        eff_scopes = _known_token_scopes(sorted(family_scopes))

    new_access_token = create_access_token(
        username=rtf.user.username,
        refresh_token_family_uuid=rtf.uuid,
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


class InvalidTokenException(InvalidTokenError):
    pass
