from fastapi import APIRouter, Depends, HTTPException, status, Security
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from app import models
from app.middleware.auth import get_current_active_user
from app.services import event as event_service
from app.schemas import event, extra
from app.database import get_db

router = APIRouter(
    prefix="/events",
    tags=["events"],
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "Not found"}
    },
)


@router.post(
    "/",
    response_model=event.Event,
    dependencies=[Security(
        get_current_active_user,
        scopes=["events:edit"]
    )],
    summary="Create event",
    description="Returns created object. Requires `events:edit` scope.",
)
def create_event(event: event.EventCreate, db: Session = Depends(get_db)):
    return models.Event.create(db_session=db, **event.model_dump())


@router.get(
    "/",
    response_model=list[extra.EventExtra],
    summary="Read events",
)
def read_events(db: Session = Depends(get_db)):
    return models.Event.get_all(db_session=db)


@router.get(
    "/capacity_summary/{id}",
    response_model=extra.CapacitySummary,
    summary="Get info about event occupation",
    description="Returns JSON object with capacity summary",
)
def get_capacity_summary(id: int, db: Session = Depends(get_db)):
    return event_service.get_event_capacity_summary(
        event=read_event_by_id(id, db),
    )


@router.get(
    "/{id}",
    response_model=extra.EventExtra,
    summary="Get info about event by ID",
    description="Returns event with given ID.",
)
def read_event_by_id(id: int, db: Session = Depends(get_db)):
    event = models.Event.get_by_id(db_session=db, id=id)
    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found"
        )
    return event


@router.patch(
    "/{id}",
    response_model=event.Event,
    dependencies=[Security(
        get_current_active_user,
        scopes=["events:edit"]
    )],
    summary="Partialy edit event",
    description="Returns updated event. Requires `events:edit` scope.",
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
    dependencies=[Security(
        get_current_active_user,
        scopes=["events:edit"]
    )],
    summary="Delete event",
    description="Returns deleted. Requires `events:edit` scope.",
)
def delete_event(id: int, db: Session = Depends(get_db)):
    event = models.Event.delete(db_session=db, id=id)
    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found"
        )
    return event


@router.get(
    "/xlsx/{id}",
    response_class=StreamingResponse,
    dependencies=[Security(
        get_current_active_user,
        scopes=["events:read"]
    )],
    summary="Generate event's XLSX",
    description="Returns XLSX file with tickets in groups. Requires `events:read` scope.",
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
