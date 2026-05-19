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
    async def fake_completion(**kwargs):
        content = kwargs.get("_mock_content", '{"result": "mocked"}')
        m = MagicMock()
        m.choices[0].message.content = content
        return m
    mocker.patch("litellm.acompletion", side_effect=fake_completion)


@pytest.fixture
def sample_state():
    return {
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
