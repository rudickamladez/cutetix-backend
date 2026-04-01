"""Router for FIO bank API key management and manual payment sync."""
from fastapi import APIRouter, Depends, HTTPException, Security, status
from sqlalchemy.orm import Session

from app import models
from app.database import get_db
from app.middleware.auth import get_current_active_user
from app.schemas import event as event_schema
from app.services import fio as fio_service

router = APIRouter(
    prefix="/events",
    tags=["fio"],
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "Not found"},
    },
)


@router.put(
    "/{id}/fio-api-key",
    response_model=event_schema.Event,
    dependencies=[Security(get_current_active_user, scopes=["events:edit"])],
    summary="Set FIO API key for event",
    description=(
        "Sets or clears the FIO bank read-only API key for an event. "
        "The key is stored server-side and never returned in public responses. "
        "Requires `events:edit` scope."
    ),
)
def set_fio_api_key(
    id: int,
    body: event_schema.EventFioApiKey,
    db: Session = Depends(get_db),
):
    event = models.Event.get_by_id(db_session=db, id=id)
    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found",
        )
    event.fio_api_key = body.fio_api_key
    db.commit()
    db.refresh(event)
    return event


@router.post(
    "/{id}/fio/sync",
    response_model=dict,
    dependencies=[Security(get_current_active_user, scopes=["events:edit"])],
    summary="Manually trigger FIO payment sync for event",
    description=(
        "Fetches recent FIO bank transactions and marks matching tickets as paid "
        "by pairing the transaction variable symbol with the ticket ID. "
        "Requires `events:edit` scope."
    ),
)
def sync_fio_payments(id: int, db: Session = Depends(get_db)):
    event = models.Event.get_by_id(db_session=db, id=id)
    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found",
        )
    if not event.fio_api_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="FIO API key is not configured for this event",
        )
    count = fio_service.sync_event_payments(event=event, db=db)
    return {"updated_tickets": count}
