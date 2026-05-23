import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime
from langchain_core.runnables import RunnableConfig
from models import Flight, FlightPair, POI, DayPlan, ItineraryOption


def _make_config():
    return RunnableConfig(configurable={"thread_id": "t1", "tools": {}})


def _make_itinerary():
    """Create a sample ItineraryOption for testing."""
    out = Flight(platform="ctrip", depart_airport="PVG", arrive_airport="DCY", price=980, flight_no="MU1", depart_time=datetime(2026, 7, 1))
    ret = Flight(platform="ctrip", depart_airport="DCY", arrive_airport="PVG", price=760, flight_no="CA1", depart_time=datetime(2026, 7, 8))
    fp = FlightPair(pair_id="uuid-1", outbound=out, return_flight=ret, total_price=1740)

    poi1 = POI(poi_id="p1", name="稻城亚丁", coords=(28.67, 100.3), category="自然", tags=[], desc="desc", amap_rating=4.9, sources=[], mention_count=3, platform_count=2, confidence="high")
    poi2 = POI(poi_id="p2", name="贡嘎山", coords=(29.6, 101.8), category="自然", tags=[], desc="desc", amap_rating=4.8, sources=[], mention_count=5, platform_count=3, confidence="high")

    day1 = DayPlan(day=1, pois=[poi1], transport_note="飞行 + 休整", estimated_travel_minutes=0)
    day2 = DayPlan(day=2, pois=[poi2], transport_note="游览景区", estimated_travel_minutes=55)

    return ItineraryOption(
        option_id="A",
        summary="稻城亚丁深度游：7天",
        flights=fp,
        days=[day1, day2]
    )


def _make_state():
    return {
        "itineraries": [_make_itinerary()],
        "errors": [], "warnings": [], "job_id": "test",
    }


@pytest.mark.asyncio
async def test_human_review_calls_interrupt(mocker):
    mock_interrupt = mocker.patch("agent.nodes.human_review.interrupt",
                                  return_value={"text": "选A方案"})
    mocker.patch("agent.nodes.human_review._parse_user_reply", new_callable=AsyncMock,
                 return_value={"selected_option_id": "A", "adjustment_notes": ""})

    from agent.nodes.human_review import run
    await run(_make_state(), _make_config())
    mock_interrupt.assert_called_once()
    call_data = mock_interrupt.call_args[0][0]
    assert call_data["type"] == "review_plan"
    assert "plans" in call_data
    assert "message" in call_data


@pytest.mark.asyncio
async def test_human_review_writes_state(mocker):
    mocker.patch("agent.nodes.human_review.interrupt", return_value={"text": "选A"})
    mocker.patch("agent.nodes.human_review._parse_user_reply", new_callable=AsyncMock,
                 return_value={"selected_option_id": "A", "adjustment_notes": "多加景点"})

    from agent.nodes.human_review import run
    result = await run(_make_state(), _make_config())
    assert result["selected_option_id"] == "A"
    assert result["adjustment_notes"] == "多加景点"
    # Legacy fields should also be populated
    assert result["user_flight_choice"] == "A"
    assert result["user_poi_prefs"] == "多加景点"


def test_format_plans_for_display_returns_list():
    from agent.nodes.human_review import _format_plans_for_display
    itinerary = _make_itinerary()
    result = _format_plans_for_display([itinerary])
    assert len(result) == 1
    assert result[0]["option_id"] == "A"
    assert "flight" in result[0]
    assert "days" in result[0]
    assert "summary" in result[0]
