"""Module for easier ticket groups management"""
from app.schemas import extra, ticket


def get_ticket_groups_with_capacity(tgs: list[extra.TicketGroupExtra]):
    for tg in tgs:
        tg.free_positions = 0
        tg.paid = 0
        tg.cancelled = 0
        for t in tg.tickets:
            if t.status in [
                ticket.TicketStatusEnum.new,
                ticket.TicketStatusEnum.confirmed,
                ticket.TicketStatusEnum.paid
            ]:
                tg.paid += 1
            elif t.status == ticket.TicketStatusEnum.cancelled:
                tg.cancelled += 1
        free_positions = tg.capacity - tg.paid
        if free_positions > 0:
            tg.free_positions = free_positions
    return tgs
