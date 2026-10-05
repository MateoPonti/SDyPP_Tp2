import logging
import time
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException

from hit1.executor import DockerTaskExecutor, LocalTaskExecutor
from hit2.pool import WorkerPool
from hit3.election import BullyCoordinator, parse_peers
from hit3.scheduler import NodeTaskScheduler
from shared.clock import LamportClock
from shared.config import Settings
from shared.logging_config import configure_logging
from shared.models import HealthResponse, TaskRequest, TaskResponse

settings = Settings()
configure_logging(settings.log_file)
logger = logging.getLogger(__name__)
clock = LamportClock()
peer_urls = parse_peers(settings.peers)
coordinator = BullyCoordinator(
    settings.node_id,
    peer_urls,
    heartbeat_interval=settings.heartbeat_interval,
    startup_delay=settings.startup_delay,
)
executor = LocalTaskExecutor() if settings.executor == "local" else DockerTaskExecutor(
    settings.task_network, settings.task_service_port, settings.task_timeout_seconds
)
pool = WorkerPool(executor, settings.workers)
scheduler = NodeTaskScheduler(
    settings.node_id,
    peer_urls,
    pool,
    settings.task_timeout_seconds + 5,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await pool.start()
    await coordinator.start()
    yield
    await coordinator.stop()
    await pool.stop()


app = FastAPI(title="TP2 Hit 3 - Fault Tolerance", version="0.1.0", lifespan=lifespan)


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(
        service="hit3-coordinated-task-server",
        status="ok",
        node_id=settings.node_id,
        leader_id=coordinator.leader_id,
        queue_size=pool.queue_size,
        active_workers=pool.active_workers,
    )


async def ejecutarTareaEnEsteNodo(task: TaskRequest) -> TaskResponse:
    received_timestamp = await clock.receive(task.lamport_timestamp)
    started = time.perf_counter()
    try:
        execution = await pool.submit(task)
    except Exception as error:
        logger.exception("task=%s failed", task.task_id)
        raise HTTPException(status_code=502, detail=str(error)) from error
    response_timestamp = await clock.tick()
    logger.info("hit=3 node=%s task=%s completed locally", settings.node_id, task.task_id)
    return TaskResponse(
        task_id=task.task_id,
        result=execution.result,
        node_id=settings.node_id,
        lamport_timestamp=max(received_timestamp, response_timestamp),
        duration_ms=(time.perf_counter() - started) * 1000,
    )


async def dispatch_at_coordinator(task: TaskRequest) -> TaskResponse:
    if not coordinator.is_leader:
        raise HTTPException(status_code=503, detail="This node is not the elected coordinator")
    await clock.receive(task.lamport_timestamp)
    scheduled_task = task.model_copy(
        update={"lamport_timestamp": await clock.tick()}
    )
    try:
        return await scheduler.dispatch(scheduled_task, ejecutarTareaEnEsteNodo)
    except Exception as error:
        logger.exception("coordinator failed to dispatch task=%s", task.task_id)
        raise HTTPException(status_code=502, detail=str(error)) from error


async def forward_to_coordinator(task: TaskRequest) -> TaskResponse:
    leader_id = coordinator.leader_id
    if leader_id is None:
        raise HTTPException(status_code=503, detail="No coordinator is currently available")
    leader_url = peer_urls.get(leader_id)
    if leader_url is None:
        raise HTTPException(
            status_code=503,
            detail=f"Coordinator {leader_id} is not configured as a peer",
        )
    try:
        async with httpx.AsyncClient(timeout=settings.task_timeout_seconds + 5) as client:
            response = await client.post(
                f"{leader_url}/cluster/dispatch",
                json=task.model_dump(mode="json"),
            )
            response.raise_for_status()
            return TaskResponse.model_validate(response.json())
    except (httpx.HTTPError, ValueError) as error:
        logger.exception("failed to forward task=%s to coordinator=%s", task.task_id, leader_id)
        raise HTTPException(status_code=502, detail="Coordinator dispatch failed") from error


@app.post("/getRemoteTask", response_model=TaskResponse)
async def get_remote_task(task: TaskRequest) -> TaskResponse:
    if coordinator.is_leader:
        return await dispatch_at_coordinator(task)
    return await forward_to_coordinator(task)


@app.post("/cluster/dispatch", response_model=TaskResponse)
async def cluster_dispatch(task: TaskRequest) -> TaskResponse:
    return await dispatch_at_coordinator(task)


@app.post("/cluster/execute", response_model=TaskResponse)
async def cluster_execute(task: TaskRequest) -> TaskResponse:
    return await ejecutarTareaEnEsteNodo(task)


@app.post("/cluster/election")
async def election(candidate_id: int) -> dict[str, int | str]:
    return await coordinator.handle_election(candidate_id)


@app.post("/cluster/coordinator")
async def coordinator_message(leader_id: int) -> dict[str, int | str]:
    return await coordinator.handle_coordinator(leader_id)


@app.get("/cluster/status")
async def cluster_status() -> dict[str, object]:
    if coordinator.is_leader:
        await scheduler.refresh_node_registry()
    return {
        "node_id": settings.node_id,
        "leader_id": coordinator.leader_id,
        "last_election_ms": coordinator.last_election_ms,
        "last_failover_ms": coordinator.last_failover_ms,
        "nodes": scheduler.status_snapshot(),
    }
