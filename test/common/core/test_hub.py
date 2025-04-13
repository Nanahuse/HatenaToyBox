from collections.abc import Callable, Coroutine
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from common.base_model import BaseEvent, BaseService

# Import types and classes needed for testing/mocking
from common.core.event_publisher import EventPublisher

# Import the class to be tested
from common.core.hub import Hub
from common.core.service_caller import ServiceCaller


# Define dummy/mock types for testing
class MockEventController:
    def __init__(self, *_args: tuple[Any], **_kwargs: dict[str, Any]) -> None:
        self.add_handler = MagicMock()
        self.run = AsyncMock()  # run is async


class MockServiceController:
    def __init__(self, *_args: tuple[Any], **_kwargs: dict[str, Any]) -> None:
        self.add_handler = MagicMock()
        # Add other methods if Hub interacts with them directly


class DummyEvent(BaseEvent):
    pass


class DummyService(BaseService[str, int]):
    pass


# Define mock handlers
MockEventHandler = MagicMock(spec=Callable[[DummyEvent], Coroutine[Any, Any, None]])
MockServiceHandler = MagicMock(spec=Callable[[str], Coroutine[Any, Any, int]])


# --- Fixtures ---


@pytest_asyncio.fixture
def hub_with_mocks():  # noqa: ANN201
    """
    Provides a Hub instance where its internal controllers are replaced by mocks.
    This allows checking if Hub correctly delegates calls to the controllers.
    """
    # Patch the controller classes within the hub's module scope
    with (
        patch("common.core.hub.EventController", new_callable=MagicMock) as MockEventController,  # noqa: N806
        patch("common.core.hub.ServiceController", new_callable=MagicMock) as MockServiceController,  # noqa: N806
    ):
        # Instantiate the Hub - this will now use the mocked controllers
        hub_instance = Hub()

        # Return the hub and the mock instances for assertions
        yield hub_instance, MockEventController.return_value, MockServiceController.return_value


# --- Test Cases ---


def test_initialization(hub_with_mocks: tuple[Hub, MockEventController, MockServiceController]) -> None:
    """Test that Hub initializes its internal controllers."""
    hub, mock_event_controller, mock_service_controller = hub_with_mocks

    # Check if the controllers were instantiated during Hub.__init__
    # The patch context manager already provides the mock classes,
    # Hub.__init__ calls them, creating the .return_value instances.
    assert hub._event_controller is mock_event_controller
    assert hub._service_controller is mock_service_controller


def test_create_publisher(hub_with_mocks: tuple[Hub, MockEventController, MockServiceController]) -> None:
    """Test that create_publisher returns an EventPublisher linked to the correct controller."""
    hub, mock_event_controller, _ = hub_with_mocks

    # Patch EventPublisher to check its constructor call
    with patch("common.core.hub.EventPublisher", spec=EventPublisher) as MockEventPublisher:  # noqa: N806
        publisher = hub.create_publisher()

        # Check that EventPublisher was instantiated correctly
        MockEventPublisher.assert_called_once_with(mock_event_controller)
        # Check the returned object is the instance created by the mock
        assert publisher is MockEventPublisher.return_value


def test_create_caller(hub_with_mocks: tuple[Hub, MockEventController, MockServiceController]) -> None:
    """Test that create_caller returns a ServiceCaller linked to the correct controller."""
    hub, _, mock_service_controller = hub_with_mocks

    # Patch ServiceCaller to check its constructor call
    with patch("common.core.hub.ServiceCaller", spec=ServiceCaller) as MockServiceCaller:  # noqa: N806
        caller = hub.create_caller()

        # Check that ServiceCaller was instantiated correctly
        MockServiceCaller.assert_called_once_with(mock_service_controller)
        # Check the returned object is the instance created by the mock
        assert caller is MockServiceCaller.return_value


def test_add_service_handler_delegates(hub_with_mocks: tuple[Hub, MockEventController, MockServiceController]) -> None:
    """Test that add_service_handler delegates to the ServiceController."""
    hub, _, mock_service_controller = hub_with_mocks
    mock_handler = MockServiceHandler()
    service_type = DummyService

    hub.add_service_handler(service_type, mock_handler)

    # Assert that the service controller's add_handler was called with the correct args
    mock_service_controller.add_handler.assert_called_once_with(service_type, mock_handler)


def test_add_event_handler_delegates(hub_with_mocks: tuple[Hub, MockEventController, MockServiceController]) -> None:
    """Test that add_event_handler delegates to the EventController."""
    hub, mock_event_controller, _ = hub_with_mocks
    mock_handler = MockEventHandler()
    event_type = DummyEvent

    hub.add_event_handler(event_type, mock_handler)

    # Assert that the event controller's add_handler was called with the correct args
    mock_event_controller.add_handler.assert_called_once_with(event_type, mock_handler)


@pytest.mark.asyncio
async def test_run_delegates(hub_with_mocks: tuple[Hub, MockEventController, MockServiceController]) -> None:
    """Test that run awaits the EventController's run method."""
    hub, mock_event_controller, _ = hub_with_mocks

    # Ensure the mock's run method is awaitable (AsyncMock handles this)
    mock_event_controller.run = AsyncMock()

    await hub.run()

    # Assert that the event controller's run method was awaited
    mock_event_controller.run.assert_awaited_once()
