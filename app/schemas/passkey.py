from pydantic import BaseModel
from uuid import UUID


class PasskeyOptionsResponse(BaseModel):
    challenge_id: UUID
    public_key: dict


class PasskeyLoginOptionsRequest(BaseModel):
    username: str | None = None


class PasskeyRegisterVerifyRequest(BaseModel):
    challenge_id: UUID
    credential: dict


class PasskeyLoginVerifyRequest(PasskeyRegisterVerifyRequest):
    requested_scopes: list[str] | None = None


class PasskeyVerifyResponse(BaseModel):
    credential_id: str
