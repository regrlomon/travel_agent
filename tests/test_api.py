import pytest, json
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient


@pytest.fixture
def mock_redis_instance():
    return MagicMock()


@pytest.fixture
def client(mock_redis_instance):
    with patch("api.main._redis", mock_redis_instance), \
         patch("api.main.run_plan") as mock_task:
        mock_task.delay = MagicMock()
        from api.main import app
        yield TestClient(app), mock_task


def test_post_plans_queues_celery_task(client):
    test_client, mock_task = client
    resp = test_client.post("/plans", json={
        "destination": "川西",
        "origin": "苏州",
        "duration_days": 7,
    })
    assert resp.status_code == 202
    assert "job_id" in resp.json()
    mock_task.delay.assert_called_once()


def test_get_state_returns_last_stream_entry(client, mock_redis_instance):
    test_client, _ = client
    payload = {"type": "hitl_request", "interrupt_id": "iid-1", "data": {}}
    mock_redis_instance.xrevrange.return_value = [
        (b"1234-0", {b"data": json.dumps(payload).encode()})
    ]
    resp = test_client.get("/plans/test-job/state")
    assert resp.status_code == 200
    assert resp.json()["type"] == "hitl_request"


def test_get_state_404_when_no_stream(client, mock_redis_instance):
    test_client, _ = client
    mock_redis_instance.xrevrange.return_value = []
    resp = test_client.get("/plans/missing-job/state")
    assert resp.status_code == 404
