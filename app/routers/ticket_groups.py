from fastapi import APIRouter, Depends, HTTPException, status, Security
from sqlalchemy.orm import Session
from app import models
from app.middleware.auth import get_current_active_user
from app.schemas import ticket_group, extra
from app.database import get_db
from app.routers.events import read_event_by_id
from app.services.ticket_groups import get_ticket_groups_with_capacity

router = APIRouter(
    prefix="/ticket_groups",
    tags=["ticket_groups"],
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "Not found"}
    },
)


@router.post(
    "/",
    response_model=ticket_group.TicketGroup,
    dependencies=[Security(
        get_current_active_user,
        scopes=["ticket_groups:edit"]
    )],
    summary="Create ticket group",
    description="Returns created object. Requires `ticket_groups:edit` scope.",
)
def create_ticket_group(
    ticket_groups: ticket_group.TicketGroupCreate,
    db: Session = Depends(get_db)
):
    return models.TicketGroup.create(db_session=db, **ticket_groups.model_dump())


@router.get(
    "/",
    response_model=list[extra.TicketGroupExtra],
    summary="Read ticket groups",
)
def read_ticket_groups(db: Session = Depends(get_db)):
    return models.TicketGroup.get_all(db_session=db)


@router.get(
    "/by-event/{id}",
    response_model=list[ticket_group.TicketGroupWithCapacity],
    summary="Read ticket group by event's  ID",
)
def read_ticket_groups_by_event_id(
    id: int,
    db: Session = Depends(get_db)
):
    event = read_event_by_id(id, db)
    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found."
        )
    return get_ticket_groups_with_capacity(event.ticket_groups)


@router.get(
    "/{id}",
    response_model=ticket_group.TicketGroup,
    summary="Read ticket group by ID",
)
def read_ticket_group_by_id(
    id: int,
    db: Session = Depends(get_db)
):
    ticket_group = models.TicketGroup.get_by_id(db_session=db, id=id)
    if ticket_group is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ticket group not found."
        )
    return ticket_group


# @router.patch(
#     "/{id}",
#     response_model=ticket_group.TicketGroup,
#     description="Returns updated ticket group."
# )
# def update_ticket_group(
#     id: int, updated_ticket_groups: ticket_group.TicketGroupBase, db: Session = Depends(get_db)
# ):
#     return models.TicketGroup.update(db_session=db, id=id, **updated_ticket_group.model_dump())

@router.put(
    "/{id}",
    response_model=ticket_group.TicketGroup,
    dependencies=[Security(
        get_current_active_user,
        scopes=["ticket_groups:edit"]
    )],
    summary="Edit ticket group",
    description="Returns updated object. Requires `ticket_groups:edit` scope.",
)
def edit_ticket_group(
    id: int,
    updated_ticket_groups: ticket_group.TicketGroupCreate,
    db: Session = Depends(get_db),
):
    # TODO: Test this use case
    # if id != updated_ticket_group.id:
    #     raise HTTPException(
    #         status_code=status.HTTP_400_BAD_REQUEST,
    #         detail="ID in path does not match ID in user's body."
    #     )
    return models.TicketGroup.update(db_session=db, id=id, **updated_ticket_groups.model_dump())


@router.delete(
    "/{id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Security(
        get_current_active_user,
        scopes=["ticket_groups:edit"]
    )],
    summary="Delete ticket group",
    description="Returns 204 if successful. Requires `ticket_groups:edit` scope.",
)
def delete_ticket_group(
    id: int,
    db: Session = Depends(get_db)
):
    if not models.TicketGroup.delete(db_session=db, id=id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ticket goup not exists, nothing to delete.",
        )
