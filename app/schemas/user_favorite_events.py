from pydantic import BaseModel

from app.schemas.event import Event
from app.schemas.user import UserFromDB


class UserFavoriteEvent(BaseModel):
    user: UserFromDB
    event: Event
