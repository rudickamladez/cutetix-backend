from pydantic import BaseModel
from datetime import datetime
from app.schemas.ticket_group import TicketGroup

class EventBase(BaseModel):
    name: str
    tickets_sales_start: datetime
    tickets_sales_end: datetime


class EventCreate(EventBase):
    pass


class Event(EventBase):
    id: int
    ticket_groups: list[TicketGroup] = []

    class Config:
        from_attributes = True