import asyncio
import datetime
import logging
from collections.abc import Generator
from datetime import UTC
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
import twitchio
import twitchio.errors as twitchio_errors
from freezegun import freeze_time
from pydantic import SecretStr
from twitchio.ext import commands, eventsub
from twitchio.ext.eventsub import EventSubWSClient as RealEventSubWSClient

from common.core import EventPublisher
from features.communicator.twitchio_adaptor import exceptions
from features.communicator.twitchio_adaptor.base_twitch_client import BaseTwitchClient
from features.communicator.twitchio_adaptor.twitch_client import TwitchClient
from features.communicator.twitchio_adaptor.utils import twitchio_models
from schemas import events, models

# --- Constants ---
TEST_CHANNEL_NAME = "testchannel"
TEST_TOKEN_VALUE = "testtoken123"
TEST_BOT_USER_ID = 123
TEST_BOT_USER_NAME = "test_bot"
TEST_BOT_USER_DISPLAY_NAME = "Test_Bot"
TEST_STREAMER_USER_ID = "streamer456"
NOW = datetime.datetime(2023, 10, 27, 12, 0, 0, tzinfo=UTC)

# --- Fixtures ---


@pytest.fixture
def mock_logger() -> MagicMock:
    logger = MagicMock(spec=logging.Logger)
    logger.getChild.return_value = logger
    return logger


@pytest.fixture
def mock_token() -> SecretStr:
    return SecretStr(TEST_TOKEN_VALUE)


@pytest.fixture
def mock_publisher() -> AsyncMock:
    return AsyncMock(spec=EventPublisher)


@pytest.fixture
def mock_connection_event() -> AsyncMock:
    event = AsyncMock(spec=asyncio.Event)
    event.is_set.return_value = False  # Start as not connected
    return event


@pytest.fixture
def mock_twitchio_channel() -> AsyncMock:
    channel = AsyncMock(spec=twitchio_models.Channel)
    channel.name = TEST_CHANNEL_NAME
    channel.send = AsyncMock()
    channel.user = AsyncMock()  # Mock the user() method
    return channel


@pytest.fixture
def mock_twitchio_streamer_user() -> AsyncMock:
    user = AsyncMock(spec=twitchio_models.User)
    user.id = TEST_STREAMER_USER_ID
    user.name = TEST_CHANNEL_NAME
    user.fetch_clips = AsyncMock(return_value=[])
    user.chat_announcement = AsyncMock()
    user.shoutout = AsyncMock()
    user.fetch = AsyncMock(return_value=user)  # For fetch() calls on user objects
    return user


@pytest.fixture
def mock_twitchio_bot_user() -> MagicMock:
    user = MagicMock(spec=twitchio_models.User)
    user.id = TEST_BOT_USER_ID  # Use integer ID
    user.name = TEST_BOT_USER_NAME
    user.display_name = TEST_BOT_USER_DISPLAY_NAME
    user.fetch = AsyncMock(return_value=user)
    return user


@pytest.fixture
def mock_eventsub_client() -> MagicMock:
    # This fixture might still be useful if you need a pre-configured instance mock elsewhere
    client = MagicMock(spec=RealEventSubWSClient)  # Use the real class here too
    client.subscribe_channel_stream_start = AsyncMock()
    client.subscribe_channel_raid = AsyncMock()
    client.subscribe_channel_follows_v2 = AsyncMock()
    return client


@pytest.fixture
def mock_http_client() -> MagicMock:
    http = MagicMock(spec=twitchio.http.TwitchHTTP)
    http.token = TEST_TOKEN_VALUE  # Simulate token access
    return http


