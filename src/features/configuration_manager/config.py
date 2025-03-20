from pathlib import Path
from typing import Any

from pydantic import model_validator

from common.base_model import BaseConfig


class SystemConfig(BaseConfig):
    user_setting_file: Path

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
