from __future__ import annotations

from typing import TYPE_CHECKING, override

import gpytranslate as google_translate

from schemas.enums import Language

from .translator_adaptor import TranslationError, TranslatorAdaptor

if TYPE_CHECKING:
    from logging import Logger
    from pathlib import Path

    from .translator_config import GoogleConfig


def convert(language: Language) -> str:
    match language:
        case Language.JAPANESE:
            return "ja"
        case Language.ENGLISH:
            return "en"
        case Language.UNKNOWN:
            return "auto"
    raise NotImplementedError


class GoogleTranslationError(TranslationError):
    def __init__(self) -> None:
        super().__init__("Google Translation error.")


class GoogleTranslator(TranslatorAdaptor):
    def __init__(self, logger: Logger, cache_directory: Path, cache_max: int, _: GoogleConfig) -> None:
        super().__init__(logger, cache_directory, cache_max)
        self._translator = google_translate.Translator()

    @override
    async def _translate_impl(self, text: str, target: Language, source: Language) -> str:
        try:
            translated = await self._translator.translate(text, sourcelang=convert(source), targetlang=convert(target))
        except google_translate.TranslationError as e:
            raise GoogleTranslationError from e

        return translated.text
