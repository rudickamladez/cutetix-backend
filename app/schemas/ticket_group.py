from pydantic import BaseModel
from app.schemas.event import Event


class TicketGroupBase(BaseModel):
    name: str
    capacity: int


# class TicketGroupPatch(TicketGroupBase):
#     event_id: int


class TicketGroupCreate(TicketGroupBase):
    event_id: int


class TicketGroup(TicketGroupCreate):
    id: int
    event: Event

    class Config:
        from_attributes = True
