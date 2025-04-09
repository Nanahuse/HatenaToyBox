from unittest.mock import AsyncMock, MagicMock

import pytest

from common.core import Hub
from features.message_filter import MessageFilter
from schemas import events, models


@pytest.fixture
def mock_hub() -> Hub:
    return Hub()


@pytest.fixture
def mock_publisher(mock_hub: Hub) -> AsyncMock:
    mock = AsyncMock()
    mock_hub.create_publisher = MagicMock(return_value=mock)  # type: ignore[method-assign]
    return mock


@pytest.mark.asyncio
async def test_message_filter_no_user_config(mock_hub: Hub, mock_publisher: AsyncMock) -> None:
    system_config = {"version": 0}
    message_filter = MessageFilter(mock_hub, system_config)

    message = models.Message(
        id="1",
        content="test",
        parsed_content=[],
        author=models.User(id=1, name="test_user", display_name="Test User"),
        channel="test_channel",
        is_echo=False,
    )
    event = events.NewMessageReceived(message=message)
    await message_filter._filter(event)

    mock_publisher.publish.assert_not_called()


@pytest.mark.asyncio
async def test_message_filter_echo_message(mock_hub: Hub, mock_publisher: AsyncMock) -> None:
    system_config = {"version": 0}
    user_config = {"version": 0, "ignore_accounts": set()}
    message_filter = MessageFilter(mock_hub, system_config)
    await message_filter.set_user_config(user_config)

    message = models.Message(
        id="1",
        content="test",
        parsed_content=[],
        author=models.User(id=1, name="test_user", display_name="Test User"),
        channel="test_channel",
        is_echo=True,
    )
    event = events.NewMessageReceived(message=message)
    await message_filter._filter(event)

    mock_publisher.publish.assert_not_called()


@pytest.mark.asyncio
async def test_message_filter_ignored_user(mock_hub: Hub, mock_publisher: AsyncMock) -> None:
    system_config = {"version": 0}
    user_config = {"version": 0, "ignore_accounts": {"test_user"}}
    message_filter = MessageFilter(mock_hub, system_config)
    await message_filter.set_user_config(user_config)

    message = models.Message(
        id="1",
        content="test",
        parsed_content=[],
        author=models.User(id=1, name="test_user", display_name="Test User"),
        channel="test_channel",
        is_echo=False,
    )
    event = events.NewMessageReceived(message=message)
    await message_filter._filter(event)

    mock_publisher.publish.assert_not_called()


@pytest.mark.asyncio
async def test_message_filter_valid_message(mock_hub: Hub, mock_publisher: AsyncMock) -> None:
    system_config = {"version": 0}
    user_config = {"version": 0, "ignore_accounts": set()}
    message_filter = MessageFilter(mock_hub, system_config)
    await message_filter.set_user_config(user_config)

    message = models.Message(
        id="1",
        content="test",
        parsed_content=[],
        author=models.User(id=1, name="test_user", display_name="Test User"),
        channel="test_channel",
        is_echo=False,
    )
    event = events.NewMessageReceived(message=message)
    await message_filter._filter(event)

    mock_publisher.publish.assert_called_once()
    published_event = mock_publisher.publish.call_args[0][0]
    assert isinstance(published_event, events.MessageFiltered)
    assert published_event.message == message
