import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request

from hit1.executor import DockerTaskExecutor, LocalTaskExecutor
from hit2.pool import WorkerPool
from shared.clock import LamportClock
from shared.config import Settings
from shared.logging_config import configure_logging
from shared.models import HealthResponse, TaskRequest, TaskResponse

settings = Settings()
configure_logging(settings.log_file)
logger = logging.getLogger(__name__)
clock = LamportClock()
executor = LocalTaskExecutor() if settings.executor == "local" else DockerTaskExecutor(
	settings.task_network, settings.task_service_port, settings.task_timeout_seconds
)
pool = WorkerPool(executor, settings.workers)


@asynccontextmanager
async def lifespan(_: FastAPI):
	await pool.start()
	yield
	await pool.stop()


app = FastAPI(title="TP2 Hit 2 - Concurrency", version="0.1.0", lifespan=lifespan)


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
	return HealthResponse(
		service="hit2-concurrent-task-server",
		status="ok",
		node_id=settings.node_id,
		leader_id=None,
		queue_size=pool.queue_size,
		active_workers=pool.active_workers,
	)


async def ejecutarTareaRemota(task: TaskRequest, request: Request) -> TaskResponse:
	received_timestamp = await clock.receive(task.lamport_timestamp)
	started = time.perf_counter()
	try:
		execution = await pool.submit(task)
	except Exception as error:
		logger.exception("task=%s failed", task.task_id)
		raise HTTPException(status_code=502, detail=str(error)) from error
	response_timestamp = await clock.tick()
	logger.info("hit=2 task=%s completed", task.task_id)
	return TaskResponse(
		task_id=task.task_id,
		result=execution.result,
		node_id=settings.node_id,
		lamport_timestamp=max(received_timestamp, response_timestamp),
		duration_ms=(time.perf_counter() - started) * 1000,
	)


@app.post("/getRemoteTask", response_model=TaskResponse)
async def get_remote_task(task: TaskRequest, request: Request) -> TaskResponse:
	return await ejecutarTareaRemota(task, request)
