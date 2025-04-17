import asyncio
import contextlib
from unittest.mock import AsyncMock, call  # Use AsyncMock for async handlers

import pytest
import pytest_asyncio

from common.base_model import BaseEvent
from common.core.controller.event_controller import EventController


class Event(BaseEvent):
    payload: str | None = None


# Define specific event types for testing
class EventA(Event):
    pass


class EventB(Event):
    pass


# --- Fixtures ---


@pytest_asyncio.fixture
async def controller() -> EventController:
    """Provides a fresh EventController instance for each test."""
    return EventController()


@pytest_asyncio.fixture
async def mock_handler_a() -> AsyncMock:
    """Provides an AsyncMock for an event handler."""
    return AsyncMock()


@pytest_asyncio.fixture
async def mock_handler_b() -> AsyncMock:
    """Provides another AsyncMock for an event handler."""
    return AsyncMock()


# --- Test Cases ---


@pytest.mark.asyncio
async def test_initialization(controller: EventController) -> None:
    """Test that the controller initializes with an empty queue and handlers."""
    assert isinstance(controller._queue, asyncio.Queue)
    assert controller._queue.empty()
    assert controller._handlers == {}
    # Check if logger is initialized (inherited from BaseController)
    assert hasattr(controller, "logger")
    assert controller.logger.name == "Core.EventController"


@pytest.mark.asyncio
async def test_add_handler_single(controller: EventController, mock_handler_a: AsyncMock) -> None:
    """Test adding a single handler for an event type."""
    controller.add_handler(EventA, mock_handler_a)
    assert EventA in controller._handlers
    assert controller._handlers[EventA] == [mock_handler_a]
    assert EventB not in controller._handlers


@pytest.mark.asyncio
async def test_add_handler_multiple_same_type(
    controller: EventController, mock_handler_a: AsyncMock, mock_handler_b: AsyncMock
) -> None:
    """Test adding multiple handlers for the same event type."""
    handler1 = mock_handler_a
    handler2 = mock_handler_b  # Re-using mock fixture for simplicity, it's a distinct mock instance

    controller.add_handler(EventA, handler1)
    controller.add_handler(EventA, handler2)

    assert EventA in controller._handlers
    assert controller._handlers[EventA] == [handler1, handler2]
    assert len(controller._handlers[EventA]) == 2


@pytest.mark.asyncio
async def test_add_handler_multiple_different_types(
    controller: EventController, mock_handler_a: AsyncMock, mock_handler_b: AsyncMock
) -> None:
    """Test adding handlers for different event types."""
    controller.add_handler(EventA, mock_handler_a)
    controller.add_handler(EventB, mock_handler_b)

    assert EventA in controller._handlers
    assert controller._handlers[EventA] == [mock_handler_a]
    assert EventB in controller._handlers
    assert controller._handlers[EventB] == [mock_handler_b]
    assert len(controller._handlers) == 2


@pytest.mark.asyncio
async def test_publish(controller: EventController) -> None:
    """Test the async publish method."""
    event = EventA(payload="data_async")
    assert controller._queue.empty()
    await controller.publish(event)
    assert not controller._queue.empty()
    assert controller._queue.qsize() == 1
    retrieved_event = await controller._queue.get()
    assert retrieved_event == event
    assert controller._queue.empty()


@pytest.mark.asyncio
async def test_publish_nowait(controller: EventController) -> None:
    """Test the non-blocking publish_nowait method."""
    event = EventB(payload="data_sync")
    assert controller._queue.empty()
    controller.publish_nowait(event)
    assert not controller._queue.empty()
    assert controller._queue.qsize() == 1
    retrieved_event = controller._queue.get_nowait()
    assert retrieved_event == event
    assert controller._queue.empty()


