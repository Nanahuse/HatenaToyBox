from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, cast, override

import twitchio.errors as twitchio_errors
from twitchio.ext import commands, eventsub

from schemas import events, models

from . import exceptions
from .base_twitch_client import BaseTwitchClient
from .utils import cast_user, twitchio_models
from .utils.cast_message import cast_message

if TYPE_CHECKING:
    import asyncio
    from datetime import timedelta
    from logging import Logger

    from pydantic import SecretStr

    from common.core import EventPublisher


class Client(Protocol):
    async def run(self) -> None: ...

    async def close(self) -> None: ...

    async def send_comment(self, comment: models.Comment) -> None: ...

    async def post_announcement(self, announcement: models.Announcement) -> None: ...

    async def shoutout(self, user: models.User) -> None: ...

    async def fetch_stream_info(self, user: models.User | None) -> models.StreamInfo: ...

    async def fetch_clips(self, duration: timedelta) -> list[models.Clip]: ...


class TwitchClient(BaseTwitchClient):
    def __init__(
        self,
        logger: Logger,
        token: SecretStr,
        channel: str,
        publisher: EventPublisher,
        connection_event: asyncio.Event,
    ) -> None:
        super().__init__(logger, token, channel, connection_event)

        self._publisher = publisher

        self._ws_client: eventsub.EventSubWSClient | None = None

    @override
    @property
    def is_connected(self) -> bool:
        return super().is_connected and self._ws_client is not None

    # region: twitchio events

    async def event_channel_joined(self, channel: twitchio_models.Channel) -> None:
        if self.is_connected:
            return

        # initialize event sub

        try:
            ws_client = eventsub.EventSubWSClient(self)

            self.add_event(self._notification_stream_start, name="event_eventsub_notification_stream_start")
            self.add_event(self._notification_raid, name="event_eventsub_notification_raid")
            self.add_event(self._notification_followV2, name="event_eventsub_notification_followV2")

            user = await channel.user()

            await ws_client.subscribe_channel_stream_start(token=self._token.get_secret_value(), broadcaster=user)
            await ws_client.subscribe_channel_raid(token=self._token.get_secret_value(), to_broadcaster=user)
            await ws_client.subscribe_channel_follows_v2(
                token=self._token.get_secret_value(),
                broadcaster=user,
                moderator=self.user_id,
            )
            self._ws_client = ws_client
        except twitchio_errors.Unauthorized:
            self._logger.exception("Failed to subscribe to eventsub")

        await super().event_channel_joined(channel)

    async def event_message(self, message: twitchio_models.Message) -> None:
        if not self.is_connected:
            return
        if message.content is None:
            return

        # handle command
        if not message.echo:
            context = cast("commands.Context", await self.get_context(message))
            if context.prefix:
                await self.invoke(context)
                return

        # message event
        try:
            await self._publisher.publish(events.NewMessageReceived(message=cast_message(message, self._bot_user)))
        except BaseException as e:
            raise exceptions.UnhandledError(str(e)) from e

    async def _notification_stream_start(self, event: eventsub.models.NotificationEvent) -> None:
        stream = event.data
        if not isinstance(stream, eventsub.models.StreamOnlineData):
            return

        await self._publisher.publish(events.StreamWentOnline())

    async def _notification_raid(self, event: eventsub.models.NotificationEvent) -> None:
        raid_data = event.data
        if not isinstance(raid_data, eventsub.models.ChannelRaidData):
            return

        user = await raid_data.raider.fetch()

        await self._publisher.publish(events.RaidDetected(raider=cast_user(user)))

    async def _notification_followV2(self, event: eventsub.models.NotificationEvent) -> None:  # noqa: N802
        follow_data = event.data
        if not isinstance(follow_data, eventsub.models.ChannelFollowData):
            return

        user = await follow_data.user.fetch()

        await self._publisher.publish(events.FollowDetected(user=cast_user(user)))

    # region: methods

    async def send_comment(self, comment: models.Comment) -> None:
        if not self.is_connected:
            return

        content = f"/me {comment.content}" if comment.is_italic else comment.content

        try:
            await self._channel.send(content)
            self._logger.debug("Comment - %s", content)
        except twitchio_errors.Unauthorized as e:
            raise exceptions.UnauthorizedError(e.message) from e
        except BaseException as e:
            raise exceptions.UnhandledError(str(e)) from e

    async def post_announcement(self, announcement: models.Announcement) -> None:
        if not self.is_connected:
            return

        try:
            await self._user.chat_announcement(
                self._http.token,
                self._bot_user.id,
                message=announcement.content,
                color=announcement.color,
            )
            self._logger.debug("Announce - %s", announcement.content)
        except twitchio_errors.Unauthorized as e:
            raise exceptions.UnauthorizedError(e.message) from e
        except BaseException as e:
            raise exceptions.UnhandledError(str(e)) from e

    async def shoutout(self, user: models.User) -> None:
        if not self.is_connected:
            return

        try:
            await self._user.shoutout(self._http.token, user.id, self._bot_user.id)
            self._logger.debug("Shoutout - %s", user.name)
        except twitchio_errors.Unauthorized as e:
            raise exceptions.UnauthorizedError(e.message) from e
        except BaseException as e:
            raise exceptions.UnhandledError(str(e)) from e
