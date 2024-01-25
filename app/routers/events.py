from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app import models, schemas
from app.database import SessionLocal

router = APIRouter(
    prefix="/events",
    tags=["events"],
    # dependencies=[Depends(get_token_header)],
    responses={404: {"description": "Not found"}},
)


# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/", response_model=schemas.Event)
def create_event(event: schemas.EventCreate, db: Session = Depends(get_db)):
    return models.Event.create(db_session=db, **event.model_dump())


@router.get("/", response_model=list[schemas.Event])
def read_events(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return models.Event.get_all(db_session=db)


@router.get("/{event_id}", response_model=schemas.Event)
def read_event(event_id: int, db: Session = Depends(get_db)):
    return models.Event.get_by_id(db_session=db, id=event_id)


@router.patch(
    "/{event_id}", response_model=schemas.Event, description="Returns updated event."
)
def update_event(
    event_id: int, updated_event: schemas.EventBase, db: Session = Depends(get_db)
):
    return models.Event.update(db_session=db, id=event_id, **updated_event.model_dump())


@router.delete(
    "/{event_id}", response_model=schemas.Event, description="Returns deleted event."
)
def delete_event(event_id: int, db: Session = Depends(get_db)):
    return models.Event.delete(db_session=db, id=event_id)
