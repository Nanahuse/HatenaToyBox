from __future__ import annotations

from typing import TYPE_CHECKING

from common.feature import ConfigData, Feature
from schemas import events

from .config import SystemConfig, UserConfig

if TYPE_CHECKING:
    from common.core import Hub


class MessageFilter(Feature[SystemConfig, UserConfig]):
    def __init__(self, hub: Hub, system_config: ConfigData) -> None:
        super().__init__(hub, SystemConfig, UserConfig, system_config)
        self._event_publisher = hub.create_publisher()

        hub.add_event_handler(events.NewMessageReceived, self._filter)

    async def _filter(self, event: events.NewMessageReceived) -> None:
        if self.user_config is None:
            return  # Not initialized yet.

        if event.message.is_echo:
            self.logger.debug("Ignore own message.")
            return
        if event.message.author.name in self.user_config.ignore_accounts:
            self.logger.debug("Ignore the message from %s.", event.message.author.name)
            return

        self.logger.debug("Pass the message from %s.", event.message.author.name)
        await self._event_publisher.publish(events.MessageFiltered(message=event.message))
