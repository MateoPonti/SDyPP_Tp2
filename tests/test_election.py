import asyncio

import pytest

from hit3.election import BullyCoordinator, parse_peers


async def wait_for(predicate, timeout: float = 2.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while not predicate():
        if asyncio.get_running_loop().time() >= deadline:
            raise AssertionError("Timed out waiting for cluster state")
        await asyncio.sleep(0.01)


class Cluster:
    """In-memory network for testing elections without Docker."""

    def __init__(self, node_ids: list[int], coordinator_delay: float = 0.0) -> None:
        self.alive = set(node_ids)
        self.urls = {node_id: f"n{node_id}" for node_id in node_ids}
        self.coordinator_delay = coordinator_delay
        self.nodes = {
            node_id: BullyCoordinator(
                node_id,
                {peer_id: self.urls[peer_id] for peer_id in node_ids if peer_id != node_id},
                self.send,
                heartbeat_interval=0.05,
                coordinator_wait=0.3,
                startup_delay=0,
            )
            for node_id in node_ids
        }

    async def send(self, url: str, path: str, params: dict) -> dict | None:
        node_id = int(url[1:])
        if node_id not in self.alive:
            return None
        node = self.nodes[node_id]
        if path == "/cluster/election":
            return await node.handle_election(params["candidate_id"])
        if path == "/cluster/coordinator":
            if self.coordinator_delay:
                await asyncio.sleep(self.coordinator_delay)
            return await node.handle_coordinator(params["leader_id"])
        return {"status": "ok"}

    async def start(self) -> None:
        for node in self.nodes.values():
            await node.start()

    async def stop(self) -> None:
        for node in self.nodes.values():
            await node.stop()


def test_parse_peers() -> None:
    assert parse_peers("2=http://a:1, 3=http://b:1/") == {
        2: "http://a:1",
        3: "http://b:1",
    }


@pytest.mark.asyncio
async def test_highest_id_wins_when_nodes_start_together() -> None:
    cluster = Cluster([1, 2, 3])
    await cluster.start()
    try:
        await wait_for(lambda: {node.leader_id for node in cluster.nodes.values()} == {3})
    finally:
        await cluster.stop()


@pytest.mark.asyncio
async def test_failover_records_time_and_elects_next_highest_node() -> None:
    cluster = Cluster([1, 2, 3], coordinator_delay=0.04)
    await cluster.start()
    try:
        await wait_for(lambda: {node.leader_id for node in cluster.nodes.values()} == {3})
        cluster.alive.discard(3)
        await wait_for(
            lambda: {cluster.nodes[1].leader_id, cluster.nodes[2].leader_id} == {2}
            and cluster.nodes[2].last_failover_ms is not None
        )
        assert cluster.nodes[2].last_failover_ms >= 35
    finally:
        await cluster.stop()


@pytest.mark.asyncio
async def test_returning_higher_id_node_takes_over() -> None:
    cluster = Cluster([1, 2, 3])
    cluster.alive.discard(3)
    await cluster.start()
    try:
        await wait_for(lambda: cluster.nodes[1].leader_id == cluster.nodes[2].leader_id == 2)
        cluster.alive.add(3)
        await cluster.nodes[3].start_election()
        await wait_for(lambda: cluster.nodes[1].leader_id == cluster.nodes[2].leader_id == 3)
    finally:
        await cluster.stop()


@pytest.mark.asyncio
async def test_coordinator_message_arriving_while_election_is_waiting_is_kept() -> None:
    candidate: BullyCoordinator
    calls = 0

    async def transport(url: str, path: str, params: dict) -> dict | None:
        nonlocal calls
        calls += 1
        await candidate.handle_coordinator(2)
        return {"status": "OK"}

    candidate = BullyCoordinator(
        1,
        {2: "n2"},
        transport,
        coordinator_wait=0.01,
        startup_delay=0,
    )
    await candidate.start_election()

    assert candidate.leader_id == 2
    assert calls == 1


@pytest.mark.asyncio
async def test_lower_id_coordinator_announcement_is_rejected() -> None:
    cluster = Cluster([1, 2])
    node = cluster.nodes[2]

    response = await node.handle_coordinator(1)

    assert response["status"] == "REJECTED"
    assert node.leader_id is None
    await node.stop()
