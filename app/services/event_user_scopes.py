

from uuid import UUID
from app.auth_scopes import SCOPE_MAX_LENGTH, AuthScopes
from app.utils.uuid import to_uuid_bytes
from sqlalchemy.orm import Session

from app import models


class ScopeValidationError(ValueError):
    pass


def normalize_event_grantable_scope(scope: str) -> str:
    scope = scope.strip()
    if len(scope) == 0:
        raise ScopeValidationError("Scope cannot be empty")
    if len(scope) > SCOPE_MAX_LENGTH:
        raise ScopeValidationError(
            f"Scope cannot be longer than {SCOPE_MAX_LENGTH} characters"
        )
    if scope not in AuthScopes.all_values():
        raise ScopeValidationError(f"Unknown scope '{scope}'")
    if scope not in AuthScopes.event_scopes_values():
        raise ScopeValidationError(
            f"Scope '{scope}' cannot be granted for a single event"
        )
    return scope


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
    # Validate every value before staging a row. `dict.fromkeys` preserves the
    # caller's order while collapsing duplicates that would violate the
    # (event_id, user_uuid, scope) composite primary key.
    normalized_scopes = dict.fromkeys(
        normalize_event_grantable_scope(scope) for scope in scopes
    )
    for scope in normalized_scopes:
        db.add(models.EventUserScope(
            event_id=event_id,
            user_uuid=to_uuid_bytes(user_uuid),
            scope=scope,
        ))


def _check_event_and_user_exists(
    event_id: int,
    user_uuid: UUID | bytes,
    db: Session,
) -> bytes:
    """Return the stored UUID after confirming both grant targets exist."""
    if models.Event.get_by_id(db_session=db, id=event_id) is None:
        raise ValueError("Event not found")
    user_uuid_bytes = to_uuid_bytes(user_uuid)
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
        models.EventUserScope.event_id == event_id,
    ).order_by(
        models.EventUserScope.user_uuid,
        models.EventUserScope.scope,
    ).all()


def get_scopes_for_user(
    event_id: int,
    user_uuid: UUID | bytes,
    db: Session,
) -> list[models.EventUserScope]:
    user_uuid_bytes = _check_event_and_user_exists(event_id, user_uuid, db)
    return db.query(models.EventUserScope).filter(
        models.EventUserScope.event_id == event_id,
        models.EventUserScope.user_uuid == user_uuid_bytes,
    ).order_by(models.EventUserScope.scope).all()


def get_scope(
    event_id: int,
    user_uuid: UUID | bytes,
    scope: str,
    db: Session,
) -> models.EventUserScope | None:
    return db.query(models.EventUserScope).filter(
        models.EventUserScope.event_id == event_id,
        models.EventUserScope.user_uuid == to_uuid_bytes(user_uuid),
        models.EventUserScope.scope == normalize_event_grantable_scope(scope),
    ).first()


def grant_scope(
    event_id: int,
    user_uuid: UUID | bytes,
    scope: str,
    db: Session,
) -> models.EventUserScope:
    """Grant one scope, idempotently, and persist it."""
    user_uuid_bytes = _check_event_and_user_exists(event_id, user_uuid, db)
    normalized_scope = normalize_event_grantable_scope(scope)
    event_user_scope = get_scope(
        event_id, user_uuid_bytes, normalized_scope, db)
    if event_user_scope is None:
        # Scope does not exist, create a new one
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
    """Add local scopes without removing existing grants."""
    user_uuid_bytes = _check_event_and_user_exists(event_id, user_uuid, db)
    # Validate the whole request before adding anything.
    requested_scopes = {normalize_event_grantable_scope(
        scope) for scope in scopes}
    existing_scopes = {
        event_user_scope.scope
        for event_user_scope in get_scopes_for_user(event_id, user_uuid_bytes, db)
    }
    db.add_all([
        models.EventUserScope(
            event_id=event_id,
            user_uuid=user_uuid_bytes,
            scope=scope,
        )
        for scope in requested_scopes - existing_scopes
    ])
    db.commit()
    return get_scopes_for_user(event_id, user_uuid_bytes, db)


def replace_scopes(
    event_id: int,
    user_uuid: UUID | bytes,
    scopes: list[str] | tuple[str, ...],
    db: Session,
) -> list[models.EventUserScope]:
    """Atomically replace a user's complete local scope set for an event."""
    user_uuid_bytes = _check_event_and_user_exists(event_id, user_uuid, db)
    # Validate before deleting so malformed input cannot revoke existing access.
    normalized_scopes = {
        normalize_event_grantable_scope(scope) for scope in scopes}
    db.query(models.EventUserScope).filter(
        models.EventUserScope.event_id == event_id,
        models.EventUserScope.user_uuid == user_uuid_bytes,
    ).delete(synchronize_session=False)
    db.add_all([
        models.EventUserScope(
            event_id=event_id,
            user_uuid=user_uuid_bytes,
            scope=scope,
        )
        for scope in normalized_scopes
    ])
    db.commit()
    return get_scopes_for_user(event_id, user_uuid_bytes, db)


def revoke_scope(
    event_id: int,
    user_uuid: UUID | bytes,
    scope: str,
    db: Session,
) -> bool:
    """Revoke one local scope. Returns false when that grant is absent."""
    event_user_scope = get_scope(event_id, user_uuid, scope, db)
    if event_user_scope is None:
        return False
    db.delete(event_user_scope)
    db.commit()
    return True


# Backwards-compatible spelling for callers that model revocation as deletion.
delete_scope = revoke_scope


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
            models.EventUserScope.scope == normalize_event_grantable_scope(
                scope),
        ).exists()
    ).scalar())
