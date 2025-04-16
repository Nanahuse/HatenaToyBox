import asyncio
import logging
from unittest.mock import MagicMock

import pytest
import pytest_asyncio
from pydantic import ValidationError

from common.base_model import BaseConfig
from common.core.hub import Hub
from common.feature import ConfigData, Feature


# Define dummy config classes for testing
class DummySystemConfig(BaseConfig):
    system_value: int = 10


class DummyUserConfig(BaseConfig):
    user_value: str = "default"


# --- Fixtures ---


@pytest_asyncio.fixture
async def mock_hub() -> MagicMock:
    """Provides a mock Hub instance."""
    return MagicMock(spec_set=Hub)


@pytest_asyncio.fixture
async def system_config_data() -> ConfigData:
    """Provides valid system config data."""
    return {"version": 0, "system_value": 20}


@pytest_asyncio.fixture
async def user_config_data() -> ConfigData:
    """Provides valid user config data."""
    return {"version": 0, "user_value": "test"}


@pytest_asyncio.fixture
async def feature(mock_hub: MagicMock, system_config_data: ConfigData) -> Feature[DummySystemConfig, DummyUserConfig]:
    """Provides a Feature instance for testing."""
    return Feature(mock_hub, DummySystemConfig, DummyUserConfig, system_config_data)


# --- Test Cases ---


def test_initialization(
    feature: Feature[DummySystemConfig, DummyUserConfig],
    system_config_data: ConfigData,
) -> None:
    """Test that the feature initializes correctly."""
    assert feature.name == "Feature"
    assert isinstance(feature.logger, logging.Logger)
    assert isinstance(feature._task_queue, asyncio.Queue)
    assert feature._user_config_type is DummyUserConfig
    assert feature._user_config is None
    assert isinstance(feature.system_config, DummySystemConfig)
    assert feature.system_config.system_value == system_config_data["system_value"]
    assert isinstance(feature._event, asyncio.Event)
    assert not feature._event.is_set()


@pytest.mark.asyncio
async def test_initialize(feature: Feature[DummySystemConfig, DummyUserConfig]) -> None:
    """Test that initialize sets the event."""
    await feature.initialize()
    assert not feature._event.is_set()


@pytest.mark.asyncio
async def test_run_waits_for_event(feature: Feature[DummySystemConfig, DummyUserConfig]) -> None:
    """Test that run waits for the event to be set."""
    # Create a task for `run` and a separate task for setting the event
    run_task = asyncio.create_task(feature.run())

    # Ensure the run task is not done (still waiting)
    await asyncio.sleep(0.01)  # Give run time to start
    assert not run_task.done()

    # Set the event to unblock run
    feature._event.set()

    # Wait for run to complete
    await run_task

    # Assert nothing else broke (no errors)


@pytest.mark.asyncio
async def test_close_sets_event(feature: Feature[DummySystemConfig, DummyUserConfig]) -> None:
    """Test that close sets the event."""
    # Set event for testing
    feature._event.clear()

    await feature.close()
    assert feature._event.is_set()


@pytest.mark.asyncio
async def test_set_user_config_valid(
    feature: Feature[DummySystemConfig, DummyUserConfig],
    user_config_data: ConfigData,
) -> None:
    """Test set_user_config with a valid config."""
    result = await feature.set_user_config(user_config_data)
    assert result is True
    assert isinstance(feature._user_config, DummyUserConfig)
    assert feature._user_config.user_value == user_config_data["user_value"]
    result = await feature.set_user_config(user_config_data)
    assert result is False


@pytest.mark.asyncio
async def test_set_user_config_none(
    feature: Feature[DummySystemConfig, DummyUserConfig], user_config_data: ConfigData
) -> None:
    """Test set_user_config with None."""
    await feature.set_user_config(user_config_data)

    result = await feature.set_user_config(None)
    assert result is True
    assert feature.user_config is None
    result = await feature.set_user_config(None)
    assert result is False


@pytest.mark.asyncio
async def test_set_user_config_invalid_data(feature: Feature[DummySystemConfig, DummyUserConfig]) -> None:
    """Test set_user_config with invalid data."""
    invalid_data: ConfigData = {"wrong_key": 123}
    with pytest.raises(ValidationError):  # Pydantic ValidationError
        await feature.set_user_config(invalid_data)

    assert feature.user_config is None
