"""Module for easier ticket management"""
from sqlalchemy.orm import Session
from sqlalchemy import func
from app import models
from app.schemas import ticket
from datetime import datetime
import sys

# Here are the email package modules we'll need.
# from .mail import get_default_sender, get_mail_client

def can_create_ticket_in_ticket_group(
        group_id: int,
        db: Session
    ):
    # Get ticket group from database
    tg = models.TicketGroup.get_by_id(db_session=db, id=group_id)

    # Ticket group is not in database
    if tg is None:
        print(
            "Ticket group is not in database",
            file=sys.stderr,
        )
        return False

    # Prepere event for checks
    event = models.Event.get_by_id(db_session=db, id=tg.event_id)
    
    # Event is not in database
    if event is None:
        print(
            "Event is not in database.",
            file=sys.stderr
        )
        return False

    # Check if it's not end of reservations for the event
    if event.tickets_sales_end < datetime.now():
        print(
            "Reservations are closed.",
            file=sys.stderr
        )
        return False

    # Check if reservations started for the event
    if event.tickets_sales_start > datetime.now():
        print(
            "Reservations are not opened yet.",
            file=sys.stderr
        )
        return False
    
    # Check if there is place for the ticket in ticket group
    count_of_tickets_in_tg = db.query(func.count(models.Ticket.id)).filter(models.Ticket.group_id == group_id).scalar()
    if count_of_tickets_in_tg >= tg.capacity:
        return False
    return True

def create_ticket_easily(
        t: ticket.TicketCreate,
        db: Session
    ):
    
    # Check if they can create ticket
    if not can_create_ticket_in_ticket_group(t.group_id, db=db):
        return None

    # Write ticket to database
    t_db: ticket.Ticket = models.Ticket.create(db_session=db, **t.model_dump())

    # Send the email via SMTP server
    # smtp_client = get_mail_client()
    # smtp_client.send(
    #     subject="Vaše vstupenka",
    #     sender=get_default_sender(),
    #     receivers=[t_db.email],
    #     text=f"Dobrý den,\n\nzde je potvrzení Vaší rezervace:\nID: { t_db.id }\nKřestní jméno: { t_db.firstname }\nPříjmení: { t_db.lastname }\nE-mail: { t_db.email }\nČas: { t_db }",
    # )
    return t_db
