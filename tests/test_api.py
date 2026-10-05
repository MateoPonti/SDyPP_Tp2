from fastapi.testclient import TestClient

from hit2.server import app


def test_health_and_remote_task_endpoint() -> None:
    with TestClient(app) as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["status"] == "ok"

        response = client.post(
            "/getRemoteTask",
            json={
                "calculation": "multiply",
                "parameters": [3, 4],
                "lamport_timestamp": 5,
            },
        )
        assert response.status_code == 200
        assert response.json()["result"] == 12
        assert response.json()["lamport_timestamp"] >= 6
