"""Module for easier event management"""
from app.models import Event, TicketStatusEnum
from app.schemas import extra
from openpyxl import Workbook
from openpyxl.workbook.child import INVALID_TITLE_REGEX
from tempfile import NamedTemporaryFile
from io import BytesIO
import sys
import re


def get_event_capacity_summary(event: Event):
    if not event:
        print(
            "There is not event",
            file=sys.stderr,
        )
    
    # Prepare response
    cs = extra.CapacitySummary()

    for tg in event.ticket_groups:
        cs.total += tg.capacity
        tg_free = tg.capacity
        for t in tg.tickets:
            # Increase per status
            if t.status == TicketStatusEnum.new:
                cs.reserved += 1
            # elif t.status == TicketStatusEnum.confirmed:
            elif t.status == TicketStatusEnum.paid:
                cs.paid += 1
            elif t.status == TicketStatusEnum.cancelled:
                cs.cancelled += 1

            # Decrase free tickets
            if not t.status == TicketStatusEnum.cancelled:
                tg_free -= 1
        cs.free += tg_free
    return cs


def get_event_xlsx(event: Event):

    # Create workbook
    wb = Workbook(iso_dates=True)
    
    for tg in event.ticket_groups:
        # Create worksheet for ticket group
        title = re.sub(INVALID_TITLE_REGEX, '_', tg.name)
        ws = wb.create_sheet(title=title)

        # Create heading
        ws.append([
            "Lastname",
            "Firsname",
            "E-mail",
            "Description",
            "Status",
            "Ticket ID",
            "Order date",
        ])

        for t in tg.tickets:
            # Add row with ticket
            ws.append([
                t.lastname,
                t.firstname,
                t.email,
                t.description,
                str(t.status),
                t.id,
                t.order_date,
            ])

    # Remove default blank sheet
    if 'Sheet' in wb.sheetnames:
        del wb['Sheet']

    # Return workbook
    with NamedTemporaryFile() as tmp:
        wb.save(tmp.name)
        return BytesIO(tmp.read())
