import asyncio


class ResizableQueue[T](asyncio.Queue[T]):
    def change_maxsize(self, maxsize: int) -> None:
        """
        Change the maxsize of the queue.
        If qsize is greater than maxsize, pop the latest value until qsize equals maxsize.

        If maxsize is less than or equal to zero, the queue size is infinite.
        If it is an integer greater than 0, then "await put()" will block when the
        queue reaches maxsize, until an item is removed by get().
        """

        if maxsize > 0:
            while self.qsize() > maxsize:
                self._queue.pop()  # type: ignore[attr-defined]

        self._maxsize = maxsize
