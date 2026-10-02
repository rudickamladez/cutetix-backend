from typing import Annotated
from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.middleware.auth import get_current_active_user
from app.auth_scopes import AuthScope
from app.schemas.user import UserFromDB
from app.database import get_db
from app.services.event import resolve_event_id, check_event_scope_or_403

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
        db: Session = Depends(get_db),
    ):
        event_id = resolve_event_id(resource, id, db)
        if event_id is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"{resource.replace('_', ' ').capitalize()} not found",
            )
        check_event_scope_or_403(current_user, event_id, scope_name, db)
        return current_user

    dependency.__name__ = (
        f"require_event_scope_{resource}_{scope_name.replace(':', '_')}"
    )
    return dependency
