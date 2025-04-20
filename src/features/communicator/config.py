from pathlib import Path

from common.base_model import BaseConfig


class SystemConfig(BaseConfig):
    token_file_directory: Path
    stream_info_storage_directory: Path


class UserConfig(BaseConfig):
    channel: str
    enable_stream_info_command: bool
