import pytest
from unittest.mock import AsyncMock, MagicMock
from tools.airports import AirportsClient, AIRPORT_MAP


def test_static_lookup_suzhou():
    client = AirportsClient()
    result = client._static_lookup("苏州")
    assert result == ["SHA"]


def test_static_lookup_beijing():
    client = AirportsClient()
    result = client._static_lookup("北京")
    assert "BJS" in result


def test_static_lookup_unknown_returns_empty():
    client = AirportsClient()
    result = client._static_lookup("某个不存在的城市xyz")
    assert result == []


@pytest.mark.asyncio
async def test_lookup_uses_static_for_known_city():
    client = AirportsClient()
    result = await client.lookup("上海")
    assert "SHA" in result


@pytest.mark.asyncio
async def test_lookup_llm_fallback_for_unknown(mocker):
    mock_msg = MagicMock()
    mock_msg.content = '["XYZ"]'
    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value=mock_msg)
    mocker.patch("tools.airports.get_llm", return_value=mock_llm)

    client = AirportsClient()
    result = await client.lookup("某小城市")
    assert result == ["XYZ"]
