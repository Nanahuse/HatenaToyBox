from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

from common.base_model import BaseEvent

# Import the class to be tested
from common.core.event_publisher import EventPublisher


# Define specific event types for testing
class MyEvent(BaseEvent):
    pass


class AnotherEvent(BaseEvent):
    pass


# Define a non-event class for testing type checks
class NotAnEvent:
    pass


# --- Fixtures ---


@pytest_asyncio.fixture
async def mock_controller() -> MagicMock:
    """Provides a mock EventController with mocked publish methods."""
    controller = MagicMock(name="MockEventController")
    # publish is async, needs AsyncMock
    controller.publish = AsyncMock(name="MockEventController.publish")
    # publish_nowait is sync, MagicMock is fine
    controller.publish_nowait = MagicMock(name="MockEventController.publish_nowait")
    return controller


@pytest_asyncio.fixture
async def publisher(mock_controller: MagicMock) -> EventPublisher:
    """Provides an EventPublisher instance initialized with the mock controller."""
    return EventPublisher(controller=mock_controller)


# --- Test Cases ---


def test_initialization(publisher: EventPublisher, mock_controller: MagicMock) -> None:
    """Test that the publisher stores the controller correctly."""
    assert publisher._controller is mock_controller


@pytest.mark.asyncio
async def test_publish_valid_event(publisher: EventPublisher, mock_controller: MagicMock) -> None:
    """Test publish calls controller.publish with a valid BaseEvent."""
    event = MyEvent(payload="data1")

    await publisher.publish(event)

    # Assert that the controller's async publish method was awaited with the event
    mock_controller.publish.assert_awaited_once_with(event)
    # Ensure publish_nowait was not called
    mock_controller.publish_nowait.assert_not_called()


@pytest.mark.asyncio
async def test_publish_invalid_event_type(publisher: EventPublisher, mock_controller: MagicMock) -> None:
    """Test publish does nothing if the object is not a BaseEvent."""
    invalid_event = NotAnEvent()  # Not an instance of BaseEvent

    # We need to tell type checkers to ignore this misuse for the test
    await publisher.publish(invalid_event)  # type: ignore[arg-type]

    # Assert that neither publish method on the controller was called
    mock_controller.publish.assert_not_awaited()
    mock_controller.publish_nowait.assert_not_called()


@pytest.mark.asyncio
async def test_publish_none(publisher: EventPublisher, mock_controller: MagicMock) -> None:
    """Test publish does nothing if None is passed."""
    await publisher.publish(None)  # type: ignore[arg-type]

    # Assert that neither publish method on the controller was called
    mock_controller.publish.assert_not_awaited()
    mock_controller.publish_nowait.assert_not_called()


def test_publish_nowait_valid_event(publisher: EventPublisher, mock_controller: MagicMock) -> None:
    """Test publish_nowait calls controller.publish_nowait with a valid BaseEvent."""
    event = AnotherEvent(payload={"key": "value"})

    publisher.publish_nowait(event)

    # Assert that the controller's sync publish_nowait method was called with the event
    mock_controller.publish_nowait.assert_called_once_with(event)
    # Ensure async publish was not called
    mock_controller.publish.assert_not_awaited()


def test_publish_nowait_invalid_event_type(publisher: EventPublisher, mock_controller: MagicMock) -> None:
    """Test publish_nowait does nothing if the object is not a BaseEvent."""
    invalid_event = NotAnEvent()

    # We need to tell type checkers to ignore this misuse for the test
    publisher.publish_nowait(invalid_event)  # type: ignore[arg-type]

    # Assert that neither publish method on the controller was called
    mock_controller.publish.assert_not_awaited()
    mock_controller.publish_nowait.assert_not_called()


def test_publish_nowait_none(publisher: EventPublisher, mock_controller: MagicMock) -> None:
    """Test publish_nowait does nothing if None is passed."""
    publisher.publish_nowait(None)  # type: ignore[arg-type]

    # Assert that neither publish method on the controller was called
    mock_controller.publish.assert_not_awaited()
    mock_controller.publish_nowait.assert_not_called()
