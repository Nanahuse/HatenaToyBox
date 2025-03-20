from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from schemas.enums import Language


class IdentifierAdaptor:
    def identify(self, text: str) -> Language:
        raise NotImplementedError
