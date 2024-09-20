from pydantic import BaseModel
from app.schemas.event import Event
from app.schemas.ticket_group import TicketGroup
from app.schemas.ticket import Ticket


class CapacitySummary(BaseModel):
    paid: int = 0
    free: int = 0
    reserved: int = 0
    cancelled: int = 0
    total: int = 0

    class Config:
        from_attributes = True

class TicketGroupExtra(TicketGroup):
    tickets: list[Ticket] = []

    class Config:
        from_attributes = True

class EventExtra(Event):
    ticket_groups: list[TicketGroup] = []

    class Config:
        from_attributes = True
