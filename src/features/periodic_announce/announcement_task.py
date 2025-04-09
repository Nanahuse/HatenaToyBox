import datetime

from pydantic import BaseModel

from schemas.enums import AnnouncementColor


class AnnouncementTask(BaseModel):
    message: str
    initial_wait: datetime.timedelta
    interval: datetime.timedelta
    color: AnnouncementColor | None = None
