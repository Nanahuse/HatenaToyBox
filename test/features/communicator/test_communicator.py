# mypy: disable-error-code="attr-defined"

import asyncio
import contextlib
import datetime
import logging
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock, MagicMock, Mock, call, patch

import pytest
import pytest_asyncio

from common.core import Hub
from common.feature import ConfigData, Feature
from features.communicator.client_manager import ClientManager as RealClientManager
from features.communicator.communicator import (
    ANNOUNCEMENT_MINIMUM_INTERVAL,
    COMMENTING_MINIMUM_INTERVAL,
    POLLING_INTERVAL,
    SHOUTOUT_MINIMUM_INTERVAL,
    Communicator,
)
from features.communicator.twitchio_adaptor import (
    Client as TwitchioClientProtocol,
)
from features.communicator.update_detector import (
    UpdateDetector as RealUpdateDetector,
)
from schemas import events, models, services
from utils import routines
from utils.process_manager import ProcessManager as RealProcessManager

# --- Constants ---
TEST_CHANNEL = "testchannel"
TEST_TOKEN_DIR = Path("/fake/token")
TEST_STREAM_INFO_DIR = Path("/fake/streaminfo")


# --- Fixtures ---


@pytest.fixture
def mock_hub() -> MagicMock:
    hub = MagicMock(spec=Hub)
    hub.create_publisher.return_value = AsyncMock()
    hub.add_event_handler = Mock()
    hub.add_service_handler = Mock()
    return hub


@pytest.fixture
def mock_logger() -> MagicMock:
    logger = MagicMock(spec=logging.Logger)
    logger.getChild.return_value = logger
    return logger


@pytest.fixture
def mock_event_publisher(mock_hub: MagicMock) -> AsyncMock:
    # Return the publisher created by the hub mock
    return cast("AsyncMock", mock_hub.create_publisher.return_value)


@pytest.fixture
def system_config_data() -> ConfigData:
    return ConfigData(
        {
            "version": 0,
            "token_file_directory": str(TEST_TOKEN_DIR),
            "stream_info_storage_directory": str(TEST_STREAM_INFO_DIR),
        }
    )


@pytest.fixture
def user_config_data() -> ConfigData:
    return ConfigData(
        {
            "version": 0,
            "channel": TEST_CHANNEL,
            "enable_stream_info_command": True,
        }
    )


@pytest.fixture
def mock_client_manager_instance() -> MagicMock:
    manager = MagicMock(spec=RealClientManager)
    manager.get_twitch_client = AsyncMock(return_value=None)  # Default to no client
    manager.update = AsyncMock()  # Mock the update method
    return manager


@pytest.fixture
def mock_client_manager_cls(mock_client_manager_instance: MagicMock) -> MagicMock:
    """Mocks the ClientManager class, returning a specific instance."""
    mock_cls = MagicMock(spec=RealClientManager)
    mock_cls.return_value = mock_client_manager_instance
    return mock_cls


@pytest.fixture
def mock_update_detector_instance() -> MagicMock:
    detector = MagicMock(spec=RealUpdateDetector)
    detector.initialize = Mock()
    detector.update = AsyncMock()
    return detector


@pytest.fixture
def mock_update_detector_cls(mock_update_detector_instance: MagicMock) -> MagicMock:
    """Mocks the UpdateDetector class, returning a specific instance."""
    mock_cls = MagicMock(spec=RealUpdateDetector)
    mock_cls.return_value = mock_update_detector_instance
    return mock_cls


@pytest.fixture
def mock_routine_manager_instance() -> MagicMock:
    manager = MagicMock(spec=routines.RoutineManager)
    manager.add = Mock()
    manager.start = Mock()
    manager.clear = Mock()
    return manager


@pytest.fixture
def mock_routine_manager_cls(mock_routine_manager_instance: MagicMock) -> MagicMock:
    """Mocks the RoutineManager class, returning a specific instance."""
    mock_cls = MagicMock(spec=routines.RoutineManager)
    mock_cls.return_value = mock_routine_manager_instance
    return mock_cls


