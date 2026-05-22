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
async def test_parse_input_calls_interrupt(mocker):
    mocker.patch("agent.nodes.parse_input._llm_parse_destination", new_callable=AsyncMock, return_value={
        "region": "甘孜州", "city_names": ["甘孜藏族自治州"],
        "destination_airports": ["CTU"], "origin_airports": ["PVG"],
        "search_keywords": ["川西 攻略"],
    })
    mock_amap = MagicMock()
    mock_amap.get_district_codes = AsyncMock(return_value={"甘孜藏族自治州": "513300"})
    mock_interrupt = mocker.patch("agent.nodes.parse_input.interrupt", return_value={"text": ""})

    from agent.nodes.parse_input import run
    await run(_base_state(), _make_config(mock_amap))
    mock_interrupt.assert_called_once()
    call_data = mock_interrupt.call_args[0][0]
    assert call_data["type"] == "confirm_params"


@pytest.mark.asyncio
async def test_parse_input_applies_corrections_when_user_replies(mocker):
    mocker.patch("agent.nodes.parse_input._llm_parse_destination", new_callable=AsyncMock, return_value={
        "region": "甘孜州", "city_names": ["甘孜藏族自治州"],
        "destination_airports": ["CTU"], "origin_airports": ["PVG"],
        "search_keywords": ["川西"],
    })
    mock_amap = MagicMock()
    mock_amap.get_district_codes = AsyncMock(return_value={"甘孜藏族自治州": "513300"})
    mocker.patch("agent.nodes.parse_input.interrupt", return_value={"text": "改成北京出发"})
    mock_correct = mocker.patch("agent.nodes.parse_input._apply_corrections", new_callable=AsyncMock,
        return_value={
            "region": "甘孜州", "city_names": ["甘孜藏族自治州"],
            "destination_airports": ["CTU"], "origin_airports": ["PEK", "PKX"],
            "search_keywords": ["川西"],
        })

    from agent.nodes.parse_input import run
    result = await run(_base_state(), _make_config(mock_amap))
    mock_correct.assert_called_once()
    assert "PEK" in result["origin_airports"]


@pytest.mark.asyncio
async def test_parse_input_single_date(mocker):
    mocker.patch("agent.nodes.parse_input._llm_parse_destination", new_callable=AsyncMock, return_value={
        "region": "甘孜州", "city_names": ["甘孜藏族自治州"],
        "destination_airports": ["CTU"], "origin_airports": ["PVG"],
        "search_keywords": ["川西"],
    })
    mock_amap = MagicMock()
    mock_amap.get_district_codes = AsyncMock(return_value={"甘孜藏族自治州": "513300"})
    mocker.patch("agent.nodes.parse_input.interrupt", return_value={"text": ""})

    state = {**_base_state(), "depart_date": "2026-07-01"}
    from agent.nodes.parse_input import run
    result = await run(state, _make_config(mock_amap))
    assert result["depart_dates"] == [date(2026, 7, 1)]
