import asyncio
import time
from dataclasses import dataclass
from typing import Protocol

import httpx

from shared.models import TaskRequest


@dataclass
class ExecutionResult:
    result: object
    duration_ms: float


class TaskExecutor(Protocol):
    async def execute(self, task: TaskRequest) -> ExecutionResult: ...


class DockerTaskExecutor:
    def __init__(self, network: str, service_port: int, timeout: float) -> None:
        import docker

        self.network = network
        self.service_port = service_port
        self.timeout = timeout
        self.client = docker.from_env()

    async def execute(self, task: TaskRequest) -> ExecutionResult:
        started = time.perf_counter()
        container = await asyncio.to_thread(
            self.client.containers.run,
            task.image,
            detach=True,
            network=self.network,
            auto_remove=False,
        )
        try:
            container.reload()
            address = container.attrs["NetworkSettings"]["Networks"][self.network]["IPAddress"]
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"http://{address}:{self.service_port}/execute",
                    json=task.model_dump(mode="json"),
                )
                response.raise_for_status()
            return ExecutionResult(response.json()["result"], (time.perf_counter() - started) * 1000)
        finally:
            await asyncio.to_thread(container.remove, force=True)


class LocalTaskExecutor:
    async def execute(self, task: TaskRequest) -> ExecutionResult:
        started = time.perf_counter()
        if task.calculation == "add":
            result = sum(task.parameters)
        elif task.calculation == "subtract":
            result = task.parameters[0] - sum(task.parameters[1:])
        elif task.calculation == "multiply":
            result = 1
            for value in task.parameters:
                result *= value
        else:
            result = task.parameters[0]
            for value in task.parameters[1:]:
                result /= value
        return ExecutionResult(result, (time.perf_counter() - started) * 1000)