@pytest.fixture
def twitch_client(
    mock_logger: MagicMock,
    mock_token: SecretStr,
    mock_publisher: AsyncMock,
    mock_connection_event: AsyncMock,
    mock_twitchio_channel: AsyncMock,
    mock_twitchio_streamer_user: AsyncMock,
    mock_twitchio_bot_user: MagicMock,
    mock_http_client: MagicMock,
) -> Generator[TwitchClient, None, None]:
    # Patch BaseTwitchClient.__init__ to avoid its complexities during init
    # Patch EventSubWSClient instantiation
    with (
        patch.object(BaseTwitchClient, "__init__", return_value=None) as mock_base_init,
        patch("features.communicator.twitchio_adaptor.twitch_client.eventsub.EventSubWSClient") as mock_eventsub_cls,
    ):
        mock_eventsub_cls.return_value = MagicMock(spec=RealEventSubWSClient)

        client = TwitchClient(
            logger=mock_logger,
            token=mock_token,
            channel=TEST_CHANNEL_NAME,
            publisher=mock_publisher,
            connection_event=mock_connection_event,
        )

        # Manually set attributes usually set by BaseTwitchClient or assumed to exist after connection
        client._logger = mock_logger
        client._BaseTwitchClient__token = mock_token  # Use name mangling if necessary
        client._publisher = mock_publisher
        client._connection_event = mock_connection_event
        client._ws_client = None  # Start as None

        # Mock attributes that would be set in event_channel_joined for testing methods
        client._BaseTwitchClient__channel = mock_twitchio_channel
        client._BaseTwitchClient__user = mock_twitchio_streamer_user
        client._BaseTwitchClient__bot_user = mock_twitchio_bot_user
        client._http = mock_http_client  # Set the mocked http client

        client._http.user_id = TEST_BOT_USER_ID
        client._events = {}
        client.registered_callbacks = {}
        client._waiting = []  # Also initialize this, might be needed later

        # Mock the user() method return value on the channel mock
        mock_twitchio_channel.user.return_value = mock_twitchio_streamer_user

        yield client

    mock_base_init.assert_called_once_with(mock_logger, mock_token, TEST_CHANNEL_NAME, mock_connection_event)


# --- Test Cases ---


def test_init(twitch_client: TwitchClient, mock_logger: MagicMock, mock_publisher: AsyncMock) -> None:
    """Test initialization of TwitchClient."""
    assert twitch_client._logger is mock_logger
    assert twitch_client._publisher is mock_publisher
    assert twitch_client._ws_client is None
    # Base init call is checked in the fixture teardown


def test_is_connected(twitch_client: TwitchClient, mock_eventsub_client: MagicMock) -> None:
    """Test the is_connected property."""
    # Initially, Base is not connected, ws_client is None
    with patch.object(BaseTwitchClient, "is_connected", False, create=True):
        assert not twitch_client.is_connected

    # Base connected, ws_client is None
    with patch.object(BaseTwitchClient, "is_connected", True, create=True):
        assert not twitch_client.is_connected

    # Base connected, ws_client is set
    with patch.object(BaseTwitchClient, "is_connected", True, create=True):
        twitch_client._ws_client = mock_eventsub_client
        assert twitch_client.is_connected

    # Base not connected, ws_client is set (shouldn't happen but test logic)
    with patch.object(BaseTwitchClient, "is_connected", False, create=True):
        twitch_client._ws_client = mock_eventsub_client
        assert not twitch_client.is_connected


@pytest.mark.asyncio
async def test_event_channel_joined_already_connected(
    twitch_client: TwitchClient,
    mock_twitchio_channel: AsyncMock,
) -> None:
    """Test event_channel_joined does nothing if already connected."""
    with patch.object(TwitchClient, "is_connected", True, create=True):
        await twitch_client.event_channel_joined(mock_twitchio_channel)
        # Assert no major setup methods were called again
        assert twitch_client._ws_client is None  # Should not have been set
        mock_twitchio_channel.user.assert_not_awaited()


