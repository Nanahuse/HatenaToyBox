from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from common.core import Hub
from features.door_bell import DoorBell
from schemas import events, models, services


@pytest.fixture
def mock_hub() -> Hub:
    return Hub()


@pytest.fixture
def mock_service_handler(mock_hub: Hub) -> MagicMock:
    mock = MagicMock()
    mock.mock_play_sound = AsyncMock()

    mock_hub.add_service_handler(services.PlaySound, mock.mock_play_sound)

    return mock


@pytest.mark.asyncio
async def test_door_bell_new_user_with_no_user_config(mock_hub: Hub, mock_service_handler: MagicMock) -> None:
    system_config = {"version": 0}
    door_bell = DoorBell(mock_hub, system_config)

    event = events.MessageFiltered(
        message=models.Message(
            content="test",
            parsed_content=["test"],
            author=models.User(id=0, name="test", display_name="test"),
            is_echo=False,
        )
    )
    await door_bell._message_received(event)

    mock_service_handler.mock_play_sound.assert_not_called()


@pytest.mark.asyncio
async def test_door_bell_new_user(test_sound_file: Path, mock_hub: Hub, mock_service_handler: MagicMock) -> None:
    system_config = {"version": 0}
    user_config = {"version": 0, "sound_file": test_sound_file}
    door_bell = DoorBell(mock_hub, system_config)
    await door_bell.set_user_config(user_config)

    event = events.MessageFiltered(
        message=models.Message(
            content="test",
            parsed_content=["test"],
            author=models.User(id=0, name="test", display_name="test"),
            is_echo=False,
        )
    )
    await door_bell._message_received(event)
    await door_bell._message_received(event)

    mock_service_handler.mock_play_sound.assert_called_once()
    play_sound_payload = mock_service_handler.mock_play_sound.call_args[0][0]
    assert play_sound_payload.path == test_sound_file
