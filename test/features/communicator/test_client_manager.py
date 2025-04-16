# mypy: disable-error-code="attr-defined"

import asyncio
import datetime
import inspect
import logging
from asyncio import Event as RealAsyncioEvent
from collections.abc import Generator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, call, patch

import pytest
from pydantic import SecretStr
from twitchio import AuthenticationError

from common.core import EventPublisher
from features.communicator import constants as communicator_constants
from features.communicator.client_manager import ClientManager, TokenTag
from features.communicator.token_manager import TokenManager as RealTokenManager
from features.communicator.twitchio_adaptor import (
    Client as TwitchioClientProtocol,
)
from features.communicator.twitchio_adaptor import (
    StreamInfoManager as RealStreamInfoManager,
)
from features.communicator.twitchio_adaptor import TwitchClient as RealTwitchClient
from schemas import errors, events, models
from utils.process_manager import Process, ProcessManager

# --- Constants ---
TEST_CHANNEL = "testchannel"
TEST_TOKEN_FILE_DIR = Path("/fake/token/dir")
TEST_STREAM_INFO_DIR = Path("/fake/streaminfo/dir")


# --- Fixtures ---


@pytest.fixture
def mock_logger() -> MagicMock:
    logger = MagicMock(spec=logging.Logger)
    logger.getChild.return_value = logger
    return logger


@pytest.fixture
def mock_event_publisher() -> AsyncMock:
    return AsyncMock(spec=EventPublisher)


@pytest.fixture
def mock_close_event() -> MagicMock:
    event = MagicMock(spec=RealAsyncioEvent)

    async def wait_side_effect(*_args: object, **_kwargs: object) -> None:
        await asyncio.sleep(1)
        msg = "mock_close_event.wait() completed without being cancelled."
        raise AssertionError(msg)

    event.wait = AsyncMock(side_effect=wait_side_effect)
    event.set = Mock()
    return event


@pytest.fixture
def mock_connection_event() -> MagicMock:
    event = MagicMock(spec=RealAsyncioEvent)
    event.wait = AsyncMock()
    event.set = Mock()
    return event


@pytest.fixture
def mock_process_manager_cls() -> MagicMock:
    """Mocks the ProcessManager class itself."""
    mock_cls = MagicMock(spec=ProcessManager)
    # Mock the class constructor to return a mock instance
    mock_instance = MagicMock(spec=ProcessManager)
    mock_instance.get = AsyncMock(return_value=None)  # Default to no process
    mock_instance.update = AsyncMock()
    mock_instance.store = AsyncMock()

    def create_new_mock_instance(*_args: object, **_kwargs: object) -> MagicMock:
        # Create a new instance mock for each call
        instance = MagicMock(spec=ProcessManager)
        instance.get = AsyncMock(return_value=None)  # Default to no process
        instance.update = AsyncMock()
        instance.store = AsyncMock()
        return instance

    mock_cls.side_effect = create_new_mock_instance
    return mock_cls


@pytest.fixture
def mock_token_manager_cls() -> MagicMock:
    """Mocks the TokenManager class."""
    return MagicMock(spec=RealTokenManager)


@pytest.fixture
def mock_twitch_client_cls() -> MagicMock:
    """Mocks the TwitchClient class."""
    return MagicMock(spec=RealTwitchClient)


@pytest.fixture
def mock_stream_info_manager_cls() -> MagicMock:
    """Mocks the StreamInfoManager class."""
    return MagicMock(spec=RealStreamInfoManager)


@pytest.fixture
def mock_twitch_client_instance() -> MagicMock:
    """Mocks an instance of TwitchClient."""
    client = MagicMock(spec=TwitchioClientProtocol)  # Use protocol for spec
    client.run = AsyncMock()
    client.close = AsyncMock()
    client.nick = "test_bot_nick"
    client.is_streamer = False  # Default to not streamer
    return client


@pytest.fixture
def mock_stream_info_manager_instance() -> MagicMock:
    """Mocks an instance of StreamInfoManager."""
    manager = MagicMock(spec=RealStreamInfoManager)
    manager.run = AsyncMock()
    manager.close = AsyncMock()
    return manager


