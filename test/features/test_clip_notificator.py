from unittest.mock import AsyncMock, MagicMock

import pytest

from common.core import Hub
from features.clip_notificator import ClipNotificator
from schemas import enums, events, models, services


@pytest.fixture
def mock_hub() -> Hub:
    return Hub()


@pytest.fixture
def mock_service_handler(mock_hub: Hub) -> MagicMock:
    mock = MagicMock()
    mock.mock_post_announcement = AsyncMock()

    mock_hub.add_service_handler(services.PostAnnouncement, mock.mock_post_announcement)

    return mock


@pytest.mark.asyncio
async def test_clip_notificator_find_new_clip_no_user_config(mock_hub: Hub, mock_service_handler: MagicMock) -> None:
    system_config = {"version": 0}
    clip_notificator = ClipNotificator(mock_hub, system_config)

    clip = models.Clip(title="test_title", creator="test_creator", url="test_url")
    event = events.ClipFound(clip=clip)
    await clip_notificator._new_clip_found(event)

    mock_service_handler.mock_post_announcement.assert_not_called()


@pytest.mark.asyncio
async def test_clip_notificator_find_new_clip_valid_clip(mock_hub: Hub, mock_service_handler: MagicMock) -> None:
    system_config = {"version": 0}
    user_config = {
        "version": 0,
        "message_format": "{url} - {title} by {creator}",
        "color": enums.AnnouncementColor.BLUE,
    }
    clip_notificator = ClipNotificator(mock_hub, system_config)
    await clip_notificator.set_user_config(user_config)

    clip = models.Clip(title="test_title", creator="test_creator", url="test_url")
    event = events.ClipFound(clip=clip)
    await clip_notificator._new_clip_found(event)

    mock_service_handler.mock_post_announcement.assert_called_once()
    announcement_payload = mock_service_handler.mock_post_announcement.call_args[0][0]
    assert announcement_payload.content == "test_url - test_title by test_creator"
    assert announcement_payload.color == enums.AnnouncementColor.BLUE


@pytest.mark.asyncio
async def test_clip_notificator_find_new_clip_runtime_error(mock_hub: Hub, mock_service_handler: MagicMock) -> None:
    system_config = {"version": 0}
    user_config = {
        "version": 0,
        "message_format": "{url} - {title} by {creator}",
        "color": enums.AnnouncementColor.BLUE,
    }
    clip_notificator = ClipNotificator(mock_hub, system_config)
    await clip_notificator.set_user_config(user_config)

    mock_service_handler.mock_post_announcement.side_effect = RuntimeError("Test Error")

    clip = models.Clip(title="test_title", creator="test_creator", url="test_url")
    event = events.ClipFound(clip=clip)
    await clip_notificator._new_clip_found(event)

    mock_service_handler.mock_post_announcement.assert_called_once()


def test_clip_notificator_init_event_handler(mock_hub: Hub) -> None:
    system_config = {"version": 0}
    ClipNotificator(mock_hub, system_config)

    assert mock_hub._event_controller._handlers[events.ClipFound] is not None
