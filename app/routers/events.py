from typing_extensions import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Response, status, Security
from fastapi.responses import StreamingResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from app import models
from app.auth_scopes import AuthScopes, SCOPE_MAX_LENGTH
from app.middleware.auth import get_current_active_user
from app.middleware.event_scopes import require_event_scope
from app.services import event as event_service
from app.services import ticket as ticket_service
from app.schemas import event, event_user_scope, extra, ticket, ticket_group
from uuid import UUID
from app.database import get_db
from app.services import event_user_scopes as event_user_scopes_service

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
    # No event exists yet, so there is nothing a local grant could attach to:
    # creating an event stays a globally-scoped operation.
    dependencies=[Security(
        get_current_active_user,
        scopes=[AuthScopes.Event.Edit.value]
    )],
    summary="Create event",
    description=f"Returns created object. Requires `{AuthScopes.Event.Edit.value}` scope.",
)
def create_event(
    event: event.EventCreate,
    current_user: Annotated[models.User, Depends(get_current_active_user)],
    db: Session = Depends(get_db)
):
    # Event creation and the creator's event-local grants share one
    # transaction, so a failure cannot leave an unmanageable orphan event.
    event_db = models.Event(**event.model_dump())
    db.add(event_db)
    try:
        db.flush()  # assign the autoincrement id before granting scopes
        event_user_scopes_service.grant_scopes_staged(
            event_id=event_db.id,
            user_uuid=current_user.uuid,
            scopes=AuthScopes.event_scopes_values(),
            db=db,
        )
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise
    db.refresh(event_db)
    return event_db


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


@router.get(
    "/{id}/tickets",
    response_model=list[ticket.Ticket],
    dependencies=[Depends(
        require_event_scope(AuthScopes.Ticket.Read)
    )],
    summary="Get tickets by event's ID",
    description=f"Returns tickets for the event with the given ID. Requires `{AuthScopes.Ticket.Read.value}` scope.",
)
def read_event_by_id_with_tickets(id: int, db: Session = Depends(get_db)):
    if not models.Event.exists(id=id, db_session=db):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found"
        )

    return ticket_service.get_tickets_by_event_id(
        event_id=id,
        db=db
    )


# This endpoint is maybe not needed, because we can get ticket groups with event info in /events/{id} endpoint, but it can be useful if we want to get only ticket groups without event info
@router.get(
    "/{id}/ticket_groups",
    response_model=list[ticket_group.TicketGroup],
    summary="Get ticket groups by event's ID",
    description="Returns ticket groups for the event with the given ID.",
)
def read_event_by_id_with_tickets_groups(id: int, db: Session = Depends(get_db)):
    if not models.Event.exists(id=id, db_session=db):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found"
        )

    return models.TicketGroup.get_list_by_param(
        param_name="event_id",
        param_value=id,
        db_session=db,
    )


def _scope_error_to_http_exception(error: ValueError) -> HTTPException:
    """Map missing resources to 404 and invalid scope input to 422."""
    if str(error) in {"Event not found", "User not found"}:
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error))


@router.get(
    "/{id}/scopes",
    response_model=list[event_user_scope.EventUserScope],
    dependencies=[Depends(require_event_scope(AuthScopes.Event.Read))],
    summary="List event-local scopes",
    description=f"Lists every user scope for this event. Requires `{AuthScopes.Event.Read.value}` scope.",
)
def read_event_user_scopes(
    id: int,
    db: Session = Depends(get_db)
):
    try:
        return event_user_scopes_service.get_scopes_by_event(id, db)
    except ValueError as error:
        raise _scope_error_to_http_exception(error)


@router.get(
    "/{id}/scopes/me",
    response_model=list[event_user_scope.EventUserScope],
    summary="List my event-local scopes",
    description="Lists the authenticated user's local scopes for this event.",
)
def read_my_event_user_scopes(
    id: int,
    current_user: Annotated[models.User, Depends(get_current_active_user)],
    db: Session = Depends(get_db),
):
    """Return only this caller's event-local grants.

    Authentication is sufficient: knowing one's own permissions must not
    itself require one of those permissions.
    """
    try:
        return event_user_scopes_service.get_scopes_for_user(
            event_id=id,
            user_uuid=current_user.uuid,
            db=db,
        )
    except ValueError as error:
        raise _scope_error_to_http_exception(error)


