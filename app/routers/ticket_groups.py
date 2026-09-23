from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session
from app import models
from app.auth_scopes import AuthScope
from app.middleware.auth import get_current_active_user
from app.middleware.event_scopes import (
    check_event_scope_or_403,
    check_scope_on_new_owner_or_403,
    get_event_ids_with_scope,
    require_event_scope,
)
from app.schemas import ticket_group, extra
from app.schemas.user import UserFromDB
from app.database import get_db
from app.routers.events import read_event_by_id
from app.services.ticket_groups import get_ticket_groups_with_capacity

router = APIRouter(
    prefix="/ticket_groups",
    tags=["ticket_groups"],
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "Not found"}
    },
)


def _require_event_exists(db: Session, event_id: int) -> None:
    """404 rather than a 500 from the FK layer when a body names no event."""
    if models.Event.get_by_id(db_session=db, id=event_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found",
        )


def _readable_event_ids(
    scopes: tuple[AuthScope, ...],
    current_user,
    db: Session,
) -> list[int] | None:
    """Events the caller holds *every* listed scope on; None means no filter.

    ``get_event_ids_with_scope`` returns None for a global holder, so the
    intersection is only taken between callers who are actually restricted.
    """
    allowed: list[int] | None = None
    for scope in scopes:
        scoped = get_event_ids_with_scope(
            current_user=current_user,
            scope=scope,
            db=db,
        )
        if scoped is None:
            continue
        allowed = scoped if allowed is None else sorted(set(allowed) & set(scoped))
        if len(allowed) == 0:
            return []
    return allowed


@router.post(
    "/",
    response_model=ticket_group.TicketGroup,
    summary="Create ticket group",
    description=(
        "Returns created object. Requires the global `ticket_groups:edit` "
        "scope or an event-local `ticket_groups:edit` grant for the event "
        "named in the request body."
    ),
)
def create_ticket_group(
    ticket_groups: ticket_group.TicketGroupCreate,
    current_user: Annotated[UserFromDB, Depends(get_current_active_user)],
    db: Session = Depends(get_db)
):
    # The event comes from the request body rather than a path parameter, so
    # the either/or check runs inline instead of through a dependency.
    _require_event_exists(db, ticket_groups.event_id)
    check_event_scope_or_403(
        user=current_user,
        event_id=ticket_groups.event_id,
        scope=AuthScope.TICKET_GROUPS_EDIT,
        db=db,
    )
    return models.TicketGroup.create(db_session=db, **ticket_groups.model_dump())


@router.get(
    "/",
    response_model=list[extra.TicketGroupExtra],
    summary="Read ticket groups",
    description=(
        "Returns ticket groups from events where the user holds both "
        "`ticket_groups:read` and `tickets:read` (globally or per event) - "
        "each row embeds its tickets' personal data."
    ),
)
def read_ticket_groups(
    current_user: Annotated[UserFromDB, Depends(get_current_active_user)],
    db: Session = Depends(get_db),
):
    # Each TicketGroupExtra embeds its tickets, so a caller who may read group
    # metadata but not attendees must not receive them; both grants are
    # required on the same event.
    event_ids = _readable_event_ids(
        (AuthScope.TICKET_GROUPS_READ, AuthScope.TICKETS_READ),
        current_user,
        db,
    )
    if event_ids is not None:
        if len(event_ids) == 0:
            return []
        return db.query(models.TicketGroup).filter(
            models.TicketGroup.event_id.in_(event_ids)
        ).order_by(models.TicketGroup.id).all()
    return models.TicketGroup.get_all(db_session=db)


@router.get(
    "/by-event/{id}",
    response_model=list[ticket_group.TicketGroupWithCapacity],
    summary="Read ticket group by event's  ID",
)
def read_ticket_groups_by_event_id(
    id: int,
    db: Session = Depends(get_db)
):
    event = read_event_by_id(id, db)
    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found."
        )
    return get_ticket_groups_with_capacity(event.ticket_groups)


@router.get(
    "/{id}",
    response_model=ticket_group.TicketGroup,
    dependencies=[
        Depends(require_event_scope(
            AuthScope.TICKET_GROUPS_READ, resource="ticket_group")),
        Depends(require_event_scope(
            AuthScope.TICKETS_READ, resource="ticket_group")),
    ],
    summary="Read ticket group by ID",
    description=(
        "Returns ticket group by ID. Requires the global `ticket_groups:read` "
        "and `tickets:read` scopes, or event-local grants of both on the "
        "owning event - the response embeds the group's tickets."
    ),
)
def read_ticket_group_by_id(id: int, db: Session = Depends(get_db)):
    ticket_group_db = models.TicketGroup.get_by_id(db_session=db, id=id)
    if ticket_group_db is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ticket group not found",
        )
    return ticket_group_db


# @router.patch(
#     "/{id}",
#     response_model=ticket_group.TicketGroup,
#     description="Returns updated ticket group."
# )
# def update_ticket_group(
#     id: int, updated_ticket_groups: ticket_group.TicketGroupBase, db: Session = Depends(get_db)
# ):
#     return models.TicketGroup.update(db_session=db, id=id, **updated_ticket_group.model_dump())

@router.put(
    "/{id}",
    response_model=ticket_group.TicketGroup,
    dependencies=[Depends(
        require_event_scope(AuthScope.TICKET_GROUPS_EDIT, resource="ticket_group")
    )],
    summary="Edit ticket group",
    description=(
        "Returns updated object. Requires the global `ticket_groups:edit` "
        "scope or an event-local `ticket_groups:edit` grant for the owning "
        "event - and, when moving the group to another event, for the "
        "destination event too."
    ),
)
def edit_ticket_group(
    id: int,
    updated_ticket_groups: ticket_group.TicketGroupCreate,
    current_user: Annotated[UserFromDB, Depends(get_current_active_user)],
    db: Session = Depends(get_db),
):
    # TODO: Test this use case
    # if id != updated_ticket_group.id:
    #     raise HTTPException(
    #         status_code=status.HTTP_400_BAD_REQUEST,
    #         detail="ID in path does not match ID in user's body."
    #     )
    group_db = models.TicketGroup.get_by_id(db_session=db, id=id)
    _require_event_exists(db, updated_ticket_groups.event_id)
    # The dependency authorized the group's current event; `event_id` in the
    # body can name a different one, and the write lands there as well.
    check_scope_on_new_owner_or_403(
        user=current_user,
        current_event_id=group_db.event_id,
        target_event_id=updated_ticket_groups.event_id,
        scope=AuthScope.TICKET_GROUPS_EDIT,
        db=db,
    )
    return models.TicketGroup.update(
        db_session=db,
        id=id,
        **updated_ticket_groups.model_dump(),
    )


@router.delete(
    "/{id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    dependencies=[Depends(
        require_event_scope(AuthScope.TICKET_GROUPS_EDIT, resource="ticket_group")
    )],
    summary="Delete ticket group",
    description=(
        "Returns 204 if successful. Requires the global `ticket_groups:edit` "
        "scope or an event-local `ticket_groups:edit` grant for the owning "
        "event."
    ),
)
def delete_ticket_group(
    id: int,
    db: Session = Depends(get_db)
):
    if models.TicketGroup.delete(db_session=db, id=id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ticket group not found",
        )
