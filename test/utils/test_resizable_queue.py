# ruff: noqa: PLR2004

import pytest


@pytest.mark.asyncio
async def test_change_maxsize() -> None:
    from utils.resizable_queue import ResizableQueue

    queue = ResizableQueue[int]()

    for i in range(10):
        await queue.put(i)

    assert queue.qsize() == 10

    queue.change_maxsize(5)

    assert queue.qsize() == 5

    for i in range(5):
        v = await queue.get()
        assert v == i
