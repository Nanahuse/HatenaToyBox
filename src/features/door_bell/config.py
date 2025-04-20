from pathlib import Path

from common.base_model import BaseConfig


class SystemConfig(BaseConfig):
    pass


class UserConfig(BaseConfig):
    sound_file: Path
