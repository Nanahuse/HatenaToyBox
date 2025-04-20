from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import TYPE_CHECKING, cast

from common.feature import Config, SetConfigService

from .auto_interception import AutoInterception
from .clip_notificator import ClipNotificator
from .communicator import Communicator
from .configuration_manager import ConfigurationManager
from .door_bell import DoorBell
from .message_filter import MessageFilter
from .message_translator import MessageTranslator
from .periodic_announce import PeriodicAnnounce
from .sound_player import SoundPlayer

if TYPE_CHECKING:
    from common.core import Hub
    from common.feature import ConfigData, FeatureProtocol


class FeatureManager:
    def __init__(self, hub: Hub, config_file: Path) -> None:
        system_configs = self.load_system_config(config_file)

        self._features: dict[str, FeatureProtocol] = {
            feature_type.__name__: feature_type(hub, system_configs[feature_type.__name__])
            for feature_type in (
                AutoInterception,
                ClipNotificator,
                Communicator,
                ConfigurationManager,
                DoorBell,
                MessageFilter,
                MessageTranslator,
                PeriodicAnnounce,
                SoundPlayer,
            )
        }

        hub.add_service_handler(SetConfigService, self.handle_set_config)

    def load_system_config(self, config_file: Path) -> dict[str, ConfigData]:
        with Path(config_file).open(encoding="utf-8") as f:
            configs = json.load(f)

        return cast("dict[str, ConfigData]", configs)

    async def handle_set_config(self, config: Config) -> None:
        if config.name not in self._features:
            msg = f"Unknown feature: {config.name}"
            raise ValueError(msg)

        feature = self._features[config.name]
        await feature.set_user_config(config.data)

    async def run(self) -> None:
        await asyncio.gather(
            *(feature.run() for feature in self._features.values()),
        )

    async def close(self) -> None:
        await asyncio.gather(
            *(feature.close() for feature in self._features.values()),
        )
