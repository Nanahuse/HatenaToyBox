import asyncio
import contextlib
import datetime
import json

# Import ANY for assertions
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest
from freezegun import freeze_time

from features.communicator.token_manager import constants, exceptions, responses
from features.communicator.token_manager.client import (
    Client,
    response_to_token,
    response_to_verification,
)
from features.communicator.token_manager.responses import StatusCode
from features.communicator.token_manager.twitch_token import TwitchToken
from schemas import models

# --- Constants for Testing ---
TEST_SCOPES = "chat:read chat:edit"
# Use a timezone-aware datetime for consistency with the code
NOW = datetime.datetime(2021, 2, 24, 11, 0, 0, tzinfo=datetime.UTC)
DEVICE_CODE_EXPIRES_IN = 1800  # 30 minutes
ACCESS_TOKEN_EXPIRES_IN = 3600  # 1 hour
INTERVAL = 5


# --- Fixtures ---


@pytest.fixture
def mock_session() -> MagicMock:
    """Mocks aiohttp.ClientSession."""
    session = MagicMock(spec=aiohttp.ClientSession)
    # *** FIX: session.post should return the response context manager directly ***
    session.post = MagicMock()
    # Mock the async context manager methods for the session itself
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock()
    return session


@pytest.fixture
def mock_response() -> MagicMock:
    """Mocks aiohttp.ClientResponse which acts as an async context manager."""
    response = MagicMock(spec=aiohttp.ClientResponse)
    response.status = 200
    response.json = AsyncMock()  # json() is async, so needs AsyncMock
    response.raise_for_status = MagicMock()
    # Mock the async context manager methods for the response
    response.__aenter__ = AsyncMock(return_value=response)
    response.__aexit__ = AsyncMock()
    return response


@pytest.fixture
def client(mock_session: MagicMock) -> Client:
    """Provides a Client instance with a mocked session."""
    with patch("aiohttp.ClientSession", return_value=mock_session):
        return Client(scopes=TEST_SCOPES)


@pytest.fixture
def device_code_response_data() -> dict[str, Any]:
    return {
        "device_code": "test_device_code",
        "expires_in": DEVICE_CODE_EXPIRES_IN,
        "interval": INTERVAL,
        "user_code": "TESTCODE",
        "verification_uri": "https://twitch.tv/activate",
    }


@pytest.fixture
def access_token_response_data() -> dict[str, Any]:
    return {
        "access_token": "test_access_token",
        "expires_in": ACCESS_TOKEN_EXPIRES_IN,
        "refresh_token": "test_refresh_token",
        "scope": TEST_SCOPES.split(),
        "token_type": "bearer",
    }


@pytest.fixture
def auth_pending_response_data() -> dict[str, Any]:
    return {
        "message": "authorization_pending",
    }


@pytest.fixture
def verification_model() -> models.TwitchVerification:
    # Ensure the expires_at matches the NOW fixture timezone
    return models.TwitchVerification(
        device_code="test_device_code",
        interval=datetime.timedelta(seconds=INTERVAL),
        user_code="TESTCODE",
        uri="https://twitch.tv/activate",
        expires_at=NOW + datetime.timedelta(seconds=DEVICE_CODE_EXPIRES_IN),
    )


# --- Helper Function Tests ---


@freeze_time(NOW)
def test_response_to_verification(device_code_response_data: dict[str, Any]) -> None:
    """Test converting DeviceCodeResponse data to TwitchVerification model."""
    response_model = responses.DeviceCodeResponse(status=200, **device_code_response_data)
    verification = response_to_verification(response_model)

    assert isinstance(verification, models.TwitchVerification)
    assert verification.device_code == "test_device_code"
    assert verification.interval == datetime.timedelta(seconds=INTERVAL)
    assert verification.user_code == "TESTCODE"
    assert verification.uri == "https://twitch.tv/activate"
    assert verification.expires_at == NOW + datetime.timedelta(seconds=DEVICE_CODE_EXPIRES_IN)


