from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from common.base_model import BaseService

    from .controller import ServiceController


class ServiceCaller:
    def __init__(self, controller: ServiceController) -> None:
        self._controller = controller

    async def call[Tin, Tout](self, service: BaseService[Tin, Tout]) -> Tout:
        return await self._controller.call(service)
