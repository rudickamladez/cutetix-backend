from pydantic import BaseModel
from app.schemas.ticket import Ticket
# from app.schemas.event import Event


class TicketGroupBase(BaseModel):
    name: str
    capacity: int


class TicketGroupCreate(TicketGroupBase):
    event_id: int


class TicketGroup(TicketGroupBase):
    id: int
    tickets: list[Ticket] = []
    # event: Event

    class Config:
        from_attributes = True
