from common.base_model import BaseConfig
from schemas import enums


class SystemConfig(BaseConfig):
    pass


class UserConfig(BaseConfig):
    """
    {url} -> clip url
    {title} -> clip title
    {creator} -> clip creator name
    """

    message_format: str
    color: enums.AnnouncementColor | None
