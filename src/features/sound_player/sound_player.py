from __future__ import annotations

import asyncio
import datetime
from typing import TYPE_CHECKING, override

from playsound3 import playsound

from common.feature import ConfigData, Feature
from schemas import models, services
from utils import routines
from utils.resizable_queue import ResizableQueue

from .config import SystemConfig, UserConfig

if TYPE_CHECKING:
    from common.core import Hub


SOUND_INTERVAL = datetime.timedelta(seconds=1)


class SoundPlayer(Feature[SystemConfig, UserConfig]):
    def __init__(self, hub: Hub, system_config: ConfigData) -> None:
        super().__init__(hub, SystemConfig, UserConfig, system_config)

        self._sound_queue = ResizableQueue[models.Sound]()

        hub.add_service_handler(services.PlaySound, self._sound_queue.put)

    @override
    async def run(self) -> None:
        routine_manager = routines.RoutineManager()
        routine_manager.add(self._main, SOUND_INTERVAL)

        routine_manager.start()
        await super().run()
        routine_manager.clear()

    @override
    async def set_user_config(self, config: ConfigData | None) -> bool:
        result = await super().set_user_config(config)
        if not result:
            return False

        if self.user_config is None:
            return True

        self._sound_queue.change_maxsize(self.user_config.queue_max)

        return True

    async def _main(self) -> None:
        sound = await self._sound_queue.get()

        if not sound.path.exists() or not sound.path.is_file():
            self.logger.warning("Sound file not found: %s", sound.path)

        thread = playsound(sound.path, block=False)

        while thread.is_alive():  # noqa: ASYNC110
            await asyncio.sleep(0.1)

        self.logger.debug("Sound finished: %s", sound.path)
