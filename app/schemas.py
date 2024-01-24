from pydantic import BaseModel
from datetime import datetime
from enum import Enum, auto


class TicketStatusEnum(Enum):
    new = auto()
    confirmed = auto()
    paid = auto()
    cancelled = auto()


class TicketBase(BaseModel):
    email: str
    filename: str
    lastname: str
    status: TicketStatusEnum = TicketStatusEnum.new
    description: str = ""


class TicketCreate(TicketBase):
    order_date: datetime = datetime.utcnow()


class Ticket(TicketBase):
    id: int
    order_date: datetime

    class Config:
        from_attributes = True


class TicketGroupBase(BaseModel):
    name: str
    capacity: int


class TicketGroupCreate(TicketGroupBase):
    pass


class TicketGroup(TicketGroupBase):
    id: int
    # tickets: list[Ticket] = []

    class Config:
        from_attributes = True


class EventBase(BaseModel):
    name: str
    tickets_sales_start: datetime
    tickets_sales_end: datetime


class EventCreate(EventBase):
    pass


class Event(EventBase):
    id: int
    # ticket_groups: list[TicketGroup] = []

    class Config:
        from_attributes = True


class RootResponse(BaseModel):
    git: str
    message: str
    time: datetime

    class Config:
        from_attributes = True
