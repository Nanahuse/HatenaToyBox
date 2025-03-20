import asyncio
import datetime
from collections.abc import Awaitable, Callable
from typing import Any

from .routine_manager import RoutineManager

class Routine:
    def start(self) -> asyncio.Task[None]: ...
    def stop(self) -> None: ...
    def cancel(self) -> None: ...
    def restart(self) -> None: ...
    def before_routine(self, coro: Callable[[Any], None]) -> None: ...
    def after_routine(self, coro: Callable[[Any], None]) -> None: ...
    def change_interval(
        self,
        *,
        seconds: float | None = 0,
        minutes: float | None = 0,
        hours: float | None = 0,
        time: datetime.datetime | None = None,
        wait_first: bool | None = False,
    ) -> None: ...
    def error(self, coro: Callable[[Exception], None]) -> None: ...
    async def on_error(self, error: Exception) -> None: ...
    @property
    def completed_iterations(self) -> int: ...
    @property
    def remaining_iterations(self) -> int | None: ...
    @property
    def start_time(self) -> datetime.datetime | None: ...

def routine(
    *,
    seconds: float | None = 0,
    minutes: float | None = 0,
    hours: float | None = 0,
    time: datetime.datetime | None = None,
    iterations: int | None = None,
    wait_first: bool | None = False,
) -> Callable[[Callable[[], Awaitable[None]]], Routine]: ...

__all__ = [
    "Routine",
    "RoutineManager",
    "routine",
]
