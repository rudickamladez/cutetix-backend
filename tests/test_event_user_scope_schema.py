import pytest
from pydantic import ValidationError

from app.schemas.event_user_scope import EventUserScopesReplace


def test_replace_payload_requires_scopes_key():
    with pytest.raises(ValidationError):
        EventUserScopesReplace.model_validate({})


def test_replace_payload_accepts_explicit_empty_scope_list():
    payload = EventUserScopesReplace.model_validate({"scopes": []})

    assert payload.scopes == []
