import json
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy.orm import Session
from webauthn import (
    base64url_to_bytes,
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers.structs import (
    PublicKeyCredentialDescriptor,
    UserVerificationRequirement,
)

from app import models
from app.schemas.settings import settings
from app.schemas.user import UserFromDB
from app.services import auth as auth_service
from app.services import user as user_service


def _utc_now() -> datetime:
    return datetime.utcnow()


def _as_uuid(value: UUID | bytes | str) -> UUID:
    if isinstance(value, UUID):
        return value
    if isinstance(value, bytes):
        return UUID(bytes=value)
    return UUID(str(value))


def _as_uuid_bytes(value: UUID | bytes | str | None) -> bytes | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        return value
    return _as_uuid(value).bytes


def _challenge_ttl() -> timedelta:
    return timedelta(seconds=settings.webauthn_challenge_ttl_seconds)


def _require_user_verification() -> UserVerificationRequirement:
    if settings.webauthn_require_user_verification:
        return UserVerificationRequirement.REQUIRED
    return UserVerificationRequirement.PREFERRED


def _create_challenge(
    db: Session,
    challenge_type: str,
    challenge_bytes: bytes,
    user_uuid: UUID | bytes | str | None = None,
    username: str | None = None,
) -> models.WebAuthnChallenge:
    return models.WebAuthnChallenge.create(
        db_session=db,
        challenge=challenge_bytes,
        challenge_type=challenge_type,
        expires_at=_utc_now() + _challenge_ttl(),
        used=False,
        user_uuid=_as_uuid_bytes(user_uuid),
        username=username,
    )


def _get_valid_challenge(
    db: Session,
    challenge_id: UUID,
    challenge_type: str,
) -> models.WebAuthnChallenge:
    challenge = models.WebAuthnChallenge.get_by_id(challenge_id.bytes, db)
    if challenge is None:
        raise ValueError("Challenge not found.")
    if challenge.challenge_type != challenge_type:
        raise ValueError("Challenge type mismatch.")
    if challenge.used:
        raise ValueError("Challenge has already been used.")
    expires_at = challenge.expires_at
    if expires_at.tzinfo is not None:
        expires_at = expires_at.replace(tzinfo=None)
    if expires_at < _utc_now():
        raise ValueError("Challenge has expired.")
    return challenge


def begin_registration(user: UserFromDB, db: Session) -> dict:
    user_uuid = _as_uuid(user.uuid)
    user_credentials = models.WebAuthnCredential.get_list_by_param(
        db_session=db,
        param_name="user_uuid",
        param_value=user_uuid.bytes,
    ) or []

    exclude_credentials = [
        PublicKeyCredentialDescriptor(id=credential.credential_id)
        for credential in user_credentials
    ]

    options = generate_registration_options(
        rp_id=settings.webauthn_rp_id,
        rp_name=settings.webauthn_rp_name,
        user_id=user_uuid.bytes,
        user_name=user.username,
        user_display_name=user.full_name or user.username,
        exclude_credentials=exclude_credentials,
        user_verification=_require_user_verification(),
    )
    options_dict = json.loads(options_to_json(options))

    challenge = _create_challenge(
        db=db,
        challenge_type="registration",
        challenge_bytes=base64url_to_bytes(options_dict["challenge"]),
        user_uuid=user_uuid,
        username=user.username,
    )
    return {
        "challenge_id": str(UUID(bytes=challenge.uuid)),
        "public_key": options_dict,
    }


def finish_registration(
    user: UserFromDB,
    challenge_id: UUID,
    credential: dict,
    db: Session,
) -> str:
    challenge = _get_valid_challenge(db, challenge_id, "registration")
    if challenge.user_uuid is None or challenge.user_uuid != _as_uuid(user.uuid).bytes:
        raise ValueError("Challenge does not belong to current user.")

    verification = verify_registration_response(
        credential=credential,
        expected_challenge=challenge.challenge,
        expected_origin=settings.webauthn_origin,
        expected_rp_id=settings.webauthn_rp_id,
        require_user_verification=settings.webauthn_require_user_verification,
    )

    existing = models.WebAuthnCredential.get_one_by_param(
        db_session=db,
        param_name="credential_id",
        param_value=verification.credential_id,
    )
    if existing:
        raise ValueError("Passkey already registered.")

    created = models.WebAuthnCredential.create(
        db_session=db,
        credential_id=verification.credential_id,
        public_key=verification.credential_public_key,
        sign_count=verification.sign_count,
        transports=[],
        backed_up=bool(getattr(verification, "credential_backed_up", False)),
        device_type=str(getattr(verification, "credential_device_type", "")),
        user_uuid=_as_uuid(user.uuid).bytes,
    )

    challenge.used = True
    db.commit()
    return created.credential_id.hex()


def begin_authentication(username: str | None, db: Session) -> dict:
    allow_credentials: list[PublicKeyCredentialDescriptor] = []
    user_uuid: bytes | None = None

    if username:
        db_user = user_service.get_by_username(username, db)
        if db_user is None:
            raise ValueError("User not found.")

        user_uuid = _as_uuid(db_user.uuid).bytes
        credentials = models.WebAuthnCredential.get_list_by_param(
            db_session=db,
            param_name="user_uuid",
            param_value=user_uuid,
        ) or []
        if not credentials:
            raise ValueError("User does not have a passkey.")

        allow_credentials = [
            PublicKeyCredentialDescriptor(id=credential.credential_id)
            for credential in credentials
        ]

    options = generate_authentication_options(
        rp_id=settings.webauthn_rp_id,
        allow_credentials=allow_credentials,
        user_verification=_require_user_verification(),
    )
    options_dict = json.loads(options_to_json(options))
    challenge = _create_challenge(
        db=db,
        challenge_type="authentication",
        challenge_bytes=base64url_to_bytes(options_dict["challenge"]),
        user_uuid=user_uuid,
        username=username,
    )
    return {
        "challenge_id": str(UUID(bytes=challenge.uuid)),
        "public_key": options_dict,
    }


def finish_authentication(
    challenge_id: UUID,
    credential: dict,
    db: Session,
    requested_scopes: list[str] | None = None,
):
    challenge = _get_valid_challenge(db, challenge_id, "authentication")
    credential_id = base64url_to_bytes(credential.get("id", ""))
    if not credential_id:
        raise ValueError("Credential ID is missing.")

    db_credential = models.WebAuthnCredential.get_one_by_param(
        db_session=db,
        param_name="credential_id",
        param_value=credential_id,
    )
    if db_credential is None:
        raise ValueError("Passkey not found.")

    if challenge.user_uuid is not None and challenge.user_uuid != db_credential.user_uuid:
        raise ValueError("Passkey does not match challenge user.")

    verification = verify_authentication_response(
        credential=credential,
        expected_challenge=challenge.challenge,
        expected_origin=settings.webauthn_origin,
        expected_rp_id=settings.webauthn_rp_id,
        credential_public_key=db_credential.public_key,
        credential_current_sign_count=db_credential.sign_count,
        require_user_verification=settings.webauthn_require_user_verification,
    )

    db_credential.sign_count = verification.new_sign_count
    challenge.used = True
    db.commit()

    user = models.User.get_by_id(db_credential.user_uuid, db)
    if user is None:
        raise ValueError("User not found for passkey.")
    if user.disabled:
        raise ValueError("User is disabled.")

    return auth_service.issue_tokens_for_user(
        db_user=user,
        db=db,
        scopes=requested_scopes,
    )
