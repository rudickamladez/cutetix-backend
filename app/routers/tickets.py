from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app import models
from app.schemas import ticket, extra
from app.database import SessionLocal, engine
from app.services import ticket as ticket_service

from app.services.ticket import create_ticket_easily

router = APIRouter(
    prefix="/tickets",
    tags=["tickets"],
    # dependencies=[Depends(get_token_header)],
    responses={404: {"description": "Not found"}},
)

# Create table if not exists
models.Ticket.__table__.create(bind=engine, checkfirst=True)


# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/", response_model=ticket.Ticket)
def create_ticket(ticket: ticket.TicketPatch, db: Session = Depends(get_db)):
    return models.Ticket.create(db_session=db, **ticket.model_dump())


@router.post("/easy", response_model=ticket.Ticket)
def create_ticket_easy(t: ticket.TicketCreate, db: Session = Depends(get_db)):
    t_db = create_ticket_easily(t, db)

    # Send error when cannot create ticket
    if t_db is None:
        raise HTTPException(status_code=400, detail="Can't create ticket.")
    return t_db


@router.post("/cancel", response_model=ticket.Ticket)
def cancel_ticket(ct: extra.CancelTicket, db: Session = Depends(get_db)):
    t_db = read_ticket_by_id(ct.id, db)

    # Send error when cannot cancel ticket
    if t_db is None:
        raise HTTPException(
            status_code=400,
            detail="Can't cancel ticket. Ticket with given ID not found."
        )
    ct_db: ticket.TicketPatch = ticket_service.cancel_ticket(
        ct=ct,
        t=t_db,
        db=db
    )
    if ct_db is None:
        raise HTTPException(
            status_code=400,
            detail="Wrong e-mail or ID."
        )
    return ct_db


@router.get("/", response_model=list[ticket.Ticket])
def read_tickets(db: Session = Depends(get_db)):
    return models.Ticket.get_all(db_session=db)


@router.get("/{id}", response_model=ticket.Ticket)
def read_ticket_by_id(id: int, db: Session = Depends(get_db)):
    ticket = models.Ticket.get_by_id(db_session=db, id=id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return ticket


@router.patch(
    "/{id}", response_model=ticket.Ticket, description="Returns updated ticket group."
)
def update_ticket(
    id: int, updated_ticket: ticket.TicketPatch, db: Session = Depends(get_db)
):
    return models.Ticket.update(db_session=db, id=id, **updated_ticket.model_dump())


@router.delete(
    "/{id}", response_model=ticket.Ticket, description="Returns deleted ticket group."
)
def delete_ticket(id: int, db: Session = Depends(get_db)):
    return models.Ticket.delete(db_session=db, id=id)
