import pytest
from datetime import datetime
from unittest.mock import AsyncMock
from agent.nodes.plan_itinerary import run, _build_poi_table, _build_flight_table


def make_poi(poi_id, name, confidence="high", tags=None):
    from models import POI
    return POI(poi_id=poi_id, name=name, coords=(28.0, 100.0), category="自然景观",
               tags=tags or [], desc="", amap_rating=4.5, sources=[],
               mention_count=3, platform_count=2, confidence=confidence)


def make_pair(pair_id):
    from models import Flight, FlightPair
    out = Flight("携程", "PVG", "DCY", 980, "MU1", datetime(2026, 7, 1))
    ret = Flight("携程", "CTU", "PVG", 760, "CA1", datetime(2026, 7, 8))
    return FlightPair(pair_id, out, ret, 1740)


def test_build_poi_table():
    pois = [make_poi("p1", "稻城亚丁", tags=["自然风光"]), make_poi("p2", "四姑娘山", tags=["徒步"])]
    table = _build_poi_table(pois)
    assert "p1" in table
    assert "稻城亚丁" in table
    assert "自然风光" in table


def test_build_flight_table():
    pairs = [make_pair("uuid-1")]
    table = _build_flight_table(pairs)
    assert "uuid-1" in table
    assert "PVG" in table


@pytest.mark.asyncio
async def test_run_returns_itineraries(mocker):
    phase1_response = '''[
        {"plan_id": "A", "pair_id": "uuid-1", "days": [{"day": 1, "poi_ids": ["p1"]}, {"day": 2, "poi_ids": ["p2"]}]}
    ]'''
    phase2_response = '''{
        "option_id": "A",
        "summary": "DCY进CTU出7天",
        "days": [
            {"day": 1, "transport_note": "驾车55分钟", "estimated_travel_minutes": 55}
        ]
    }'''
    call_count = 0
    async def fake_llm(**kwargs):
        nonlocal call_count
        call_count += 1
        m = __import__("unittest.mock", fromlist=["MagicMock"]).MagicMock()
        m.choices[0].message.content = phase1_response if call_count == 1 else phase2_response
        return m

    mocker.patch("litellm.acompletion", side_effect=fake_llm)

    state = {
        "pois": [make_poi("p1", "稻城亚丁"), make_poi("p2", "四姑娘山")],
        "flight_pairs": [make_pair("uuid-1")],
        "travel_time_matrix": {"p1|p2": 30},
        "interests": ["徒步"],
        "duration_days": 7,
        "errors": [], "warnings": [], "job_id": "test",
    }
    result = await run(state)
    assert len(result["itineraries"]) >= 1
