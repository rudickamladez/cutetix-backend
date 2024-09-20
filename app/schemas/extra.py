from app.schemas.event import Event
from app.schemas.ticket_group import TicketGroup
from app.schemas.ticket import Ticket


class TicketGroupExtra(TicketGroup):
    tickets: list[Ticket] = []

    class Config:
        from_attributes = True

class EventExtra(Event):
    ticket_groups: list[TicketGroup] = []

    class Config:
        from_attributes = True