@freeze_time(NOW)
def test_response_to_token(access_token_response_data: dict[str, Any]) -> None:
    """Test converting AccessTokenResponse data to TwitchToken model."""
    response_model = responses.AccessTokenResponse(status=200, **access_token_response_data)
    token = response_to_token(response_model, TEST_SCOPES)

    assert isinstance(token, TwitchToken)
    assert token.access_token == "test_access_token"
    assert token.refresh_token == "test_refresh_token"
    assert token.scopes == TEST_SCOPES
    assert token.expires_at == NOW + datetime.timedelta(seconds=ACCESS_TOKEN_EXPIRES_IN)


# --- Client Method Tests ---


def test_client_init(mock_session: MagicMock) -> None:
    """Test Client initialization."""
    with patch("aiohttp.ClientSession", return_value=mock_session) as mock_session_cls:
        client_instance = Client(scopes=TEST_SCOPES)
        mock_session_cls.assert_called_once()
        assert client_instance._scopes == TEST_SCOPES
        assert client_instance._session is mock_session


@pytest.mark.asyncio
async def test_client_context_manager(mock_session: MagicMock) -> None:
    """Test the async context manager behavior."""
    with patch("aiohttp.ClientSession", return_value=mock_session):
        async with Client(scopes=TEST_SCOPES) as client_instance:
            assert client_instance._session is mock_session
            mock_session.__aenter__.assert_awaited_once()
        mock_session.__aexit__.assert_awaited_once()


@pytest.mark.asyncio
async def test_request_success(
    client: Client, mock_session: MagicMock, mock_response: MagicMock, device_code_response_data: dict[str, Any]
) -> None:
    """Test the internal _request method with a successful response matching the model."""
    mock_response.status = 200
    mock_response.json.return_value = device_code_response_data
    # Set the return value of the MagicMock session.post
    mock_session.post.return_value = mock_response
    url = "http://test.com"
    payload = {"key": "value"}

    result = await client._request((responses.DeviceCodeResponse,), url, payload)

    # Check that session.post was called (not awaited)
    mock_session.post.assert_called_once_with(url, data=payload)
    # Check that response context manager methods were awaited/called
    mock_response.__aenter__.assert_awaited_once()
    mock_response.json.assert_awaited_once()
    mock_response.__aexit__.assert_awaited_once()
    assert isinstance(result, responses.DeviceCodeResponse)
    assert result.device_code == device_code_response_data["device_code"]
    assert result.status == StatusCode.Success
    mock_response.raise_for_status.assert_not_called()


@pytest.mark.asyncio
async def test_request_model_mismatch_unknown_error(
    client: Client, mock_session: MagicMock, mock_response: MagicMock
) -> None:
    """Test _request when response doesn't match any possible models."""
    mock_response.status = 200
    mock_response.json.return_value = {"unexpected": "data"}
    # Set the return value of the MagicMock session.post
    mock_session.post.return_value = mock_response
    url = "http://test.com"
    payload = {"key": "value"}

    with pytest.raises(exceptions.UnknownResponseError) as exc_info:
        await client._request((responses.DeviceCodeResponse,), url, payload)

    mock_session.post.assert_called_once_with(url, data=payload)
    mock_response.__aenter__.assert_awaited_once()
    mock_response.json.assert_awaited_once()
    expected_error_data = {"unexpected": "data", "status": 200}
    assert "Unknown response error" in str(exc_info.value)
    assert json.dumps(expected_error_data) in str(exc_info.value)
    mock_response.raise_for_status.assert_called_once()
    mock_response.__aexit__.assert_awaited_once()


