"""Bully leader election using ELECTION, OK, and COORDINATOR messages."""

import asyncio
import logging
import time
from typing import Awaitable, Callable

import httpx

logger = logging.getLogger(__name__)

Transport = Callable[[str, str, dict], Awaitable[dict | None]]


def parse_peers(raw: str) -> dict[int, str]:
    peers: dict[int, str] = {}
    for item in raw.split(","):
        if item.strip():
            node_id, url = item.strip().split("=", 1)
            peers[int(node_id)] = url.rstrip("/")
    return peers


async def http_transport(url: str, path: str, params: dict, timeout: float = 1.0) -> dict | None:
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            method = client.get if path == "/health" else client.post
            response = await method(f"{url}{path}", params=params)
            response.raise_for_status()
            return response.json()
    except (httpx.HTTPError, ValueError):
        return None


class BullyCoordinator:
    def __init__(
        self,
        node_id: int,
        peers: dict[int, str],
        transport: Transport = http_transport,
        heartbeat_interval: float = 1.0,
        coordinator_wait: float = 1.5,
        startup_delay: float = 1.0,
    ) -> None:
        self.node_id = node_id
        self.peers = peers
        self.transport = transport
        self.heartbeat_interval = heartbeat_interval
        self.coordinator_wait = coordinator_wait
        self.startup_delay = startup_delay
        self.leader_id: int | None = None
        self.last_election_ms: float | None = None
        self.last_failover_ms: float | None = None
        self._failover_started_at: float | None = None
        self.elections_started = 0
        self._electing = False
        self._coordinator_event = asyncio.Event()
        self._tasks: set[asyncio.Task[None]] = set()

    @property
    def is_leader(self) -> bool:
        return self.leader_id == self.node_id

    async def start(self) -> None:
        self._spawn(self._boot())

    async def _boot(self) -> None:
        if self.startup_delay:
            await asyncio.sleep(self.startup_delay)
        await self.start_election()
        await self._heartbeat_loop()

    async def stop(self) -> None:
        tasks = list(self._tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    def _spawn(self, coro: Awaitable[None]) -> None:
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def start_election(self) -> None:
        if self._electing:
            return
        self._electing = True
        started = time.perf_counter()
        self.elections_started += 1
        try:
            while True:
                self._coordinator_event.clear()
                higher_peers = {
                    node_id: url for node_id, url in self.peers.items() if node_id > self.node_id
                }
                replies = await asyncio.gather(
                    *(
                        self.transport(url, "/cluster/election", {"candidate_id": self.node_id})
                        for url in higher_peers.values()
                    )
                )
                if not any(reply is not None for reply in replies):
                    await self._become_leader()
                    break
                try:
                    await asyncio.wait_for(self._coordinator_event.wait(), self.coordinator_wait)
                    break
                except asyncio.TimeoutError:
                    logger.warning("node=%s has no COORDINATOR; retrying election", self.node_id)
        finally:
            self.last_election_ms = (time.perf_counter() - started) * 1000
            self._electing = False

    async def _become_leader(self) -> None:
        self.leader_id = self.node_id
        logger.info("node=%s became coordinator", self.node_id)
        await asyncio.gather(
            *(
                self.transport(url, "/cluster/coordinator", {"leader_id": self.node_id})
                for url in self.peers.values()
            )
        )
        self._record_failover()

    async def handle_election(self, candidate_id: int) -> dict[str, int | str]:
        if candidate_id < self.node_id:
            self._spawn(self.start_election())
            return {"status": "OK", "node_id": self.node_id}
        return {"status": "IGNORED", "node_id": self.node_id}

    async def handle_coordinator(self, leader_id: int) -> dict[str, int | str]:
        if leader_id < self.node_id:
            self._spawn(self.start_election())
            return {"status": "REJECTED", "node_id": self.node_id}
        self.leader_id = leader_id
        self._coordinator_event.set()
        self._record_failover()
        logger.info("node=%s accepted coordinator=%s", self.node_id, leader_id)
        return {"status": "ACK", "leader_id": leader_id}

    def _record_failover(self) -> None:
        if self._failover_started_at is not None:
            self.last_failover_ms = (time.perf_counter() - self._failover_started_at) * 1000
            self._failover_started_at = None

    async def _heartbeat_loop(self) -> None:
        while True:
            await asyncio.sleep(self.heartbeat_interval)
            if self.leader_id is None:
                await self.start_election()
            elif not self.is_leader:
                leader_url = self.peers.get(self.leader_id)
                if leader_url is None or await self.transport(leader_url, "/health", {}) is None:
                    logger.warning(
                        "node=%s detected unavailable coordinator=%s",
                        self.node_id,
                        self.leader_id,
                    )
                    if self._failover_started_at is None:
                        self._failover_started_at = time.perf_counter()
                    self.leader_id = None
                    await self.start_election()
