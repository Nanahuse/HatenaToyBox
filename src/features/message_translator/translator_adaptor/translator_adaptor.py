from __future__ import annotations

from typing import TYPE_CHECKING

from .cache import Cache

if TYPE_CHECKING:
    from logging import Logger
    from pathlib import Path

    from schemas.enums import Language


class TranslatorAdaptor:
    def __init__(self, logger: Logger, cache_directory: Path, cache_max: int) -> None:
        self._logger = logger.getChild(type(self).__name__)
        self._cache = Cache(cache_directory / type(self).__name__, cache_max)

    async def translate(self, text: str, target: Language, source: Language) -> str:
        if cache := self._cache.get(text, target, source):
            self._logger.debug("Load from cache. text: '%s'", text)
            return cache

        result = await self._translate_impl(text, target, source)
        self._cache.set(text, target, source, result)

        return result

    async def _translate_impl(self, text: str, target: Language, source: Language) -> str:
        raise NotImplementedError


class TranslationError(RuntimeError):
    def __init__(self, message: str) -> None:
        self.message = message
