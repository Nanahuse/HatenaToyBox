from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any, Protocol, final

from common.base_model import BaseConfig

if TYPE_CHECKING:
    from common.core import Hub

    from .set_config_service import ConfigData

logger = logging.getLogger("Feat")


class FeatureProtocol(Protocol):
    def __init__(self, hub: Hub, system_config: ConfigData) -> None: ...
    async def run(self) -> None: ...
    async def set_user_config(self, config: ConfigData | None) -> bool: ...


class Feature[SystemConfig: BaseConfig, UserConfig: BaseConfig]:
    def __init__(
        self,
        _: Hub,
        system_config_type: type[SystemConfig],
        user_config_type: type[UserConfig],
        system_config_value: ConfigData,
    ) -> None:
        self._logger = logger.getChild(self.name)
        self._task_queue = asyncio.Queue[asyncio.Task[Any]]()

        self._user_config_type = user_config_type
        self._user_config: UserConfig | None = None

        self._system_config = system_config_type.model_validate(system_config_value)

        self._event = asyncio.Event()

    @final
    @property
    def logger(self) -> logging.Logger:
        return self._logger

    @final
    @property
    def name(self) -> str:
        return type(self).__name__

    @final
    @property
    def system_config(self) -> SystemConfig:
        return self._system_config

    @final
    @property
    def user_config(self) -> UserConfig | None:
        return self._user_config

    async def initialize(self) -> None:
        self._event.clear()

    async def run(self) -> None:
        await self.initialize()

        await self._event.wait()

    async def close(self) -> None:
        self._event.set()

    async def set_user_config(self, config: ConfigData | None) -> bool:
        user_config = None if config is None else self._user_config_type.model_validate(config)

        if self._user_config == user_config:
            return False

        self._user_config = user_config

        if self._user_config is None:
            self.logger.debug("Disable")
        else:
            self.logger.debug("Config update")

        return True
