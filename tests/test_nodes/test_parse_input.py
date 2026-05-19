import pytest
from datetime import date, timedelta
from unittest.mock import AsyncMock, patch, MagicMock
from agent.nodes.parse_input import run


@pytest.fixture
def base_state():
    return {
        "destination": "川西",
        "origin": "苏州",
        "duration_days": 7,
        "travelers": 2,
        "transport_mode": "self_drive",
        "difficulty_level": "medium",
        "interests": ["徒步", "摄影"],
        "depart_date": None,
        "errors": [],
        "warnings": [],
        "job_id": "test-job",
    }


@pytest.mark.asyncio
async def test_parse_input_expands_depart_dates_when_none(base_state, mocker):
    mocker.patch("agent.nodes.parse_input._llm_parse_destination", new_callable=AsyncMock, return_value={
        "region": "甘孜州+阿坝州",
        "city_names": ["甘孜藏族自治州"],
        "destination_airports": ["CTU", "DCY"],
        "origin_airports": ["PVG", "SHA", "NKG"],
        "search_keywords": ["川西 攻略", "稻城亚丁 游记"],
    })
    mocker.patch("agent.nodes.parse_input._resolve_amap_codes", new_callable=AsyncMock, return_value=["513300"])

    result = await run(base_state)
    assert len(result["depart_dates"]) == 14
    assert result["depart_dates"][0] == date.today()


@pytest.mark.asyncio
async def test_parse_input_single_date_when_specified(base_state, mocker):
    base_state["depart_date"] = "2026-07-01"
    mocker.patch("agent.nodes.parse_input._llm_parse_destination", new_callable=AsyncMock, return_value={
        "region": "甘孜州+阿坝州",
        "city_names": ["甘孜藏族自治州"],
        "destination_airports": ["CTU", "DCY"],
        "origin_airports": ["PVG", "SHA", "NKG"],
        "search_keywords": ["川西 攻略"],
    })
    mocker.patch("agent.nodes.parse_input._resolve_amap_codes", new_callable=AsyncMock, return_value=["513300"])

    result = await run(base_state)
    assert result["depart_dates"] == [date(2026, 7, 1)]


@pytest.mark.asyncio
async def test_parse_input_writes_search_keywords(base_state, mocker):
    mocker.patch("agent.nodes.parse_input._llm_parse_destination", new_callable=AsyncMock, return_value={
        "region": "甘孜州+阿坝州",
        "city_names": ["甘孜藏族自治州"],
        "destination_airports": ["CTU", "DCY"],
        "origin_airports": ["PVG", "SHA", "NKG"],
        "search_keywords": ["川西 攻略", "稻城亚丁 游记"],
    })
    mocker.patch("agent.nodes.parse_input._resolve_amap_codes", new_callable=AsyncMock, return_value=["513300"])

    result = await run(base_state)
    assert "川西 攻略" in result["search_keywords"]
