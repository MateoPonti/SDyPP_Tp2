"""Coordinator-side task scheduling and best-effort node registry."""

import logging
from datetime import UTC, datetime
from typing import Awaitable, Callable

import httpx

from hit2.pool import WorkerPool
from shared.models import TaskRequest, TaskResponse

logger = logging.getLogger(__name__)

LocalTaskRunner = Callable[[TaskRequest], Awaitable[TaskResponse]]


class NodeTaskScheduler:
    def __init__(
        self,
        node_id: int,
        peer_urls: dict[int, str],
        pool: WorkerPool,
        timeout_seconds: float,
    ) -> None:
        self.node_id = node_id
        self.peer_urls = peer_urls
        self.pool = pool
        self.timeout_seconds = timeout_seconds
        self.node_registry: dict[int, dict[str, object]] = {}

    async def dispatch(self, task: TaskRequest, run_local: LocalTaskRunner) -> TaskResponse:
        candidates = await self.refresh_node_registry()
        candidates.sort(
            key=lambda node: (
                int(node["queue_size"]) + int(node["active_workers"]),
                int(node["node_id"]),
            )
        )

        last_error: Exception | None = None
        for candidate in candidates:
            node_id = int(candidate["node_id"])
            try:
                if node_id == self.node_id:
                    return await run_local(task)
                return await self._send_task(str(candidate["url"]), task)
            except Exception as error:
                last_error = error
                logger.warning("node=%s failed task=%s: %s", node_id, task.task_id, error)
                if node_id != self.node_id and isinstance(error, httpx.HTTPError):
                    self._mark_unavailable(node_id)

        raise RuntimeError("No available node could execute the task") from last_error

    async def refresh_node_registry(self) -> list[dict[str, object]]:
        now = datetime.now(UTC).isoformat()
        live: list[dict[str, object]] = []

        local = {
            "node_id": self.node_id,
            "status": "online",
            "queue_size": self.pool.queue_size,
            "active_workers": self.pool.active_workers,
            "last_seen": now,
            "last_checked": now,
            "url": None,
        }
        self.node_registry[self.node_id] = local.copy()
        live.append(local)

        async with httpx.AsyncClient(timeout=min(self.timeout_seconds, 2.0)) as client:
            for node_id, url in self.peer_urls.items():
                entry = self.node_registry.setdefault(
                    node_id,
                    {
                        "node_id": node_id,
                        "status": "unknown",
                        "queue_size": 0,
                        "active_workers": 0,
                        "last_seen": None,
                        "last_checked": None,
                        "url": url,
                    },
                )
                try:
                    response = await client.get(f"{url}/health")
                    response.raise_for_status()
                    health = response.json()
                    if int(health["node_id"]) != node_id:
                        raise ValueError(f"peer URL {url} returned unexpected node_id")
                    entry.update(
                        status="online",
                        queue_size=int(health["queue_size"]),
                        active_workers=int(health["active_workers"]),
                        last_seen=now,
                        last_checked=now,
                    )
                    live.append(
                        {
                            "node_id": node_id,
                            "queue_size": int(health["queue_size"]),
                            "active_workers": int(health["active_workers"]),
                            "url": url,
                        }
                    )
                except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
                    entry.update(status="offline", last_checked=now, error=str(error))
                    logger.warning("peer=%s unavailable during task scheduling: %s", node_id, error)
        return live

    async def _send_task(self, url: str, task: TaskRequest) -> TaskResponse:
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(
                f"{url}/cluster/execute",
                json=task.model_dump(mode="json"),
            )
            response.raise_for_status()
            return TaskResponse.model_validate(response.json())

    def _mark_unavailable(self, node_id: int) -> None:
        entry = self.node_registry.get(node_id)
        if entry is not None:
            entry["status"] = "offline"

    def status_snapshot(self) -> list[dict[str, object]]:
        return [self.node_registry[node_id].copy() for node_id in sorted(self.node_registry)]
