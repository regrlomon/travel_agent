import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from agent.nodes.plan_itinerary import run, _build_poi_table, _build_flight_table


def make_poi(poi_id, name, confidence="high", tags=None,
             mention_count=3, amap_rating=4.5, has_negative=False, warning=False):
    from models import POI
    return POI(poi_id=poi_id, name=name, coords=(28.0, 100.0), category="自然景观",
               tags=tags or [], desc="", amap_rating=amap_rating, sources=[],
               mention_count=mention_count, platform_count=2, confidence=confidence,
               has_negative=has_negative, warning=warning)


def make_pair(pair_id):
    from models import Flight, FlightPair
    out = Flight(platform="携程", depart_airport="PVG", arrive_airport="DCY", price=980, flight_no="MU1", depart_time=datetime(2026, 7, 1))
    ret = Flight(platform="携程", depart_airport="CTU", arrive_airport="PVG", price=760, flight_no="CA1", depart_time=datetime(2026, 7, 8))
    return FlightPair(pair_id=pair_id, outbound=out, return_flight=ret, total_price=1740)


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

    async def fake_ainvoke(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        m = MagicMock()
        m.content = phase1_response if call_count == 1 else phase2_response
        return m

    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(side_effect=fake_ainvoke)
    mocker.patch("agent.nodes.plan_itinerary.get_llm", return_value=mock_llm)

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


def test_build_poi_table_includes_mention_and_rating():
    from agent.nodes.plan_itinerary import _build_poi_table
    poi = make_poi("p1", "外滩", mention_count=15, amap_rating=4.8)
    table = _build_poi_table([poi])
    assert "15" in table
    assert "4.8" in table
    assert "confidence" not in table
    assert "region" not in table


def test_build_poi_table_shows_warning_emoji():
    from agent.nodes.plan_itinerary import _build_poi_table
    poi = make_poi("p1", "灵隐寺", warning=True)
    table = _build_poi_table([poi])
    assert "⚠️" in table


def test_preprocess_pois_niche_mode_filters_negative():
    from agent.nodes.plan_itinerary import _preprocess_pois
    p_ok = make_poi("p1", "断桥", has_negative=False)
    p_bad = make_poi("p2", "灵隐寺", has_negative=True)
    result = _preprocess_pois([p_ok, p_bad], interests=["小众", "安静"])
    names = [p.name for p in result]
    assert "断桥" in names
    assert "灵隐寺" not in names


def test_preprocess_pois_popular_mode_keeps_negative_with_warning():
    from agent.nodes.plan_itinerary import _preprocess_pois
    p_bad = make_poi("p1", "灵隐寺", has_negative=True)
    result = _preprocess_pois([p_bad], interests=["热门景点", "网红打卡"])
    assert len(result) == 1
    assert result[0].warning is True


def test_preprocess_pois_default_keeps_negative_with_warning():
    from agent.nodes.plan_itinerary import _preprocess_pois
    p_bad = make_poi("p1", "灵隐寺", has_negative=True)
    result = _preprocess_pois([p_bad], interests=["历史文化"])
    assert len(result) == 1
    assert result[0].warning is True


@pytest.mark.asyncio
async def test_run_filters_negative_pois_in_niche_mode(mocker):
    phase1_response = '[{"plan_id": "A", "pair_id": null, "days": [{"day": 1, "poi_ids": ["p1"]}]}]'
    phase2_response = '{"option_id": "A", "summary": "test", "days": [{"day": 1, "transport_note": "", "estimated_travel_minutes": 0}]}'
    call_count = 0

    async def fake_ainvoke(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        m = MagicMock()
        m.content = phase1_response if call_count == 1 else phase2_response
        return m

    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(side_effect=fake_ainvoke)
    mocker.patch("agent.nodes.plan_itinerary.get_llm", return_value=mock_llm)

    state = {
        "pois": [
            make_poi("p1", "断桥", has_negative=False),
            make_poi("p2", "灵隐寺", has_negative=True),
        ],
        "flight_pairs": [],
        "travel_time_matrix": {},
        "interests": ["小众", "安静"],
        "duration_days": 3,
        "errors": [], "warnings": [], "job_id": "test",
    }
    result = await run(state)
    first_call_prompt = mock_llm.ainvoke.call_args_list[0][0][0][0].content
    assert "灵隐寺" not in first_call_prompt
    assert "断桥" in first_call_prompt