@pytest.mark.asyncio
async def test_run_no_handlers(controller: EventController) -> None:
    """Test run processes an event with no registered handlers without error."""
    event = EventA(payload="test")
    await controller.publish(event)
    # Add a sentinel event to stop the loop gracefully
    sentinel = EventB(payload="STOP")
    await controller.publish(sentinel)

    processed_events = []

    async def run_wrapper() -> None:
        while True:
            evt = await controller._queue.get()
            processed_events.append(evt)  # Simulate processing outside run
            controller.logger.debug("Wrapper got %s", type(evt).__name__)  # Simulate logging
            if evt == sentinel:
                controller.logger.debug("Wrapper stopping on sentinel")
                controller._queue.task_done()  # Mark sentinel as done
                break
            # Simulate the check inside run() - no handlers, so just mark done
            if type(evt) not in controller._handlers:
                controller.logger.debug("Wrapper found no handler for %s", type(evt).__name__)
            controller._queue.task_done()  # Mark event as done

    # We don't run controller.run() directly as it's an infinite loop.
    # Instead, we simulate its core logic by consuming the queue.
    run_task = asyncio.create_task(run_wrapper())

    # Wait for the queue to be processed
    await asyncio.wait_for(controller._queue.join(), timeout=1.0)
    run_task.cancel()  # Cancel the wrapper task
    with contextlib.suppress(asyncio.CancelledError):
        await run_task

    assert processed_events == [event, sentinel]  # Ensure both were dequeued
    # No handlers were added, so no mocks to check


@pytest.mark.asyncio
async def test_run_single_handler(controller: EventController, mock_handler_a: AsyncMock) -> None:
    """Test run calls the correct single handler for an event."""
    event_a = EventA(payload="payload_a")
    controller.add_handler(EventA, mock_handler_a)

    # Start controller run in the background
    run_task = asyncio.create_task(controller.run())

    # Publish the event
    await controller.publish(event_a)

    # Give the loop time to process the event
    await asyncio.sleep(0.01)  # Small delay

    # Assertions
    mock_handler_a.assert_awaited_once_with(event_a)
    assert controller._queue.empty()  # Event should be consumed

    # Clean up the run task
    run_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await run_task


@pytest.mark.asyncio
async def test_run_multiple_handlers_same_event(
    controller: EventController, mock_handler_a: AsyncMock, mock_handler_b: AsyncMock
) -> None:
    """Test run calls all registered handlers for an event."""
    handler1 = mock_handler_a
    handler2 = mock_handler_b  # Distinct mock instance
    event_a = EventA(payload="payload_multi")

    controller.add_handler(EventA, handler1)
    controller.add_handler(EventA, handler2)

    run_task = asyncio.create_task(controller.run())
    await controller.publish(event_a)
    await asyncio.sleep(0.01)

    handler1.assert_awaited_once_with(event_a)
    handler2.assert_awaited_once_with(event_a)
    assert controller._queue.empty()

    run_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await run_task


@pytest.mark.asyncio
async def test_run_multiple_events_different_handlers(
    controller: EventController, mock_handler_a: AsyncMock, mock_handler_b: AsyncMock
) -> None:
    """Test run calls the correct handlers for different event types."""
    event_a = EventA(payload="payload_a_diff")
    event_b = EventB(payload="payload_b_diff")

    controller.add_handler(EventA, mock_handler_a)
    controller.add_handler(EventB, mock_handler_b)

    run_task = asyncio.create_task(controller.run())

    # Publish events (order might matter for timing, but handlers should be correct)
    await controller.publish(event_a)
    await controller.publish(event_b)

    # Wait long enough for both events to be processed
    await asyncio.sleep(0.02)

    mock_handler_a.assert_awaited_once_with(event_a)
    mock_handler_b.assert_awaited_once_with(event_b)
    mock_handler_a.assert_has_awaits([call(event_a)])  # More explicit check
    mock_handler_b.assert_has_awaits([call(event_b)])
    assert controller._queue.empty()

    run_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await run_task


@pytest.mark.asyncio
async def test_run_event_with_no_matching_handler(controller: EventController, mock_handler_a: AsyncMock) -> None:
    """Test run processes an event when handlers exist, but not for this event type."""
    event_a = EventA(payload="payload_a_match")
    event_b = EventB(payload="payload_b_no_match")

    controller.add_handler(EventA, mock_handler_a)  # Only handler for EventA

    run_task = asyncio.create_task(controller.run())

    await controller.publish(event_b)  # Publish event with no handler
    await controller.publish(event_a)

    try:
        # mock_handler_a
        async def wait_for_handler_a_call() -> None:
            while not mock_handler_a.called:  # noqa: ASYNC110
                await asyncio.sleep(0.01)

        await asyncio.wait_for(wait_for_handler_a_call(), timeout=5.0)
    except TimeoutError:
        pytest.fail("Timed out waiting for mock_handler_a to be called.")

    # Handler for A should be called only once with event_a
    # No handler for B, so no calls expected related to it
    mock_handler_a.assert_awaited_once_with(event_a)

    assert controller._queue.empty()  # Both events should be consumed

    run_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await run_task