@pytest.mark.asyncio
async def test_request_http_error(client: Client, mock_session: MagicMock, mock_response: MagicMock) -> None:
    """Test _request when the HTTP request itself fails (e.g., 404)."""
    mock_response.status = 404
    mock_response.json.return_value = {"error": "Not Found"}
    mock_response.raise_for_status.side_effect = aiohttp.ClientResponseError(MagicMock(), (), status=404)
    # Set the return value of the MagicMock session.post
    mock_session.post.return_value = mock_response
    url = "http://test.com"
    payload = {"key": "value"}

    with contextlib.suppress(Exception):
        await client._request((responses.DeviceCodeResponse,), url, payload)

    mock_session.post.assert_called_once_with(url, data=payload)
    mock_response.__aenter__.assert_awaited_once()
    mock_response.json.assert_awaited_once()  # Called before raise_for_status
    mock_response.raise_for_status.assert_called_once()
    mock_response.__aexit__.assert_awaited_once()  # Should still be called


@pytest.mark.asyncio
async def test_get_device_code_success(
    client: Client, mock_session: MagicMock, mock_response: MagicMock, device_code_response_data: dict[str, Any]
) -> None:
    """Test get_device_code successfully retrieves and parses the code."""
    mock_response.status = 200
    mock_response.json.return_value = device_code_response_data
    # Set the return value of the MagicMock session.post
    mock_session.post.return_value = mock_response
    expected_payload = {
        "client_id": constants.CLIENT_ID,
        "scopes": TEST_SCOPES,
    }

    with freeze_time(NOW):
        verification = await client.get_device_code()

    mock_session.post.assert_called_once_with(constants.DEVICE_CODE_URL, data=expected_payload)
    # Check response methods were awaited/called within _request
    mock_response.__aenter__.assert_awaited_once()
    mock_response.json.assert_awaited_once()
    mock_response.__aexit__.assert_awaited_once()
    assert isinstance(verification, models.TwitchVerification)
    assert verification.device_code == "test_device_code"
    assert verification.expires_at == NOW + datetime.timedelta(seconds=DEVICE_CODE_EXPIRES_IN)


@pytest.mark.asyncio
async def test_get_device_code_request_error(client: Client, mock_session: MagicMock, mock_response: MagicMock) -> None:
    """Test get_device_code wraps request errors."""
    mock_response.status = 500
    mock_response.json.return_value = {"error": "server error"}
    mock_response.raise_for_status.side_effect = aiohttp.ClientResponseError(MagicMock(), (), status=500)
    # Set the return value of the MagicMock session.post
    mock_session.post.return_value = mock_response
    expected_payload = {
        "client_id": constants.CLIENT_ID,
        "scopes": TEST_SCOPES,
    }

    with pytest.raises(exceptions.DeviceCodeRequestError):
        await client.get_device_code()

    mock_session.post.assert_called_once_with(constants.DEVICE_CODE_URL, data=expected_payload)
    mock_response.__aenter__.assert_awaited_once()
    mock_response.json.assert_awaited_once()
    mock_response.raise_for_status.assert_called_once()
    mock_response.__aexit__.assert_awaited_once()


@pytest.mark.asyncio
@freeze_time(NOW)
async def test_get_access_token_success_first_try(
    client: Client,
    mock_session: MagicMock,
    mock_response: MagicMock,
    access_token_response_data: dict[str, Any],
    verification_model: models.TwitchVerification,
) -> None:
    """Test get_access_token succeeds on the first attempt."""
    mock_response.status = 200
    mock_response.json.return_value = access_token_response_data
    # Set the return value of the MagicMock session.post
    mock_session.post.return_value = mock_response
    expected_payload = {
        "client_id": constants.CLIENT_ID,
        "device_code": verification_model.device_code,
        "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
    }

    with patch("asyncio.sleep", AsyncMock()) as mock_sleep:
        token = await client.get_access_token(verification_model)

    mock_session.post.assert_called_once_with(constants.AUTHORIZE_URL, data=expected_payload)
    mock_response.__aenter__.assert_awaited_once()
    mock_response.json.assert_awaited_once()
    mock_response.__aexit__.assert_awaited_once()
    mock_sleep.assert_not_awaited()
    assert isinstance(token, TwitchToken)
    assert token.access_token == "test_access_token"
    assert token.expires_at == NOW + datetime.timedelta(seconds=ACCESS_TOKEN_EXPIRES_IN)


