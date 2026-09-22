from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session
from datetime import datetime

from app import models
from app.auth_scopes import AuthScope
from app.middleware.auth import (
    get_current_active_user,
    get_event_ids_with_scope,
    require_event_scope_for_ticket,
    require_event_scope_for_ticket_group,
)
from app.models import TicketStatusEnum
from app.schemas import ticket, extra
from app.schemas.user import UserFromDB
from app.database import get_db
from app.services import ticket as ticket_service

from app.services.ticket import create_ticket, create_ticket_easily

router = APIRouter(
    prefix="/tickets",
    tags=["tickets"],
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "Not found"}
    },
)


@router.post(
    "/",
    response_model=ticket.Ticket,
    summary="Create ticket",
    description="Returns created object. Requires event-local `tickets:edit` scope.",
)
def create(
    ticket: ticket.TicketCreate,
    current_user: Annotated[UserFromDB, Depends(get_current_active_user)],
    send_mail: bool = True,
    db: Session = Depends(get_db)
):
    require_event_scope_for_ticket_group(
        ticket_group_id=ticket.group_id,
        current_user=current_user,
        scope=AuthScope.TICKETS_EDIT,
        db=db,
    )
    if ticket.order_date is None:
        ticket.order_date = datetime.now()
    return create_ticket(ticket, send_mail=send_mail, db=db)


@router.post(
    "/easy",
    response_model=ticket.Ticket,
    summary="Create ticket easily",
    description="Returns created object. Does not require any security scopes."
)
def create_ticket_easy(t: ticket.TicketCreate, db: Session = Depends(get_db)):
    # Prevent random clients create (for examples) paid tickets
    t.status = TicketStatusEnum.new
    t_db = create_ticket_easily(t, db)

    # Send error when cannot create ticket
    if t_db is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can't create ticket."
        )
    return t_db


@router.post(
    "/cancel",
    response_model=ticket.Ticket,
    summary="Cancel ticket",
    description="This route enable users cancel their tickets without any admin work. Does not require any security scopes."
)
def cancel_ticket(ct: extra.CancelTicket, db: Session = Depends(get_db)):
    t_db = models.Ticket.get_by_id(db_session=db, id=ct.id)

    # Send error when cannot cancel ticket
    if t_db is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can't cancel ticket. Ticket with given ID not found."
        )
    try:
        ct_db: ticket.TicketPatch = ticket_service.cancel_ticket(
            ct=ct,
            t=t_db,
            db=db
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    return ct_db


@router.get(
    "/",
    response_model=list[ticket.Ticket],
    summary="Read tickets",
    description="Returns tickets from events where the user has event-local `tickets:read` scope.",
)
def read_tickets(
    current_user: Annotated[UserFromDB, Depends(get_current_active_user)],
    db: Session = Depends(get_db)
):
    event_ids = get_event_ids_with_scope(
        current_user=current_user,
        scope=AuthScope.TICKETS_READ,
        db=db,
    )
    return ticket_service.get_tickets_by_event_ids(
        event_ids=event_ids,
        db=db,
    )


@router.get(
    "/{id}",
    response_model=ticket.Ticket,
    summary="Read ticket by ID",
    description="Returns ticket by ID. Requires event-local `tickets:read` scope.",
)
def read_ticket_by_id(
    id: int,
    current_user: Annotated[UserFromDB, Depends(get_current_active_user)],
    db: Session = Depends(get_db)
):
    return require_event_scope_for_ticket(
        ticket_id=id,
        current_user=current_user,
        scope=AuthScope.TICKETS_READ,
        db=db,
    )


@router.put(
    "/{id}",
    response_model=ticket.Ticket,
    summary="Edit ticket",
    description="Returns updated ticket. Requires event-local `tickets:edit` scope.",
)
def update_ticket(
    id: int,
    updated_ticket: ticket.TicketPatch,
    current_user: Annotated[UserFromDB, Depends(get_current_active_user)],
    db: Session = Depends(get_db)
):
    existing_ticket = require_event_scope_for_ticket(
        ticket_id=id,
        current_user=current_user,
        scope=AuthScope.TICKETS_EDIT,
        db=db,
    )
    if updated_ticket.group_id != existing_ticket.group_id:
        require_event_scope_for_ticket_group(
            ticket_group_id=updated_ticket.group_id,
            current_user=current_user,
            scope=AuthScope.TICKETS_EDIT,
            db=db,
        )
    return models.Ticket.update(db_session=db, id=id, **updated_ticket.model_dump())


@router.delete(
    "/{id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Delete ticket",
    description="Returns 204 if successful. Requires event-local `tickets:edit` scope.",
)
def delete_ticket(
    id: int,
    current_user: Annotated[UserFromDB, Depends(get_current_active_user)],
    db: Session = Depends(get_db)
):
    require_event_scope_for_ticket(
        ticket_id=id,
        current_user=current_user,
        scope=AuthScope.TICKETS_EDIT,
        db=db,
    )
    if models.Ticket.delete(db_session=db, id=id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ticket not found"
        )
