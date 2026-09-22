from fastapi import APIRouter, Depends, HTTPException, Response, status, Security
from fastapi.responses import StreamingResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from typing import Annotated
from uuid import UUID
from app import models
from app.auth_scopes import AuthScope, ScopeValidationError
from app.middleware.auth import get_current_active_user
from app.middleware.event_scopes import (
    require_event_scope,
    token_scopes_of,
)
from app.services import event as event_service
from app.services import event_user_scopes as event_user_scopes_service
from app.services.event_user_scopes import NotFoundError
from app.services import ticket as ticket_service
from app.uuid_utils import to_uuid_bytes
from app.schemas import event, event_user_scope, extra, ticket, ticket_group
from app.schemas.user import UserFromDB
from app.database import get_db

router = APIRouter(
    prefix="/events",
    tags=["events"],
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "Not found"}
    },
)


def _refuse_self_lockout(
    current_user,
    target_user_id: UUID,
    keeps_events_edit: bool,
) -> None:
    """Refuse to strip the caller's own last `events:edit` grant for an event.

    `events:edit` is the only scope that manages an event's scopes, and once it
    is gone nothing the caller can still reach will mint it back - a purely
    local admin (no global `events:edit`) loses their event permanently. Both
    scope-revoking routes must apply this: a check on only one of them is
    bypassed by using the other. A caller who holds the scope globally is
    unaffected, so the guard fires only on the self-targeted, no-fallback case.
    """
    if (
        keeps_events_edit
        or to_uuid_bytes(target_user_id) != to_uuid_bytes(current_user.uuid)
        or AuthScope.EVENTS_EDIT.value in token_scopes_of(current_user)
    ):
        return
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=(
            "Cannot remove your own last 'events:edit' grant for this "
            "event - you would lose the ability to manage its scopes."
        ),
    )


