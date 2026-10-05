from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class TaskRequest(BaseModel):
    calculation: Literal["add", "subtract", "multiply", "divide"]
    parameters: list[float] = Field(min_length=2)
    data: dict[str, Any] = Field(default_factory=dict)
    image: str = "tp2-task-service:latest"
    task_id: UUID = Field(default_factory=uuid4)
    lamport_timestamp: int = Field(default=0, ge=0)


class TaskResponse(BaseModel):
    task_id: UUID
    result: Any
    node_id: int
    lamport_timestamp: int
    duration_ms: float


class HealthResponse(BaseModel):
    service: str
    status: str
    node_id: int
    leader_id: int | None
    queue_size: int
    active_workers: int
