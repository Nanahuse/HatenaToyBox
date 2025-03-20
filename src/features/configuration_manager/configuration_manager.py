from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, override

from common.feature import Config, ConfigData, Feature, SetConfigService

from .config import SystemConfig, UserConfig

if TYPE_CHECKING:
    from common.core import Hub


class ConfigurationManager(Feature[SystemConfig, UserConfig]):
    def __init__(self, hub: Hub, system_config: ConfigData) -> None:
        super().__init__(hub, SystemConfig, UserConfig, system_config)

        self._caller = hub.create_caller()

    @override
    async def run(self) -> None:
        await self.load_config()
        return await super().run()

    async def load_config(self) -> None:
        with self.system_config.user_setting_file.open("r", encoding="utf-8") as f:
            configs: dict[str, dict[str, Any]] = json.load(f)

        for key, value in configs.items():
            self.logger.debug("load config: %s=%s", key, value)
            await self._caller.call(SetConfigService(payload=Config(name=key, data=value)))
