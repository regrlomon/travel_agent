import pytest
from datetime import date
from unittest.mock import AsyncMock, MagicMock
from langchain_core.runnables import RunnableConfig


def _make_config(mock_amap=None):
    amap = mock_amap or MagicMock()
    return RunnableConfig(configurable={"thread_id": "t1", "tools": {"amap": amap}})


def _base_state():
    return {
        "destination": "川西", "origin": "苏州", "duration_days": 7,
        "travelers": 2, "transport_mode": "self_drive",
        "difficulty_level": "medium", "interests": ["徒步"],
        "depart_date": None, "errors": [], "warnings": [], "job_id": "test",
    }


@pytest.mark.asyncio
async def test_parse_input_respects_existing_origin_airports(mocker):
    """Test that origin_airports from state (set by collect_intent) is respected."""
    mocker.patch("agent.nodes.parse_input._llm_parse_destination", new_callable=AsyncMock, return_value={
        "region": "甘孜州", "city_names": ["甘孜藏族自治州"],
        "destination_airports": ["CTU"], "origin_airports": ["PVG"],
    })
    mock_amap = MagicMock()
    mock_amap.get_district_codes = AsyncMock(return_value={"甘孜藏族自治州": "513300"})

    # origin_airports already set by collect_intent
    state = {**_base_state(), "origin_airports": ["PEK", "PKX"]}
    from agent.nodes.parse_input import run
    result = await run(state, _make_config(mock_amap))
    # Should use state's origin_airports, not LLM-parsed ones
    assert result["origin_airports"] == ["PEK", "PKX"]


@pytest.mark.asyncio
async def test_parse_input_fallback_to_static_lookup(mocker):
    """Test that _city_to_iata static lookup is used if origin_airports not in state."""
    mocker.patch("agent.nodes.parse_input._llm_parse_destination", new_callable=AsyncMock, return_value={
        "region": "甘孜州", "city_names": ["甘孜藏族自治州"],
        "destination_airports": ["CTU"],
    })
    mock_amap = MagicMock()
    mock_amap.get_district_codes = AsyncMock(return_value={"甘孜藏族自治州": "513300"})

    # origin "上海" is in CITY_CODES → ["SHA"]; no origin_airports in state
    state = {**_base_state(), "origin": "上海"}
    from agent.nodes.parse_input import run
    result = await run(state, _make_config(mock_amap))
    assert result["origin_airports"] == ["SHA"]


@pytest.mark.asyncio
async def test_parse_input_single_date(mocker):
    mocker.patch("agent.nodes.parse_input._llm_parse_destination", new_callable=AsyncMock, return_value={
        "region": "甘孜州", "city_names": ["甘孜藏族自治州"],
        "destination_airports": ["CTU"], "origin_airports": ["PVG"],
    })
    mock_amap = MagicMock()
    mock_amap.get_district_codes = AsyncMock(return_value={"甘孜藏族自治州": "513300"})

    state = {**_base_state(), "depart_date": "2026-07-01"}
    from agent.nodes.parse_input import run
    result = await run(state, _make_config(mock_amap))
    assert result["depart_dates"] == [date(2026, 7, 1)]


@pytest.mark.asyncio
async def test_run_does_not_return_search_keywords(mocker):
    mocker.patch(
        "agent.nodes.parse_input._llm_parse_destination",
        new_callable=AsyncMock,
        return_value={"region": "上海", "city_names": ["上海市"]},
    )
    mock_amap = MagicMock()
    mock_amap.get_district_codes = AsyncMock(return_value={"上海市": "310100"})
    state = {**_base_state(), "destination": "上海", "origin": "北京"}
    from agent.nodes.parse_input import run
    result = await run(state, _make_config(mock_amap))
    assert "search_keywords" not in result
    assert "destination_region" in result
    assert result["destination_amap_cities"] == ["310100"]
