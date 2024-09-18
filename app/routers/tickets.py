from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app import models
from app.schemas import ticket
from app.database import SessionLocal, engine

# Here are the email package modules we'll need.
from app.services.mail import get_default_sender, get_mail_client

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
    # TODO: Add missing statements from previous versions

    # Write ticket to database
    t_db: ticket.Ticket = models.Ticket.create(db_session=db, **t.model_dump())

    # Send the email via SMTP server
    smtp_client = get_mail_client()
    smtp_client.send(
        subject="Vaše vstupenka",
        sender=get_default_sender(),
        receivers=[t_db.email],
        text=f"id:{t_db.id}",
        html=f"<h1>Hi, </h1><p>this is an email with ticket.id: {t_db.id}.</p>"
    )
    return t_db


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
