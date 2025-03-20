from __future__ import annotations

import asyncio
import contextlib
from typing import Protocol, overload


class Process(Protocol):
    async def run(self) -> None: ...
    async def close(self) -> None: ...


class ProcessManager[T: Process]:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._running_service: T | None = None
        self._running_task: asyncio.Task[None] | None = None

    async def get(self) -> T | None:
        async with self._lock:
            return self._running_service

    async def update(self, service: T | None) -> None:
        if service is None:
            await self._swap_run_task(None, None)
        else:
            await self._swap_run_task(service, asyncio.create_task(service.run()))

    async def store(self, service: T, task: asyncio.Task[None]) -> None:
        await self._swap_run_task(service, task)

    @overload
    async def _swap_run_task(self, running_service: T, running_task: asyncio.Task[None]) -> None: ...

    @overload
    async def _swap_run_task(self, running_service: None, running_task: None) -> None: ...

    async def _swap_run_task(self, running_service: T | None, running_task: asyncio.Task[None] | None) -> None:
        async with self._lock:
            running_task, self._running_task = self._running_task, running_task
            running_service, self._running_service = self._running_service, running_service

        if running_task is None or running_service is None:
            return

        await running_service.close()
        with contextlib.suppress(Exception):
            await running_task