@router.post(
    "/",
    response_model=event.Event,
    # No event exists yet, so there is nothing a local grant could attach to:
    # creating an event stays a globally-scoped operation.
    dependencies=[Security(
        get_current_active_user,
        scopes=[AuthScope.EVENTS_EDIT.value],
    )],
    summary="Create event",
    description="Returns created object. Requires the global `events:edit` scope.",
)
def create_event(
    event: event.EventCreate,
    current_user: Annotated[UserFromDB, Depends(get_current_active_user)],
    db: Session = Depends(get_db),
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
            scopes=event_user_scopes_service.EVENT_CREATOR_SCOPES,
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
    dependencies=[Depends(require_event_scope(AuthScope.TICKETS_READ))],
    summary="Get tickets by event's ID",
    description=(
        "Returns tickets for the event with the given ID. Requires the global "
        "`tickets:read` scope or an event-local `tickets:read` grant."
    ),
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


@router.get(
    "/{id}/scopes",
    response_model=list[event_user_scope.EventUserScope],
    dependencies=[Depends(require_event_scope(AuthScope.EVENTS_READ))],
    summary="Get scopes for event",
    description=(
        "Returns event user scopes. Requires the global `events:read` scope "
        "or an event-local `events:read` grant."
    ),
)
def read_event_user_scopes(id: int, db: Session = Depends(get_db)):
    try:
        return event_user_scopes_service.get_scopes_by_event(
            event_id=id,
            db=db,
        )
    except NotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@router.get(
    "/{id}/scopes/{user_id}",
    response_model=list[event_user_scope.EventUserScope],
    dependencies=[Depends(require_event_scope(AuthScope.EVENTS_READ))],
    summary="Get user scopes for event",
    description=(
        "Returns user's scopes for event. Requires the global `events:read` "
        "scope or an event-local `events:read` grant."
    ),
)
def read_event_user_scopes_by_user(
    id: int,
    user_id: UUID,
    db: Session = Depends(get_db),
):
    try:
        return event_user_scopes_service.get_scopes_for_user(
            event_id=id,
            user_uuid=user_id,
            db=db,
        )
    except NotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@router.put(
    "/{id}/scopes/{user_id}",
    response_model=list[event_user_scope.EventUserScope],
    summary="Set user scopes for event",
    description=(
        "Replaces user's scopes for event. Requires the global `events:edit` "
        "scope or an event-local `events:edit` grant. Removing your own last "
        "`events:edit` grant is refused unless you hold it globally, since "
        "that would lock you out of the event permanently."
    ),
)
def replace_event_user_scopes(
    id: int,
    user_id: UUID,
    payload: event_user_scope.EventUserScopesReplace,
    current_user: Annotated[
        UserFromDB,
        Depends(require_event_scope(AuthScope.EVENTS_EDIT)),
    ],
    db: Session = Depends(get_db),
):
    # Only events:edit can manage scopes, and nothing else can grant it on
    # this event, so dropping your own last copy has no way back.
    _refuse_self_lockout(
        current_user=current_user,
        target_user_id=user_id,
        keeps_events_edit=AuthScope.EVENTS_EDIT.value in payload.scopes,
    )
    try:
        # PUT on the collection replaces the user's complete event-scope set.
        return event_user_scopes_service.replace_scopes(
            event_id=id,
            user_uuid=user_id,
            scopes=payload.scopes,
            db=db,
        )
    except ScopeValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )
    except NotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@router.put(
    "/{id}/scopes/{user_id}/{scope}",
    response_model=event_user_scope.EventUserScope,
    dependencies=[Depends(require_event_scope(AuthScope.EVENTS_EDIT))],
    summary="Grant scope for event",
    description=(
        "Grants one user scope for event. Requires the global `events:edit` "
        "scope or an event-local `events:edit` grant."
    ),
)
def grant_event_user_scope(
    id: int,
    user_id: UUID,
    scope: event_user_scope.ScopePath,
    db: Session = Depends(get_db),
):
    try:
        # PUT on a single scope behaves as an idempotent grant.
        return event_user_scopes_service.grant_scope(
            event_id=id,
            user_uuid=user_id,
            scope=scope,
            db=db,
        )
    except ScopeValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )
    except NotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@router.delete(
    "/{id}/scopes/{user_id}/{scope}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    dependencies=[Depends(require_event_scope(AuthScope.EVENTS_EDIT))],
    summary="Delete scope for event",
    description=(
        "Deletes one user scope for event. Requires the global `events:edit` "
        "scope or an event-local `events:edit` grant. Removing your own last "
        "`events:edit` grant is refused unless you hold it globally, since "
        "that would lock you out of the event permanently."
    ),
)
def delete_event_user_scope(
    id: int,
    user_id: UUID,
    scope: event_user_scope.ScopePath,
    current_user: Annotated[
        UserFromDB,
        Depends(require_event_scope(AuthScope.EVENTS_EDIT)),
    ],
    db: Session = Depends(get_db),
):
    # The single-scope route revokes exactly as effectively as the replace
    # route above, so it needs the same guard - otherwise revoking your own
    # last events:edit is reachable one route over.
    _refuse_self_lockout(
        current_user=current_user,
        target_user_id=user_id,
        keeps_events_edit=scope != AuthScope.EVENTS_EDIT.value,
    )
    try:
        if not event_user_scopes_service.delete_scope(
            event_id=id,
            user_uuid=user_id,
            scope=scope,
            db=db,
        ):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Event user scope not found",
            )
    except ScopeValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )
    except NotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@router.patch(
    "/{id}",
    response_model=event.Event,
    dependencies=[Depends(require_event_scope(AuthScope.EVENTS_EDIT))],
    summary="Partialy edit event",
    description=(
        "Returns updated event. Requires the global `events:edit` scope or an "
        "event-local `events:edit` grant."
    ),
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
    dependencies=[Depends(require_event_scope(AuthScope.EVENTS_EDIT))],
    summary="Delete event",
    description=(
        "Returns 204 if successful. Requires the global `events:edit` scope "
        "or an event-local `events:edit` grant."
    ),
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
    # Two grants on purpose: the workbook lists every attendee, so holding
    # only `events:read` (event metadata) must not be enough to export it.
    dependencies=[
        Depends(require_event_scope(AuthScope.EVENTS_READ)),
        Depends(require_event_scope(AuthScope.TICKETS_READ)),
    ],
    summary="Generate event's XLSX",
    description=(
        "Returns XLSX file with tickets in groups. Requires the global "
        "`events:read` and `tickets:read` scopes, or event-local grants of "
        "both - the file contains attendees' personal data."
    ),
)
def get_event_xlsx(
    id: int,
    format_for_libor: bool = False,
    db: Session = Depends(get_db),
):
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
