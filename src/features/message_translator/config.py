from pathlib import Path

from common.base_model import BaseConfig
from schemas.enums import Language

from .translator_adaptor.translator_config import DeeplConfig, GoogleConfig, TranslatorConfig


class SystemConfig(BaseConfig):
    cache_max: int
    cache_directory: Path


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
