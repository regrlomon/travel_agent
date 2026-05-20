import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import date


@pytest.fixture
def mock_redis(mocker):
    r = MagicMock()
    r.get = MagicMock(return_value=None)
    r.set = MagicMock()
    r.setex = MagicMock()
    mocker.patch("redis.from_url", return_value=r)
    return r


@pytest.fixture
def mock_litellm(mocker):
    mock = AsyncMock()
    mock.return_value.choices[0].message.content = '{"result": "mocked"}'
    mocker.patch("litellm.acompletion", mock)
    return mock


@pytest.fixture
def sample_state():
    return {
        "job_id": "test-job",
        "destination": "川西",
        "origin": "苏州",
        "duration_days": 7,
        "travelers": 2,
        "transport_mode": "self_drive",
        "difficulty_level": "medium",
        "interests": ["徒步", "摄影"],
        "errors": [],
        "warnings": [],
    }

