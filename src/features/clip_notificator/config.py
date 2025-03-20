from typing import Any

from pydantic import model_validator

from common.base_model import BaseConfig
from schemas import enums


class SystemConfig(BaseConfig):
    @model_validator(mode="before")
    @classmethod
    def preprocess(cls, values: dict[str, Any]) -> dict[str, Any]:
        version = values.get("version")
        match version:
            case 0:
                pass
            case _:
                msg = f"Unsupported version: {version}"
                raise ValueError(msg)
        return values


class UserConfig(BaseConfig):
    """
    {url} -> clip url
    {title} -> clip title
    {creator} -> clip creator name
    """

    message_format: str
    color: enums.AnnouncementColor | None

    @model_validator(mode="before")
    @classmethod
    def preprocess(cls, values: dict[str, Any]) -> dict[str, Any]:
        version = values.get("version")
        match version:
            case 0:
                pass
            case _:
                msg = f"Unsupported version: {version}"
                raise ValueError(msg)
        return values
