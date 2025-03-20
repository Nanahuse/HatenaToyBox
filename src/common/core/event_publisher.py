from __future__ import annotations

from typing import TYPE_CHECKING

from common.base_model import BaseEvent

if TYPE_CHECKING:
    from .controller import EventController


class EventPublisher:
    def __init__(self, controller: EventController) -> None:
        self._controller = controller

    async def publish(self, event: BaseEvent) -> None:
        if not isinstance(event, BaseEvent):
            return
        await self._controller.publish(event)

    def publish_nowait(self, event: BaseEvent) -> None:
        if not isinstance(event, BaseEvent):
            return
        self._controller.publish_nowait(event)
