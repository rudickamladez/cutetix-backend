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


class Ticket(TicketBase):
    id: int
    order_date: datetime

    class Config:
        from_attributes = True