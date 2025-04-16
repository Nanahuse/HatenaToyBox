import datetime
import logging
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from freezegun import freeze_time

from features.communicator.token_manager import TokenManager, exceptions
from features.communicator.token_manager.client import Client
from features.communicator.token_manager.twitch_token import TwitchToken
from schemas import models
from utils.model_file import ModelFile
from utils.routines import Routine

# Constants for testing
TEST_NAME = "test_bot"
TEST_SCOPES_LIST = ["chat:read", "chat:edit"]
TEST_SCOPES_STR = " ".join(TEST_SCOPES_LIST)
TOKEN_FILE_NAME = f"token_{TEST_NAME}.json"
TOKEN_EXPIRE_MARGIN = datetime.timedelta(minutes=10)
TOKEN_CHECK_INTERVAL = datetime.timedelta(minutes=5)
NOW = datetime.datetime(2021, 2, 24, 11, 0, 0, tzinfo=datetime.UTC)
FUTURE_EXPIRY = NOW + datetime.timedelta(hours=1)
PAST_EXPIRY = NOW - datetime.timedelta(hours=1)
SOON_EXPIRY = NOW + TOKEN_EXPIRE_MARGIN - datetime.timedelta(seconds=1)


# --- Fixtures ---


@pytest.fixture
def mock_logger() -> MagicMock:
    logger = MagicMock(spec=logging.Logger)
    logger.getChild.return_value = logger
    return logger


@pytest.fixture
def mock_token_file() -> MagicMock:
    return MagicMock(spec=ModelFile)


@pytest.fixture
def mock_start_verification_callback() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_token_update_callback() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_routine_instance() -> MagicMock:
    routine = MagicMock(spec=Routine)
    routine.start = AsyncMock()
    routine.cancel = Mock()
    return routine


@pytest.fixture
def mock_routine_decorator(mock_routine_instance: MagicMock) -> MagicMock:
    # Mock the @routines.routine decorator
    decorator = MagicMock()
    # When the decorator is called with args (like seconds=...),
    # it should return a function that takes the decorated method (e.g., _refresh_token)
    # and returns our mock_routine_instance.
    decorator.return_value = lambda _: mock_routine_instance
    return decorator


@pytest.fixture
def mock_client() -> MagicMock:
    client = MagicMock(spec=Client)
    client.__aenter__.return_value = client  # Simulate async context manager
    client.__aexit__ = AsyncMock()
    client.refresh_access_token = AsyncMock()
    client.get_device_code = AsyncMock()
    client.get_access_token = AsyncMock()
    return client


@pytest.fixture
def valid_twitch_token() -> TwitchToken:
    return TwitchToken(
        access_token="valid_access",
        refresh_token="valid_refresh",
        scopes=TEST_SCOPES_STR,
        expires_at=FUTURE_EXPIRY,
    )


@pytest.fixture
def expired_twitch_token() -> TwitchToken:
    return TwitchToken(
        access_token="expired_access",
        refresh_token="expired_refresh",
        scopes=TEST_SCOPES_STR,
        expires_at=PAST_EXPIRY,
    )


@pytest.fixture
def soon_expiring_twitch_token() -> TwitchToken:
    return TwitchToken(
        access_token="soon_access",
        refresh_token="soon_refresh",
        scopes=TEST_SCOPES_STR,
        expires_at=SOON_EXPIRY,
    )


@pytest.fixture
def verification_model() -> models.TwitchVerification:
    return models.TwitchVerification(
        device_code="device123",
        interval=datetime.timedelta(seconds=5),
        user_code="USERCODE",
        uri="http://verify.me",
        expires_at=NOW + datetime.timedelta(minutes=5),
    )


@pytest.fixture
def token_manager(
    mock_logger: MagicMock,
    mock_token_file: MagicMock,
    mock_start_verification_callback: AsyncMock,
    mock_token_update_callback: AsyncMock,
    tmp_path: Path,
) -> TokenManager:
    # Patch ModelFile instantiation within the TokenManager constructor
    with patch(
        "features.communicator.token_manager.token_manager.ModelFile",
        return_value=mock_token_file,
    ) as mock_model_file_cls:
        manager = TokenManager(
            logger=mock_logger,
            name=TEST_NAME,
            scopes=TEST_SCOPES_LIST,
            token_file_directory=tmp_path,
            start_verification_callback=mock_start_verification_callback,
            token_update_callback=mock_token_update_callback,
        )
        mock_model_file_cls.assert_called_once_with(TwitchToken, tmp_path / TOKEN_FILE_NAME, manager._logger)
        return manager


