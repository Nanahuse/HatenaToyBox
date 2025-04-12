from __future__ import annotations

import asyncio
import contextlib
import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, override

from cachetools import TTLCache, cached

from common.feature import ConfigData, Feature
from schemas import events, models, services
from utils import routines
from utils.process_manager import ProcessManager

from .client_manager import ClientManager
from .config import SystemConfig, UserConfig
from .update_detector import UpdateDetector

if TYPE_CHECKING:
    from common.core import Hub

    from .twitchio_adaptor import Client


COMMENTING_MINIMUM_INTERVAL = datetime.timedelta(seconds=1)
ANNOUNCEMENT_MINIMUM_INTERVAL = datetime.timedelta(seconds=5)
SHOUTOUT_MINIMUM_INTERVAL = datetime.timedelta(minutes=2, seconds=5)  # 2分に一回がシステム上限。5秒はおまけ
POLLING_INTERVAL = datetime.timedelta(seconds=45)  # どのくらいが良いのだろうか

STREAM_INFO_CACHE_TTL = datetime.timedelta(seconds=10)
CLIP_CACHE_TTL = datetime.timedelta(seconds=10)


class TokenTag(StrEnum):
    BOT = "bot"
    STREAMER = "streamer"


class Communicator(Feature[SystemConfig, UserConfig]):
    def __init__(self, hub: Hub, system_config: ConfigData) -> None:
        super().__init__(hub, SystemConfig, UserConfig, system_config)
        self._event_publisher = hub.create_publisher()

        self._comment_queue = asyncio.Queue[models.Comment]()
        self._announce_queue = asyncio.Queue[models.Announcement]()
        self._shoutout_queue = asyncio.Queue[models.User]()

        self._client_manager = ProcessManager[ClientManager]()
        self._update_detector = UpdateDetector(self.logger, self._event_publisher)

        self._routine_manager = routines.RoutineManager()

        # Initialize events
        hub.add_event_handler(events.TwitchChannelConnected, self._on_twitch_channel_connected)

        # Initialize services
        hub.add_service_handler(services.FetchClip, self.fetch_clips)
        hub.add_service_handler(services.FetchStreamInfo, self.fetch_stream_info)
        hub.add_service_handler(services.SendComment, self._comment_queue.put)
        hub.add_service_handler(services.PostAnnouncement, self._announce_queue.put)
        hub.add_service_handler(services.Shoutout, self._shoutout_queue.put)

    @override
    async def run(self) -> None:
        self._routine_manager.add(self._send_comment, COMMENTING_MINIMUM_INTERVAL)
        self._routine_manager.add(self._post_announce, ANNOUNCEMENT_MINIMUM_INTERVAL)
        self._routine_manager.add(self._shoutout, SHOUTOUT_MINIMUM_INTERVAL)
        self._routine_manager.add(self._polling, POLLING_INTERVAL)

        self._routine_manager.start()
        await super().run()
        self._routine_manager.clear()

    @override
    async def set_user_config(self, config: ConfigData | None) -> bool:
        result = await super().set_user_config(config)
        if not result:
            return False

        if self.user_config is None:
            await self._client_manager.update(None)
            return True

        await self._client_manager.update(
            ClientManager(
                self.logger,
                self._event_publisher,
                self.system_config.token_file_directory,
                self.system_config.stream_info_storage_directory,
                self.user_config.channel,
                self.user_config.enable_stream_info_command,
            ),
        )

        self.logger.info("config updated. target channel: %s", self.user_config.channel)
        return True

    async def _on_twitch_channel_connected(self, _: events.TwitchChannelConnected) -> None:
        try:
            client = await self._get_twitch_client()

            stream_info = await client.fetch_stream_info(None)
            clips = await client.fetch_clips(datetime.timedelta(minutes=10))

            self._update_detector.initialize(stream_info, clips)

            with contextlib.suppress(RuntimeError):
                await self._polling()

        except Exception:
            self.logger.exception("Failed to initialize update detector")

    async def _get_twitch_client(self) -> Client:
        client_manager = await self._client_manager.get()

        if client_manager is None:
            msg = "ClientManger is not initialized"
            raise RuntimeError(msg)

        client = await client_manager.get_twitch_client()

        if client is None:
            msg = "TwitchClient is not initialized"
            raise RuntimeError(msg)

        return client

    @cached(cache=TTLCache(maxsize=10, ttl=STREAM_INFO_CACHE_TTL.total_seconds()))
    async def fetch_stream_info(self, user: models.User | None) -> models.StreamInfo:
        client = await self._get_twitch_client()

        return await client.fetch_stream_info(user)

    @cached(cache=TTLCache(maxsize=10, ttl=CLIP_CACHE_TTL.total_seconds()))
    async def fetch_clips(self, duration: datetime.timedelta) -> list[models.Clip]:
        client = await self._get_twitch_client()

        return await client.fetch_clips(duration)

    # region: Routines

    async def _send_comment(self) -> None:
        comment = await self._comment_queue.get()

        try:
            client = await self._get_twitch_client()

            await client.send_comment(comment)
        except RuntimeError:
            await self._comment_queue.put(comment)

    async def _post_announce(self) -> None:
        announce = await self._announce_queue.get()

        try:
            client = await self._get_twitch_client()

            await client.post_announcement(announce)
        except RuntimeError:
            await self._announce_queue.put(announce)

    async def _shoutout(self) -> None:
        user = await self._shoutout_queue.get()

        try:
            client = await self._get_twitch_client()

            await client.shoutout(user)
        except RuntimeError:
            await self._shoutout_queue.put(user)

    async def _polling(self) -> None:
        try:
            client = await self._get_twitch_client()

            stream_info = await client.fetch_stream_info(None)
            clips = await client.fetch_clips(datetime.timedelta(minutes=10))

            await self._update_detector.update(stream_info, clips)
        except RuntimeError:
            return
