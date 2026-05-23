import pytest
from unittest.mock import AsyncMock, MagicMock
from agent.nodes.collect_intent import _is_complete, _llm_extract, _llm_build_reply


def test_is_complete_all_fields():
    assert _is_complete({"destination": "川西", "origin": "苏州", "duration_days": 7}) is True


def test_is_complete_missing_duration():
    assert _is_complete({"destination": "川西", "origin": "苏州"}) is False


def test_is_complete_missing_origin():
    assert _is_complete({"destination": "川西", "duration_days": 7}) is False


def test_is_complete_empty():
    assert _is_complete({}) is False


@pytest.mark.asyncio
async def test_llm_extract_full_sentence(mocker):
    mock_resp = MagicMock()
    mock_resp.choices[0].message.content = (
        '{"destination": "川西", "origin": "苏州", "duration_days": 7, '
        '"interests": ["自然风光"], "depart_date": null}'
    )
    mocker.patch("litellm.acompletion", AsyncMock(return_value=mock_resp))

    result = await _llm_extract("川西7天，苏州出发，喜欢自然风光", {})
    assert result["destination"] == "川西"
    assert result["origin"] == "苏州"
    assert result["duration_days"] == 7
    assert "自然风光" in result["interests"]


@pytest.mark.asyncio
async def test_llm_build_reply_asks_missing(mocker):
    mock_resp = MagicMock()
    mock_resp.choices[0].message.content = "从哪里出发？大概玩几天？"
    mocker.patch("litellm.acompletion", AsyncMock(return_value=mock_resp))

    reply = await _llm_build_reply({"destination": "川西"})
    assert len(reply) > 0