# --- Test Cases ---


def test_init_no_existing_token(
    token_manager: TokenManager,
    mock_logger: MagicMock,
    mock_token_file: MagicMock,
    mock_start_verification_callback: AsyncMock,
    mock_token_update_callback: AsyncMock,
) -> None:
    """Test initialization when the token file doesn't exist or is empty."""
    mock_token_file.data = None

    # Re-run init logic implicitly via fixture setup
    # Assertions
    assert token_manager._logger is mock_logger
    assert token_manager._name == TEST_NAME
    assert token_manager._scopes == TEST_SCOPES_STR
    assert token_manager._token_file is mock_token_file
    assert token_manager._start_verification is mock_start_verification_callback
    assert token_manager._token_update_callback is mock_token_update_callback
    assert token_manager._update_routine is None


def test_init_existing_token_matching_scopes(  # noqa: PLR0913
    mock_logger: MagicMock,
    mock_token_file: MagicMock,
    mock_start_verification_callback: AsyncMock,
    mock_token_update_callback: AsyncMock,
    valid_twitch_token: TwitchToken,
    tmp_path: Path,
) -> None:
    """Test initialization with an existing token file with matching scopes."""
    mock_token_file.data = valid_twitch_token
    assert valid_twitch_token.scopes == TEST_SCOPES_STR  # Pre-condition

    with patch(
        "features.communicator.token_manager.token_manager.ModelFile",
        return_value=mock_token_file,
    ):
        TokenManager(
            logger=mock_logger,
            name=TEST_NAME,
            scopes=TEST_SCOPES_LIST,
            token_file_directory=tmp_path,
            start_verification_callback=mock_start_verification_callback,
            token_update_callback=mock_token_update_callback,
        )
    mock_token_file.clear.assert_not_called()


def test_init_existing_token_mismatched_scopes(  # noqa: PLR0913
    mock_logger: MagicMock,
    mock_token_file: MagicMock,
    mock_start_verification_callback: AsyncMock,
    mock_token_update_callback: AsyncMock,
    valid_twitch_token: TwitchToken,
    tmp_path: Path,
) -> None:
    """Test initialization with an existing token file with mismatched scopes."""
    mismatched_token = valid_twitch_token.model_copy()
    mismatched_token.scopes = "read:only"
    mock_token_file.data = mismatched_token

    with patch(
        "features.communicator.token_manager.token_manager.ModelFile",
        return_value=mock_token_file,
    ):
        TokenManager(
            logger=mock_logger,
            name=TEST_NAME,
            scopes=TEST_SCOPES_LIST,  # Different scopes
            token_file_directory=tmp_path,
            start_verification_callback=mock_start_verification_callback,
            token_update_callback=mock_token_update_callback,
        )
    mock_token_file.clear.assert_called_once()


@freeze_time(NOW)
def test_get_valid_token_none(token_manager: TokenManager, mock_token_file: MagicMock) -> None:
    """Test _get_valid_token when no token exists."""
    mock_token_file.data = None
    assert token_manager._get_valid_token() is None


@freeze_time(NOW)
def test_get_valid_token_valid(
    token_manager: TokenManager, mock_token_file: MagicMock, valid_twitch_token: TwitchToken
) -> None:
    """Test _get_valid_token with a valid token."""
    mock_token_file.data = valid_twitch_token
    assert token_manager._get_valid_token() == valid_twitch_token


@freeze_time(NOW)
def test_get_valid_token_expired(
    token_manager: TokenManager, mock_token_file: MagicMock, expired_twitch_token: TwitchToken
) -> None:
    """Test _get_valid_token with an expired token."""
    mock_token_file.data = expired_twitch_token
    assert token_manager._get_valid_token() is None


@freeze_time(NOW)
def test_get_valid_token_expiring_soon(
    token_manager: TokenManager, mock_token_file: MagicMock, soon_expiring_twitch_token: TwitchToken
) -> None:
    """Test _get_valid_token with a token expiring within the margin."""
    mock_token_file.data = soon_expiring_twitch_token
    assert token_manager._get_valid_token() is None


