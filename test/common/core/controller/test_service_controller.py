from typing import Any
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

from common.base_model import BaseService
from common.core.controller import exceptions
from common.core.controller.service_controller import ServiceController


# Define specific service types for testing
class ServiceA(BaseService[str, int]):
    pass


class ServiceB(BaseService[dict[str, Any], bool]):
    pass


class ServiceC(BaseService[None, str]):  # Example with None payload
    pass


# --- Fixtures ---


@pytest_asyncio.fixture
async def controller() -> ServiceController:
    """Provides a fresh ServiceController instance for each test."""
    return ServiceController()


@pytest_asyncio.fixture
async def mock_handler_a() -> AsyncMock:
    """Provides an AsyncMock for a service handler."""
    # Example: Define a default return value if useful
    return AsyncMock(return_value=123)  # ServiceA returns int


@pytest_asyncio.fixture
async def mock_handler_b() -> AsyncMock:
    """Provides another AsyncMock for a service handler."""
    return AsyncMock(return_value=True)  # ServiceB returns bool


# --- Test Cases ---


@pytest.mark.asyncio
async def test_initialization(controller: ServiceController) -> None:
    """Test that the controller initializes with an empty handlers dict."""
    assert controller._handlers == {}
    # Check if logger is initialized (inherited from BaseController)
    assert hasattr(controller, "logger")
    assert controller.logger.name == "Core.ServiceController"


@pytest.mark.asyncio
async def test_add_handler_single(controller: ServiceController, mock_handler_a: AsyncMock) -> None:
    """Test adding a single handler for a service type."""
    controller.add_handler(ServiceA, mock_handler_a)
    assert ServiceA in controller._handlers
    assert controller._handlers[ServiceA] is mock_handler_a
    assert ServiceB not in controller._handlers


@pytest.mark.asyncio
async def test_add_handler_multiple_different_types(
    controller: ServiceController, mock_handler_a: AsyncMock, mock_handler_b: AsyncMock
) -> None:
    """Test adding handlers for different service types."""
    controller.add_handler(ServiceA, mock_handler_a)
    controller.add_handler(ServiceB, mock_handler_b)

    assert ServiceA in controller._handlers
    assert controller._handlers[ServiceA] is mock_handler_a
    assert ServiceB in controller._handlers
    assert controller._handlers[ServiceB] is mock_handler_b
    assert len(controller._handlers) == 2


@pytest.mark.asyncio
async def test_add_handler_duplicate_raises(
    controller: ServiceController, mock_handler_a: AsyncMock, mock_handler_b: AsyncMock
) -> None:
    """Test that adding a handler for an existing service type raises ServiceHandlerExistsError."""
    controller.add_handler(ServiceA, mock_handler_a)

    with pytest.raises(exceptions.ServiceHandlerExistsError) as excinfo:
        controller.add_handler(ServiceA, mock_handler_b)  # Attempt to add another handler for ServiceA

    assert excinfo.value.args[0] is ServiceA  # Check the exception carries the service type
    # Ensure the original handler is still there and wasn't overwritten
    assert ServiceA in controller._handlers
    assert controller._handlers[ServiceA] is mock_handler_a
    assert len(controller._handlers) == 1


@pytest.mark.asyncio
async def test_call_success(controller: ServiceController, mock_handler_a: AsyncMock) -> None:
    """Test calling a service successfully when a handler exists."""
    payload_in = "input_string"
    expected_result = 456  # Override default mock return for clarity
    mock_handler_a.return_value = expected_result

    controller.add_handler(ServiceA, mock_handler_a)
    service_instance = ServiceA(payload=payload_in)

    result = await controller.call(service_instance)

    assert result == expected_result
    mock_handler_a.assert_awaited_once_with(payload_in)  # Handler receives the payload


@pytest.mark.asyncio
async def test_call_no_handler_raises(controller: ServiceController) -> None:
    """Test that calling a service with no registered handler raises ServiceNotHandledError."""
    service_instance = ServiceB(payload={"key": "value"})  # No handler added for ServiceB

    with pytest.raises(exceptions.ServiceNotHandledError) as excinfo:
        await controller.call(service_instance)

    expected_msg = f"{service_instance} was not handled."
    assert str(excinfo.value) == expected_msg


@pytest.mark.asyncio
async def test_call_handler_raises_exception(controller: ServiceController, mock_handler_a: AsyncMock) -> None:
    """Test that if the handler itself raises an exception, call() propagates it."""
    payload_in = "trigger_error"
    error_message = "Handler failed internally!"
    mock_handler_a.side_effect = ValueError(error_message)  # Configure mock to raise

    controller.add_handler(ServiceA, mock_handler_a)
    service_instance = ServiceA(payload=payload_in)

    with pytest.raises(ValueError, match=error_message) as excinfo:
        await controller.call(service_instance)

    assert str(excinfo.value) == error_message
    # Ensure the handler was still called (or attempted to be called)
    mock_handler_a.assert_awaited_once_with(payload_in)


@pytest.mark.asyncio
async def test_call_different_services(
    controller: ServiceController, mock_handler_a: AsyncMock, mock_handler_b: AsyncMock
) -> None:
    """Test calling different services routed to their respective handlers."""
    payload_a = "service_a_payload"
    result_a = 999
    mock_handler_a.return_value = result_a

    payload_b = {"id": 1, "active": False}
    result_b = False
    mock_handler_b.return_value = result_b

    controller.add_handler(ServiceA, mock_handler_a)
    controller.add_handler(ServiceB, mock_handler_b)

    service_a_instance = ServiceA(payload=payload_a)
    service_b_instance = ServiceB(payload=payload_b)

    # Call A
    actual_result_a = await controller.call(service_a_instance)
    assert actual_result_a == result_a
    mock_handler_a.assert_awaited_once_with(payload_a)
    mock_handler_b.assert_not_awaited()  # Ensure B wasn't called

    # Call B
    actual_result_b = await controller.call(service_b_instance)
    assert actual_result_b == result_b
    mock_handler_b.assert_awaited_once_with(payload_b)
    # Ensure A wasn't called again
    assert mock_handler_a.await_count == 1


@pytest.mark.asyncio
async def test_call_with_none_payload(controller: ServiceController) -> None:
    """Test calling a service where the payload type hint is None."""
    # Define a handler specifically for ServiceC
    mock_handler_c = AsyncMock(return_value="Processed None")
    controller.add_handler(ServiceC, mock_handler_c)

    # ServiceC expects None as payload according to its type hint
    service_instance = ServiceC(payload=None)

    result = await controller.call(service_instance)

    assert result == "Processed None"
    mock_handler_c.assert_awaited_once_with(None)  # Handler receives None
