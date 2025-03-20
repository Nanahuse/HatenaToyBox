from __future__ import annotations

import asyncio
import datetime
from typing import TYPE_CHECKING, override

from common.feature import ConfigData, Feature
from schemas import models, services
from utils import routines

from .config import SystemConfig, UserConfig

if TYPE_CHECKING:
    from common.core import Hub, ServiceCaller

    from .announcement_task import AnnouncementTask


TRANSLATION_INTERVAL = datetime.timedelta(seconds=1)


class AnnouncementHandler:
    def __init__(self, service_caller: ServiceCaller, task: AnnouncementTask) -> None:
        self._service_caller = service_caller

        self._task = task

    async def main(self) -> None:
        await asyncio.sleep(self._task.initial_wait.total_seconds())

        await self._service_caller.call(
            services.PostAnnouncement(payload=models.Announcement(content=self._task.message, color=self._task.color)),
        )


class PeriodicAnnounce(Feature[SystemConfig, UserConfig]):
    def __init__(self, hub: Hub, system_config: ConfigData) -> None:
        super().__init__(hub, SystemConfig, UserConfig, system_config)
        self._service_caller = hub.create_caller()
        self._routine_manager = routines.RoutineManager()

    @override
    async def set_user_config(self, config: ConfigData | None) -> bool:
        result = await super().set_user_config(config)
        if not result:
            return False

        self._routine_manager.clear()

        if self.user_config is None:
            return True

        for announce in self.user_config.announcements:
            handler = AnnouncementHandler(self._service_caller, announce)
            self._routine_manager.add(handler.main, announce.interval)

        self._routine_manager.start()

        return True
