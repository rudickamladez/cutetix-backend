from sqlalchemy import Column, DateTime, Integer, String
# from sqlalchemy.orm import relationship

from .database import Base


# class Ticket(Base):
#     __tablename__ = "tickets"

#     id = Column(Integer, primary_key=True, index=True)
#     email = Column(String)
#     firstname = Column(String)
#     lastname = Column(String)
#     order_date = Column(DateTime)
#     # maybe there should be an attribute for ticket cancellation

#     group = relationship("TicketGroup", back_populates="tickets")


# class TicketGroup(Base):
#     __tablename__ = "ticket_groups"

#     id = Column(Integer, primary_key=True, index=True)
#     name = Column(String, index=True)
#     capacity = Column(Integer)

#     tickets = relationship("Ticket", back_populates="group")
#     event = relationship("Event", back_populates="ticket_groups")

class Event(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    tickets_sales_start = Column(DateTime)
    tickets_sales_end = Column(DateTime)

    # ticket_groups = relationship("Event", back_populates="event")