@pytest.mark.asyncio
async def test_event_channel_joined_success(
    twitch_client: TwitchClient,
    mock_twitchio_channel: AsyncMock,
    mock_twitchio_streamer_user: AsyncMock,
    mock_twitchio_bot_user: AsyncMock,
    mock_eventsub_client: MagicMock,
    mock_token: SecretStr,
    mock_connection_event: AsyncMock,
) -> None:
    """Test successful initialization in event_channel_joined."""
    # Ensure base class thinks it's not connected initially
    with (
        patch.object(BaseTwitchClient, "is_connected", False, create=True),
        patch(
            "features.communicator.twitchio_adaptor.twitch_client.eventsub.EventSubWSClient",
            return_value=mock_eventsub_client,
        ) as mock_eventsub_cls,
        # --- FIX: Remove this patch ---
        # patch.object(BaseTwitchClient, "event_channel_joined", new_callable=AsyncMock) as mock_base_event_joined,
        # --- End FIX ---
        patch.object(TwitchClient, "add_event") as mock_add_event,
        patch.object(
            # Keep patching fetch_users on the TwitchClient instance being tested
            TwitchClient,
            "fetch_users",
            new_callable=AsyncMock,
            return_value=[mock_twitchio_bot_user],
        ) as mock_fetch_users,
    ):
        # Mock the channel.user() call
        mock_twitchio_channel.user.return_value = mock_twitchio_streamer_user

        # Ensure user_id is set for the base class method to use
        # (Already done in the fixture by setting client._http.user_id)

        await twitch_client.event_channel_joined(mock_twitchio_channel)

        # Assert EventSubWSClient was created
        mock_eventsub_cls.assert_called_once_with(twitch_client)

        # Assert add_event was called for notifications
        expected_add_event_calls = [
            call(twitch_client._notification_stream_start, name="event_eventsub_notification_stream_start"),
            call(twitch_client._notification_raid, name="event_eventsub_notification_raid"),
            call(twitch_client._notification_followV2, name="event_eventsub_notification_followV2"),
        ]
        mock_add_event.assert_has_calls(expected_add_event_calls, any_order=True)

        # Assert subscriptions were called
        token_val = mock_token.get_secret_value()
        mock_eventsub_client.subscribe_channel_stream_start.assert_awaited_once_with(
            token=token_val, broadcaster=mock_twitchio_streamer_user
        )
        mock_eventsub_client.subscribe_channel_raid.assert_awaited_once_with(
            token=token_val, to_broadcaster=mock_twitchio_streamer_user
        )
        mock_eventsub_client.subscribe_channel_follows_v2.assert_awaited_once_with(
            token=token_val, broadcaster=mock_twitchio_streamer_user, moderator=TEST_BOT_USER_ID
        )

        # Assert ws_client is set
        assert twitch_client._ws_client is mock_eventsub_client

        # Assert attributes set by the *real* base class method are now set
        assert twitch_client._BaseTwitchClient__channel is mock_twitchio_channel
        assert twitch_client._BaseTwitchClient__user is mock_twitchio_streamer_user
        assert twitch_client._BaseTwitchClient__bot_user is mock_twitchio_bot_user

        # Assert fetch_users was called by the *real* base class method
        mock_fetch_users.assert_awaited_once_with(ids=[TEST_BOT_USER_ID])

        # Assert connection event was set by the *real* base class method
        mock_connection_event.set.assert_called_once()


@pytest.mark.asyncio
async def test_event_channel_joined_eventsub_unauthorized(
    twitch_client: TwitchClient,
    mock_twitchio_channel: AsyncMock,
    mock_twitchio_streamer_user: AsyncMock,
) -> None:
    """Test event_channel_joined handles UnauthorizedError during eventsub setup."""
    auth_error = twitchio_errors.Unauthorized("Eventsub auth failed")
    with (
        patch.object(BaseTwitchClient, "is_connected", False, create=True),
        patch("features.communicator.twitchio_adaptor.twitch_client.eventsub.EventSubWSClient") as mock_eventsub_cls,
        patch.object(BaseTwitchClient, "event_channel_joined", new_callable=AsyncMock) as mock_base_event_joined,
    ):
        # Make one of the subscribe calls fail
        mock_ws_instance = MagicMock()
        mock_ws_instance.subscribe_channel_stream_start.side_effect = auth_error
        mock_eventsub_cls.return_value = mock_ws_instance

        # Mock the channel.user() call
        mock_twitchio_channel.user.return_value = mock_twitchio_streamer_user

        await twitch_client.event_channel_joined(mock_twitchio_channel)

        # Assert ws_client was NOT set
        assert twitch_client._ws_client is None

        # Assert base class method was still called
        mock_base_event_joined.assert_awaited_once_with(mock_twitchio_channel)


