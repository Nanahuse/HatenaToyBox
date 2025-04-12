import datetime
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest
from twitchio.ext import routines

from utils.routines import RoutineManager


@pytest.fixture
def mock_routine() -> MagicMock:
    mock = MagicMock(spec=routines.Routine)
    mock.start = Mock()
    mock.cancel = Mock()
    mock.restart = Mock()
    return mock


@pytest.fixture
def mock_routine_factory(mock_routine: MagicMock) -> MagicMock:
    return MagicMock(return_value=mock_routine)


@pytest.mark.asyncio
async def test_routine_manager_add(mock_routine_factory: MagicMock) -> None:
    manager = RoutineManager()
    mock_coro = AsyncMock()
    interval = datetime.timedelta(seconds=1)

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(routines, "routine", mock_routine_factory)
        manager.add(mock_coro, interval)

    mock_routine_factory.assert_called_once_with(seconds=interval.total_seconds())


@pytest.mark.asyncio
async def test_routine_manager_start(mock_routine: MagicMock) -> None:
    manager = RoutineManager()
    manager._routines = [mock_routine]
    manager.start()  # Await the start method
    mock_routine.start.assert_called_once()


@pytest.mark.asyncio
async def test_routine_manager_clear(mock_routine: MagicMock) -> None:
    manager = RoutineManager()
    manager._routines = [mock_routine]
    manager.clear()  # Await the cancel method
    mock_routine.cancel.assert_called_once()


@pytest.mark.asyncio
async def test_routine_manager_restart(mock_routine: MagicMock) -> None:
    manager = RoutineManager()
    manager._routines = [mock_routine]
    manager.restart()  # Await the restart method
    mock_routine.restart.assert_called_once()
