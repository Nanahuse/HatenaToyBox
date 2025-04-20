from pydantic import Field

from common.base_model import BaseConfig


class SystemConfig(BaseConfig):
    pass


class UserConfig(BaseConfig):
    ignore_accounts: set[str] = Field(default_factory=set)
