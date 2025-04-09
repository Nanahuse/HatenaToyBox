from __future__ import annotations

from pydantic import BaseModel


class BaseService[Tin, Tout](BaseModel, frozen=True):
    payload: Tin
