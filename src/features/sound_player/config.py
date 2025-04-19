from common.base_model import BaseConfig


class SystemConfig(BaseConfig):
    pass


class UserConfig(BaseConfig):
    queue_max: int