@router.get(
    "/{id}/scopes/{user_id}",
    response_model=list[event_user_scope.EventUserScope],
    dependencies=[Depends(require_event_scope(AuthScopes.Event.Read))],
    summary="List a user's event-local scopes",
    description=f"Lists one user's scopes for this event. Requires `{AuthScopes.Event.Read.value}` scope.",
)
def read_event_user_scopes_by_user(
    id: int,
    user_id: UUID,
    db: Session = Depends(get_db)
):
    try:
        return event_user_scopes_service.get_scopes_for_user(id, user_id, db)
    except ValueError as error:
        raise _scope_error_to_http_exception(error)


@router.put(
    "/{id}/scopes/{user_id}",
    response_model=list[event_user_scope.EventUserScope],
    dependencies=[Depends(require_event_scope(AuthScopes.Event.Edit))],
    summary="Replace a user's event-local scopes",
    description=f"Replaces one user's scopes for this event. Requires `{AuthScopes.Event.Edit.value}` scope.",
)
def replace_event_user_scopes(
    id: int,
    user_id: UUID,
    payload: event_user_scope.EventUserScopesReplace,
    db: Session = Depends(get_db),
):
    try:
        return event_user_scopes_service.replace_scopes(id, user_id, payload.scopes, db)
    except ValueError as error:
        raise _scope_error_to_http_exception(error)


@router.put(
    "/{id}/scopes/{user_id}/{scope}",
    response_model=event_user_scope.EventUserScope,
    dependencies=[Depends(require_event_scope(AuthScopes.Event.Edit))],
    summary="Grant an event-local scope",
    description=f"Idempotently grants one scope. Requires `{AuthScopes.Event.Edit.value}` scope.",
)
def grant_event_user_scope(
    id: int,
    user_id: UUID,
    scope: Annotated[
        str,
        Path(min_length=1, max_length=SCOPE_MAX_LENGTH, pattern=r".*\S.*"),
    ],
    db: Session = Depends(get_db),
):
    try:
        return event_user_scopes_service.grant_scope(id, user_id, scope, db)
    except ValueError as error:
        raise _scope_error_to_http_exception(error)


@router.delete(
    "/{id}/scopes/{user_id}/{scope}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    dependencies=[Depends(require_event_scope(AuthScopes.Event.Edit))],
    summary="Revoke an event-local scope",
    description=f"Revokes one scope. Requires `{AuthScopes.Event.Edit.value}` scope.",
)
def revoke_event_user_scope(
    id: int,
    user_id: UUID,
    scope: str,
    db: Session = Depends(get_db),
):
    try:
        revoked = event_user_scopes_service.revoke_scope(
            id, user_id, scope, db)
    except ValueError as error:
        raise _scope_error_to_http_exception(error)
    if not revoked:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Event user scope not found")


@router.patch(
    "/{id}",
    response_model=event.Event,
    dependencies=[Depends(require_event_scope(AuthScopes.Event.Edit))],
    summary="Partialy edit event",
    description=f"Returns updated event. Requires `{AuthScopes.Event.Edit.value}` scope.",
)
def update_event(
    id: int,
    updated_event: event.EventBase,
    db: Session = Depends(get_db)
):
    return models.Event.update(db_session=db, id=id, **updated_event.model_dump())


@router.delete(
    "/{id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    dependencies=[Depends(require_event_scope(AuthScopes.Event.Edit))],
    summary="Delete event",
    description=f"Returns 204 if successful. Requires `{AuthScopes.Event.Edit.value}` scope.",
)
def delete_event(id: int, db: Session = Depends(get_db)):
    event = models.Event.delete(db_session=db, id=id)
    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found"
        )


@router.get(
    "/xlsx/{id}",
    response_class=StreamingResponse,
    dependencies=[Depends(require_event_scope(AuthScopes.Event.Read))],
    summary="Generate event's XLSX",
    description=f"Returns XLSX file with tickets in groups. Requires `{AuthScopes.Event.Read.value}` scope.",
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
