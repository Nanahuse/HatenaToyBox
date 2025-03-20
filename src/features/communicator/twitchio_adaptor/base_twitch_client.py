from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, cast

import twitchio.errors as twitchio_errors
from twitchio.ext import commands

from schemas import models

from . import exceptions

if TYPE_CHECKING:
    import asyncio
    from logging import Logger

    from pydantic import SecretStr

    from .utils import twitchio_models


class BaseTwitchClient(commands.Bot):  # type:ignore[misc]
    def __init__(
        self,
        logger: Logger,
        token: SecretStr,
        channel: str,
        connection_event: asyncio.Event,
    ) -> None:
        super().__init__(token.get_secret_value(), client_secret="", prefix="!", initial_channels=[channel])
        self._logger = logger.getChild(type(self).__name__)
        self.__token = token

        self._connection_event = connection_event

        # 接続後初期化。直接アクセスせず、同名のproperty経由でアクセスする。
        self.__channel: twitchio_models.Channel | None = None
        self.__user: twitchio_models.User | None = None
        self.__bot_user: twitchio_models.User | None = None

    # region: properties

    @property
    def _channel(self) -> twitchio_models.Channel:
        if self.__channel is None:
            msg = "Not connected yet"
            raise exceptions.ImplementationError(msg)

        return self.__channel

    @property
    def _user(self) -> twitchio_models.User:
        if self.__user is None:
            msg = "Not connected yet"
            raise exceptions.ImplementationError(msg)

        return self.__user

    @property
    def _bot_user(self) -> twitchio_models.User:
        if self.__bot_user is None:
            msg = "Not connected yet"
            raise exceptions.ImplementationError(msg)

        return self.__bot_user

    @property
    def _token(self) -> SecretStr:
        return self.__token

    @property
    def is_connected(self) -> bool:
        return all(
            (
                self.__channel is not None,
                self.__user is not None,
                self.__bot_user is not None,
            ),
        )

    @property
    def is_streamer(self) -> bool:
        return cast("bool", self._user.id == self._bot_user.id)

    # region: TaskService methods

    async def run(self) -> None:
        try:
            await super().start()
        except twitchio_errors.AuthenticationError as e:
            msg = "Twitch authentication failed."
            raise exceptions.UnauthorizedError(msg) from e
        except BaseException as e:
            raise exceptions.UnhandledError(str(e)) from e

    async def close(self) -> None:
        self._logger.debug("Closing")
        await super().close()

    # region: twitchio events

    async def event_channel_joined(self, channel: twitchio_models.Channel) -> None:
        if self.is_connected:
            return

        # initialize

        self._logger.debug("Connected to %s", channel.name)
        self.__channel = channel
        self.__user = await channel.user()
        self.__bot_user = (await self.fetch_users(ids=[self.user_id]))[0]

        self._connection_event.set()

    async def event_channel_join_failure(self, channel: str) -> None:
        self._logger.error("Failed to connect to %s", channel)
        self._connection_event.set()

    async def event_command_error(self, _: commands.Context, error: Exception) -> None:
        match error:
            case commands.CommandNotFound():
                self._logger.warning("Command Failed - %s", error)
            case _:
                self._logger.error("Command Failed - %s", error)

    # region: commands

    @commands.command()  # type: ignore[misc]
    async def info(self, context: commands.Context, action: str, name: str) -> None:
        pass

    # region: methods

    async def fetch_stream_info(self, user: models.User | None) -> models.StreamInfo:
        if not self.is_connected:
            msg = "Not connected yet"
            raise exceptions.UnauthorizedError(msg)

        name = user.name if user is not None else self._user.name

        channel_info = await self.fetch_channel(name)

        if channel_info.game_id == "":
            game = None
        else:
            game = models.Game(game_id=channel_info.game_id, name=channel_info.game_name)

        return models.StreamInfo(title=channel_info.title, game=game, tags=channel_info.tags)

    async def fetch_clips(self, duration: datetime.timedelta) -> list[models.Clip]:
        if not self.is_connected:
            msg = "Not connected yet"
            raise exceptions.UnauthorizedError(msg)

        started_at = datetime.datetime.now(datetime.UTC) - duration

        clips = await self._user.fetch_clips(started_at=started_at)

        self._logger.debug("Find clips(len=%d) duration: %s", len(clips), duration)

        return [models.Clip(url=clip.url, title=clip.title, creator=clip.creator.name or "Anonymous") for clip in clips]
