from __future__ import annotations

from typing import TYPE_CHECKING, cast, override

import deepl
import deepl.errors

from schemas.enums import Language

from .translator_adaptor import TranslationError, TranslatorAdaptor

if TYPE_CHECKING:
    from logging import Logger
    from pathlib import Path

    from .translator_config import DeeplConfig


def convert(language: Language) -> deepl.TargetLang:
    match language:
        case Language.JAPANESE:
            return deepl.TargetLang.Japanese
        case Language.ENGLISH:
            return deepl.TargetLang.English
        case Language.UNKNOWN:
            return None
    raise NotImplementedError


class DeeplTranslationError(TranslationError):
    def __init__(self) -> None:
        super().__init__("Deepl translation error.")


class DeeplTranslator(TranslatorAdaptor):
    def __init__(self, logger: Logger, cache_directory: Path, cache_max: int, config: DeeplConfig) -> None:
        super().__init__(logger, cache_directory, cache_max)

        self._translator = deepl.Translator(deepl.AiohttpAdapter(config.api_key))

    @override
    async def _translate_impl(self, text: str, target: Language, source: Language) -> str:
        try:
            return cast(
                "str",
                await self._translator.translate(text, target_lang=convert(target), source_lang=convert(source)),
            )
        except deepl.errors.DeepLException as e:
            raise DeeplTranslationError from e
