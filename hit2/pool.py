import asyncio
import logging
from dataclasses import dataclass

from hit1.executor import ExecutionResult, TaskExecutor
from shared.models import TaskRequest

logger = logging.getLogger(__name__)


@dataclass
class QueuedTask:
    request: TaskRequest
    future: asyncio.Future[ExecutionResult]


class WorkerPool:
    """Bounded FIFO pool: one Docker task per worker at a time."""

    def __init__(self, executor: TaskExecutor, worker_count: int) -> None:
        if worker_count < 1:
            raise ValueError("worker_count must be positive")
        self.executor = executor
        self.worker_count = worker_count
        self.queue: asyncio.Queue[QueuedTask] = asyncio.Queue()
        self._workers: list[asyncio.Task[None]] = []
        self._active = 0
        self._active_lock = asyncio.Lock()

    async def start(self) -> None:
        self._workers = [asyncio.create_task(self._worker(index)) for index in range(self.worker_count)]

    async def stop(self) -> None:
        for worker in self._workers:
            worker.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()

    async def submit(self, request: TaskRequest) -> ExecutionResult:
        loop = asyncio.get_running_loop()
        future: asyncio.Future[ExecutionResult] = loop.create_future()
        await self.queue.put(QueuedTask(request, future))
        return await future

    @property
    def queue_size(self) -> int:
        return self.queue.qsize()

    @property
    def active_workers(self) -> int:
        return self._active

    async def _worker(self, index: int) -> None:
        while True:
            item = await self.queue.get()
            async with self._active_lock:
                self._active += 1
            try:
                logger.info("hit=2 worker=%s task=%s started", index, item.request.task_id)
                if not item.future.cancelled():
                    item.future.set_result(await self.executor.execute(item.request))
            except Exception as error:
                if not item.future.cancelled():
                    item.future.set_exception(error)
                logger.exception("worker=%s task=%s failed", index, item.request.task_id)
            finally:
                async with self._active_lock:
                    self._active -= 1
                self.queue.task_done()
