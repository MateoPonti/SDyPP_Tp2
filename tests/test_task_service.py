from fastapi.testclient import TestClient

from hit1.task_service.main import app


def test_task_service_executes_arithmetic() -> None:
    with TestClient(app) as client:
        response = client.post("/execute", json={"calculation": "add", "parameters": [2, 5, 8]})
        assert response.status_code == 200
        assert response.json() == {"result": 15}


def test_task_service_rejects_division_by_zero() -> None:
    with TestClient(app) as client:
        response = client.post("/execute", json={"calculation": "divide", "parameters": [4, 0]})
        assert response.status_code == 422
