

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
    for scope in scopes:
        if scope not in AuthScopes.event_scopes_values():
            raise ScopeValidationError(
                f"Scope '{scope}' cannot be granted for a single event"
            )
        db.add(models.EventUserScope(
            event_id=event_id,
            user_uuid=to_uuid_bytes(user_uuid),
            scope=scope,
        ))


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
            models.EventUserScope.scope == normalize_event_grantable_scope(scope),
        ).exists()
    ).scalar())
