from typing import Annotated
from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.middleware.auth import get_current_active_user, oauth2_scheme
from app.auth_scopes import AuthScope
from app.schemas.user import UserFromDB
from app.database import get_db
from app.services.auth import InvalidTokenException, has_access_token_required_scopes
from app.services.event import get_event_id_by_resource
from app.services import event_user_scopes as event_user_scopes_service

SUPPORTED_RESOURCES = ("event", "ticket_group", "ticket")


def require_event_scope(
    scope: AuthScope | str,
    resource: str = "event",
):
    """Dependency factory: token scope OR event-local grant.

    The route's ``id`` path parameter identifies the resource:

    - ``resource="event"``: ``id`` is the event id itself.
    - ``resource="ticket_group"``: ``id`` is a ticket-group id; the owning
      event is resolved through ``ticket_groups.event_id``.
    - ``resource="ticket"``: ``id`` is a ticket id; the owning event is
      resolved through ``tickets.group_id -> ticket_groups.event_id``.

    The request is allowed when the user carries ``scope`` on the request
    token or holds an event-local ``scope`` grant for the owning event.
    ``Security(get_current_active_user, scopes=[scope])`` cannot express
    this - it would *require* the global scope even where a local grant
    suffices - so the either/or rule lives in ``check_event_scope_or_403``.
    """
    if resource not in SUPPORTED_RESOURCES:
        # A typo here is a programming error; fail at import time rather than
        # answering 500 on every request to the route.
        raise ValueError(
            f"Unknown resource type '{resource}'. "
            f"Must be one of: {', '.join(SUPPORTED_RESOURCES)}"
        )
    scope_name = scope.value if isinstance(scope, AuthScope) else scope

    # Must stay a plain def: FastAPI runs coroutine dependencies on the event
    # loop, and the lookups below are blocking DB calls.
    def dependency(
        id: int,
        current_user: Annotated[
            UserFromDB,
            Depends(get_current_active_user),
        ],
        access_token: Annotated[str, Depends(oauth2_scheme)],
        db: Session = Depends(get_db),
    ):
        event_id = get_event_id_by_resource(resource, id, db)
        if event_id is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"{resource.replace('_', ' ').capitalize()} not found",
            )
        check_event_scope_or_403(
            current_user, access_token, event_id, scope_name, db
        )
        return current_user

    dependency.__name__ = (
        f"require_event_scope_{resource}_{scope_name.replace(':', '_')}"
    )
    return dependency


def check_event_scope_or_403(
    user,
    access_token: str,
    event_id: int,
    scope: AuthScope | str,
    db: Session,
) -> None:
    """Allow the request when the user holds the token scope *or* an
    event-local grant for ``scope`` on ``event_id``.

    Raises 403 when the user has neither.
    """
    scope_value = scope.value if isinstance(scope, AuthScope) else scope
    try:
        if has_access_token_required_scopes(access_token, [scope_value], db):
            return # User has the required global token scope, no more checks required
        # User does not have the required global token scope, check event-local grant next
    except InvalidTokenException as e:
        # Log the exception or handle it if needed
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e)
        )

    if event_user_scopes_service.has_scope(
        event_id=event_id,
        user_uuid=user.uuid,
        scope=scope_value,
        db=db,
    ):
        return # User has the required event-local scope
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=f"Not enough permissions for event {event_id} (missing '{scope_value}')",
    )
