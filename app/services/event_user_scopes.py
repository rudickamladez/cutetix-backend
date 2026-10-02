

from uuid import UUID
from app.utils.uuid import to_uuid_bytes
from sqlalchemy.orm import Session

from app import models


def grant_scopes_staged(
    event_id: int,
    user_uuid: UUID,
    scopes: list[str] | tuple[str, ...],
    db: Session,
) -> None:
    """Stage scope grants without committing.

    Lets callers combine the grants with other writes (event creation) in one
    atomic transaction. The caller owns the final commit/rollback.
    """
    for scope in scopes:
        db.add(models.EventUserScope(
            event_id=event_id,
            user_uuid=to_uuid_bytes(user_uuid),
            scope=scope,
        ))