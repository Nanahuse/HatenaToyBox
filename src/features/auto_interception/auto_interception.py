from __future__ import annotations

import asyncio
import datetime
from typing import TYPE_CHECKING, override

from common.feature import ConfigData, Feature
from schemas import events, models, services
from utils import routines

from .config import SystemConfig, UserConfig

if TYPE_CHECKING:
    from common.core import Hub

INTERCEPTION_INTERVAL = datetime.timedelta(seconds=1)


class AutoInterception(Feature[SystemConfig, UserConfig]):
    def __init__(self, hub: Hub, system_config: ConfigData) -> None:
        super().__init__(hub, SystemConfig, UserConfig, system_config)
        self._service_caller = hub.create_caller()

        self._raid_event_queue = asyncio.Queue[events.RaidDetected]()

        hub.add_event_handler(events.RaidDetected, self._raid_event_queue.put)

    @override
    async def run(self) -> None:
        routine_manager = routines.RoutineManager()

        routine_manager.add(self._main, INTERCEPTION_INTERVAL)

        routine_manager.start()
        await super().run()
        routine_manager.clear()

    async def _main(self) -> None:
        event = await self._raid_event_queue.get()

        if self.user_config is None:
            await self._raid_event_queue.put(event)
            return  # Not initialized yet.

        if not self.user_config.do_announcement and not self.user_config.do_shoutout:
            return  # No action

        self.logger.info(
            "Intercept %d seconds later - target: %s",
            self.user_config.reaction_delay.total_seconds(),
            event.raider.display_name,
        )

        if self.user_config.do_announcement:
            stream_info = await self._service_caller.call(services.FetchStreamInfo(payload=event.raider))

            message = (
                self.user_config.message_format.replace("{raider}", event.raider.display_name)
                .replace("{title}", stream_info.title)
                .replace("{game}", stream_info.game.name if stream_info.game is not None else "???")
            )
        else:
            message = ""

        await asyncio.sleep(self.user_config.reaction_delay.total_seconds())

        try:
            if self.user_config.do_announcement:
                await self._service_caller.call(
                    services.PostAnnouncement(
                        payload=models.Announcement(
                            content=message,
                            color=self.user_config.color,
                        ),
                    ),
                )

            if self.user_config.do_shoutout:
                await self._service_caller.call(
                    services.Shoutout(
                        payload=event.raider,
                    ),
                )
        except RuntimeError as e:
            self.logger.error("Failed to intersection: %s", e)  # noqa: TRY400
