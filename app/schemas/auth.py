from pydantic import BaseModel
# import uuid

class User(BaseModel):
    email: str | None = None
    full_name: str | None = None
    disabled: bool | None = None


class UserInDB(User):
    uuid: str
    hashed_password: str
