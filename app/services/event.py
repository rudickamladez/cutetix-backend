"""Module for easier event management"""
from app.models import Event
from openpyxl import Workbook
from tempfile import NamedTemporaryFile
from io import BytesIO


def get_event_xlsx(event: Event):

    # Create workbook
    wb = Workbook(iso_dates=True)
    
    for tg in event.ticket_groups:
        # Create worksheet for ticket group
        ws = wb.create_sheet(title=tg.name)

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
                t.firstname,
                t.lastname,
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
