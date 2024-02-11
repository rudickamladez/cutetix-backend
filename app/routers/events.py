from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app import models
from app.schemas import event
from app.database import SessionLocal, engine

router = APIRouter(
    prefix="/events",
    tags=["events"],
    # dependencies=[Depends(get_token_header)],
    responses={404: {"description": "Not found"}},
)

# Create table if not exists
models.Event.__table__.create(bind=engine, checkfirst=True)


# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/", response_model=event.Event)
def create_event(event: event.EventCreate, db: Session = Depends(get_db)):
    return models.Event.create(db_session=db, **event.model_dump())


@router.get("/", response_model=list[event.Event])
def read_events(db: Session = Depends(get_db)):
    return models.Event.get_all(db_session=db)


@router.get("/{id}", response_model=event.Event)
def read_event_by_id(id: int, db: Session = Depends(get_db)):
    event = models.Event.get_by_id(db_session=db, id=id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return event


# @router.patch(
#     "/{id}", response_model=event.Event, description="Returns updated event."
# )
# def update_event(
#     id: int, updated_event: event.EventBase, db: Session = Depends(get_db)
# ):
#     return models.Event.update(db_session=db, id=id, **updated_event.model_dump())


@router.delete(
    "/{id}", response_model=event.Event, description="Returns deleted event."
)
def delete_event(id: int, db: Session = Depends(get_db)):
    event = models.Event.delete(db_session=db, id=id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return event
