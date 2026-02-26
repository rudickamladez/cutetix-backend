from jwt import decode, InvalidTokenError, PyJWKClient
from typing import Annotated
from functools import lru_cache
from pydantic import ValidationError
from sqlalchemy.orm import Session
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, SecurityScopes

from app.schemas.auth import AuthTokenData
from app.schemas.user import UserFromDB
from app.database import get_db
from app.services.user import get_by_username
from app.schemas.settings import settings

# https://fastapi.tiangolo.com/advanced/security/oauth2-scopes/
OAUTH_SCOPES = {
    "users:read": "Read information about users.",
    "users:edit": "Edit information about users.",
    "events:read": "Read information about events.",
    "events:edit": "Edit information about events.",
    "token_family:read": "Read all token families from DB",
    "ticket_groups:read": "Read information about ticket groups.",
    "ticket_groups:edit": "Edit information about ticket groups.",
    "tickets:read": "Read information about tickets.",
    "tickets:edit": "Edit information about tickets.",
}

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/auth/login",
    refreshUrl="/auth/refresh",
    scopes=OAUTH_SCOPES,
)

mcp_oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/auth/login",
    refreshUrl="/auth/refresh",
    scopes=OAUTH_SCOPES,
    auto_error=False,
)


def _get_resource_metadata_url() -> str | None:
    if not settings.mcp_public_base_url or not settings.mcp_oauth_issuer:
        return None
    base_url = settings.mcp_public_base_url.rstrip("/")
    return f"{base_url}{settings.mcp_oauth_resource_metadata_path}"
    return None


def _build_www_authenticate(security_scopes: SecurityScopes) -> str:
    params: list[str] = []
    if security_scopes.scopes:
        params.append(f'scope="{security_scopes.scope_str}"')
    resource_metadata_url = _get_resource_metadata_url()
    if resource_metadata_url:
        params.append(f'resource_metadata="{resource_metadata_url}"')
    if params:
        return f"Bearer {', '.join(params)}"
    return "Bearer"


def _build_basic_www_authenticate(security_scopes: SecurityScopes) -> str:
    if security_scopes.scopes:
        return f'Bearer scope="{security_scopes.scope_str}"'
    return "Bearer"


@lru_cache
def _get_jwks_client() -> PyJWKClient | None:
    if not settings.mcp_oauth_jwks_url:
        return None
    return PyJWKClient(settings.mcp_oauth_jwks_url)


def _decode_with_jwks(token: str) -> dict:
    jwks_client = _get_jwks_client()
    if not jwks_client:
        raise InvalidTokenError("Missing JWKS configuration.")
    signing_key = jwks_client.get_signing_key_from_jwt(token)
    options = {
        "verify_aud": bool(settings.mcp_oauth_audience),
        "verify_iss": bool(settings.mcp_oauth_issuer),
    }
    return decode(
        token,
        signing_key.key,
        algorithms=settings.mcp_oauth_jwt_algorithms or ["RS256"],
        audience=settings.mcp_oauth_audience if settings.mcp_oauth_audience else None,
        issuer=settings.mcp_oauth_issuer if settings.mcp_oauth_issuer else None,
        options=options,
    )


def _decode_access_token(token: str) -> dict:
    try:
        payload = decode(
            token,
            settings.jwt_public,
            algorithms=[settings.jwt_algorithm],
            options={"verify_aud": False},
        )
        if settings.mcp_oauth_audience and payload.get("aud") and payload.get("aud") != settings.mcp_oauth_audience:
            raise InvalidTokenError("Invalid audience")
        return payload
    except InvalidTokenError:
        if settings.mcp_oauth_jwks_url:
            return _decode_with_jwks(token)
        raise


def _extract_scopes(payload: dict) -> list[str]:
    scope_value = payload.get("scope")
    if scope_value is None:
        scope_value = payload.get("scp")
    if scope_value is None:
        scope_value = payload.get("permissions")

    if scope_value is None:
        return []
    if isinstance(scope_value, str):
        return [scope for scope in scope_value.split() if scope]
    if isinstance(scope_value, list):
        return [str(scope) for scope in scope_value if scope]
    return []


def _extract_username(payload: dict) -> str | None:
    for claim in settings.mcp_oauth_username_claims:
        value = payload.get(claim)
        if isinstance(value, list) and value:
            return str(value[0])
        if value:
            return str(value)
    return None


async def _authenticate_user(
    security_scopes: SecurityScopes,
    token: str | None,
    db: Session,
    include_resource_metadata: bool,
):
    authenticate_value = (
        _build_www_authenticate(security_scopes)
        if include_resource_metadata
        else _build_basic_www_authenticate(security_scopes)
    )
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": authenticate_value},
    )
    if not token:
        raise credentials_exception
    try:
        payload = _decode_access_token(token)
        username = _extract_username(payload)
        if username is None:
            raise credentials_exception
        token_scopes = _extract_scopes(payload)
        token_data = AuthTokenData(scopes=token_scopes, username=username)
    except (InvalidTokenError, ValidationError):
        raise credentials_exception
    user = get_by_username(token_data.username, db=db)
    if user is None:
        raise credentials_exception
    for scope in security_scopes.scopes:
        if scope not in token_data.scopes:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not enough permissions",
                headers={"WWW-Authenticate": authenticate_value},
            )
    return user


async def get_current_user(
    security_scopes: SecurityScopes, token: Annotated[str, Depends(oauth2_scheme)],
    db: Session = Depends(get_db),
):
    return await _authenticate_user(
        security_scopes=security_scopes,
        token=token,
        db=db,
        include_resource_metadata=False,
    )


async def get_current_active_user(
    current_user: Annotated[UserFromDB, Depends(get_current_user)],
):
    if current_user.disabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Disabled user"
        )
    return current_user


async def mcp_authentication(
    security_scopes: SecurityScopes,
    token: Annotated[str | None, Depends(mcp_oauth2_scheme)],
    db: Session = Depends(get_db),
):
    return await _authenticate_user(
        security_scopes=security_scopes,
        token=token,
        db=db,
        include_resource_metadata=True,
    )
