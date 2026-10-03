
from fastapi import APIRouter, Depends, HTTPException, Response, Security, status
from sqlalchemy.orm import Session
from app.auth_scopes import AuthScopes
from datetime import datetime

from app import models
from app.middleware.auth import get_current_active_user, oauth2_scheme
from app.middleware.event_scopes import require_event_scope, check_event_scope_or_403
from app.models import TicketStatusEnum
from app.schemas import ticket, extra
from app.database import get_db
from app.schemas.user import UserFromDB
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
    dependencies=[Security(
        get_current_active_user,
        scopes=[AuthScopes.Event.Edit.value]
    )],
    summary="Create ticket",
    description=f"Returns created object. Requires `{AuthScopes.Ticket.Edit.value}` scope.",
)
def create(
    ticket: ticket.TicketCreate,
    send_mail: bool = True,
    current_user: UserFromDB = Depends(get_current_active_user),
    access_token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    if ticket.order_date is None:
        ticket.order_date = datetime.now()
    group = db.get(models.TicketGroup, ticket.group_id)
    if group is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ticket group not found",
        )
    check_event_scope_or_403(
        current_user,
        access_token,
        group.event_id,
        AuthScopes.Ticket.Edit,
        db,
    )
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
    t_db = read_ticket_by_id(ct.id, db)

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
    dependencies=[Security(get_current_active_user, scopes=[
                           AuthScopes.Ticket.Read.value])],
    summary="Read tickets",
    description=f"Returns list of object. Requires `{AuthScopes.Ticket.Read.value}` scope.",
)
def read_tickets(
    db: Session = Depends(get_db)
):
    """
    Returns a list of all tickets. Requires the user to have the global `Ticket.Read` scope.
    """
    return models.Ticket.get_all(db_session=db)


@router.get(
    "/{id}",
    response_model=ticket.Ticket,
    summary="Read ticket by ID",
)
def read_ticket_by_id(
    id: int,
    db: Session = Depends(get_db)
):
    ticket = models.Ticket.get_by_id(db_session=db, id=id)
    if ticket is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ticket not found"
        )
    return ticket


@router.put(
    "/{id}",
    response_model=ticket.Ticket,
    dependencies=[Depends(require_event_scope(
        AuthScopes.Ticket.Edit, resource="ticket"))],
    summary="Edit ticket",
    description=f"Returns updated. Requires `{AuthScopes.Ticket.Edit.value}` scope.",
)
def update_ticket(
    id: int,
    updated_ticket: ticket.TicketPatch,
    current_user: UserFromDB = Depends(get_current_active_user),
    access_token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    group = db.get(models.TicketGroup, updated_ticket.group_id)
    if group is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ticket group not found",
        )
    check_event_scope_or_403(
        current_user,
        access_token,
        group.event_id,
        AuthScopes.Ticket.Edit,
        db,
    )
    return models.Ticket.update(db_session=db, id=id, **updated_ticket.model_dump())


@router.delete(
    "/{id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    dependencies=[Depends(require_event_scope(
        AuthScopes.Ticket.Edit, resource="ticket"))],
    summary="Delete ticket",
    description=f"Returns 204 if successful. Requires `{AuthScopes.Ticket.Edit.value}` scope.",
)
def delete_ticket(
    id: int,
    db: Session = Depends(get_db)
):
    if models.Ticket.delete(db_session=db, id=id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ticket not found"
        )
