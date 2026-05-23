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
    mock_msg = MagicMock()
    mock_msg.content = (
        '{"destination": "川西", "origin": "苏州", "duration_days": 7, '
        '"interests": ["自然风光"], "depart_date": null}'
    )
    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value=mock_msg)
    mocker.patch("agent.nodes.collect_intent.get_llm", return_value=mock_llm)

    result = await _llm_extract("川西7天，苏州出发，喜欢自然风光", {})
    assert result["destination"] == "川西"
    assert result["origin"] == "苏州"
    assert result["duration_days"] == 7
    assert "自然风光" in result["interests"]


@pytest.mark.asyncio
async def test_llm_build_reply_asks_missing(mocker):
    mock_msg = MagicMock()
    mock_msg.content = "从哪里出发？大概玩几天？"
    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value=mock_msg)
    mocker.patch("agent.nodes.collect_intent.get_llm", return_value=mock_llm)

    reply = await _llm_build_reply({"destination": "川西"})
    assert isinstance(reply, str)
    assert len(reply) > 5


@pytest.mark.asyncio
async def test_llm_build_reply_includes_intro_when_empty(mocker):
    """_llm_build_reply prompt must request self-introduction when collected={}."""
    mock_msg = MagicMock()
    mock_msg.content = "我是小Z助手，你想去哪儿？"
    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value=mock_msg)
    mocker.patch("agent.nodes.collect_intent.get_llm", return_value=mock_llm)

    reply = await _llm_build_reply({})
    prompt_sent = mock_llm.ainvoke.call_args[0][0][0].content
    assert "自我介绍" in prompt_sent or "小Z" in prompt_sent


@pytest.mark.asyncio
async def test_empty_raw_message_triggers_hardcoded_greeting(mocker):
    """When raw_message is empty, first interrupt must contain hardcoded greeting with '小Z助手'."""
    greeting_reply = {"text": "川西7天，苏州出发"}
    confirm_reply  = {"text": "确认"}

    mock_interrupt = mocker.patch(
        "agent.nodes.collect_intent.interrupt",
        side_effect=[
            greeting_reply,   # greeting → user sends full intent
            {"text": "自然风光、徒步"},  # select_interests
            {"text": ""},             # depart_date skip
            {"text": ""},             # time_pref skip
            confirm_reply,            # confirm
        ],
    )
    mocker.patch("agent.nodes.collect_intent._llm_extract",
                 new_callable=AsyncMock,
                 return_value={"destination": "川西", "origin": "苏州",
                               "duration_days": 7, "interests": []})
    mocker.patch("agent.nodes.collect_intent._llm_generate_tags",
                 new_callable=AsyncMock, return_value=["自然风光", "徒步"])
    mocker.patch("agent.nodes.collect_intent._llm_extract_time_prefs",
                 new_callable=AsyncMock, return_value=(None, None))
    mocker.patch("agent.nodes.collect_intent._parse_confirm_reply",
                 new_callable=AsyncMock, return_value={"action": "confirm", "updates": {}})

    mock_tools = MagicMock()
    mock_tools.__getitem__ = MagicMock(return_value=MagicMock(
        lookup=AsyncMock(return_value=["PVG"])
    ))
    config = {"configurable": {"tools": mock_tools}}

    from agent.nodes.collect_intent import run
    await run({"raw_message": "", "errors": [], "warnings": []}, config)

    first_call = mock_interrupt.call_args_list[0][0][0]
    assert first_call["type"] == "collect_intent"
    # Greeting must be hardcoded (deterministic), not LLM-generated
    assert "小Z助手" in first_call["message"]
    assert "搜景点" in first_call["message"] or "帮你" in first_call["message"]
