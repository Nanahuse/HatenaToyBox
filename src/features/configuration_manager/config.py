from pathlib import Path

from common.base_model import BaseConfig


class SystemConfig(BaseConfig):
    user_setting_file: Path


class UserConfig(BaseConfig):
    pass
