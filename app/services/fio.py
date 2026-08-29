"""Service for FIO bank API integration."""
import logging
from datetime import datetime, timedelta
from typing import Optional

import httpx
from sqlalchemy.orm import Session

from app import models

logger = logging.getLogger(__name__)

FIO_BASE_URL = "https://fioapi.fio.cz/v1/rest"
LOOKBACK_DAYS = 31


def fetch_transactions(api_key: str) -> list[dict]:
    """Fetch transactions from FIO API for the last LOOKBACK_DAYS days."""
    now = datetime.now()
    date_to = now.strftime("%Y-%m-%d")
    date_from = (now - timedelta(days=LOOKBACK_DAYS)).strftime("%Y-%m-%d")
    url = f"{FIO_BASE_URL}/periods/{api_key}/{date_from}/{date_to}/transactions.json"
    with httpx.Client(timeout=30.0) as client:
        response = client.get(url)
        response.raise_for_status()
        data = response.json()
    transactions = (
        data.get("accountStatement", {})
        .get("transactionList", {})
        .get("transaction", []) or []
    )
    return transactions


def get_variable_symbol(transaction: dict) -> Optional[str]:
    """Extract the variable symbol (column5) from a FIO transaction."""
    vs_col = transaction.get("column5")
    if vs_col and vs_col.get("value") is not None:
        # FIO returns VS as a float-like number; convert to int string
        return str(int(vs_col["value"]))
    return None


def sync_event_payments(event: models.Event, db: Session) -> int:
    """
    Fetch FIO transactions for the event and mark matching tickets as paid
    by pairing the transaction variable symbol with the ticket ID.

    Returns the number of tickets updated to paid status.
    """
    if not event.fio_api_key:
        return 0

    try:
        transactions = fetch_transactions(event.fio_api_key)
    except Exception as exc:
        logger.error(
            "Failed to fetch FIO transactions for event %s: %s",
            event.id,
            exc,
        )
        return 0

    # Build a mapping of ticket ID → ticket object for tickets in this event
    tickets_by_id: dict[int, models.Ticket] = {
        ticket.id: ticket
        for group in event.ticket_groups
        for ticket in group.tickets
    }

    updated = 0
    for transaction in transactions:
        vs = get_variable_symbol(transaction)
        if vs is None:
            continue
        try:
            ticket_id = int(vs)
        except ValueError:
            continue

        ticket = tickets_by_id.get(ticket_id)
        if ticket is None:
            continue
        # Skip already-paid or cancelled tickets
        if ticket.status in (
            models.TicketStatusEnum.paid,
            models.TicketStatusEnum.cancelled,
        ):
            continue

        ticket.status = models.TicketStatusEnum.paid
        updated += 1
        logger.info(
            "Ticket %s for event %s marked as paid via FIO",
            ticket_id,
            event.id,
        )

    if updated > 0:
        db.commit()

    return updated


def sync_all_events(db: Session) -> None:
    """Sync FIO payments for all events that have a FIO API key configured."""
    events = models.Event.get_all(db_session=db)
    for event in events:
        if event.fio_api_key:
            count = sync_event_payments(event=event, db=db)
            if count > 0:
                logger.info(
                    "Event %s: %s ticket(s) marked as paid via FIO",
                    event.id,
                    count,
                )