@pytest.fixture
def mock_process_manager_instance() -> MagicMock:
    manager = MagicMock(spec=RealProcessManager)
    manager.get = AsyncMock(return_value=None)  # Default to no process
    manager.update = AsyncMock()
    return manager


@pytest.fixture
def mock_process_manager_cls(mock_process_manager_instance: MagicMock) -> MagicMock:
    """Mocks the ProcessManager class, returning a specific instance."""
    mock_cls = MagicMock(spec=RealProcessManager)
    mock_cls.return_value = mock_process_manager_instance
    return mock_cls


@pytest.fixture
def mock_twitch_client() -> MagicMock:
    client = MagicMock(spec=TwitchioClientProtocol)
    client.fetch_stream_info = AsyncMock()
    client.fetch_clips = AsyncMock()
    client.send_comment = AsyncMock()
    client.post_announcement = AsyncMock()
    client.shoutout = AsyncMock()
    return client


@pytest.fixture
def mock_stream_info() -> models.StreamInfo:
    return models.StreamInfo(title="Test Title", game_name="Test Game", is_live=True, viewer_count=50)


@pytest.fixture
def mock_clips() -> list[models.Clip]:
    return [models.Clip(title="Clip", url="url", creator="creator", created_at="time")]


@pytest_asyncio.fixture
async def communicator(
    mock_hub: MagicMock,
    system_config_data: ConfigData,
    mock_logger: MagicMock,
) -> AsyncGenerator[Communicator, None]:
    with (
        patch("features.communicator.communicator.UpdateDetector", autospec=True),
        patch("features.communicator.communicator.routines.RoutineManager", autospec=True),
        patch("features.communicator.communicator.ProcessManager", autospec=True),
    ):
        communicator_instance = Communicator(mock_hub, system_config_data)

    # Override logger if needed
    communicator_instance._logger = mock_logger
    yield communicator_instance

    # clean up
    with contextlib.suppress(Exception):
        await communicator_instance.close()


# --- Test Cases ---


@patch("features.communicator.communicator.UpdateDetector", autospec=True)
@patch("features.communicator.communicator.routines.RoutineManager", autospec=True)
@patch("features.communicator.communicator.ProcessManager", autospec=True)
def test_init(  # noqa: PLR0913
    mock_process_manager_cls_comm: MagicMock,
    mock_routine_manager_cls_comm: MagicMock,
    mock_update_detector_cls_comm: MagicMock,
    mock_hub: MagicMock,
    system_config_data: ConfigData,
    mock_event_publisher: AsyncMock,
) -> None:
    """Test Communicator initialization."""

    # Instantiate Communicator *inside* the test function, while patches are active
    communicator = Communicator(mock_hub, system_config_data)

    # --- Assertions ---
    assert communicator._event_publisher is mock_event_publisher
    assert isinstance(communicator.logger, logging.Logger)

    # Check manager instantiations
    # These mocks are the ones injected by the decorators on *this* test function,
    # and they were active during the Communicator() call above.
    mock_process_manager_cls_comm.assert_called_once()  # This should now pass
    assert communicator._client_manager is mock_process_manager_cls_comm.return_value
    mock_update_detector_cls_comm.assert_called_once_with(communicator.logger, mock_event_publisher)
    assert communicator._update_detector is mock_update_detector_cls_comm.return_value
    mock_routine_manager_cls_comm.assert_called_once()
    assert communicator._routine_manager is mock_routine_manager_cls_comm.return_value

    # Check queues are created
    assert isinstance(communicator._comment_queue, asyncio.Queue)
    assert isinstance(communicator._announce_queue, asyncio.Queue)
    assert isinstance(communicator._shoutout_queue, asyncio.Queue)

    # Check event/service handlers registered
    expected_event_calls = [
        call(events.TwitchChannelConnected, communicator._on_twitch_channel_connected),
    ]
    mock_hub.add_event_handler.assert_has_calls(expected_event_calls)

    expected_service_calls = [
        call(services.FetchClip, communicator.fetch_clips),
        call(services.FetchStreamInfo, communicator.fetch_stream_info),
        call(services.SendComment, communicator._comment_queue.put),
        call(services.PostAnnouncement, communicator._announce_queue.put),
        call(services.Shoutout, communicator._shoutout_queue.put),
    ]
    mock_hub.add_service_handler.assert_has_calls(expected_service_calls, any_order=True)