@pytest.mark.asyncio
async def test_event_message_not_connected(twitch_client: TwitchClient, mock_publisher: AsyncMock) -> None:
    """Test event_message does nothing if not connected."""
    mock_message = MagicMock(spec=twitchio_models.Message)
    with patch.object(TwitchClient, "is_connected", False, create=True):
        await twitch_client.event_message(mock_message)
        mock_publisher.publish.assert_not_called()


@pytest.mark.asyncio
async def test_event_message_no_content(twitch_client: TwitchClient, mock_publisher: AsyncMock) -> None:
    """Test event_message does nothing if message content is None."""
    mock_message = MagicMock(spec=twitchio_models.Message)
    mock_message.content = None
    with patch.object(TwitchClient, "is_connected", True, create=True):
        await twitch_client.event_message(mock_message)
        mock_publisher.publish.assert_not_called()


@pytest.mark.asyncio
async def test_event_message_is_command(twitch_client: TwitchClient, mock_publisher: AsyncMock) -> None:
    """Test event_message invokes command handler if it's a command."""
    mock_message = MagicMock(spec=twitchio_models.Message)
    mock_message.content = "!hello"
    mock_message.echo = False
    mock_context = MagicMock(spec=commands.Context)
    mock_context.prefix = "!"

    with (
        patch.object(TwitchClient, "is_connected", True, create=True),
        patch.object(
            TwitchClient, "get_context", new_callable=AsyncMock, return_value=mock_context
        ) as mock_get_context,
        patch.object(TwitchClient, "invoke", new_callable=AsyncMock) as mock_invoke,
    ):
        await twitch_client.event_message(mock_message)

        mock_get_context.assert_awaited_once_with(mock_message)
        mock_invoke.assert_awaited_once_with(mock_context)
        mock_publisher.publish.assert_not_called()


@pytest.mark.asyncio
async def test_event_message_is_echo(twitch_client: TwitchClient, mock_publisher: AsyncMock) -> None:
    """Test event_message ignores echo messages."""
    mock_message = MagicMock(spec=twitchio_models.Message)
    mock_message.content = "hello"
    mock_message.echo = True  # Echo message
    mock_message.author = None  # author を None で設定
    mock_message.tags = {}  # tags を空辞書で設定

    with (
        patch.object(TwitchClient, "is_connected", True, create=True),
        patch.object(TwitchClient, "get_context", new_callable=AsyncMock) as mock_get_context,
        patch.object(TwitchClient, "invoke", new_callable=AsyncMock) as mock_invoke,
    ):
        await twitch_client.event_message(mock_message)

        mock_get_context.assert_not_called()
        mock_invoke.assert_not_called()
        mock_publisher.publish.assert_awaited_once_with(
            events.NewMessageReceived(
                message=models.Message(
                    content=mock_message.content,
                    parsed_content=[mock_message.content],
                    author=models.User(
                        id=TEST_BOT_USER_ID, name=TEST_BOT_USER_NAME, display_name=TEST_BOT_USER_DISPLAY_NAME
                    ),
                    is_echo=mock_message.echo,
                )
            )
        )


@pytest.mark.asyncio
async def test_event_message_publishes_event(
    twitch_client: TwitchClient,
    mock_publisher: AsyncMock,
    mock_twitchio_bot_user: AsyncMock,
) -> None:
    """Test event_message publishes NewMessageReceived for regular messages."""
    mock_message = MagicMock(spec=twitchio_models.Message)
    mock_message.content = "hello world"
    mock_message.echo = False
    mock_context = MagicMock(spec=commands.Context)
    mock_context.prefix = None  # Not a command

    mock_model_message = models.Message(
        content=mock_message.content,
        parsed_content=[mock_message.content],
        author=models.User(id=1, name="a", display_name="A"),
        is_italic=False,
    )

    with (
        patch.object(TwitchClient, "is_connected", True, create=True),
        patch.object(
            TwitchClient, "get_context", new_callable=AsyncMock, return_value=mock_context
        ) as mock_get_context,
        patch.object(TwitchClient, "invoke", new_callable=AsyncMock) as mock_invoke,
        patch(
            "features.communicator.twitchio_adaptor.twitch_client.cast_message", return_value=mock_model_message
        ) as mock_cast_message,
    ):
        await twitch_client.event_message(mock_message)

        mock_get_context.assert_awaited_once_with(mock_message)
        mock_invoke.assert_not_called()  # Not invoked as prefix is None
        mock_cast_message.assert_called_once_with(mock_message, mock_twitchio_bot_user)
        mock_publisher.publish.assert_awaited_once_with(events.NewMessageReceived(message=mock_model_message))


