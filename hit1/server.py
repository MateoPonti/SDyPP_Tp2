import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request

from hit1.executor import DockerTaskExecutor, LocalTaskExecutor
from shared.config import Settings
from shared.logging_config import configure_logging
from shared.models import HealthResponse, TaskRequest, TaskResponse

settings = Settings()
configure_logging(settings.log_file)
logger = logging.getLogger(__name__)
executor = LocalTaskExecutor() if settings.executor == "local" else DockerTaskExecutor(
	settings.task_network, settings.task_service_port, settings.task_timeout_seconds
)


@asynccontextmanager
async def lifespan(_: FastAPI):
	yield


app = FastAPI(title="TP2 Hit 1 - Remote Tasks", version="0.1.0", lifespan=lifespan)


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
	return HealthResponse(
		service="hit1-remote-task-server",
		status="ok",
		node_id=settings.node_id,
		leader_id=None,
		queue_size=0,
		active_workers=0,
	)


async def ejecutarTareaRemota(task: TaskRequest, request: Request) -> TaskResponse:
	started = time.perf_counter()
	try:
		execution = await executor.execute(task)
	except Exception as error:
		logger.exception("task=%s failed", task.task_id)
		raise HTTPException(status_code=502, detail=str(error)) from error
	logger.info(
		"hit=1 task=%s remote=%s elapsed_ms=%.2f",
		task.task_id,
		request.client.host if request.client else "unknown",
		(time.perf_counter() - started) * 1000,
	)
	return TaskResponse(
		task_id=task.task_id,
		result=execution.result,
		node_id=settings.node_id,
		lamport_timestamp=task.lamport_timestamp,
		duration_ms=execution.duration_ms,
	)


@app.post("/getRemoteTask", response_model=TaskResponse)
async def get_remote_task(task: TaskRequest, request: Request) -> TaskResponse:
	return await ejecutarTareaRemota(task, request)
