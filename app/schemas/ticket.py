from pydantic import BaseModel
from datetime import datetime
from app.models import TicketStatusEnum


class TicketBase(BaseModel):
    email: str
    firstname: str
    lastname: str
    status: TicketStatusEnum = TicketStatusEnum.new
    description: str = ""


class TicketCreate(TicketBase):
    order_date: datetime = datetime.utcnow()
    group_id: int


class TicketPatch(TicketBase):
    order_date: datetime
    group_id: int


class Ticket(TicketPatch):
    id: int

    class Config:
        from_attributes = True
