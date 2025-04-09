from __future__ import annotations

from typing import TYPE_CHECKING

from common.feature import ConfigData, Feature
from schemas import events, models, services

from .config import SystemConfig, UserConfig

if TYPE_CHECKING:
    from common.core import Hub


class ClipNotificator(Feature[SystemConfig, UserConfig]):
    def __init__(self, hub: Hub, system_config: ConfigData) -> None:
        super().__init__(hub, SystemConfig, UserConfig, system_config)
        self._service_caller = hub.create_caller()

        hub.add_event_handler(events.ClipFound, self._new_clip_found)

    async def _new_clip_found(self, event: events.ClipFound) -> None:
        if self.user_config is None:
            return  # Not initialized yet.

        self.logger.info("New clip found: '%s' created by '%s'", event.clip.title, event.clip.creator)

        message = (
            self.user_config.message_format.replace("{url}", event.clip.url)
            .replace("{title}", event.clip.title)
            .replace("{creator}", event.clip.creator)
        )

        try:
            await self._service_caller.call(
                services.PostAnnouncement(
                    payload=models.Announcement(
                        content=message,
                        color=self.user_config.color,
                    ),
                ),
            )
        except RuntimeError as e:
            self.logger.error("Failed to post announcement: %s", e)  # noqa: TRY400
