from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app import models
from app.schemas import ticket_group, extra
from app.database import engine, get_db
from app.routers.events import read_event_by_id
from app.services.ticket_groups import get_ticket_groups_with_capacity

router = APIRouter(
    prefix="/ticket_groups",
    tags=["ticket_groups"],
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "Not found"}
    },
)

# Create table if not exists
models.TicketGroup.__table__.create(bind=engine, checkfirst=True)


@router.post("/", response_model=ticket_group.TicketGroup)
def create_ticket_group(ticket_group: ticket_group.TicketGroupCreate, db: Session = Depends(get_db)):
    return models.TicketGroup.create(db_session=db, **ticket_group.model_dump())


@router.get("/", response_model=list[extra.TicketGroupExtra])
def read_ticket_groups(db: Session = Depends(get_db)):
    return models.TicketGroup.get_all(db_session=db)


@router.get("/by-event/{id}", response_model=list[ticket_group.TicketGroupWithCapacity])
def read_ticket_groups_by_event_id(id: int, db: Session = Depends(get_db)):
    event = read_event_by_id(id, db)
    return get_ticket_groups_with_capacity(event.ticket_groups)


@router.get("/{id}", response_model=ticket_group.TicketGroup)
def read_ticket_group_by_id(id: int, db: Session = Depends(get_db)):
    ticket_group = models.TicketGroup.get_by_id(db_session=db, id=id)
    if ticket_group is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ticket group not found"
        )
    return ticket_group


# @router.patch(
#     "/{id}",
#     response_model=ticket_group.TicketGroup,
#     description="Returns updated ticket group."
# )
# def update_ticket_group(
#     id: int, updated_ticket_group: ticket_group.TicketGroupBase, db: Session = Depends(get_db)
# ):
#     return models.TicketGroup.update(db_session=db, id=id, **updated_ticket_group.model_dump())

@router.put(
    "/{id}",
    response_model=ticket_group.TicketGroup,
    description="Returns updated ticket group."
)
def replace_ticket_group(
    id: int, updated_ticket_group: ticket_group.TicketGroupCreate, db: Session = Depends(get_db)
):
    return models.TicketGroup.update(db_session=db, id=id, **updated_ticket_group.model_dump())


@router.delete(
    "/{id}",
    response_model=ticket_group.TicketGroup,
    description="Returns deleted ticket group."
)
def delete_ticket_group(id: int, db: Session = Depends(get_db)):
    return models.TicketGroup.delete(db_session=db, id=id)
