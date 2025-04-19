# mypy: disable-error-code="attr-defined"

from collections.abc import Callable, Coroutine
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from common.base_model import BaseEvent, BaseService
from common.core.controller import EventController, ServiceController

# Import types and classes needed for testing/mocking
from common.core.event_publisher import EventPublisher

# Import the class to be tested
from common.core.hub import Hub
from common.core.service_caller import ServiceCaller


@pytest.fixture
def mock_event_controller() -> MagicMock:
    controller = MagicMock(spec=EventController)
    # publish is async, needs AsyncMock
    controller.add_handler = MagicMock()
    controller.run = AsyncMock()
    return controller


@pytest.fixture
def mock_service_controller() -> MagicMock:
    controller = MagicMock(spec=ServiceController)
    # publish is async, needs AsyncMock
    controller.add_handler = MagicMock()
    return controller


class DummyEvent(BaseEvent):
    pass


class DummyService(BaseService[str, int]):
    pass


# Define mock handlers
MockEventHandler = MagicMock(spec=Callable[[DummyEvent], Coroutine[Any, Any, None]])
MockServiceHandler = MagicMock(spec=Callable[[str], Coroutine[Any, Any, int]])


# --- Fixtures ---


@pytest.fixture
def mocked_hub() -> Hub:
    """
    Provides a Hub instance where its internal controllers are replaced by mocks.
    This allows checking if Hub correctly delegates calls to the controllers.
    """
    # Patch the controller classes within the hub's module scope
    with (
        patch("common.core.hub.EventController", autospec=True),
        patch("common.core.hub.ServiceController", autospec=True),
    ):
        return Hub()


# --- Test Cases ---


def test_create_publisher(mocked_hub: Hub) -> None:
    """Test that create_publisher returns an EventPublisher linked to the correct controller."""
    # Patch EventPublisher to check its constructor call
    with patch("common.core.hub.EventPublisher", spec=EventPublisher) as MockEventPublisher:  # noqa: N806
        publisher = mocked_hub.create_publisher()

        # Check that EventPublisher was instantiated correctly
        MockEventPublisher.assert_called_once_with(mocked_hub._event_controller)
        # Check the returned object is the instance created by the mock
        assert publisher is MockEventPublisher.return_value


def test_create_caller(mocked_hub: Hub) -> None:
    """Test that create_caller returns a ServiceCaller linked to the correct controller."""
    # Patch ServiceCaller to check its constructor call
    with patch("common.core.hub.ServiceCaller", spec=ServiceCaller) as MockServiceCaller:  # noqa: N806
        caller = mocked_hub.create_caller()

        # Check that ServiceCaller was instantiated correctly
        MockServiceCaller.assert_called_once_with(mocked_hub._service_controller)
        # Check the returned object is the instance created by the mock
        assert caller is MockServiceCaller.return_value


def test_add_service_handler_delegates(mocked_hub: Hub) -> None:
    """Test that add_service_handler delegates to the ServiceController."""
    mock_handler = MockServiceHandler()
    service_type = DummyService

    mocked_hub.add_service_handler(service_type, mock_handler)

    # Assert that the service controller's add_handler was called with the correct args
    mocked_hub._service_controller.add_handler.assert_called_once_with(service_type, mock_handler)


def test_add_event_handler_delegates(mocked_hub: Hub) -> None:
    """Test that add_event_handler delegates to the EventController."""
    mock_handler = MockEventHandler()
    event_type = DummyEvent

    mocked_hub.add_event_handler(event_type, mock_handler)

    # Assert that the event controller's add_handler was called with the correct args
    mocked_hub._event_controller.add_handler.assert_called_once_with(event_type, mock_handler)


@pytest.mark.asyncio
async def test_run_delegates(mocked_hub: Hub) -> None:
    """Test that run awaits the EventController's run method."""
    # Ensure the mock's run method is awaitable (AsyncMock handles this)
    await mocked_hub.run()

    # Assert that the event controller's run method was awaited
    mocked_hub._event_controller.run.assert_awaited_once()
