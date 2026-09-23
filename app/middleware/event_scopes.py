"""Event-tenancy authorization.

A request may touch an event when the caller holds the scope *globally* (in
the access token) or *locally* (a row in ``event_user_scopes`` for that one
event). Everything here answers the second half of that question.
"""
from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import models
from app.auth_scopes import AuthScope
from app.database import get_db
from app.middleware.auth import get_current_active_user
from app.schemas.user import UserFromDB
from app.services import event_user_scopes as event_user_scopes_service

SUPPORTED_RESOURCES = ("event", "ticket_group", "ticket")


def token_scopes_of(user) -> list[str]:
    """Scopes carried by the access token that authenticated this request.

    ``get_current_user`` attaches these after verifying the JWT. Falls back
    to no scopes, which fails closed: the caller then needs an explicit
    event-local grant.

    Deliberately *not* ``user.scopes``. That column is the user's global
    scope set, and ``login``/``refresh`` may issue a token holding a narrower
    subset on purpose - reading the column here would silently upgrade a
    least-privilege token back to the user's full powers.
    """
    return getattr(user, "token_scopes", None) or []


def check_event_scope_or_403(
    user,
    event_id: int,
    scope: AuthScope | str,
    db: Session,
) -> None:
    """Allow the request when the user holds the token scope *or* an
    event-local grant for ``scope`` on ``event_id``.

    Raises 403 when the user has neither.
    """
    scope_value = scope.value if isinstance(scope, AuthScope) else scope
    if scope_value in token_scopes_of(user):
        return
    if event_user_scopes_service.has_scope(
        event_id=event_id,
        user_uuid=user.uuid,
        scope=scope_value,
        db=db,
    ):
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=f"Not enough permissions for event {event_id} (missing '{scope_value}')",
    )


def check_scope_on_new_owner_or_403(
    user,
    current_event_id: int,
    target_event_id: int,
    scope: AuthScope | str,
    db: Session,
) -> None:
    """Additionally require ``scope`` on the destination event of a move.

    Routes authorize against the resource's *current* owner, which is right
    for an ordinary edit - but a body field can name a different parent, and
    then the write also lands on the destination. Without this second check an
    admin of event A could push tickets (with attendee names and e-mail) into
    event B, where B's admins would read them.

    No-op when the parent is unchanged, so normal edits cost nothing.
    """
    if target_event_id == current_event_id:
        return
    check_event_scope_or_403(user, target_event_id, scope, db)


def resolve_event_id(
    resource: str,
    resource_id: int,
    db: Session,
) -> int | None:
    """Resolve the owning event id for an event / ticket-group / ticket id.

    Returns None when the resource does not exist.
    """
    if resource == "event":
        return resource_id if db.get(models.Event, resource_id) is not None else None
    if resource == "ticket_group":
        group = db.get(models.TicketGroup, resource_id)
        return group.event_id if group is not None else None
    if resource == "ticket":
        ticket = db.get(models.Ticket, resource_id)
        if ticket is None:
            return None
        # group_id has no enforceable FK on every backend (SQLite ignores it
        # unless asked), so a ticket can outlive its group. Treat that as
        # "cannot be authorised" rather than crashing the dependency, which
        # would make the row impossible to repair through the API.
        return ticket.group.event_id if ticket.group is not None else None
    raise ValueError(f"Unknown resource type '{resource}'")


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


def get_event_ids_with_scope(
    current_user,
    scope: AuthScope | str,
    db: Session,
) -> list[int] | None:
    """Event ids the user may read, or None when no filter should apply.

    Collection routes cannot authorize against a path parameter, so they
    narrow their query with this instead. A caller holding the scope globally
    sees every event and gets None - filtering such a user down to the events
    they happen to have rows on would make the global scope *weaker* than the
    local one. A locally-scoped caller is restricted to their grants.
    """
    scope_value = scope.value if isinstance(scope, AuthScope) else scope
    if scope_value in token_scopes_of(current_user):
        return None
    return event_user_scopes_service.get_event_ids_with_scope(
        user_uuid=current_user.uuid,
        scope=scope_value,
        db=db,
    )


__all__ = [
    "SUPPORTED_RESOURCES",
    "check_event_scope_or_403",
    "check_scope_on_new_owner_or_403",
    "get_event_ids_with_scope",
    "require_event_scope",
    "resolve_event_id",
    "token_scopes_of",
]