@pytest.mark.asyncio
async def test_event_message_publish_exception(
    twitch_client: TwitchClient,
    mock_publisher: AsyncMock,
) -> None:
    """Test event_message handles exceptions during publishing."""
    mock_message = MagicMock(spec=twitchio_models.Message)
    mock_message.content = "hello world"
    mock_message.echo = False
    mock_context = MagicMock(spec=commands.Context)
    mock_context.prefix = None  # Not a command

    mock_model_message = models.Message(
        content=mock_message.content,
        parsed_content=[mock_message.content],
        author=models.User(id=1, name="a", display_name="A"),
        is_italic=False,
    )

    publish_error = ValueError("Publish failed")
    mock_publisher.publish.side_effect = publish_error

    with (
        patch.object(TwitchClient, "is_connected", True, create=True),
        patch.object(TwitchClient, "get_context", new_callable=AsyncMock, return_value=mock_context),
        patch.object(TwitchClient, "invoke", new_callable=AsyncMock),
        patch("features.communicator.twitchio_adaptor.twitch_client.cast_message", return_value=mock_model_message),
    ):
        with pytest.raises(exceptions.UnhandledError) as exc_info:
            await twitch_client.event_message(mock_message)

        assert str(publish_error) in str(exc_info.value)
        assert exc_info.value.__cause__ is publish_error
        mock_publisher.publish.assert_awaited_once()  # Ensure it was called


@pytest.mark.asyncio
async def test_notification_stream_start(twitch_client: TwitchClient, mock_publisher: AsyncMock) -> None:
    """Test _notification_stream_start publishes StreamWentOnline."""
    mock_event_data = MagicMock(spec=eventsub.models.StreamOnlineData)
    mock_event = MagicMock(spec=eventsub.models.NotificationEvent)
    mock_event.data = mock_event_data

    await twitch_client._notification_stream_start(mock_event)

    mock_publisher.publish.assert_awaited_once_with(events.StreamWentOnline())


@pytest.mark.asyncio
async def test_notification_stream_start_wrong_type(twitch_client: TwitchClient, mock_publisher: AsyncMock) -> None:
    """Test _notification_stream_start ignores events of the wrong type."""
    mock_event_data = MagicMock()  # Not StreamOnlineData
    mock_event = MagicMock(spec=eventsub.models.NotificationEvent)
    mock_event.data = mock_event_data

    await twitch_client._notification_stream_start(mock_event)

    mock_publisher.publish.assert_not_called()


@pytest.mark.asyncio
async def test_notification_raid(twitch_client: TwitchClient, mock_publisher: AsyncMock) -> None:
    """Test _notification_raid publishes RaidDetected."""
    mock_raider_user = MagicMock(spec=twitchio_models.User)
    mock_raider_user.id = 123
    mock_raider_user.name = "raider1"
    mock_raider_user.display_name = "RaiderOne"
    mock_raider_user.fetch = AsyncMock(return_value=mock_raider_user)  # Mock fetch on the user itself

    mock_event_data = MagicMock(spec=eventsub.models.ChannelRaidData)
    mock_event_data.raider = mock_raider_user  # Assign the mock user

    mock_event = MagicMock(spec=eventsub.models.NotificationEvent)
    mock_event.data = mock_event_data

    expected_model_user = models.User(
        id=mock_raider_user.id, name=mock_raider_user.name, display_name=mock_raider_user.display_name
    )

    await twitch_client._notification_raid(mock_event)

    mock_publisher.publish.assert_awaited_once_with(events.RaidDetected(raider=expected_model_user))


