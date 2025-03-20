from __future__ import annotations

from typing import TYPE_CHECKING

from .controller import EventController, EventHandler, ServiceController, ServiceHandler
from .event_publisher import EventPublisher
from .service_caller import ServiceCaller

if TYPE_CHECKING:
    from common.base_model import BaseEvent, BaseService


class Hub:
    def __init__(self) -> None:
        self._event_controller = EventController()
        self._service_controller = ServiceController()

    def create_publisher(self) -> EventPublisher:
        return EventPublisher(self._event_controller)

    def create_caller(self) -> ServiceCaller:
        return ServiceCaller(self._service_controller)

    def add_service_handler[Tin, Tout](
        self,
        service_type: type[BaseService[Tin, Tout]],
        handler: ServiceHandler[Tin, Tout],
    ) -> None:
        self._service_controller.add_handler(service_type, handler)

    def add_event_handler[T: BaseEvent](self, event_type: type[T], handler: EventHandler[T]) -> None:
        self._event_controller.add_handler(event_type, handler)

    async def run(self) -> None:
        await self._event_controller.run()