@pytest.fixture
def mock_token() -> models.Token:
    return models.Token(name=TokenTag.BOT, access_token=SecretStr("fake_access_token"))


@pytest.fixture
def mock_verification() -> models.TwitchVerification:
    return models.TwitchVerification(
        device_code="dev123",
        interval=datetime.timedelta(seconds=5),
        user_code="USER123",
        uri="http://verify.test",
        expires_at=datetime.datetime.now(datetime.UTC) + datetime.timedelta(minutes=5),
    )


@pytest.fixture
def client_manager(
    mock_logger: MagicMock,
    mock_event_publisher: AsyncMock,
    mock_close_event: MagicMock,
    mock_process_manager_cls: MagicMock,  # Use the class mock
) -> Generator[ClientManager, None, None]:
    # Patch ProcessManager globally for this fixture's scope
    with (
        patch("features.communicator.client_manager.ProcessManager", mock_process_manager_cls),
        patch("features.communicator.client_manager.asyncio.Event", return_value=mock_close_event),
    ):
        manager = ClientManager(
            logger=mock_logger,
            event_publisher=mock_event_publisher,
            token_file_directory=TEST_TOKEN_FILE_DIR,
            stream_info_storage_directory=TEST_STREAM_INFO_DIR,
            channel=TEST_CHANNEL,
            enable_stream_info_command=True,  # Default to enabled
        )
        yield manager


# --- Test Cases ---


def test_init(
    client_manager: ClientManager,
    mock_logger: MagicMock,
    mock_event_publisher: AsyncMock,
    mock_close_event: MagicMock,
    mock_process_manager_cls: MagicMock,
) -> None:
    """Test ClientManager initialization."""
    assert client_manager._logger is mock_logger.getChild.return_value
    assert client_manager._event_publisher is mock_event_publisher
    assert client_manager._token_file_directory == TEST_TOKEN_FILE_DIR
    assert client_manager._stream_info_storage_directory == TEST_STREAM_INFO_DIR
    assert client_manager._channel == TEST_CHANNEL
    assert client_manager._enable_stream_info_command is True
    assert client_manager._close_event is mock_close_event

    # Check ProcessManager was instantiated 4 times
    assert mock_process_manager_cls.call_count == 4
    assert isinstance(client_manager._twitch_client_manager, MagicMock)
    assert isinstance(client_manager._twitch_token_manager, MagicMock)
    assert isinstance(client_manager._stream_info_manager, MagicMock)
    assert isinstance(client_manager._stream_info_token_manager, MagicMock)


@pytest.mark.asyncio
async def test_get_twitch_client(client_manager: ClientManager, mock_twitch_client_instance: MagicMock) -> None:
    """Test retrieving the twitch client."""
    # Setup mock ProcessManager to return the client instance
    client_manager._twitch_client_manager.get.return_value = mock_twitch_client_instance

    client = await client_manager.get_twitch_client()

    assert client is mock_twitch_client_instance
    client_manager._twitch_client_manager.get.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_twitch_client_none(client_manager: ClientManager) -> None:
    """Test retrieving the twitch client when none exists."""
    # Default behavior of the mock ProcessManager is to return None
    client = await client_manager.get_twitch_client()
    assert client is None
    client_manager._twitch_client_manager.get.assert_awaited_once()


@pytest.mark.asyncio
async def test_run(
    client_manager: ClientManager, mock_token_manager_cls: MagicMock, mock_close_event: MagicMock
) -> None:
    """Test the main run loop starts the bot token manager and waits."""
    with patch("features.communicator.client_manager.TokenManager", mock_token_manager_cls):
        # Run in a separate task to allow asserting wait
        run_task = asyncio.create_task(client_manager.run())
        await asyncio.sleep(0)  # Allow run task to start

        # Assert Bot TokenManager was created and updated
        mock_token_manager_cls.assert_called_once_with(
            client_manager._logger,
            TokenTag.BOT,
            communicator_constants.BOT_SCOPES,
            TEST_TOKEN_FILE_DIR,
            client_manager._start_verification_bot,
            client_manager._initialize_twitch_client,
        )
        client_manager._twitch_token_manager.update.assert_awaited_once_with(mock_token_manager_cls.return_value)

        # Assert it waits on the close event
        mock_close_event.wait.assert_awaited_once()

        # Clean up task
        run_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await run_task


