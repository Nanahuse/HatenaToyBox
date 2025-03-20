from __future__ import annotations

from typing import TYPE_CHECKING

import twitchio.errors as twitchio_errors
from twitchio.ext import commands

from schemas import models
from utils.model_file import ModelFile

from . import exceptions
from .base_twitch_client import BaseTwitchClient
from .custom_commands import StreamInfoCommand

if TYPE_CHECKING:
    import asyncio
    from logging import Logger
    from pathlib import Path

    from pydantic import SecretStr

    from common.core.event_publisher import EventPublisher


class StreamInfoManager(BaseTwitchClient):
    def __init__(  # noqa: PLR0913
        self,
        logger: Logger,
        token: SecretStr,
        channel: str,
        stream_info_storage_directory: Path,
        publisher: EventPublisher,
        connection_event: asyncio.Event,
    ) -> None:
        super().__init__(logger, token, channel, connection_event)
        self._publisher = publisher
        self._stream_info_storage_directory = stream_info_storage_directory
        self._stream_info_storage = dict[str, ModelFile[models.StreamInfo]]()

    @commands.command()  # type: ignore[misc]
    async def info(self, context: commands.Context, action: str, name: str) -> None:
        if not context.author.is_broadcaster and not context.author.is_mod:
            self._logger.error("Execute by non-broadcaster and non-moderator user - %s", context.author.name)
            return

        if name in self._stream_info_storage:
            model_file = self._stream_info_storage[name]
        else:
            model_file = ModelFile(
                models.StreamInfo,
                self._stream_info_storage_directory / f"{name}.json",
                self._logger,
            )
            self._stream_info_storage[name] = model_file

        match action:
            case StreamInfoCommand.SAVE:
                stream_info = await self.fetch_stream_info(None)
                model_file.update(stream_info)
                self._logger.info("StreamInfo saved. Name: %s", name)
                return

            case StreamInfoCommand.LOAD:
                if model_file.data is None:
                    self._logger.error("StreamInfo is not saved yet. Name: %s", name)
                    return
                try:
                    await self._update_stream_info(model_file.data)
                except exceptions.TwitchioAdaptorError:
                    self._logger.exception("StreamInfo update failed.")
                else:
                    self._logger.info("StreamInfo loaded. Name: %s", name)

                return

            case StreamInfoCommand.CLEAR:
                model_file.clear()
                self._logger.info("StreamInfo cleared. Name: %s", name)
                return

    async def _update_stream_info(self, stream_info: models.StreamInfo) -> None:
        if self.is_connected is False:
            msg = "StreamInfo update failed."
            raise exceptions.NotConnectedError(msg)

        try:
            await self._user.modify_stream(
                self._token.get_secret_value(),
                game_id=None if stream_info.game is None else stream_info.game.game_id,
                title=stream_info.title,
                tags=stream_info.tags,
            )
        except twitchio_errors.Unauthorized as e:
            raise exceptions.StreamInfoUpdateError(e.message) from e
        except twitchio_errors.HTTPException as e:
            raise exceptions.StreamInfoUpdateError(e.message) from e
        except BaseException as e:
            raise exceptions.UnhandledError(str(e)) from e