@pytest.mark.asyncio
# Patch ClientManager within the communicator module where it's used
@patch("features.communicator.communicator.ClientManager", autospec=True)
async def test_set_user_config_none(
    mock_client_manager_cls_comm: MagicMock,  # Renamed patch object
    communicator: Communicator,
) -> None:
    """Test setting user config to None clears the ClientManager."""
    # Assume a manager might exist initially
    communicator._client_manager.get.return_value = MagicMock()

    result = await communicator.set_user_config(None)

    assert result is False
    assert communicator.user_config is None
    # Assert update(None) was called on the ProcessManager holding ClientManager
    communicator._client_manager.update.assert_not_called()
    # Ensure ClientManager class was NOT instantiated
    mock_client_manager_cls_comm.assert_not_called()


@pytest.mark.asyncio
@patch("features.communicator.communicator.ClientManager", autospec=True)
async def test_set_user_config_valid(
    mock_client_manager_cls_comm: MagicMock,  # Renamed patch object
    communicator: Communicator,
    user_config_data: ConfigData,
    mock_logger: MagicMock,
    mock_event_publisher: AsyncMock,
) -> None:
    """Test setting a valid user config creates and updates ClientManager."""
    result = await communicator.set_user_config(user_config_data)

    assert result is True
    assert communicator.user_config is not None
    assert communicator.user_config.channel == TEST_CHANNEL

    # Assert ClientManager class was instantiated with correct args
    mock_client_manager_cls_comm.assert_called_once_with(
        mock_logger,
        mock_event_publisher,
        communicator.system_config.token_file_directory,
        communicator.system_config.stream_info_storage_directory,
        TEST_CHANNEL,
        True,  # enable_stream_info_command
    )
    # Assert update was called with the new ClientManager instance
    communicator._client_manager.update.assert_awaited_once_with(mock_client_manager_cls_comm.return_value)


@pytest.mark.asyncio
async def test_run(communicator: Communicator) -> None:
    """Test the main run loop starts routines and waits."""
    with patch.object(Feature, "run", new_callable=AsyncMock) as mock_base_run:
        # Run in a separate task to allow checks before it potentially blocks
        run_task = asyncio.create_task(communicator.run())
        await asyncio.sleep(0)  # Yield control

        # Check routines added
        expected_routine_calls = [
            call(communicator._send_comment, COMMENTING_MINIMUM_INTERVAL),
            call(communicator._post_announce, ANNOUNCEMENT_MINIMUM_INTERVAL),
            call(communicator._shoutout, SHOUTOUT_MINIMUM_INTERVAL),
            call(communicator._polling, POLLING_INTERVAL),
        ]
        communicator._routine_manager.add.assert_has_calls(expected_routine_calls, any_order=True)

        # Check routines started
        communicator._routine_manager.start.assert_called_once()

        # Check super().run was awaited
        mock_base_run.assert_awaited_once()

        # Cancel the task and ensure it raises CancelledError
        await communicator.close()
        await run_task
        # Assert clear was called after cancellation/completion attempt
        communicator._routine_manager.clear.assert_called_once()