@pytest.mark.asyncio
@freeze_time(NOW)
async def test_run_no_initial_token(
    token_manager: TokenManager,
    mock_token_file: MagicMock,
    mock_token_update_callback: AsyncMock,
    mock_routine_decorator: MagicMock,
    mock_routine_instance: MagicMock,
) -> None:
    """Test run when no valid token is initially loaded."""
    mock_token_file.data = None

    with patch("features.communicator.token_manager.token_manager.routines.routine", mock_routine_decorator):
        await token_manager.run()

    mock_token_update_callback.assert_not_called()
    mock_routine_decorator.assert_called_once_with(seconds=TOKEN_CHECK_INTERVAL.total_seconds())
    assert token_manager._update_routine is mock_routine_instance
    mock_routine_instance.start.assert_awaited_once()


@pytest.mark.asyncio
@freeze_time(NOW)
async def test_run_with_valid_initial_token(  # noqa: PLR0913
    token_manager: TokenManager,
    mock_token_file: MagicMock,
    mock_token_update_callback: AsyncMock,
    mock_routine_decorator: MagicMock,
    mock_routine_instance: MagicMock,
    valid_twitch_token: TwitchToken,
) -> None:
    """Test run when a valid token is initially loaded."""
    mock_token_file.data = valid_twitch_token

    with patch("features.communicator.token_manager.token_manager.routines.routine", mock_routine_decorator):
        await token_manager.run()

    # Check _update_token was called
    mock_token_file.update.assert_called_once_with(valid_twitch_token)
    mock_token_update_callback.assert_awaited_once_with(
        models.Token(name=TEST_NAME, access_token=valid_twitch_token.access_token)
    )
    # Check routine started
    mock_routine_decorator.assert_called_once_with(seconds=TOKEN_CHECK_INTERVAL.total_seconds())
    assert token_manager._update_routine is mock_routine_instance
    mock_routine_instance.start.assert_awaited_once()


@pytest.mark.asyncio
async def test_close_not_running(token_manager: TokenManager) -> None:
    """Test close when the manager is not running."""
    assert not token_manager.is_running
    await token_manager.close()
    # No cancel call expected
    assert token_manager._update_routine is None


@pytest.mark.asyncio
async def test_close_running(token_manager: TokenManager, mock_routine_instance: MagicMock) -> None:
    """Test close when the manager is running."""
    token_manager._update_routine = mock_routine_instance  # Manually set routine
    assert token_manager.is_running

    await token_manager.close()

    mock_routine_instance.cancel.assert_called_once()
    assert token_manager._update_routine is None


def test_is_running(token_manager: TokenManager, mock_routine_instance: MagicMock) -> None:
    """Test the is_running property."""
    assert not token_manager.is_running
    token_manager._update_routine = mock_routine_instance
    assert token_manager.is_running
    token_manager._update_routine = None
    assert not token_manager.is_running


@pytest.mark.asyncio
@freeze_time(NOW)
async def test_refresh_token_still_valid(
    token_manager: TokenManager,
    mock_token_file: MagicMock,
    mock_client: MagicMock,
    valid_twitch_token: TwitchToken,
) -> None:
    """Test _refresh_token when the current token is still valid."""
    mock_token_file.data = valid_twitch_token

    with patch("features.communicator.token_manager.token_manager.Client", return_value=mock_client):
        await token_manager._refresh_token()

    mock_client.__aenter__.assert_not_called()  # Client shouldn't be used
    mock_token_file.update.assert_not_called()


@pytest.mark.asyncio
@freeze_time(NOW)
async def test_refresh_token_success(  # noqa: PLR0913
    token_manager: TokenManager,
    mock_token_file: MagicMock,
    mock_client: MagicMock,
    mock_token_update_callback: AsyncMock,
    expired_twitch_token: TwitchToken,
    valid_twitch_token: TwitchToken,  # Use as the refreshed token
) -> None:
    """Test _refresh_token successfully refreshing an expired token."""
    mock_token_file.data = expired_twitch_token
    mock_client.refresh_access_token.return_value = valid_twitch_token

    with patch("features.communicator.token_manager.token_manager.Client", return_value=mock_client):
        await token_manager._refresh_token()

    mock_client.__aenter__.assert_awaited_once()
    mock_client.refresh_access_token.assert_awaited_once_with(expired_twitch_token.refresh_token)
    mock_token_file.update.assert_called_once_with(valid_twitch_token)
    mock_token_update_callback.assert_awaited_once_with(
        models.Token(name=TEST_NAME, access_token=valid_twitch_token.access_token)
    )
    mock_client.get_device_code.assert_not_called()