@pytest.mark.asyncio
async def test_close(client_manager: ClientManager, mock_close_event: MagicMock) -> None:
    """Test closing the client manager."""
    await client_manager.close()

    # Assert all process managers were cleared
    client_manager._twitch_client_manager.update.assert_awaited_once_with(None)
    client_manager._twitch_token_manager.update.assert_awaited_once_with(None)
    client_manager._stream_info_manager.update.assert_awaited_once_with(None)
    client_manager._stream_info_token_manager.update.assert_awaited_once_with(None)

    # Assert close event was set
    mock_close_event.set.assert_called_once()


@pytest.mark.asyncio
async def test_start_verification_bot(
    client_manager: ClientManager, mock_event_publisher: AsyncMock, mock_verification: models.TwitchVerification
) -> None:
    """Test the bot verification callback."""
    await client_manager._start_verification_bot(mock_verification)
    mock_event_publisher.publish.assert_awaited_once_with(
        events.StartTwitchVerification(tag=TokenTag.BOT, verification=mock_verification)
    )


@pytest.mark.asyncio
async def test_start_verification_streamer(
    client_manager: ClientManager, mock_event_publisher: AsyncMock, mock_verification: models.TwitchVerification
) -> None:
    """Test the streamer verification callback."""
    await client_manager._start_verification_streamer(mock_verification)
    mock_event_publisher.publish.assert_awaited_once_with(
        events.StartTwitchVerification(tag=TokenTag.STREAMER, verification=mock_verification)
    )


@pytest.mark.asyncio
@patch("features.communicator.client_manager.asyncio.create_task")
@patch("features.communicator.client_manager.asyncio.wait_for")
async def test_initialize_twitch_client_success(  # noqa: PLR0913
    mock_wait_for: AsyncMock,
    mock_create_task: MagicMock,
    client_manager: ClientManager,
    mock_twitch_client_cls: MagicMock,
    mock_twitch_client_instance: MagicMock,
    mock_token: models.Token,
    mock_event_publisher: AsyncMock,
    mock_connection_event: MagicMock,  # Used inside TwitchClient mock
) -> None:
    """Test successful initialization of TwitchClient."""
    mock_twitch_client_cls.return_value = mock_twitch_client_instance
    # Simulate connection event being set during wait_for
    mock_wait_for.side_effect = lambda coro, timeout: coro  # Just return the coro  # noqa: ARG005

    with (
        patch("features.communicator.client_manager.TwitchClient", mock_twitch_client_cls),
        patch("features.communicator.client_manager.asyncio.Event", return_value=mock_connection_event),
    ):
        await client_manager._initialize_twitch_client(mock_token)

    # Assert TwitchClient instantiated
    mock_twitch_client_cls.assert_called_once_with(
        client_manager._logger,
        mock_token.access_token,
        TEST_CHANNEL,
        client_manager._event_publisher,
        mock_connection_event,
    )

    # Assert create_task was called correctly
    mock_create_task.assert_called_once()
    actual_create_args, actual_create_kwargs = mock_create_task.call_args
    assert len(actual_create_args) == 1
    assert not actual_create_kwargs
    assert inspect.iscoroutine(actual_create_args[0])

    mock_wait_for.assert_awaited_once()
    actual_await_args, actual_await_kwargs = mock_wait_for.await_args  # type: ignore[misc]
    assert len(actual_await_args) == 1
    assert inspect.iscoroutine(actual_await_args[0])
    assert actual_await_kwargs == {"timeout": 10}

    #    This confirms the coroutine passed to wait_for originated from the event.
    mock_connection_event.wait.assert_called_once()
    # Assert client stored
    client_manager._twitch_client_manager.store.assert_awaited_once_with(
        mock_twitch_client_instance, mock_create_task.return_value
    )
    # Assert event published
    mock_event_publisher.publish.assert_awaited_once_with(
        events.TwitchChannelConnected(
            connection_info=models.ConnectionInfo(
                bot_user=mock_twitch_client_instance.nick,
                channel=TEST_CHANNEL,
            ),
        ),
    )