@pytest.mark.asyncio
async def test_notification_raid_invalid_event(twitch_client: TwitchClient, mock_publisher: AsyncMock) -> None:
    """Test _notification_raid publishes RaidDetected."""
    mock_event = MagicMock(spec=eventsub.models.NotificationEvent)
    mock_event.data = None

    await twitch_client._notification_raid(mock_event)

    mock_publisher.publish.assert_not_called()


@pytest.mark.asyncio
async def test_notification_follow(twitch_client: TwitchClient, mock_publisher: AsyncMock) -> None:
    """Test _notification_followV2 publishes FollowDetected."""
    mock_follower_user = MagicMock(spec=twitchio_models.User)
    mock_follower_user.id = 1234
    mock_follower_user.name = "follower1"
    mock_follower_user.display_name = "FollowerOne"
    mock_follower_user.fetch = AsyncMock(return_value=mock_follower_user)

    mock_event_data = MagicMock(spec=eventsub.models.ChannelFollowData)
    mock_event_data.user = mock_follower_user

    mock_event = MagicMock(spec=eventsub.models.NotificationEvent)
    mock_event.data = mock_event_data

    expected_model_user = models.User(
        id=mock_follower_user.id, name=mock_follower_user.name, display_name=mock_follower_user.display_name
    )

    await twitch_client._notification_followV2(mock_event)

    mock_publisher.publish.assert_awaited_once_with(events.FollowDetected(user=expected_model_user))


@pytest.mark.asyncio
async def test_notification_follow_invalid_event(twitch_client: TwitchClient, mock_publisher: AsyncMock) -> None:
    """Test _notification_followV2 publishes FollowDetected."""
    mock_event = MagicMock(spec=eventsub.models.NotificationEvent)
    mock_event.data = None

    await twitch_client._notification_followV2(mock_event)
    mock_publisher.publish.assert_not_called()


@pytest.mark.asyncio
async def test_send_comment_not_connected(twitch_client: TwitchClient, mock_twitchio_channel: AsyncMock) -> None:
    """Test send_comment does nothing if not connected."""
    comment = models.Comment(content="hello", is_italic=False)
    with patch.object(TwitchClient, "is_connected", False, create=True):
        await twitch_client.send_comment(comment)
        mock_twitchio_channel.send.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("is_italic", "expected_content"),
    [
        (False, "hello there"),
        (True, "/me hello italic"),
    ],
)
async def test_send_comment_success(
    twitch_client: TwitchClient,
    mock_twitchio_channel: AsyncMock,
    is_italic: bool,  # noqa: FBT001
    expected_content: str,
) -> None:
    """Test send_comment sends the correct content."""
    content = expected_content.replace("/me ", "") if is_italic else expected_content
    comment = models.Comment(content=content, is_italic=is_italic)
    with patch.object(TwitchClient, "is_connected", True, create=True):
        await twitch_client.send_comment(comment)
        mock_twitchio_channel.send.assert_awaited_once_with(expected_content)


@pytest.mark.asyncio
async def test_send_comment_unauthorized(twitch_client: TwitchClient, mock_twitchio_channel: AsyncMock) -> None:
    """Test send_comment wraps UnauthorizedError."""
    comment = models.Comment(content="hello", is_italic=False)
    auth_error = twitchio_errors.Unauthorized("Send failed")
    mock_twitchio_channel.send.side_effect = auth_error
    with patch.object(TwitchClient, "is_connected", True, create=True):
        with pytest.raises(exceptions.UnauthorizedError) as exc_info:
            await twitch_client.send_comment(comment)
        assert auth_error.message in str(exc_info.value)
        assert exc_info.value.__cause__ is auth_error


@pytest.mark.asyncio
async def test_send_comment_unhandled_error(twitch_client: TwitchClient, mock_twitchio_channel: AsyncMock) -> None:
    """Test send_comment wraps other errors."""
    comment = models.Comment(content="hello", is_italic=False)
    other_error = ValueError("Something else failed")
    mock_twitchio_channel.send.side_effect = other_error
    with patch.object(TwitchClient, "is_connected", True, create=True):
        with pytest.raises(exceptions.UnhandledError) as exc_info:
            await twitch_client.send_comment(comment)
        assert str(other_error) in str(exc_info.value)
        assert exc_info.value.__cause__ is other_error


