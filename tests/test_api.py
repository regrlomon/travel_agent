import pytest
import sys
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient


def test_post_plans_returns_job_id(mock_redis):
    # Fresh import for each test
    if "api.main" in sys.modules:
        del sys.modules["api.main"]
    from api.main import app

    client = TestClient(app)
    with patch("api.main.asyncio.create_task"):
        resp = client.post("/plans", json={
            "destination": "川西",
            "origin": "苏州",
            "duration_days": 7,
            "travelers": 2,
        })
    assert resp.status_code == 202
    assert "job_id" in resp.json()
    assert resp.json()["status"] == "pending"


def test_get_plans_pending(mock_redis):
    # Fresh import for each test
    if "api.main" in sys.modules:
        del sys.modules["api.main"]

    # Set mock return value BEFORE import
    mock_redis.get.return_value = b'{"status":"pending","progress":"parse_input: done"}'

    from api.main import app
    client = TestClient(app)
    resp = client.get("/plans/test-job-id")
    assert resp.status_code == 200
    assert resp.json()["status"] == "pending"


def test_get_plans_done(mock_redis):
    # Fresh import for each test
    if "api.main" in sys.modules:
        del sys.modules["api.main"]

    import json
    result = {"status": "done", "result": {"itineraries": [], "flights_comparison": []}}
    mock_redis.get.return_value = json.dumps(result).encode()

    from api.main import app
    client = TestClient(app)
    resp = client.get("/plans/test-job-id")
    assert resp.status_code == 200
    assert resp.json()["status"] == "done"


def test_get_plans_not_found(mock_redis):
    # Fresh import for each test
    if "api.main" in sys.modules:
        del sys.modules["api.main"]

    mock_redis.get.return_value = None

    from api.main import app
    client = TestClient(app)
    resp = client.get("/plans/nonexistent-id")
    assert resp.status_code == 404
