from __future__ import annotations

from typing import TYPE_CHECKING

from twitchio.ext import routines

if TYPE_CHECKING:
    import datetime
    from collections.abc import Awaitable, Callable


class RoutineManager:
    def __init__(self) -> None:
        self._routines: list[routines.Routine] = []

    def add(self, coro: Callable[[], Awaitable[None]], interval: datetime.timedelta) -> None:
        self._routines.append(routines.routine(seconds=interval.total_seconds())(coro))

    def start(self) -> None:
        for routine in self._routines:
            routine.start()

    def restart(self) -> None:
        for routine in self._routines:
            routine.restart()

    def clear(self) -> None:
        for routine in self._routines:
            routine.cancel()

        self._routines.clear()