@pytest.mark.asyncio
async def test_post_announcement_not_connected(
    twitch_client: TwitchClient, mock_twitchio_streamer_user: AsyncMock
) -> None:
    """Test post_announcement does nothing if not connected."""
    announcement = models.Announcement(content="hello", color="orange")
    with patch.object(TwitchClient, "is_connected", False, create=True):
        await twitch_client.post_announcement(announcement)
        mock_twitchio_streamer_user.chat_announcement.assert_not_called()


@pytest.mark.asyncio
async def test_post_announcement_success(
    twitch_client: TwitchClient,
    mock_twitchio_streamer_user: AsyncMock,
    mock_twitchio_bot_user: AsyncMock,
    mock_http_client: MagicMock,
) -> None:
    """Test post_announcement calls the correct API."""
    announcement = models.Announcement(content="Test Announce", color="purple")
    with patch.object(TwitchClient, "is_connected", True, create=True):
        await twitch_client.post_announcement(announcement)
        mock_twitchio_streamer_user.chat_announcement.assert_awaited_once_with(
            mock_http_client.token,  # Access token from http client
            mock_twitchio_bot_user.id,
            message=announcement.content,
            color=announcement.color,
        )


@pytest.mark.asyncio
async def test_post_announcement_unauthorized(
    twitch_client: TwitchClient, mock_twitchio_streamer_user: AsyncMock
) -> None:
    """Test post_announcement wraps UnauthorizedError."""
    announcement = models.Announcement(content="hello", color="blue")
    auth_error = twitchio_errors.Unauthorized("Announce failed")
    mock_twitchio_streamer_user.chat_announcement.side_effect = auth_error
    with patch.object(TwitchClient, "is_connected", True, create=True):
        with pytest.raises(exceptions.UnauthorizedError) as exc_info:
            await twitch_client.post_announcement(announcement)
        assert auth_error.message in str(exc_info.value)
        assert exc_info.value.__cause__ is auth_error


@pytest.mark.asyncio
async def test_post_announcement_unhandled_error(
    twitch_client: TwitchClient,
    mock_twitchio_streamer_user: AsyncMock,
) -> None:
    """Test post_announcement wraps other errors into UnhandledError."""
    announcement = models.Announcement(content="Test Announce", color="green")
    original_error = ValueError("Simulated unexpected error during chat_announcement")
    mock_twitchio_streamer_user.chat_announcement.side_effect = original_error

    with patch.object(TwitchClient, "is_connected", True, create=True):  # noqa: SIM117
        with pytest.raises(exceptions.UnhandledError) as exc_info:
            await twitch_client.post_announcement(announcement)

    assert isinstance(exc_info.value, exceptions.UnhandledError)
    assert str(original_error) in str(exc_info.value)
    assert exc_info.value.__cause__ is original_error


@pytest.mark.asyncio
async def test_shoutout_not_connected(twitch_client: TwitchClient, mock_twitchio_streamer_user: AsyncMock) -> None:
    """Test shoutout does nothing if not connected."""
    user = models.User(id=1234, name="shoutout1", display_name="ShoutUser")
    with patch.object(TwitchClient, "is_connected", False, create=True):
        await twitch_client.shoutout(user)
        mock_twitchio_streamer_user.shoutout.assert_not_called()


@pytest.mark.asyncio
async def test_shoutout_success(
    twitch_client: TwitchClient,
    mock_twitchio_streamer_user: AsyncMock,
    mock_twitchio_bot_user: AsyncMock,
    mock_http_client: MagicMock,
) -> None:
    """Test shoutout calls the correct API."""
    user = models.User(id=1234, name="shoutout1", display_name="ShoutUser")
    with patch.object(TwitchClient, "is_connected", True, create=True):
        await twitch_client.shoutout(user)
        mock_twitchio_streamer_user.shoutout.assert_awaited_once_with(
            mock_http_client.token,
            user.id,
            mock_twitchio_bot_user.id,
        )


