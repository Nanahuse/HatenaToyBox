from typing import Any

from pydantic import BaseModel

from common.base_model import BaseService

ConfigData = dict[str, Any]


class Config(BaseModel):
    name: str
    data: ConfigData | None


class SetConfigService(BaseService[Config, None]):
    pass
