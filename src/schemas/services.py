import datetime

from common.base_model import BaseService

from . import models

# MARK: Twitch communicator.


class FetchClip(BaseService[datetime.timedelta, list[models.Clip]]):
    pass


class FetchStreamInfo(BaseService[models.User | None, models.StreamInfo]):
    pass


class Shoutout(BaseService[models.User, None]):
    pass


class SendComment(BaseService[models.Comment, None]):
    pass


class PostAnnouncement(BaseService[models.Announcement, None]):
    pass


class PlaySound(BaseService[models.Sound, None]):
    pass
