from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from app import models
from app.services import event as event_service
from app.schemas import event, extra
from app.database import engine, get_db

router = APIRouter(
    prefix="/events",
    tags=["events"],
    # dependencies=[Depends(get_token_header)],
    responses={404: {"description": "Not found"}},
)

# Create table if not exists
models.Event.__table__.create(bind=engine, checkfirst=True)


@router.post("/", response_model=event.Event)
def create_event(event: event.EventCreate, db: Session = Depends(get_db)):
    return models.Event.create(db_session=db, **event.model_dump())


@router.get("/", response_model=list[extra.EventExtra])
def read_events(db: Session = Depends(get_db)):
    return models.Event.get_all(db_session=db)


@router.get("/capacity_summary/{id}", response_model=extra.CapacitySummary)
def get_capacity_summary(id: int, db: Session = Depends(get_db)):
    return event_service.get_event_capacity_summary(
        event=read_event_by_id(id, db),
    )


@router.get("/{id}", response_model=extra.EventExtra)
def read_event_by_id(id: int, db: Session = Depends(get_db)):
    event = models.Event.get_by_id(db_session=db, id=id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return event


@router.patch(
    "/{id}",
    response_model=event.Event,
    description="Returns updated event."
)
def update_event(
    id: int,
    updated_event: event.EventBase,
    db: Session = Depends(get_db)
):
    return models.Event.update(db_session=db, id=id, **updated_event.model_dump())


@router.delete(
    "/{id}",
    response_model=event.Event,
    description="Returns deleted event."
)
def delete_event(id: int, db: Session = Depends(get_db)):
    event = models.Event.delete(db_session=db, id=id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return event


@router.get(
    "/xlsx/{id}",
    response_class=StreamingResponse,
    description="Returns XLSX file with ticket in groups."
)
def get_event_xlsx(id: int, format_for_libor: bool = False, db: Session = Depends(get_db)):
    event = read_event_by_id(
        id=id,
        db=db
    )
    if format_for_libor:
        table_bytes = event_service.get_event_xlsx_for_libor(event=event)
    else:
        table_bytes = event_service.get_event_xlsx(event=event)
    return StreamingResponse(
        table_bytes,
        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={
            "Content-Disposition": f"attachment; filename=cutetix-event-{id}.xlsx"}
    )
