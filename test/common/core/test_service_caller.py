from typing import Any
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

from common.base_model import BaseService

# Import the class to be tested
from common.core.service_caller import ServiceCaller


# Define specific service types for testing
class MyService(BaseService[str, int]):
    pass


class AnotherService(BaseService[dict[str, int], bool]):
    pass


# Mock ServiceController - we only need its 'call' method mocked
class MockServiceController:
    def __init__(self) -> None:
        # The 'call' method is async, so use AsyncMock
        self.call = AsyncMock(name="ServiceController.call")


# --- Fixtures ---


@pytest_asyncio.fixture
async def mock_controller() -> MockServiceController:
    """Provides a mock ServiceController instance."""
    return MockServiceController()


@pytest_asyncio.fixture
async def caller(mock_controller: MockServiceController) -> ServiceCaller:
    """Provides a ServiceCaller instance initialized with the mock controller."""
    # We need to cast because our MockServiceController isn't formally a ServiceController
    # In a real setup, you might mock the actual ServiceController class directly
    return ServiceCaller(controller=mock_controller)  # type: ignore[arg-type]


# --- Test Cases ---


def test_initialization(caller: ServiceCaller, mock_controller: MockServiceController) -> None:
    """Test that the caller stores the controller correctly."""
    assert caller._controller is mock_controller  # type: ignore[comparison-overlap]


@pytest.mark.asyncio
async def test_call_delegates_to_controller(caller: ServiceCaller, mock_controller: MockServiceController) -> None:
    """Test that ServiceCaller.call awaits and returns the result of controller.call."""
    # Arrange
    service_instance = MyService(payload="test_payload")
    expected_result = 123
    mock_controller.call.return_value = expected_result

    # Act
    result = await caller.call(service_instance)

    # Assert
    # 1. Check that the controller's call method was awaited exactly once
    mock_controller.call.assert_awaited_once()
    # 2. Check that it was called with the correct service instance
    mock_controller.call.assert_awaited_once_with(service_instance)
    # 3. Check that the result returned by the caller is the result from the controller
    assert result == expected_result


@pytest.mark.asyncio
async def test_call_propagates_controller_exception(
    caller: ServiceCaller, mock_controller: MockServiceController
) -> None:
    """Test that exceptions raised by controller.call are propagated by ServiceCaller.call."""
    # Arrange
    service_instance = AnotherService(payload={"data": True})
    error_message = "Something went wrong in the controller"
    expected_exception = ValueError(error_message)
    mock_controller.call.side_effect = expected_exception

    # Act & Assert
    with pytest.raises(ValueError, match=error_message) as excinfo:
        await caller.call(service_instance)

    # Check that the correct exception was raised
    assert excinfo.value is expected_exception
    # Check that the controller's call method was still awaited
    mock_controller.call.assert_awaited_once_with(service_instance)


@pytest.mark.asyncio
async def test_call_with_different_service_types(caller: ServiceCaller, mock_controller: MockServiceController) -> None:
    """Test calling with different service types works correctly."""
    # Arrange Service 1
    service1 = MyService(payload="service1")
    result1 = 1
    # Arrange Service 2
    service2 = AnotherService(payload={"id": 10})
    result2 = False

    # Configure mock to return different values based on input (optional, but good practice)
    async def side_effect_func(service_arg: Any) -> int | bool:  # noqa: ANN401
        if service_arg == service1:
            return result1
        if service_arg == service2:
            return result2
        msg = "Unexpected service type in mock"
        raise TypeError(msg)

    mock_controller.call.side_effect = side_effect_func

    # Act & Assert Service 1
    actual_result1 = await caller.call(service1)
    assert actual_result1 == result1
    mock_controller.call.assert_awaited_with(service1)  # Check last await
    assert mock_controller.call.await_count == 1

    # Act & Assert Service 2
    actual_result2 = await caller.call(service2)
    assert actual_result2 == result2
    mock_controller.call.assert_awaited_with(service2)  # Check last await
    assert mock_controller.call.await_count == 2
