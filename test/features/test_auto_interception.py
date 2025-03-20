import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from common.core import Hub
from features.auto_interception import AutoInterception
from schemas import events, models, services
from utils import routines


@pytest.fixture
def mock_hub() -> Hub:
    return Hub()


@pytest.fixture
def mock_service_handler(mock_hub: Hub) -> MagicMock:
    mock = MagicMock()
    mock.mock_fetch_stream_info = AsyncMock()
    mock.mock_post_announcement = AsyncMock()
    mock.mock_shoutout = AsyncMock()

    mock_hub.add_service_handler(services.FetchStreamInfo, mock.mock_fetch_stream_info)
    mock_hub.add_service_handler(services.PostAnnouncement, mock.mock_post_announcement)
    mock_hub.add_service_handler(services.Shoutout, mock.mock_shoutout)

    return mock


@pytest.fixture
def mock_routine_manager() -> MagicMock:
    mock = MagicMock(spec=routines.RoutineManager)
    mock.add = MagicMock()
    mock.start = MagicMock()
    mock.cancel = MagicMock()
    return mock


@pytest.mark.asyncio
async def test_auto_interception_main_no_user_config(
    mock_hub: Hub,
    mock_service_handler: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    system_config = {"version": 0}
    auto_interception = AutoInterception(mock_hub, system_config)
    publisher = mock_hub.create_publisher()
    raider = models.User(id=0, name="name", display_name="display_name")

    # Mock RoutineManager to simulate the _main method being called
    mock_routine_manager = MagicMock(spec=routines.RoutineManager)
    mock_routine_manager.add = MagicMock(side_effect=lambda coro, interval: asyncio.create_task(coro()))  # noqa: ARG005
    mock_routine_manager.start = MagicMock()
    mock_routine_manager.cancel = MagicMock()
    monkeypatch.setattr(routines, "RoutineManager", MagicMock(return_value=mock_routine_manager))

    hub_task = asyncio.create_task(mock_hub.run())
    task = asyncio.create_task(auto_interception.run())
    await publisher.publish(events.RaidDetected(raider=raider))
    await asyncio.sleep(0.1)

    hub_task.cancel()
    task.cancel()

    mock_service_handler.mock_fetch_stream_info.assert_not_called()
    mock_service_handler.mock_post_announcement.assert_not_called()
    mock_service_handler.mock_shoutout.assert_not_called()


@pytest.mark.asyncio
async def test_auto_interception_main_with_user_config(
    mock_hub: Hub,
    mock_service_handler: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    system_config = {"version": 0}
    auto_interception = AutoInterception(mock_hub, system_config)
    user_config = {
        "version": 0,
        "reaction_delay": 0,
        "do_shoutout": True,
        "do_announcement": True,
        "message_format": "{raider},{title},{game}",
        "color": None,
    }
    await auto_interception.set_user_config(user_config)

    mock_service_handler.mock_fetch_stream_info.return_value = models.StreamInfo(
        title="test_stream",
        game=models.Game(game_id="123", name="test_game"),
        tags=[],
    )

    publisher = mock_hub.create_publisher()
    raider = models.User(id=0, name="name", display_name="display_name")

    # Mock RoutineManager to simulate the _main method being called
    mock_routine_manager = MagicMock(spec=routines.RoutineManager)
    mock_routine_manager.add = MagicMock(side_effect=lambda coro, interval: asyncio.create_task(coro()))  # noqa: ARG005
    mock_routine_manager.start = MagicMock()
    mock_routine_manager.cancel = MagicMock()
    monkeypatch.setattr(routines, "RoutineManager", MagicMock(return_value=mock_routine_manager))

    hub_task = asyncio.create_task(mock_hub.run())
    task = asyncio.create_task(auto_interception.run())
    await publisher.publish(events.RaidDetected(raider=raider))
    await asyncio.sleep(0.1)

    hub_task.cancel()
    task.cancel()

    mock_service_handler.mock_fetch_stream_info.assert_called_once_with(raider)
    mock_service_handler.mock_post_announcement.assert_called_once()
    mock_service_handler.mock_shoutout.assert_called_once_with(raider)

    announcement_payload = mock_service_handler.mock_post_announcement.call_args[0][0]
    assert announcement_payload.content == "display_name,test_stream,test_game"
    assert announcement_payload.color is None


@pytest.mark.asyncio
async def test_auto_interception_main_no_announcement(
    mock_hub: Hub,
    mock_service_handler: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    system_config = {"version": 0}
    auto_interception = AutoInterception(mock_hub, system_config)
    user_config = {
        "version": 0,
        "reaction_delay": 0,
        "do_shoutout": True,
        "do_announcement": False,
        "message_format": "{raider},{title},{game}",
        "color": None,
    }
    await auto_interception.set_user_config(user_config)

    mock_service_handler.mock_fetch_stream_info.return_value = models.StreamInfo(
        title="test_stream",
        game=models.Game(game_id="123", name="test_game"),
        tags=[],
    )

    publisher = mock_hub.create_publisher()
    raider = models.User(id=0, name="name", display_name="display_name")

    # Mock RoutineManager to simulate the _main method being called
    mock_routine_manager = MagicMock(spec=routines.RoutineManager)
    mock_routine_manager.add = MagicMock(side_effect=lambda coro, interval: asyncio.create_task(coro()))  # noqa: ARG005
    mock_routine_manager.start = MagicMock()
    mock_routine_manager.cancel = MagicMock()
    monkeypatch.setattr(routines, "RoutineManager", MagicMock(return_value=mock_routine_manager))

    hub_task = asyncio.create_task(mock_hub.run())
    task = asyncio.create_task(auto_interception.run())
    await publisher.publish(events.RaidDetected(raider=raider))
    await asyncio.sleep(0.1)

    hub_task.cancel()
    task.cancel()

    mock_service_handler.mock_fetch_stream_info.assert_not_called()
    mock_service_handler.mock_post_announcement.assert_not_called()
    mock_service_handler.mock_shoutout.assert_called_once_with(raider)


@pytest.mark.asyncio
async def test_auto_interception_main_no_shoutout(
    mock_hub: Hub,
    mock_service_handler: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    system_config = {"version": 0}
    auto_interception = AutoInterception(mock_hub, system_config)
    user_config = {
        "version": 0,
        "reaction_delay": 0,
        "do_shoutout": False,
        "do_announcement": True,
        "message_format": "{raider},{title},{game}",
        "color": None,
    }
    await auto_interception.set_user_config(user_config)

    mock_service_handler.mock_fetch_stream_info.return_value = models.StreamInfo(
        title="test_stream",
        game=models.Game(game_id="123", name="test_game"),
        tags=[],
    )

    publisher = mock_hub.create_publisher()
    raider = models.User(id=0, name="name", display_name="display_name")

    # Mock RoutineManager to simulate the _main method being called
    mock_routine_manager = MagicMock(spec=routines.RoutineManager)
    mock_routine_manager.add = MagicMock(side_effect=lambda coro, interval: asyncio.create_task(coro()))  # noqa: ARG005
    mock_routine_manager.start = MagicMock()
    mock_routine_manager.cancel = MagicMock()
    monkeypatch.setattr(routines, "RoutineManager", MagicMock(return_value=mock_routine_manager))

    hub_task = asyncio.create_task(mock_hub.run())
    task = asyncio.create_task(auto_interception.run())
    await publisher.publish(events.RaidDetected(raider=raider))
    await asyncio.sleep(0.1)

    hub_task.cancel()
    task.cancel()

    mock_service_handler.mock_fetch_stream_info.assert_called_once_with(raider)
    mock_service_handler.mock_post_announcement.assert_called_once()
    mock_service_handler.mock_shoutout.assert_not_called()


@pytest.mark.asyncio
async def test_auto_interception_main_delay(
    mock_hub: Hub,
    mock_service_handler: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    system_config = {"version": 0}
    auto_interception = AutoInterception(mock_hub, system_config)
    user_config = {
        "version": 0,
        "reaction_delay": 0.1,
        "do_shoutout": True,
        "do_announcement": True,
        "message_format": "{raider},{title},{game}",
        "color": None,
    }
    await auto_interception.set_user_config(user_config)

    mock_service_handler.mock_fetch_stream_info.return_value = models.StreamInfo(
        title="test_stream",
        game=models.Game(game_id="123", name="test_game"),
        tags=[],
    )

    publisher = mock_hub.create_publisher()
    raider = models.User(id=0, name="name", display_name="display_name")

    # Mock RoutineManager to simulate the _main method being called
    mock_routine_manager = MagicMock(spec=routines.RoutineManager)
    mock_routine_manager.add = MagicMock(side_effect=lambda coro, interval: asyncio.create_task(coro()))  # noqa: ARG005
    mock_routine_manager.start = MagicMock()
    mock_routine_manager.cancel = MagicMock()
    monkeypatch.setattr(routines, "RoutineManager", MagicMock(return_value=mock_routine_manager))

    hub_task = asyncio.create_task(mock_hub.run())
    task = asyncio.create_task(auto_interception.run())
    await publisher.publish(events.RaidDetected(raider=raider))
    await asyncio.sleep(0.05)

    mock_service_handler.mock_post_announcement.assert_not_called()
    mock_service_handler.mock_shoutout.assert_not_called()

    await asyncio.sleep(0.2)

    hub_task.cancel()
    task.cancel()

    mock_service_handler.mock_fetch_stream_info.assert_called_once_with(raider)
    mock_service_handler.mock_post_announcement.assert_called_once()
    mock_service_handler.mock_shoutout.assert_called_once_with(raider)


@pytest.mark.asyncio
async def test_auto_interception_main_fetch_stream_info_none(
    mock_hub: Hub,
    mock_service_handler: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    system_config = {"version": 0}
    auto_interception = AutoInterception(mock_hub, system_config)
    user_config = {
        "version": 0,
        "reaction_delay": 0,
        "do_shoutout": True,
        "do_announcement": True,
        "message_format": "{raider},{title},{game}",
        "color": None,
    }
    await auto_interception.set_user_config(user_config)

    mock_service_handler.mock_fetch_stream_info.return_value = models.StreamInfo(
        title="test_stream",
        game=None,
        tags=[],
    )

    publisher = mock_hub.create_publisher()
    raider = models.User(id=0, name="name", display_name="display_name")

    # Mock RoutineManager to simulate the _main method being called
    mock_routine_manager = MagicMock(spec=routines.RoutineManager)
    mock_routine_manager.add = MagicMock(side_effect=lambda coro, interval: asyncio.create_task(coro()))  # noqa: ARG005
    mock_routine_manager.start = MagicMock()
    mock_routine_manager.cancel = MagicMock()
    monkeypatch.setattr(routines, "RoutineManager", MagicMock(return_value=mock_routine_manager))

    hub_task = asyncio.create_task(mock_hub.run())
    task = asyncio.create_task(auto_interception.run())
    await publisher.publish(events.RaidDetected(raider=raider))
    await asyncio.sleep(0.1)

    hub_task.cancel()
    task.cancel()

    mock_service_handler.mock_fetch_stream_info.assert_called_once_with(raider)
    mock_service_handler.mock_post_announcement.assert_called_once()
    mock_service_handler.mock_shoutout.assert_called_once_with(raider)

    announcement_payload = mock_service_handler.mock_post_announcement.call_args[0][0]
    assert announcement_payload.content == "display_name,test_stream,???"
    assert announcement_payload.color is None


@pytest.mark.asyncio
async def test_auto_interception_main_runtime_error(
    mock_hub: Hub,
    mock_service_handler: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    system_config = {"version": 0}
    auto_interception = AutoInterception(mock_hub, system_config)
    user_config = {
        "version": 0,
        "reaction_delay": 0,
        "do_shoutout": True,
        "do_announcement": True,
        "message_format": "{raider},{title},{game}",
        "color": None,
    }
    await auto_interception.set_user_config(user_config)

    mock_service_handler.mock_fetch_stream_info.side_effect = RuntimeError("Test Error")

    publisher = mock_hub.create_publisher()
    raider = models.User(id=0, name="name", display_name="display_name")

    # Mock RoutineManager to simulate the _main method being called
    mock_routine_manager = MagicMock(spec=routines.RoutineManager)
    mock_routine_manager.add = MagicMock(side_effect=lambda coro, interval: asyncio.create_task(coro()))  # noqa: ARG005
    mock_routine_manager.start = MagicMock()
    mock_routine_manager.cancel = MagicMock()
    monkeypatch.setattr(routines, "RoutineManager", MagicMock(return_value=mock_routine_manager))

    hub_task = asyncio.create_task(mock_hub.run())
    task = asyncio.create_task(auto_interception.run())
    await publisher.publish(events.RaidDetected(raider=raider))
    await asyncio.sleep(0.1)

    hub_task.cancel()
    task.cancel()

    mock_service_handler.mock_fetch_stream_info.assert_called_once_with(raider)
    mock_service_handler.mock_post_announcement.assert_not_called()
    mock_service_handler.mock_shoutout.assert_not_called()
