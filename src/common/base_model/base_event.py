from __future__ import annotations

from pydantic import BaseModel


class BaseEvent(BaseModel, frozen=True):
    pass
