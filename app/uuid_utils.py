from uuid import UUID


def to_uuid_bytes(uuid: UUID | bytes) -> bytes:
    if isinstance(uuid, UUID):
        return uuid.bytes
    return uuid