@pytest.mark.asyncio
@freeze_time(NOW)
async def test_get_access_token_pending_then_success(
    client: Client,
    mock_session: MagicMock,
    auth_pending_response_data: dict[str, Any],
    access_token_response_data: dict[str, Any],
    verification_model: models.TwitchVerification,
) -> None:
    """Test get_access_token succeeds after one pending response."""
    response_pending = MagicMock(spec=aiohttp.ClientResponse)
    response_pending.status = 400
    response_pending.json = AsyncMock(return_value=auth_pending_response_data)
    response_pending.raise_for_status = MagicMock()
    response_pending.__aenter__ = AsyncMock(return_value=response_pending)
    response_pending.__aexit__ = AsyncMock()

    response_success = MagicMock(spec=aiohttp.ClientResponse)
    response_success.status = 200
    response_success.json = AsyncMock(return_value=access_token_response_data)
    response_success.raise_for_status = MagicMock()
    response_success.__aenter__ = AsyncMock(return_value=response_success)
    response_success.__aexit__ = AsyncMock()

    # Set the side effect for the MagicMock session.post
    mock_session.post.side_effect = [response_pending, response_success]
    expected_payload = {
        "client_id": constants.CLIENT_ID,
        "device_code": verification_model.device_code,
        "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
    }

    with patch("asyncio.sleep", AsyncMock()) as mock_sleep:
        token = await client.get_access_token(verification_model)

    assert mock_session.post.call_count == 2
    mock_session.post.assert_called_with(constants.AUTHORIZE_URL, data=expected_payload)
    # Check context managers were used for both responses
    response_pending.__aenter__.assert_awaited_once()
    response_pending.json.assert_awaited_once()
    response_pending.__aexit__.assert_awaited_once()
    response_success.__aenter__.assert_awaited_once()
    response_success.json.assert_awaited_once()
    response_success.__aexit__.assert_awaited_once()
    mock_sleep.assert_awaited_once_with(verification_model.interval.total_seconds())
    assert isinstance(token, TwitchToken)
    assert token.access_token == "test_access_token"


@pytest.mark.asyncio
@freeze_time(NOW)
async def test_get_access_token_expired(
    client: Client,
    mock_session: MagicMock,
    # auth_pending_response_data is not used but required by pytest fixture injection
    auth_pending_response_data: dict[str, Any],  # noqa: ARG001
    verification_model: models.TwitchVerification,
) -> None:
    """Test get_access_token raises AuthorizationError caused by DeviceCodeExpiredError."""
    # No need to mock post as the loop condition should prevent it

    verification_model_expired = verification_model.model_copy(
        update={"expires_at": NOW - datetime.timedelta(seconds=1)}
    )

    with patch("asyncio.sleep", AsyncMock()) as mock_sleep:  # noqa: SIM117
        with pytest.raises(exceptions.AuthorizationError) as exc_info:
            await client.get_access_token(verification_model_expired)

    assert isinstance(exc_info.value.__cause__, exceptions.DeviceCodeExpiredError)
    mock_session.post.assert_not_called()
    mock_sleep.assert_not_awaited()


@pytest.mark.asyncio
@freeze_time(NOW)
async def test_get_access_token_request_error(
    client: Client,
    mock_session: MagicMock,
    mock_response: MagicMock,
    verification_model: models.TwitchVerification,
) -> None:
    """Test get_access_token wraps request errors into AuthorizationError."""
    mock_response.status = 503
    mock_response.json.return_value = {"error": "service unavailable"}
    mock_response.raise_for_status.side_effect = aiohttp.ClientResponseError(MagicMock(), (), status=503)
    # Set the return value of the MagicMock session.post
    mock_session.post.return_value = mock_response
    expected_payload = {
        "client_id": constants.CLIENT_ID,
        "device_code": verification_model.device_code,
        "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
    }

    with patch("asyncio.sleep", AsyncMock()):  # noqa: SIM117
        with pytest.raises(exceptions.AuthorizationError):
            await client.get_access_token(verification_model)

    mock_session.post.assert_called_once_with(constants.AUTHORIZE_URL, data=expected_payload)
    mock_response.__aenter__.assert_awaited_once()
    mock_response.json.assert_awaited_once()
    mock_response.raise_for_status.assert_called_once()
    mock_response.__aexit__.assert_awaited_once()


