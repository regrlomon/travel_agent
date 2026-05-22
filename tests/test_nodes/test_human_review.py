import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime
from langchain_core.runnables import RunnableConfig
from models import Flight, FlightPair, POI


def _make_config():
    return RunnableConfig(configurable={"thread_id": "t1", "tools": {}})


def _make_state():
    out = Flight("ctrip", "PVG", "DCY", 980, "MU1", datetime(2026, 7, 1))
    ret = Flight("ctrip", "DCY", "PVG", 760, "CA1", datetime(2026, 7, 8))
    pair = FlightPair("uuid-1", out, ret, 1740)
    poi = POI("p1", "稻城亚丁", (28.67, 100.3), "自然", [], "desc", 4.9, [], 3, 2, "high")
    return {
        "flight_pairs": [pair],
        "pois": [poi],
        "errors": [], "warnings": [], "job_id": "test",
    }


@pytest.mark.asyncio
async def test_human_review_calls_interrupt(mocker):
    mock_interrupt = mocker.patch("agent.nodes.human_review.interrupt",
                                  return_value={"text": "选第一个航班"})
    mocker.patch("agent.nodes.human_review._parse_review_reply", new_callable=AsyncMock,
                 return_value={"flight_choice": "uuid-1", "poi_prefs": ""})

    from agent.nodes.human_review import run
    await run(_make_state(), _make_config())
    mock_interrupt.assert_called_once()
    call_data = mock_interrupt.call_args[0][0]
    assert call_data["type"] == "review_flights_pois"
    assert "flights_summary" in call_data
    assert "poi_summary" in call_data


@pytest.mark.asyncio
async def test_human_review_writes_state(mocker):
    mocker.patch("agent.nodes.human_review.interrupt", return_value={"text": "选便宜的"})
    mocker.patch("agent.nodes.human_review._parse_review_reply", new_callable=AsyncMock,
                 return_value={"flight_choice": "uuid-1", "poi_prefs": "不要太累的"})

    from agent.nodes.human_review import run
    result = await run(_make_state(), _make_config())
    assert result["user_flight_choice"] == "uuid-1"
    assert result["user_poi_prefs"] == "不要太累的"


def test_format_flights_returns_list():
    from agent.nodes.human_review import _format_flights
    out = Flight("ctrip", "PVG", "DCY", 980, "MU1", datetime(2026, 7, 1))
    ret = Flight("ctrip", "DCY", "PVG", 760, "CA1", datetime(2026, 7, 8))
    pair = FlightPair("uuid-1", out, ret, 1740)
    result = _format_flights([pair])
    assert len(result) == 1
    assert result[0]["pair_id"] == "uuid-1"
    assert result[0]["total_price"] == 1740
