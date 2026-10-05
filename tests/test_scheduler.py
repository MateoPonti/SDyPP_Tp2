import httpx
import pytest

from hit1.executor import LocalTaskExecutor
from hit2.pool import WorkerPool
from hit3.scheduler import NodeTaskScheduler
from shared.models import TaskRequest, TaskResponse


class FakeScheduler(NodeTaskScheduler):
    def __init__(self) -> None:
        super().__init__(
            node_id=1,
            peer_urls={2: "http://node-2"},
            pool=WorkerPool(LocalTaskExecutor(), worker_count=1),
            timeout_seconds=1,
        )
        self.candidates = []
        self.remote_attempts = []

    async def refresh_node_registry(self) -> list[dict[str, object]]:
        self.node_registry = {
            int(node["node_id"]): dict(node)
            for node in self.candidates
        }
        return self.candidates

    async def _send_task(self, url: str, task: TaskRequest) -> TaskResponse:
        self.remote_attempts.append(url)
        if url == "http://node-2":
            raise httpx.ConnectError("node is unavailable")
        return TaskResponse(
            task_id=task.task_id,
            result=12,
            node_id=3,
            lamport_timestamp=task.lamport_timestamp + 1,
            duration_ms=3,
        )


@pytest.mark.asyncio
async def test_coordinator_dispatches_to_least_loaded_available_peer() -> None:
    scheduler = FakeScheduler()
    scheduler.candidates = [
        {"node_id": 1, "queue_size": 2, "active_workers": 1, "url": None},
        {"node_id": 2, "queue_size": 0, "active_workers": 0, "url": "http://node-2"},
        {"node_id": 3, "queue_size": 1, "active_workers": 0, "url": "http://node-3"},
    ]
    task = TaskRequest(calculation="multiply", parameters=[3, 4])
    local_calls = 0

    async def run_local(request: TaskRequest) -> TaskResponse:
        nonlocal local_calls
        local_calls += 1
        return TaskResponse(
            task_id=request.task_id,
            result=12,
            node_id=1,
            lamport_timestamp=request.lamport_timestamp + 1,
            duration_ms=1,
        )

    response = await scheduler.dispatch(task, run_local)

    assert response.node_id == 3
    assert scheduler.remote_attempts == ["http://node-2", "http://node-3"]
    assert scheduler.node_registry[2]["status"] == "offline"
    assert local_calls == 0


@pytest.mark.asyncio
async def test_coordinator_uses_local_worker_when_it_is_least_loaded() -> None:
    scheduler = FakeScheduler()
    scheduler.candidates = [
        {"node_id": 1, "queue_size": 0, "active_workers": 0, "url": None},
        {"node_id": 2, "queue_size": 1, "active_workers": 0, "url": "http://node-2"},
    ]
    task = TaskRequest(calculation="add", parameters=[2, 5])

    async def run_local(request: TaskRequest) -> TaskResponse:
        return TaskResponse(
            task_id=request.task_id,
            result=7,
            node_id=1,
            lamport_timestamp=request.lamport_timestamp + 1,
            duration_ms=1,
        )

    response = await scheduler.dispatch(task, run_local)

    assert response.result == 7
    assert response.node_id == 1
    assert scheduler.remote_attempts == []