@pytest.mark.asyncio
@freeze_time(NOW)
async def test_refresh_token_refresh_fails_get_new_success(  # noqa: PLR0913
    token_manager: TokenManager,
    mock_token_file: MagicMock,
    mock_client: MagicMock,
    mock_start_verification_callback: AsyncMock,
    mock_token_update_callback: AsyncMock,
    expired_twitch_token: TwitchToken,
    verification_model: models.TwitchVerification,
    valid_twitch_token: TwitchToken,  # Use as the new token
) -> None:
    """Test _refresh_token when refresh fails, but getting a new token succeeds."""
    mock_token_file.data = expired_twitch_token
    mock_client.refresh_access_token.side_effect = exceptions.AuthorizationError("Refresh failed")
    mock_client.get_device_code.return_value = verification_model
    mock_client.get_access_token.return_value = valid_twitch_token

    with patch("features.communicator.token_manager.token_manager.Client", return_value=mock_client):
        await token_manager._refresh_token()

    mock_client.__aenter__.assert_awaited_once()
    mock_client.refresh_access_token.assert_awaited_once_with(expired_twitch_token.refresh_token)
    mock_client.get_device_code.assert_awaited_once()
    mock_start_verification_callback.assert_awaited_once_with(verification_model)
    mock_client.get_access_token.assert_awaited_once_with(verification_model)
    mock_token_file.update.assert_called_once_with(valid_twitch_token)
    mock_token_update_callback.assert_awaited_once_with(
        models.Token(name=TEST_NAME, access_token=valid_twitch_token.access_token)
    )


@pytest.mark.asyncio
@freeze_time(NOW)
async def test_refresh_token_no_token_get_new_success(  # noqa: PLR0913
    token_manager: TokenManager,
    mock_token_file: MagicMock,
    mock_client: MagicMock,
    mock_start_verification_callback: AsyncMock,
    mock_token_update_callback: AsyncMock,
    verification_model: models.TwitchVerification,
    valid_twitch_token: TwitchToken,  # Use as the new token
) -> None:
    """Test _refresh_token when no token exists, and getting a new token succeeds."""
    mock_token_file.data = None  # No initial token
    mock_client.get_device_code.return_value = verification_model
    mock_client.get_access_token.return_value = valid_twitch_token

    with patch("features.communicator.token_manager.token_manager.Client", return_value=mock_client):
        await token_manager._refresh_token()

    mock_client.__aenter__.assert_awaited_once()
    mock_client.refresh_access_token.assert_not_called()  # No token to refresh
    mock_client.get_device_code.assert_awaited_once()
    mock_start_verification_callback.assert_awaited_once_with(verification_model)
    mock_client.get_access_token.assert_awaited_once_with(verification_model)
    mock_token_file.update.assert_called_once_with(valid_twitch_token)
    mock_token_update_callback.assert_awaited_once_with(
        models.Token(name=TEST_NAME, access_token=valid_twitch_token.access_token)
    )


@pytest.mark.asyncio
@freeze_time(NOW)
async def test_refresh_token_get_new_fails(  # noqa: PLR0913
    token_manager: TokenManager,
    mock_token_file: MagicMock,
    mock_client: MagicMock,
    mock_start_verification_callback: AsyncMock,
    mock_token_update_callback: AsyncMock,
    verification_model: models.TwitchVerification,
) -> None:
    """Test _refresh_token when getting a new token fails."""
    mock_token_file.data = None  # No initial token
    mock_client.get_device_code.return_value = verification_model
    mock_client.get_access_token.side_effect = exceptions.AuthorizationError("Get new failed")

    with patch("features.communicator.token_manager.token_manager.Client", return_value=mock_client):
        await token_manager._refresh_token()

    mock_client.__aenter__.assert_awaited_once()
    mock_client.refresh_access_token.assert_not_called()
    mock_client.get_device_code.assert_awaited_once()
    mock_start_verification_callback.assert_awaited_once_with(verification_model)
    mock_client.get_access_token.assert_awaited_once_with(verification_model)
    mock_token_file.update.assert_not_called()
    mock_token_update_callback.assert_not_called()


@pytest.mark.asyncio
@freeze_time(NOW)
async def test_update_token(
    token_manager: TokenManager,
    mock_token_file: MagicMock,
    mock_token_update_callback: AsyncMock,
    valid_twitch_token: TwitchToken,
) -> None:
    """Test the _update_token method."""
    message = "Test update"
    await token_manager._update_token(message, valid_twitch_token)

    mock_token_file.update.assert_called_once_with(valid_twitch_token)
    mock_token_update_callback.assert_awaited_once_with(
        models.Token(name=TEST_NAME, access_token=valid_twitch_token.access_token)
    )
