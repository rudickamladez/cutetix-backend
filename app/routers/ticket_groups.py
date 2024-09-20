from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app import models
from app.schemas import ticket_group, extra
from app.database import SessionLocal, engine

router = APIRouter(
    prefix="/ticket_groups",
    tags=["ticket_groups"],
    # dependencies=[Depends(get_token_header)],
    responses={404: {"description": "Not found"}},
)

# Create table if not exists
models.TicketGroup.__table__.create(bind=engine, checkfirst=True)


# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/", response_model=ticket_group.TicketGroup)
def create_ticket_group(ticket_group: ticket_group.TicketGroupCreate, db: Session = Depends(get_db)):
    return models.TicketGroup.create(db_session=db, **ticket_group.model_dump())


@router.get("/", response_model=list[extra.TicketGroupExtra])
def read_ticket_groups(db: Session = Depends(get_db)):
    return models.TicketGroup.get_all(db_session=db)


@router.get("/{id}", response_model=ticket_group.TicketGroup)
def read_ticket_group_by_id(id: int, db: Session = Depends(get_db)):
    ticket_group = models.TicketGroup.get_by_id(db_session=db, id=id)
    if ticket_group is None:
        raise HTTPException(status_code=404, detail="Ticket group not found")
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


@router.delete(
    "/{id}",
    response_model=ticket_group.TicketGroup,
    description="Returns deleted ticket group."
)
def delete_ticket_group(id: int, db: Session = Depends(get_db)):
    return models.TicketGroup.delete(db_session=db, id=id)