@pytest.mark.asyncio
@patch("features.communicator.client_manager.asyncio.create_task")
@patch("features.communicator.client_manager.asyncio.wait_for", side_effect=TimeoutError)
async def test_initialize_twitch_client_timeout(  # noqa: PLR0913
    mock_wait_for: AsyncMock,
    mock_create_task: MagicMock,
    client_manager: ClientManager,
    mock_twitch_client_cls: MagicMock,
    mock_twitch_client_instance: MagicMock,
    mock_token: models.Token,
    mock_event_publisher: AsyncMock,
    mock_connection_event: MagicMock,
) -> None:
    """Test TwitchClient initialization timeout."""
    mock_twitch_client_cls.return_value = mock_twitch_client_instance

    with (
        patch("features.communicator.client_manager.TwitchClient", mock_twitch_client_cls),
        patch("features.communicator.client_manager.asyncio.Event", return_value=mock_connection_event),
    ):
        await client_manager._initialize_twitch_client(mock_token)

    # Assert TwitchClient instantiated
    mock_twitch_client_cls.assert_called_once()
    # Assert _run_client task created
    mock_create_task.assert_called_once()
    # Assert connection wait
    mock_wait_for.assert_awaited_once()
    # Assert client closed on timeout
    mock_twitch_client_instance.close.assert_awaited_once()
    # Assert client NOT stored
    client_manager._twitch_client_manager.store.assert_not_called()
    # Assert event NOT published
    mock_event_publisher.publish.assert_not_called()


@pytest.mark.asyncio
@patch.object(ClientManager, "_run_client")
@patch("features.communicator.client_manager.asyncio.create_task")
@patch("features.communicator.client_manager.asyncio.wait_for")
async def test_initialize_twitch_client_is_streamer_feature_enabled(  # noqa: PLR0913
    mock_wait_for: AsyncMock,
    mock_create_task: MagicMock,
    mock_run_client_method: MagicMock,
    client_manager: ClientManager,
    mock_twitch_client_cls: MagicMock,
    mock_twitch_client_instance: MagicMock,
    mock_token: models.Token,
    mock_stream_info_manager_cls: MagicMock,  # Need to patch this
    mock_stream_info_manager_instance: MagicMock,
) -> None:
    """Test _initialize_twitch_client when bot is streamer and feature enabled."""
    mock_twitch_client_cls.return_value = mock_twitch_client_instance
    mock_twitch_client_instance.is_streamer = True  # Bot IS the streamer
    client_manager._enable_stream_info_command = True  # Feature IS enabled
    mock_wait_for.side_effect = lambda coro, timeout: coro  # Simulate success  # noqa: ARG005

    run_client_result_1 = asyncio.Future[None]()
    run_client_result_2 = asyncio.Future[None]()
    mock_run_client_method.side_effect = [run_client_result_1, run_client_result_2]

    # Patch StreamInfoManager init for the direct call
    with (
        patch("features.communicator.client_manager.TwitchClient", mock_twitch_client_cls),
        patch(
            "features.communicator.client_manager.StreamInfoManager", mock_stream_info_manager_cls
        ) as patched_sim_cls,
        patch("features.communicator.client_manager.TokenManager"),
        patch("features.communicator.client_manager.asyncio.Event"),
    ):
        # Mock the return value for the direct call
        patched_sim_cls.return_value = mock_stream_info_manager_instance

        await client_manager._initialize_twitch_client(mock_token)

    # Assert Streamer Token Manager was cleared
    client_manager._stream_info_token_manager.update.assert_awaited_once_with(None)

    # Assert StreamInfoManager was initialized directly
    mock_stream_info_manager_cls.assert_called_once()
    assert mock_run_client_method.call_count == 2
    assert mock_run_client_method.call_args_list == [
        call(mock_twitch_client_instance),
        call(mock_stream_info_manager_instance),
    ]

    # Assert StreamInfoManager was stored
    # The second return value of create_task corresponds to the StreamInfoManager task
    assert client_manager._stream_info_manager.store.call_count == 1
    client_manager._stream_info_manager.store.assert_awaited_once_with(
        mock_stream_info_manager_instance,
        mock_create_task.return_value,  # return_value gives the last call's return
    )
    # Assert StreamInfoManager was stored
    client_manager._stream_info_manager.store.assert_awaited_once_with(
        mock_stream_info_manager_instance, mock_create_task.return_value
    )


