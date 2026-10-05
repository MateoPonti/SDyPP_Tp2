from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(title="TP2 Task Service", version="0.1.0")


class TaskInput(BaseModel):
    calculation: str
    parameters: list[float] = Field(min_length=2)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"service": "task-service", "status": "ok"}


async def ejecutarTarea(task: TaskInput) -> dict[str, float | str]:
    if task.calculation == "add":
        result = sum(task.parameters)
    elif task.calculation == "subtract":
        result = task.parameters[0] - sum(task.parameters[1:])
    elif task.calculation == "multiply":
        result = 1.0
        for value in task.parameters:
            result *= value
    elif task.calculation == "divide":
        result = task.parameters[0]
        try:
            for value in task.parameters[1:]:
                result /= value
        except ZeroDivisionError as error:
            raise HTTPException(status_code=422, detail="division by zero") from error
    else:
        raise HTTPException(status_code=422, detail="unsupported calculation")
    return {"result": result}


@app.post("/execute")
async def execute(task: TaskInput) -> dict[str, float | str]:
    return await ejecutarTarea(task)
