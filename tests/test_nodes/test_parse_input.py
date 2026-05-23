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
        "search_keywords": ["川西 攻略"],
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
async def test_parse_input_fallback_to_llm_airports(mocker):
    """Test that LLM-parsed airports are used if not in state."""
    mocker.patch("agent.nodes.parse_input._llm_parse_destination", new_callable=AsyncMock, return_value={
        "region": "甘孜州", "city_names": ["甘孜藏族自治州"],
        "destination_airports": ["CTU"], "origin_airports": ["PVG"],
        "search_keywords": ["川西"],
    })
    mock_amap = MagicMock()
    mock_amap.get_district_codes = AsyncMock(return_value={"甘孜藏族自治州": "513300"})

    from agent.nodes.parse_input import run
    result = await run(_base_state(), _make_config(mock_amap))
    # Should use LLM-parsed airports as fallback
    assert result["origin_airports"] == ["PVG"]


@pytest.mark.asyncio
async def test_parse_input_single_date(mocker):
    mocker.patch("agent.nodes.parse_input._llm_parse_destination", new_callable=AsyncMock, return_value={
        "region": "甘孜州", "city_names": ["甘孜藏族自治州"],
        "destination_airports": ["CTU"], "origin_airports": ["PVG"],
        "search_keywords": ["川西"],
    })
    mock_amap = MagicMock()
    mock_amap.get_district_codes = AsyncMock(return_value={"甘孜藏族自治州": "513300"})

    state = {**_base_state(), "depart_date": "2026-07-01"}
    from agent.nodes.parse_input import run
    result = await run(state, _make_config(mock_amap))
    assert result["depart_dates"] == [date(2026, 7, 1)]
