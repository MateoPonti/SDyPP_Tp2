import asyncio

from hit1.executor import ExecutionResult
from hit2.pool import WorkerPool
from shared.models import TaskRequest


class SlowExecutor:
    def __init__(self) -> None:
        self.active = 0
        self.maximum_active = 0

    async def execute(self, task: TaskRequest) -> ExecutionResult:
        self.active += 1
        self.maximum_active = max(self.maximum_active, self.active)
        await asyncio.sleep(0.01)
        self.active -= 1
        return ExecutionResult(task.parameters[0], 10)


def test_pool_limits_concurrent_tasks_and_returns_results() -> None:
    async def scenario() -> None:
        executor = SlowExecutor()
        pool = WorkerPool(executor, worker_count=2)
        await pool.start()
        try:
            tasks = [TaskRequest(calculation="add", parameters=[value, 0]) for value in range(5)]
            results = await asyncio.gather(*(pool.submit(task) for task in tasks))
            assert [result.result for result in results] == list(range(5))
            assert executor.maximum_active == 2
        finally:
            await pool.stop()

    asyncio.run(scenario())
