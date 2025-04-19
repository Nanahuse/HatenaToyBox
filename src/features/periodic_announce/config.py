from common.base_model import BaseConfig

from .announcement_task import AnnouncementTask


class SystemConfig(BaseConfig):
    pass


class UserConfig(BaseConfig):
    announcements: list[AnnouncementTask]