@pytest.mark.asyncio
async def test_shoutout_unauthorized(twitch_client: TwitchClient, mock_twitchio_streamer_user: AsyncMock) -> None:
    """Test shoutout wraps UnauthorizedError."""
    user = models.User(id=1234, name="shoutout1", display_name="ShoutUser")
    auth_error = twitchio_errors.Unauthorized("Shoutout failed")
    mock_twitchio_streamer_user.shoutout.side_effect = auth_error
    with patch.object(TwitchClient, "is_connected", True, create=True):
        with pytest.raises(exceptions.UnauthorizedError) as exc_info:
            await twitch_client.shoutout(user)
        assert auth_error.message in str(exc_info.value)
        assert exc_info.value.__cause__ is auth_error


@pytest.mark.asyncio
async def test_shoutout_unhandled_error(
    twitch_client: TwitchClient,
    mock_twitchio_streamer_user: AsyncMock,
) -> None:
    """Test shoutout wraps other errors into UnhandledError."""
    user = models.User(id=1234, name="shoutout1", display_name="ShoutUser")
    original_error = ValueError("Simulated unexpected error during shoutout")
    mock_twitchio_streamer_user.shoutout.side_effect = original_error

    with patch.object(TwitchClient, "is_connected", True, create=True):  # noqa: SIM117
        with pytest.raises(exceptions.UnhandledError) as exc_info:
            await twitch_client.shoutout(user)

    assert isinstance(exc_info.value, exceptions.UnhandledError)
    assert str(original_error) in str(exc_info.value)
    assert exc_info.value.__cause__ is original_error

    mock_twitchio_streamer_user.shoutout.assert_awaited_once()


@pytest.mark.asyncio
@freeze_time(NOW)
async def test_fetch_clips_not_connected(twitch_client: TwitchClient) -> None:
    """Test fetch_clips raises UnauthorizedError if not connected."""
    duration = datetime.timedelta(minutes=5)
    with patch.object(TwitchClient, "is_connected", False, create=True):  # noqa: SIM117
        with pytest.raises(exceptions.UnauthorizedError, match="Not connected yet"):
            await twitch_client.fetch_clips(duration)


@pytest.mark.asyncio
@freeze_time(NOW)
async def test_fetch_clips_success(
    twitch_client: TwitchClient,
    mock_twitchio_streamer_user: AsyncMock,
) -> None:
    """Test fetch_clips fetches and converts clips correctly."""
    duration = datetime.timedelta(minutes=10)
    expected_started_at = NOW - duration

    # Mock twitchio clip objects
    mock_clip1_creator = MagicMock(spec=twitchio_models.User)
    mock_clip1_creator.name = "Creator1"
    mock_clip1 = MagicMock(spec=twitchio_models.Clip, url="url1", title="Title 1", creator=mock_clip1_creator)
    mock_clip2_creator = MagicMock(spec=twitchio_models.User)  # Test anonymous creator
    mock_clip2_creator.name = None
    mock_clip2 = MagicMock(spec=twitchio_models.Clip, url="url2", title="Title 2", creator=mock_clip2_creator)

    mock_twitchio_streamer_user.fetch_clips.return_value = [mock_clip1, mock_clip2]

    with patch.object(TwitchClient, "is_connected", True, create=True):
        result = await twitch_client.fetch_clips(duration)

        mock_twitchio_streamer_user.fetch_clips.assert_awaited_once()
        # Check that started_at was passed correctly
        call_args, call_kwargs = mock_twitchio_streamer_user.fetch_clips.call_args
        assert "started_at" in call_kwargs
        assert call_kwargs["started_at"] == expected_started_at

        assert len(result) == 2
        assert isinstance(result[0], models.Clip)
        assert result[0].url == "url1"
        assert result[0].title == "Title 1"
        assert result[0].creator == "Creator1"
        assert isinstance(result[1], models.Clip)
        assert result[1].url == "url2"
        assert result[1].title == "Title 2"
        assert result[1].creator == "Anonymous"  # Check anonymous handling