@pytest.mark.asyncio
@patch("features.communicator.client_manager.asyncio.wait_for")
async def test_initialize_twitch_client_not_streamer_feature_enabled(  # noqa: PLR0913
    mock_wait_for: AsyncMock,
    client_manager: ClientManager,
    mock_twitch_client_cls: MagicMock,
    mock_twitch_client_instance: MagicMock,
    mock_token: models.Token,
    mock_token_manager_cls: MagicMock,  # Need to patch this
) -> None:
    """Test _initialize_twitch_client when bot is not streamer and feature enabled."""
    mock_twitch_client_cls.return_value = mock_twitch_client_instance
    mock_twitch_client_instance.is_streamer = False  # Bot is NOT the streamer
    client_manager._enable_stream_info_command = True  # Feature IS enabled
    mock_wait_for.side_effect = lambda coro, timeout: coro  # Simulate success  # noqa: ARG005

    with (
        patch("features.communicator.client_manager.TwitchClient", mock_twitch_client_cls),
        patch("features.communicator.client_manager.TokenManager", mock_token_manager_cls) as patched_tm_cls,
        patch("features.communicator.client_manager.StreamInfoManager"),
        patch("features.communicator.client_manager.asyncio.Event"),
    ):
        await client_manager._initialize_twitch_client(mock_token)

    # Assert Streamer Token Manager was initialized
    patched_tm_cls.assert_called_once_with(
        client_manager._logger,
        TokenTag.STREAMER,
        communicator_constants.STREAM_UPDATE_SCOPES,
        TEST_TOKEN_FILE_DIR,
        client_manager._start_verification_streamer,
        client_manager._initialize_stream_info_manager,
    )
    client_manager._stream_info_token_manager.update.assert_awaited_once_with(patched_tm_cls.return_value)
    # Assert StreamInfoManager was NOT initialized directly
    client_manager._stream_info_manager.store.assert_not_called()


@pytest.mark.asyncio
@patch("features.communicator.client_manager.asyncio.create_task")
@patch("features.communicator.client_manager.asyncio.wait_for")
async def test_initialize_twitch_client_feature_disabled(  # noqa: PLR0913
    mock_wait_for: AsyncMock,
    mock_create_task: MagicMock,  # noqa: ARG001
    client_manager: ClientManager,
    mock_twitch_client_cls: MagicMock,
    mock_twitch_client_instance: MagicMock,
    mock_token: models.Token,
) -> None:
    """Test _initialize_twitch_client when stream info command feature is disabled."""
    mock_twitch_client_cls.return_value = mock_twitch_client_instance
    client_manager._enable_stream_info_command = False  # Feature IS disabled
    mock_wait_for.side_effect = lambda coro, timeout: coro  # Simulate success  # noqa: ARG005

    with (
        patch("features.communicator.client_manager.TwitchClient", mock_twitch_client_cls),
        patch("features.communicator.client_manager.TokenManager") as patched_tm_cls,
        patch("features.communicator.client_manager.StreamInfoManager") as patched_sim_cls,
        patch("features.communicator.client_manager.asyncio.Event"),
    ):
        await client_manager._initialize_twitch_client(mock_token)

    # Assert Streamer Token Manager was NOT initialized
    patched_tm_cls.assert_not_called()
    client_manager._stream_info_token_manager.update.assert_not_called()
    # Assert StreamInfoManager was NOT initialized
    patched_sim_cls.assert_not_called()
    client_manager._stream_info_manager.store.assert_not_called()


