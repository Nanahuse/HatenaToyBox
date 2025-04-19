import datetime

from common.base_model import BaseConfig
from schemas import enums


class SystemConfig(BaseConfig):
    pass


class UserConfig(BaseConfig):
    """
    {raider} -> raider name
    {title} -> stream title
    {game} -> stream game
    """

    reaction_delay: datetime.timedelta
    do_shoutout: bool
    do_announcement: bool
    message_format: str
    color: enums.AnnouncementColor | None
