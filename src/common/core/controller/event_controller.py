from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from typing import Any, TypeVar

from common.base_model.base_event import BaseEvent

from .base_controller import BaseController

T = TypeVar("T", bound=BaseEvent)
EventHandler = Callable[[T], Coroutine[Any, Any, None]]


class EventController(BaseController):
    def __init__(self) -> None:
        super().__init__()
        self._queue: asyncio.Queue[BaseEvent] = asyncio.Queue()
        self._handlers: dict[type[BaseEvent], list[EventHandler[Any]]] = {}

    async def run(self) -> None:
        while True:
            event = await self._queue.get()

            self.logger.debug("%s: %s", type(event).__name__, str(event))

            if type(event) not in self._handlers:
                continue

            await asyncio.gather(*(handler(event) for handler in self._handlers[type(event)]))

    def add_handler[T: BaseEvent](self, event_type: type[T], handler: EventHandler[T]) -> None:
        self._handlers.setdefault(event_type, []).append(handler)

    async def publish(self, event: BaseEvent) -> None:
        await self._queue.put(event)

    def publish_nowait(self, event: BaseEvent) -> None:
        self._queue.put_nowait(event)
