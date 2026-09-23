from uuid import UUID
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app import models
from app.auth_scopes import (
    EVENT_GRANTABLE_SCOPE_VALUES,
    normalize_event_grantable_scope,
)
from app.uuid_utils import to_uuid_bytes


# New event creators can fully manage their event from the first request.
EVENT_CREATOR_SCOPES = EVENT_GRANTABLE_SCOPE_VALUES

# Ceiling for the optimistic retry loops below; a constraint violation that
# survives this many attempts is real, not a lost race.
_MAX_GRANT_ATTEMPTS = 3


class NotFoundError(ValueError):
    """Referenced event or user does not exist (maps to HTTP 404).

    Distinct from ScopeValidationError so a route can tell "you named
    something that is not there" from "you sent a value we never accept"
    instead of mapping every ValueError to 404 by ordering luck.
    """


def _normalize_scope(scope: str) -> str:
    # Delegates to the shared predicate so the request schema and this
    # service cannot drift apart. ScopeValidationError stays a ValueError.
    return normalize_event_grantable_scope(scope)


def _check_event_and_user(
    event_id: int,
    user_uuid: UUID | bytes,
    db: Session,
) -> bytes:
    user_uuid_bytes = to_uuid_bytes(user_uuid)
    if models.Event.get_by_id(db_session=db, id=event_id) is None:
        raise NotFoundError("Event not found")
    if models.User.get_by_id(db_session=db, id=user_uuid_bytes) is None:
        raise NotFoundError("User not found")
    return user_uuid_bytes


def get_scopes_by_event(
    event_id: int,
    db: Session,
) -> list[models.EventUserScope]:
    if models.Event.get_by_id(db_session=db, id=event_id) is None:
        raise NotFoundError("Event not found")
    # The grant list is displayed to a human, so every row carries its grantee;
    # eager-loading keeps that to one extra query instead of one per row.
    return db.query(models.EventUserScope).options(
        selectinload(models.EventUserScope.user)
    ).filter(
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


def get_event_ids_with_scope(
    user_uuid: UUID | bytes,
    scope: str,
    db: Session,
) -> list[int]:
    """Event ids the user holds ``scope`` on, ordered for stable paging."""
    return [
        event_id
        for (event_id,) in db.query(models.EventUserScope.event_id).filter(
            models.EventUserScope.user_uuid == to_uuid_bytes(user_uuid),
            models.EventUserScope.scope == _normalize_scope(scope),
        ).distinct().order_by(models.EventUserScope.event_id).all()
    ]


def get_scope(
    event_id: int,
    user_uuid: UUID | bytes,
    scope: str,
    db: Session,
) -> models.EventUserScope | None:
    return db.query(models.EventUserScope).filter(
        models.EventUserScope.event_id == event_id,
        models.EventUserScope.user_uuid == to_uuid_bytes(user_uuid),
        models.EventUserScope.scope == _normalize_scope(scope),
    ).first()


def has_scope(
    event_id: int,
    user_uuid: UUID | bytes,
    scope: str,
    db: Session,
) -> bool:
    # The inner query builds an EXISTS clause and the outer one selects it, so
    # the database stops at the first matching grant instead of loading a row.
    # This runs on every locally-scoped request.
    return bool(db.query(
        db.query(models.EventUserScope).filter(
            models.EventUserScope.event_id == event_id,
            models.EventUserScope.user_uuid == to_uuid_bytes(user_uuid),
            models.EventUserScope.scope == _normalize_scope(scope),
        ).exists()
    ).scalar())


def _stage_grants(
    event_id: int,
    user_uuid_bytes: bytes,
    scopes: list[str] | tuple[str, ...],
    existing_scopes: set[str],
    db: Session,
) -> None:
    """Stage (without committing) inserts for every scope not yet granted."""
    for scope in {_normalize_scope(scope) for scope in scopes}:
        if scope not in existing_scopes:
            db.add(models.EventUserScope(
                event_id=event_id,
                user_uuid=user_uuid_bytes,
                scope=scope,
            ))


def _existing_scope_set(
    event_id: int,
    user_uuid_bytes: bytes,
    db: Session,
) -> set[str]:
    return {
        event_user_scope.scope
        for event_user_scope in get_scopes_for_user(
            event_id=event_id,
            user_uuid=user_uuid_bytes,
            db=db,
        )
    }


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
        try:
            db.commit()
        except IntegrityError:
            # Lost a race with a concurrent grant of the same scope: the row
            # exists now, so the grant is still a success.
            db.rollback()
            existing = get_scope(
                event_id=event_id,
                user_uuid=user_uuid_bytes,
                scope=normalized_scope,
                db=db,
            )
            if existing is None:
                raise
            return existing
        db.refresh(event_user_scope)
    return event_user_scope


def grant_scopes_staged(
    event_id: int,
    user_uuid: UUID | bytes,
    scopes: list[str] | tuple[str, ...],
    db: Session,
) -> None:
    """Stage scope grants without committing.

    Lets callers combine the grants with other writes (event creation) in one
    atomic transaction. The caller owns the final commit/rollback.
    """
    user_uuid_bytes = _check_event_and_user(event_id, user_uuid, db)
    existing = _existing_scope_set(event_id, user_uuid_bytes, db)
    _stage_grants(event_id, user_uuid_bytes, scopes, existing, db)


def grant_scopes(
    event_id: int,
    user_uuid: UUID | bytes,
    scopes: list[str] | tuple[str, ...],
    db: Session,
) -> list[models.EventUserScope]:
    """Grant every scope, keeping existing ones, and commit.

    Bulk grants preserve existing scopes and add only missing ones.
    """
    user_uuid_bytes = _check_event_and_user(event_id, user_uuid, db)
    existing = _existing_scope_set(event_id, user_uuid_bytes, db)
    _stage_grants(event_id, user_uuid_bytes, scopes, existing, db)
    try:
        db.commit()
    except IntegrityError:
        # Lost a race with concurrent grants: re-derive the missing scopes
        # and insert only those.
        db.rollback()
        existing = _existing_scope_set(event_id, user_uuid_bytes, db)
        _stage_grants(event_id, user_uuid_bytes, scopes, existing, db)
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
    # Diff-based replace (instead of delete-all + reinsert) so a failure
    # mid-way cannot leave the user with an empty scope set, and so untouched
    # rows are never dropped and re-created.
    wanted = {_normalize_scope(scope) for scope in scopes}

    for attempt in range(_MAX_GRANT_ATTEMPTS):
        existing_rows = get_scopes_for_user(
            event_id=event_id,
            user_uuid=user_uuid_bytes,
            db=db,
        )
        existing = {row.scope for row in existing_rows}

        for row in existing_rows:
            if row.scope not in wanted:
                db.delete(row)
        _stage_grants(event_id, user_uuid_bytes, wanted, existing, db)
        try:
            db.commit()
            break
        except IntegrityError:
            # Lost a race with a concurrent grant: re-read and retry. Bounded,
            # because a violation a re-read cannot clear would otherwise retry
            # forever.
            db.rollback()
            if attempt == _MAX_GRANT_ATTEMPTS - 1:
                raise
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
    if models.Event.get_by_id(db_session=db, id=event_id) is None:
        raise NotFoundError("Event not found")
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
