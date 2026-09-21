from uuid import UUID
from sqlalchemy.orm import Session

from app import models


# New event creators can fully manage their event from the first request.
EVENT_CREATOR_SCOPES = (
    "events:read",
    "events:edit",
    "ticket_groups:read",
    "ticket_groups:edit",
    "tickets:read",
    "tickets:edit",
)


def _to_uuid_bytes(user_uuid: UUID | bytes) -> bytes:
    if isinstance(user_uuid, UUID):
        return user_uuid.bytes
    return user_uuid


def _normalize_scope(scope: str) -> str:
    # Store one canonical form so path/body variants do not create duplicates.
    scope = scope.strip()
    if len(scope) == 0:
        raise ValueError("Scope cannot be empty")
    return scope


def _check_event_and_user(
    event_id: int,
    user_uuid: UUID | bytes,
    db: Session,
) -> bytes:
    user_uuid_bytes = _to_uuid_bytes(user_uuid)
    if models.Event.get_by_id(db_session=db, id=event_id) is None:
        raise ValueError("Event not found")
    if models.User.get_by_id(db_session=db, id=user_uuid_bytes) is None:
        raise ValueError("User not found")
    return user_uuid_bytes


def get_scopes_by_event(
    event_id: int,
    db: Session,
) -> list[models.EventUserScope]:
    if models.Event.get_by_id(db_session=db, id=event_id) is None:
        raise ValueError("Event not found")
    return db.query(models.EventUserScope).filter(
        models.EventUserScope.event_id == event_id
    ).order_by(
        models.EventUserScope.user_uuid,
        models.EventUserScope.scope,
    ).all()


def get_scopes_for_user(
    event_id: int,
    user_uuid: UUID | bytes,
    db: Session,
) -> list[models.EventUserScope]:
    user_uuid_bytes = _check_event_and_user(event_id, user_uuid, db)
    return db.query(models.EventUserScope).filter(
        models.EventUserScope.event_id == event_id,
        models.EventUserScope.user_uuid == user_uuid_bytes,
    ).order_by(
        models.EventUserScope.scope,
    ).all()


def get_scope(
    event_id: int,
    user_uuid: UUID | bytes,
    scope: str,
    db: Session,
) -> models.EventUserScope | None:
    return db.query(models.EventUserScope).filter(
        models.EventUserScope.event_id == event_id,
        models.EventUserScope.user_uuid == _to_uuid_bytes(user_uuid),
        models.EventUserScope.scope == _normalize_scope(scope),
    ).first()


def grant_scope(
    event_id: int,
    user_uuid: UUID | bytes,
    scope: str,
    db: Session,
) -> models.EventUserScope:
    user_uuid_bytes = _check_event_and_user(event_id, user_uuid, db)
    normalized_scope = _normalize_scope(scope)
    # Granting an existing scope is idempotent for simple client retries.
    event_user_scope = get_scope(
        event_id=event_id,
        user_uuid=user_uuid_bytes,
        scope=normalized_scope,
        db=db,
    )
    if event_user_scope is None:
        event_user_scope = models.EventUserScope(
            event_id=event_id,
            user_uuid=user_uuid_bytes,
            scope=normalized_scope,
        )
        db.add(event_user_scope)
        db.commit()
        db.refresh(event_user_scope)
    return event_user_scope


def grant_scopes(
    event_id: int,
    user_uuid: UUID | bytes,
    scopes: list[str] | tuple[str, ...],
    db: Session,
) -> list[models.EventUserScope]:
    user_uuid_bytes = _check_event_and_user(event_id, user_uuid, db)
    # Bulk grants preserve existing scopes and add only missing ones.
    existing_scopes = {
        event_user_scope.scope
        for event_user_scope in get_scopes_for_user(
            event_id=event_id,
            user_uuid=user_uuid_bytes,
            db=db,
        )
    }
    for scope in {_normalize_scope(scope) for scope in scopes}:
        if scope not in existing_scopes:
            db.add(models.EventUserScope(
                event_id=event_id,
                user_uuid=user_uuid_bytes,
                scope=scope,
            ))
    db.commit()
    return get_scopes_for_user(
        event_id=event_id,
        user_uuid=user_uuid_bytes,
        db=db,
    )


def replace_scopes(
    event_id: int,
    user_uuid: UUID | bytes,
    scopes: list[str],
    db: Session,
) -> list[models.EventUserScope]:
    user_uuid_bytes = _check_event_and_user(event_id, user_uuid, db)
    # Replacing scopes is useful for permission editors that submit full state.
    db.query(models.EventUserScope).filter(
        models.EventUserScope.event_id == event_id,
        models.EventUserScope.user_uuid == user_uuid_bytes,
    ).delete()
    for scope in {_normalize_scope(scope) for scope in scopes}:
        db.add(models.EventUserScope(
            event_id=event_id,
            user_uuid=user_uuid_bytes,
            scope=scope,
        ))
    db.commit()
    return get_scopes_for_user(
        event_id=event_id,
        user_uuid=user_uuid_bytes,
        db=db,
    )


def delete_scope(
    event_id: int,
    user_uuid: UUID | bytes,
    scope: str,
    db: Session,
) -> bool:
    event_user_scope = get_scope(
        event_id=event_id,
        user_uuid=user_uuid,
        scope=scope,
        db=db,
    )
    if event_user_scope is None:
        return False
    db.delete(event_user_scope)
    db.commit()
    return True


def has_scope(
    event_id: int,
    user_uuid: UUID | bytes,
    scope: str,
    db: Session,
) -> bool:
    return get_scope(
        event_id=event_id,
        user_uuid=user_uuid,
        scope=scope,
        db=db,
    ) is not None