@pytest.mark.asyncio
@patch("features.communicator.client_manager.asyncio.create_task")
@patch("features.communicator.client_manager.asyncio.wait_for")
async def test_initialize_stream_info_manager_success(  # noqa: PLR0913
    mock_wait_for: AsyncMock,
    mock_create_task: MagicMock,
    client_manager: ClientManager,
    mock_stream_info_manager_cls: MagicMock,
    mock_stream_info_manager_instance: MagicMock,
    mock_token: models.Token,
    mock_connection_event: MagicMock,
) -> None:
    """Test successful initialization of StreamInfoManager."""
    mock_stream_info_manager_cls.return_value = mock_stream_info_manager_instance
    mock_wait_for.side_effect = lambda coro, timeout: coro  # Simulate success  # noqa: ARG005

    with (
        patch("features.communicator.client_manager.StreamInfoManager", mock_stream_info_manager_cls),
        patch("features.communicator.client_manager.asyncio.Event", return_value=mock_connection_event),
    ):
        await client_manager._initialize_stream_info_manager(mock_token)

    # Assert StreamInfoManager instantiated
    mock_stream_info_manager_cls.assert_called_once_with(
        client_manager._logger,
        mock_token.access_token,
        TEST_CHANNEL,
        TEST_STREAM_INFO_DIR,
        client_manager._event_publisher,
        mock_connection_event,
    )

    # Assert manager stored
    client_manager._stream_info_manager.store.assert_awaited_once_with(
        mock_stream_info_manager_instance, mock_create_task.return_value
    )


@pytest.mark.asyncio
@patch("features.communicator.client_manager.asyncio.create_task")
@patch("features.communicator.client_manager.asyncio.wait_for", side_effect=TimeoutError)
async def test_initialize_stream_info_manager_timeout(  # noqa: PLR0913
    mock_wait_for: AsyncMock,
    mock_create_task: MagicMock,
    client_manager: ClientManager,
    mock_stream_info_manager_cls: MagicMock,
    mock_stream_info_manager_instance: MagicMock,
    mock_token: models.Token,
    mock_connection_event: MagicMock,
) -> None:
    """Test StreamInfoManager initialization timeout."""
    mock_stream_info_manager_cls.return_value = mock_stream_info_manager_instance

    with (
        patch("features.communicator.client_manager.StreamInfoManager", mock_stream_info_manager_cls),
        patch("features.communicator.client_manager.asyncio.Event", return_value=mock_connection_event),
    ):
        await client_manager._initialize_stream_info_manager(mock_token)

    # Assert StreamInfoManager instantiated
    mock_stream_info_manager_cls.assert_called_once()
    # Assert _run_client task created
    mock_create_task.assert_called_once()
    # Assert connection wait
    mock_wait_for.assert_awaited_once()
    # Assert manager closed on timeout
    mock_stream_info_manager_instance.close.assert_awaited_once()
    # Assert manager NOT stored
    client_manager._stream_info_manager.store.assert_not_called()


@pytest.mark.asyncio
async def test_run_client_success(client_manager: ClientManager) -> None:
    """Test _run_client runs the client successfully."""
    mock_client = MagicMock(spec=Process)
    mock_client.run = AsyncMock()

    await client_manager._run_client(mock_client)

    mock_client.run.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_client_auth_error(client_manager: ClientManager, mock_event_publisher: AsyncMock) -> None:
    """Test _run_client handles AuthenticationError."""
    mock_client = MagicMock(spec=Process)
    auth_error = AuthenticationError("Invalid token")
    mock_client.run = AsyncMock(side_effect=auth_error)

    await client_manager._run_client(mock_client)

    mock_client.run.assert_awaited_once()
    mock_event_publisher.publish.assert_awaited_once_with(errors.TwitchAuthenticationError())


@pytest.mark.asyncio
async def test_run_client_unhandled_error(client_manager: ClientManager, mock_event_publisher: AsyncMock) -> None:
    """Test _run_client handles other BaseExceptions."""
    mock_client = MagicMock(spec=Process)
    other_error = ValueError("Something unexpected")
    mock_client.run = AsyncMock(side_effect=other_error)

    await client_manager._run_client(mock_client)

    mock_client.run.assert_awaited_once()
    mock_event_publisher.publish.assert_awaited_once_with(errors.UnhandledError.instance(str(other_error)))
