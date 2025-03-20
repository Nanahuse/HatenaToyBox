from __future__ import annotations

from pydantic import BaseModel


class BaseConfig(BaseModel):
    version: int
