FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml .
COPY shared ./shared
COPY hit1/task_service ./hit1/task_service
RUN pip install --no-cache-dir .

EXPOSE 8080
CMD ["uvicorn", "hit1.task_service.main:app", "--host", "0.0.0.0", "--port", "8080"]
