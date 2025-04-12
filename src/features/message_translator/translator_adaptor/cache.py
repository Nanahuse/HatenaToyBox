from __future__ import annotations

from typing import TYPE_CHECKING, cast

from cachetools import LFUCache
from shelved_cache import PersistentCache

if TYPE_CHECKING:
    from pathlib import Path

    from schemas.enums import Language


def cache_key(text: str, target: Language, source: Language) -> str:
    return f"{text}:{target!s}:{source!s}"


class Cache:
    def __init__(self, cache_file: Path, maxsize: int) -> None:
        self._cache = PersistentCache(LFUCache, str(cache_file.absolute()), maxsize=maxsize)

    def get(self, text: str, target: Language, source: Language) -> str | None:
        result = self._cache.get(cache_key(text, target, source))
        if result is None:
            return None
        return cast("str", result)

    def set(self, text: str, target: Language, source: Language, result: str) -> None:
        self._cache[cache_key(text, target, source)] = result