@pytest.mark.asyncio
@freeze_time(NOW)
async def test_get_access_token_cancelled(
    client: Client,
    mock_session: MagicMock,
    auth_pending_response_data: dict[str, Any],
    verification_model: models.TwitchVerification,
) -> None:
    """Test get_access_token handles asyncio.CancelledError correctly."""
    response_pending = MagicMock(spec=aiohttp.ClientResponse)
    response_pending.status = 400
    response_pending.json = AsyncMock(return_value=auth_pending_response_data)
    response_pending.raise_for_status = MagicMock()
    response_pending.__aenter__ = AsyncMock(return_value=response_pending)
    response_pending.__aexit__ = AsyncMock()

    # Set the return value of the MagicMock session.post
    mock_session.post.return_value = response_pending
    expected_payload = {
        "client_id": constants.CLIENT_ID,
        "device_code": verification_model.device_code,
        "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
    }

    async def sleep_then_cancel(_: float) -> None:
        raise asyncio.CancelledError

    with patch("asyncio.sleep", AsyncMock(side_effect=sleep_then_cancel)):  # noqa: SIM117
        with pytest.raises(asyncio.CancelledError):
            await client.get_access_token(verification_model)

    # Check post was called before cancellation
    mock_session.post.assert_called_once_with(constants.AUTHORIZE_URL, data=expected_payload)
    response_pending.__aenter__.assert_awaited_once()
    response_pending.json.assert_awaited_once()


@pytest.mark.asyncio
@freeze_time(NOW)
async def test_refresh_access_token_success(
    client: Client, mock_session: MagicMock, mock_response: MagicMock, access_token_response_data: dict[str, Any]
) -> None:
    """Test refresh_access_token successfully refreshes and parses the token."""
    mock_response.status = 200
    mock_response.json.return_value = access_token_response_data
    # Set the return value of the MagicMock session.post
    mock_session.post.return_value = mock_response
    refresh_token = "old_refresh_token"
    expected_payload = {
        "client_id": constants.CLIENT_ID,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }

    token = await client.refresh_access_token(refresh_token)

    mock_session.post.assert_called_once_with(constants.AUTHORIZE_URL, data=expected_payload)
    mock_response.__aenter__.assert_awaited_once()
    mock_response.json.assert_awaited_once()
    mock_response.__aexit__.assert_awaited_once()
    assert isinstance(token, TwitchToken)
    assert token.access_token == "test_access_token"
    assert token.refresh_token == "test_refresh_token"
    assert token.expires_at == NOW + datetime.timedelta(seconds=ACCESS_TOKEN_EXPIRES_IN)


@pytest.mark.asyncio
async def test_refresh_access_token_error(client: Client, mock_session: MagicMock, mock_response: MagicMock) -> None:
    """Test refresh_access_token wraps request errors into AuthorizationError."""
    mock_response.status = 400
    mock_response.json.return_value = {"error": "invalid grant"}
    mock_response.raise_for_status.side_effect = aiohttp.ClientResponseError(MagicMock(), (), status=400)
    # Set the return value of the MagicMock session.post
    mock_session.post.return_value = mock_response
    refresh_token = "invalid_or_expired_refresh_token"
    expected_payload = {
        "client_id": constants.CLIENT_ID,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }

    with pytest.raises(exceptions.AuthorizationError):
        await client.refresh_access_token(refresh_token)

    mock_session.post.assert_called_once_with(constants.AUTHORIZE_URL, data=expected_payload)
    mock_response.__aenter__.assert_awaited_once()
    mock_response.json.assert_awaited_once()
    mock_response.raise_for_status.assert_called_once()
    mock_response.__aexit__.assert_awaited_once()
