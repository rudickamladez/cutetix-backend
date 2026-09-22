from jwt import decode, InvalidTokenError
from typing import Annotated
from pydantic import ValidationError
from sqlalchemy.orm import Session
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, SecurityScopes

from app import models
from app.schemas.auth import AuthTokenData
from app.schemas.user import UserFromDB
from app.auth_scopes import AuthScope, OAUTH2_SCOPES
from app.database import get_db
from app.services.user import get_by_username
from app.schemas.settings import settings
from app.uuid_utils import to_uuid_bytes

# https://fastapi.tiangolo.com/advanced/security/oauth2-scopes/
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/auth/login",
    refreshUrl="/auth/refresh",
    scopes=OAUTH2_SCOPES,
)


async def get_current_user(
    security_scopes: SecurityScopes, token: Annotated[str, Depends(oauth2_scheme)],
    db: Session = Depends(get_db),
):
    if security_scopes.scopes:
        authenticate_value = f'Bearer scope="{security_scopes.scope_str}"'
    else:
        authenticate_value = "Bearer"
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": authenticate_value},
    )
    try:
        payload = decode(
            token,
            settings.jwt_public,
            algorithms=[settings.jwt_algorithm]
        )
        username = payload.get("sub")
        if username is None:
            raise credentials_exception
        scope: str = payload.get("scope", "")
        if type(scope) is str:
            token_scopes = scope.split(" ")
        else:
            token_scopes = scope
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


async def get_current_active_user(
    current_user: Annotated[UserFromDB, Depends(get_current_user)],
):
    if current_user.disabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Disabled user"
        )
    return current_user


def _scope_value(scope: AuthScope | str) -> str:
    return scope.value if isinstance(scope, AuthScope) else scope


def _raise_missing_permission(scope: str):
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=f"Missing event scope '{scope}'",
    )


def require_event_scope(
    event_id: int,
    current_user: UserFromDB,
    scope: AuthScope | str,
    db: Session,
):
    """Require a scope that is granted for one concrete event.

    JWT scopes are only global permissions. Event, ticket group and ticket
    administration must be checked against event_user_scopes so access can be
    delegated per event.
    """
    scope_value = _scope_value(scope)
    if models.Event.get_by_id(db_session=db, id=event_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found",
        )
    user_uuid = to_uuid_bytes(current_user.uuid)
    event_user_scope = db.query(models.EventUserScope).filter(
        models.EventUserScope.event_id == event_id,
        models.EventUserScope.user_uuid == user_uuid,
        models.EventUserScope.scope == scope_value,
    ).first()
    if event_user_scope is None:
        _raise_missing_permission(scope_value)


def require_event_scope_for_ticket_group(
    ticket_group_id: int,
    current_user: UserFromDB,
    scope: AuthScope | str,
    db: Session,
) -> models.TicketGroup:
    ticket_group = models.TicketGroup.get_by_id(
        db_session=db,
        id=ticket_group_id,
    )
    if ticket_group is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ticket group not found",
        )
    require_event_scope(
        event_id=ticket_group.event_id,
        current_user=current_user,
        scope=scope,
        db=db,
    )
    return ticket_group


def require_event_scope_for_ticket(
    ticket_id: int,
    current_user: UserFromDB,
    scope: AuthScope | str,
    db: Session,
) -> models.Ticket:
    ticket = models.Ticket.get_by_id(db_session=db, id=ticket_id)
    if ticket is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ticket not found",
        )
    require_event_scope_for_ticket_group(
        ticket_group_id=ticket.group_id,
        current_user=current_user,
        scope=scope,
        db=db,
    )
    return ticket


def get_event_ids_with_scope(
    current_user: UserFromDB,
    scope: AuthScope | str,
    db: Session,
) -> list[int]:
    """Return event IDs where the current user has a concrete event scope."""
    return [
        event_id
        for (event_id,) in db.query(models.EventUserScope.event_id).filter(
            models.EventUserScope.user_uuid == to_uuid_bytes(current_user.uuid),
            models.EventUserScope.scope == _scope_value(scope),
        ).distinct().order_by(models.EventUserScope.event_id).all()
    ]
