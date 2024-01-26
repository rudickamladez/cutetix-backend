from pydantic import BaseModel
from datetime import datetime


class RootResponse(BaseModel):
    git: str
    message: str
    time: datetime

    class Config:
        from_attributes = True
