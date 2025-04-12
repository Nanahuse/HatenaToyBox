from __future__ import annotations

from typing import TYPE_CHECKING

from schemas import models

if TYPE_CHECKING:
    from . import twitchio_models


def cast_user(user: twitchio_models.User) -> models.User:
    return models.User(id=user.id, name=user.name, display_name=user.display_name or user.name)
