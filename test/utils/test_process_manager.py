import asyncio

import pytest

from utils.process_manager import Process, ProcessManager


class MockProcess:
    def __init__(self) -> None:
        self.run_called = False
        self.close_called = False

    async def run(self) -> None:
        self.run_called = True

    async def close(self) -> None:
        self.close_called = True


@pytest.mark.asyncio
async def test_process_manager_get_none() -> None:
    manager = ProcessManager[MockProcess]()
    service = await manager.get()
    assert service is None


@pytest.mark.asyncio
async def test_process_manager_update_none() -> None:
    manager = ProcessManager[MockProcess]()
    await manager.update(None)
    service = await manager.get()
    assert service is None


@pytest.mark.asyncio
async def test_process_manager_update_and_get() -> None:
    manager = ProcessManager[MockProcess]()
    service = MockProcess()
    await manager.update(service)
    retrieved_service = await manager.get()
    assert retrieved_service is service
    assert service.run_called is False
    assert service.close_called is False


@pytest.mark.asyncio
async def test_process_manager_update_and_run() -> None:
    manager = ProcessManager[MockProcess]()
    service = MockProcess()
    await manager.update(service)
    await asyncio.sleep(0.1)  # Allow the task to start
    assert service.run_called is True
    assert service.close_called is False


@pytest.mark.asyncio
async def test_process_manager_update_twice() -> None:
    manager = ProcessManager[MockProcess]()
    service1 = MockProcess()
    await manager.update(service1)
    await asyncio.sleep(0.1)  # Allow the task to start
    service2 = MockProcess()
    await manager.update(service2)
    await asyncio.sleep(0.1)  # Allow the task to start
    assert service1.run_called is True
    assert service1.close_called is True
    assert service2.run_called is True
    assert service2.close_called is False
    retrieved_service = await manager.get()
    assert retrieved_service is service2


@pytest.mark.asyncio
async def test_process_manager_update_none_after_service() -> None:
    manager = ProcessManager[MockProcess]()
    service = MockProcess()
    await manager.update(service)
    await asyncio.sleep(0.1)  # Allow the task to start
    await manager.update(None)
    await asyncio.sleep(0.1)  # Allow the task to start
    assert service.run_called is True
    assert service.close_called is True
    retrieved_service = await manager.get()
    assert retrieved_service is None


@pytest.mark.asyncio
async def test_process_manager_store_and_get() -> None:
    manager = ProcessManager[MockProcess]()
    service = MockProcess()
    task = asyncio.create_task(service.run())
    await manager.store(service, task)
    retrieved_service = await manager.get()
    assert retrieved_service is service
    assert service.run_called is False
    assert service.close_called is False
    await asyncio.sleep(0.1)
    assert service.run_called is True


@pytest.mark.asyncio
async def test_process_manager_store_and_update() -> None:
    manager = ProcessManager[MockProcess]()
    service1 = MockProcess()
    task1 = asyncio.create_task(service1.run())
    await manager.store(service1, task1)
    await asyncio.sleep(0.1)
    service2 = MockProcess()
    await manager.update(service2)
    await asyncio.sleep(0.1)
    assert service1.run_called is True
    assert service1.close_called is True
    assert service2.run_called is True
    assert service2.close_called is False
    retrieved_service = await manager.get()
    assert retrieved_service is service2


@pytest.mark.asyncio
async def test_process_manager_task_exception() -> None:
    class ExceptionProcess(Process):
        async def run(self) -> None:
            msg = "Test Exception"
            raise ValueError(msg)

        async def close(self) -> None:
            pass

    manager = ProcessManager[ExceptionProcess]()
    service = ExceptionProcess()
    await manager.update(service)
    await asyncio.sleep(0.1)

    retrieved_service = await manager.get()
    assert retrieved_service is service
