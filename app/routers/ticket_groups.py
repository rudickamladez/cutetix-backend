from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session
from app import models
from app.auth_scopes import AuthScope
from app.middleware.auth import (
    get_current_active_user,
    get_event_ids_with_scope,
    require_event_scope,
    require_event_scope_for_ticket_group,
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


@router.post(
    "/",
    response_model=ticket_group.TicketGroup,
    summary="Create ticket group",
    description="Returns created object. Requires event-local `ticket_groups:edit` scope.",
)
def create_ticket_group(
    ticket_groups: ticket_group.TicketGroupCreate,
    current_user: Annotated[UserFromDB, Depends(get_current_active_user)],
    db: Session = Depends(get_db)
):
    require_event_scope(
        event_id=ticket_groups.event_id,
        current_user=current_user,
        scope=AuthScope.TICKET_GROUPS_EDIT,
        db=db,
    )
    return models.TicketGroup.create(db_session=db, **ticket_groups.model_dump())


@router.get(
    "/",
    response_model=list[extra.TicketGroupExtra],
    summary="Read ticket groups",
    description="Returns ticket groups from events where the user has event-local `ticket_groups:read` scope.",
)
def read_ticket_groups(
    current_user: Annotated[UserFromDB, Depends(get_current_active_user)],
    db: Session = Depends(get_db),
):
    event_ids = get_event_ids_with_scope(
        current_user=current_user,
        scope=AuthScope.TICKET_GROUPS_READ,
        db=db,
    )
    if len(event_ids) == 0:
        return []
    return db.query(models.TicketGroup).filter(
        models.TicketGroup.event_id.in_(event_ids)
    ).order_by(models.TicketGroup.id).all()


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
    summary="Read ticket group by ID",
    description="Returns ticket group by ID. Requires event-local `ticket_groups:read` scope.",
)
def read_ticket_group_by_id(
    id: int,
    current_user: Annotated[UserFromDB, Depends(get_current_active_user)],
    db: Session = Depends(get_db)
):
    return require_event_scope_for_ticket_group(
        ticket_group_id=id,
        current_user=current_user,
        scope=AuthScope.TICKET_GROUPS_READ,
        db=db,
    )


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
    summary="Edit ticket group",
    description="Returns updated object. Requires event-local `ticket_groups:edit` scope.",
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
    existing_ticket_group = require_event_scope_for_ticket_group(
        ticket_group_id=id,
        current_user=current_user,
        scope=AuthScope.TICKET_GROUPS_EDIT,
        db=db,
    )
    if updated_ticket_groups.event_id != existing_ticket_group.event_id:
        require_event_scope(
            event_id=updated_ticket_groups.event_id,
            current_user=current_user,
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
    summary="Delete ticket group",
    description="Returns 204 if successful. Requires event-local `ticket_groups:edit` scope.",
)
def delete_ticket_group(
    id: int,
    current_user: Annotated[UserFromDB, Depends(get_current_active_user)],
    db: Session = Depends(get_db)
):
    require_event_scope_for_ticket_group(
        ticket_group_id=id,
        current_user=current_user,
        scope=AuthScope.TICKET_GROUPS_EDIT,
        db=db,
    )
    if models.TicketGroup.delete(db_session=db, id=id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ticket group not found",
        )
