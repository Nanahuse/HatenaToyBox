from pathlib import Path
from typing import Any

from pydantic import model_validator

from common.base_model import BaseConfig
from schemas.enums import Language

from .translator_adaptor.translator_config import DeeplConfig, GoogleConfig, TranslatorConfig


class SystemConfig(BaseConfig):
    cache_max: int
    cache_directory: Path

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
    {author}
    {from}
    {to}
    {message}
    """

    first_language: Language = Language.JAPANESE
    second_language: Language = Language.ENGLISH
    do_comment: bool
    message_format: str
    queue_max: int
    ignore_emote_only_message: bool
    translator: GoogleConfig | DeeplConfig | TranslatorConfig

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
