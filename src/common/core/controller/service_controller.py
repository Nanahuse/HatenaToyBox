from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import TYPE_CHECKING, Any, TypeVar, cast

from . import exceptions
from .base_controller import BaseController

if TYPE_CHECKING:
    from common.base_model.base_service import BaseService

Tin = TypeVar("Tin")
Tout = TypeVar("Tout")

ServiceHandler = Callable[[Tin], Coroutine[Any, Any, Tout]]


class ServiceController(BaseController):
    def __init__(self) -> None:
        super().__init__()
        self._handlers: dict[type[BaseService[Any, Any]], ServiceHandler[Any, Any]] = {}

    def add_handler[Tin, Tout](
        self,
        service_type: type[BaseService[Tin, Tout]],
        handler: ServiceHandler[Tin, Tout],
    ) -> None:
        if service_type in self._handlers:
            raise exceptions.ServiceHandlerExistsError(service_type)

        self._handlers[service_type] = handler

    async def call[Tin, Tout](self, service: BaseService[Tin, Tout]) -> Tout:
        if type(service) not in self._handlers:
            msg = f"{service} was not handled."
            raise exceptions.ServiceNotHandledError(msg)

        handler = self._handlers[type(service)]
        result = await handler(service.payload)

        self.logger.debug("%s: %s | result: %s", type(service).__name__, str(service), result)

        return cast("Tout", result)