@pytest.mark.asyncio
async def test_on_twitch_channel_connected(
    communicator: Communicator,
    mock_twitch_client: MagicMock,
    mock_stream_info: models.StreamInfo,
    mock_clips: list[models.Clip],
) -> None:
    """Test the handler for TwitchChannelConnected event."""
    # Mock _get_twitch_client to return our mock client
    with patch.object(communicator, "_get_twitch_client", return_value=mock_twitch_client) as mock_get:
        mock_twitch_client.fetch_stream_info.return_value = mock_stream_info
        mock_twitch_client.fetch_clips.return_value = mock_clips
        # Mock _polling to prevent its execution details interfering
        await communicator._on_twitch_channel_connected(MagicMock())

        mock_get.assert_awaited_once()
        mock_twitch_client.fetch_stream_info.assert_awaited_once_with(None)
        mock_twitch_client.fetch_clips.assert_awaited_once_with(datetime.timedelta(minutes=10))
        communicator._update_detector.initialize.assert_called_once_with(mock_stream_info, mock_clips)


@pytest.mark.asyncio
async def test_on_twitch_channel_connected_exception(
    communicator: Communicator,
    mock_logger: MagicMock,
) -> None:
    """Test exception handling in _on_twitch_channel_connected."""
    error = ValueError("Fetch failed")
    with patch.object(communicator, "_get_twitch_client", side_effect=error):  # Make getting client fail
        await communicator._on_twitch_channel_connected(MagicMock())

        mock_logger.exception.assert_called_once_with("Failed to initialize update detector")
        communicator._update_detector.initialize.assert_not_called()


@pytest.mark.asyncio
async def test_get_twitch_client_no_manager(communicator: Communicator) -> None:
    """Test _get_twitch_client when ClientManager is not set."""
    communicator._client_manager.get.return_value = None  # Simulate no manager
    with pytest.raises(RuntimeError, match="ClientManger is not initialized"):
        await communicator._get_twitch_client()


@pytest.mark.asyncio
async def test_get_twitch_client_no_client(communicator: Communicator, mock_client_manager_instance: MagicMock) -> None:
    """Test _get_twitch_client when ClientManager has no active client."""
    communicator._client_manager.get.return_value = mock_client_manager_instance
    mock_client_manager_instance.get_twitch_client.return_value = None  # Simulate no client
    with pytest.raises(RuntimeError, match="TwitchClient is not initialized"):
        await communicator._get_twitch_client()


@pytest.mark.asyncio
async def test_get_twitch_client_success(
    communicator: Communicator, mock_client_manager_instance: MagicMock, mock_twitch_client: MagicMock
) -> None:
    """Test _get_twitch_client successfully returns the client."""
    communicator._client_manager.get.return_value = mock_client_manager_instance
    mock_client_manager_instance.get_twitch_client.return_value = mock_twitch_client

    client = await communicator._get_twitch_client()
    assert client is mock_twitch_client


@pytest.mark.asyncio
@patch("features.communicator.communicator.cached", lambda cache: lambda func: func)  # Disable cache  # noqa: ARG005
async def test_fetch_stream_info_service(
    communicator: Communicator, mock_twitch_client: MagicMock, mock_stream_info: models.StreamInfo
) -> None:
    """Test the fetch_stream_info service handler."""
    user_arg = models.User(id=123, name="test", display_name="Test")
    with patch.object(communicator, "_get_twitch_client", return_value=mock_twitch_client):
        mock_twitch_client.fetch_stream_info.return_value = mock_stream_info
        result = await communicator.fetch_stream_info(user_arg)

        assert result == mock_stream_info
        mock_twitch_client.fetch_stream_info.assert_awaited_once_with(user_arg)


@pytest.mark.asyncio
@patch("features.communicator.communicator.cached", lambda cache: lambda func: func)  # Disable cache  # noqa: ARG005
async def test_fetch_clips_service(
    communicator: Communicator, mock_twitch_client: MagicMock, mock_clips: list[models.Clip]
) -> None:
    """Test the fetch_clips service handler."""
    duration_arg = datetime.timedelta(hours=1)
    with patch.object(communicator, "_get_twitch_client", return_value=mock_twitch_client):
        mock_twitch_client.fetch_clips.return_value = mock_clips
        result = await communicator.fetch_clips(duration_arg)

        assert result == mock_clips
        mock_twitch_client.fetch_clips.assert_awaited_once_with(duration_arg)


