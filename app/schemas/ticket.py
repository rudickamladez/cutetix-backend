from pydantic import BaseModel, Field
from datetime import datetime
from app.models import TicketStatusEnum
from app.schemas.ticket_group import TicketGroup


class TicketBase(BaseModel):
    email: str
    firstname: str
    lastname: str
    status: TicketStatusEnum = TicketStatusEnum.new
    description: str = ""

class TicketPatch(TicketBase):
    group_id: int

class TicketCreate(TicketPatch):
    order_date: datetime = Field(default=datetime.now())


class Ticket(TicketCreate):
    id: int
    group: TicketGroup

    class Config:
        from_attributes = True
