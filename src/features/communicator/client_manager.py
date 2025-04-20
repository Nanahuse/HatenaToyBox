import asyncio
import contextlib
import datetime
import logging
from enum import StrEnum
from pathlib import Path
from typing import cast

from twitchio import AuthenticationError

from common.core import EventPublisher
from schemas import errors, events, models
from utils.process_manager import Process, ProcessManager

from . import constants
from .token_manager import TokenManager
from .twitchio_adaptor import Client, StreamInfoManager, TwitchClient

CLIENT_LOGIN_TIMEOUT = datetime.timedelta(seconds=10)


class TokenTag(StrEnum):
    BOT = "bot"
    STREAMER = "streamer"


class ClientManager:
    def __init__(  # noqa: PLR0913
        self,
        logger: logging.Logger,
        event_publisher: EventPublisher,
        token_file_directory: Path,
        stream_info_storage_directory: Path,
        channel: str,
        enable_stream_info_command: bool,  # noqa: FBT001
    ) -> None:
        self._logger = logger.getChild(self.__class__.__name__)
        self._event_publisher = event_publisher

        self._token_file_directory = token_file_directory
        self._stream_info_storage_directory = stream_info_storage_directory
        self._channel = channel
        self._enable_stream_info_command = enable_stream_info_command

        self._close_event = asyncio.Event()

        self._twitch_client_manager: ProcessManager[Client] = ProcessManager()
        self._twitch_token_manager: ProcessManager[TokenManager] = ProcessManager()

        self._stream_info_manager: ProcessManager[StreamInfoManager] = ProcessManager()
        self._stream_info_token_manager: ProcessManager[TokenManager] = ProcessManager()

    async def get_twitch_client(self) -> Client | None:
        return await self._twitch_client_manager.get()

    async def run(self) -> None:
        self._logger.debug("Starting")

        await self._twitch_token_manager.update(
            TokenManager(
                self._logger,
                TokenTag.BOT,
                constants.BOT_SCOPES,
                self._token_file_directory,
                self._start_verification_bot,
                self._initialize_twitch_client,
            ),
        )

        await self._close_event.wait()

    async def close(self) -> None:
        self._logger.debug("Stopping")

        await self._twitch_client_manager.update(None)
        await self._twitch_token_manager.update(None)

        await self._stream_info_manager.update(None)
        await self._stream_info_token_manager.update(None)

        self._close_event.set()

    async def _start_verification_bot(self, verification: models.TwitchVerification) -> None:
        await self._event_publisher.publish(
            events.StartTwitchVerification(tag=TokenTag.BOT, verification=verification),
        )
        self._logger.debug("bot account verification: %s", verification)

    async def _start_verification_streamer(self, verification: models.TwitchVerification) -> None:
        await self._event_publisher.publish(
            events.StartTwitchVerification(tag=TokenTag.STREAMER, verification=verification),
        )
        self._logger.debug("streamer account verification: %s", verification)

    async def _initialize_twitch_client(self, token: models.Token) -> None:
        connection_event = asyncio.Event()
        client = TwitchClient(
            self._logger,
            token.access_token,
            self._channel,
            self._event_publisher,
            connection_event,
        )

        task = asyncio.create_task(self._run_client(client))

        try:
            await asyncio.wait_for(connection_event.wait(), timeout=CLIENT_LOGIN_TIMEOUT.total_seconds())
        except TimeoutError:
            await client.close()
            await task
            return

        await self._twitch_client_manager.store(client, task)

        self._logger.info("`%s` connected to `%s`", client.nick, self._channel)

        await self._event_publisher.publish(
            events.TwitchChannelConnected(
                connection_info=models.ConnectionInfo(
                    bot_user=cast("str", client.nick),
                    channel=self._channel,
                ),
            ),
        )

        if self._enable_stream_info_command:
            if client.is_streamer:
                await self._stream_info_token_manager.update(None)
                await self._initialize_stream_info_manager(token)

            else:
                self._streamer_token = None
                await self._stream_info_token_manager.update(
                    TokenManager(
                        self._logger,
                        TokenTag.STREAMER,
                        constants.STREAM_UPDATE_SCOPES,
                        self._token_file_directory,
                        self._start_verification_streamer,
                        self._initialize_stream_info_manager,
                    ),
                )

    async def _initialize_stream_info_manager(self, token: models.Token) -> None:
        connection_event = asyncio.Event()
        manager = StreamInfoManager(
            self._logger,
            token.access_token,
            self._channel,
            self._stream_info_storage_directory,
            self._event_publisher,
            connection_event,
        )
        task = asyncio.create_task(self._run_client(manager))

        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(connection_event.wait(), timeout=CLIENT_LOGIN_TIMEOUT.total_seconds())

        if not manager.is_connected or not manager.is_streamer:
            self._logger.error(
                "stream info manager is not connected."
                if not manager.is_connected
                else "stream info manager is not streamer."
            )
            await manager.close()
            await task
            token_manager = await self._stream_info_token_manager.get()
            if token_manager is not None:
                token_manager.clear()
            return

        self._logger.debug("stream info manager started.")

        await self._stream_info_manager.store(manager, task)

    async def _run_client(self, client: Process) -> None:
        try:
            await client.run()

        except AuthenticationError:
            self._logger.error("Twitch authentication failure.")  # noqa: TRY400
            await self._event_publisher.publish(errors.TwitchAuthenticationError())
        except BaseException as e:
            self._logger.exception("unhandled_error")
            await self._event_publisher.publish(errors.UnhandledError.instance(str(e)))