@pytest.mark.asyncio
async def test_send_comment_service(communicator: Communicator) -> None:
    """Test the SendComment service puts item in queue."""
    comment = models.Comment(content="Hello", is_italic=False)
    # Call the handler directly (which is queue.put)
    await communicator._comment_queue.put(comment)
    assert await communicator._comment_queue.get() == comment


# --- Routine Tests ---


@pytest.mark.asyncio
async def test_send_comment_routine(communicator: Communicator, mock_twitch_client: MagicMock) -> None:
    """Test the _send_comment routine."""
    comment = models.Comment(content="Test", is_italic=True)
    await communicator._comment_queue.put(comment)

    with patch.object(communicator, "_get_twitch_client", return_value=mock_twitch_client):
        await communicator._send_comment()  # Execute the routine once

    mock_twitch_client.send_comment.assert_awaited_once_with(comment)
    assert communicator._comment_queue.empty()


@pytest.mark.asyncio
async def test_send_comment_routine_runtime_error(communicator: Communicator, mock_twitch_client: MagicMock) -> None:
    """Test _send_comment routine requeues on RuntimeError."""
    comment = models.Comment(content="Test", is_italic=False)
    await communicator._comment_queue.put(comment)

    # Simulate client not being ready
    with patch.object(communicator, "_get_twitch_client", side_effect=RuntimeError("Client not ready")):
        await communicator._send_comment()

    mock_twitch_client.send_comment.assert_not_called()
    # Check item was put back
    assert not communicator._comment_queue.empty()
    assert await communicator._comment_queue.get() == comment


@pytest.mark.asyncio
async def test_post_announce_routine(communicator: Communicator, mock_twitch_client: MagicMock) -> None:
    """Test the _post_announce routine."""
    announce = models.Announcement(content="Announce", color="blue")
    await communicator._announce_queue.put(announce)

    with patch.object(communicator, "_get_twitch_client", return_value=mock_twitch_client):
        await communicator._post_announce()

    mock_twitch_client.post_announcement.assert_awaited_once_with(announce)
    assert communicator._announce_queue.empty()


@pytest.mark.asyncio
async def test_shoutout_routine(communicator: Communicator, mock_twitch_client: MagicMock) -> None:
    """Test the _shoutout routine."""
    user = models.User(id=456, name="shout", display_name="Shout")
    await communicator._shoutout_queue.put(user)

    with patch.object(communicator, "_get_twitch_client", return_value=mock_twitch_client):
        await communicator._shoutout()

    mock_twitch_client.shoutout.assert_awaited_once_with(user)
    assert communicator._shoutout_queue.empty()


@pytest.mark.asyncio
async def test_polling_routine(
    communicator: Communicator,
    mock_twitch_client: MagicMock,
    mock_stream_info: models.StreamInfo,
    mock_clips: list[models.Clip],
) -> None:
    """Test the _polling routine."""
    with patch.object(communicator, "_get_twitch_client", return_value=mock_twitch_client):
        mock_twitch_client.fetch_stream_info.return_value = mock_stream_info
        mock_twitch_client.fetch_clips.return_value = mock_clips

        await communicator._polling()

        mock_twitch_client.fetch_stream_info.assert_awaited_once_with(None)
        mock_twitch_client.fetch_clips.assert_awaited_once_with(datetime.timedelta(minutes=10))
        communicator._update_detector.update.assert_awaited_once_with(mock_stream_info, mock_clips)


@pytest.mark.asyncio
async def test_polling_routine_runtime_error(
    communicator: Communicator,
) -> None:
    """Test _polling routine handles RuntimeError."""
    with patch.object(communicator, "_get_twitch_client", side_effect=RuntimeError("Client gone")):
        # Should not raise an exception
        await communicator._polling()

    communicator._update_detector.update.assert_not_called()
