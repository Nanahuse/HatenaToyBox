from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

from common.feature import ConfigData, Feature
from schemas import events, models, services

from .config import SystemConfig, UserConfig

if TYPE_CHECKING:
    from common.core import Hub


SOUND_INTERVAL = datetime.timedelta(seconds=1)


class DoorBell(Feature[SystemConfig, UserConfig]):
    def __init__(self, hub: Hub, system_config: ConfigData) -> None:
        super().__init__(hub, SystemConfig, UserConfig, system_config)
        self._service_caller = hub.create_caller()

        self._handled_user = set[int]()

        hub.add_event_handler(events.MessageFiltered, self._message_received)

    async def _message_received(self, event: events.MessageFiltered) -> None:
        if self.user_config is None:
            return  # Not initialized yet.

        if not self.user_config.sound_file.exists() or not self.user_config.sound_file.is_file():
            self.logger.warning("Sound file not found: %s", self.user_config.sound_file)
            return

        if event.message.author.id in self._handled_user:
            return

        self._handled_user.add(event.message.author.id)

        try:
            await self._service_caller.call(
                services.PlaySound(
                    payload=models.Sound(
                        path=self.user_config.sound_file,
                    ),
                ),
            )
        except RuntimeError as e:
            self.logger.error("Failed to play sound: %s", e)  # noqa: TRY400
