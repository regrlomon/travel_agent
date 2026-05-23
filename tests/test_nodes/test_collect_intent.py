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


@pytest.mark.asyncio
async def test_llm_generate_tags_returns_list(mocker):
    mock_msg = MagicMock()
    mock_msg.content = '["自然风光", "徒步", "寺庙朝圣", "高原摄影"]'
    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value=mock_msg)
    mocker.patch("agent.nodes.collect_intent.get_llm", return_value=mock_llm)

    from agent.nodes.collect_intent import _llm_generate_tags
    tags = await _llm_generate_tags("川西")
    assert isinstance(tags, list)
    assert len(tags) >= 4
    assert all(isinstance(t, str) for t in tags)


@pytest.mark.asyncio
async def test_llm_generate_tags_falls_back_on_bad_json(mocker):
    mock_msg = MagicMock()
    mock_msg.content = "sorry I can't"
    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value=mock_msg)
    mocker.patch("agent.nodes.collect_intent.get_llm", return_value=mock_llm)

    from agent.nodes.collect_intent import _llm_generate_tags
    tags = await _llm_generate_tags("川西")
    assert isinstance(tags, list)  # empty list fallback, not exception


@pytest.mark.asyncio
async def test_llm_extract_time_prefs_parses_both(mocker):
    mock_msg = MagicMock()
    mock_msg.content = '{"depart_time_pref": "9点左右", "return_time_pref": "下午出发"}'
    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value=mock_msg)
    mocker.patch("agent.nodes.collect_intent.get_llm", return_value=mock_llm)

    from agent.nodes.collect_intent import _llm_extract_time_prefs
    dep, ret = await _llm_extract_time_prefs("去程9点，返程下午")
    assert dep == "9点左右"
    assert ret == "下午出发"


@pytest.mark.asyncio
async def test_llm_extract_time_prefs_returns_none_on_skip(mocker):
    mock_msg = MagicMock()
    mock_msg.content = '{"depart_time_pref": null, "return_time_pref": null}'
    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value=mock_msg)
    mocker.patch("agent.nodes.collect_intent.get_llm", return_value=mock_llm)

    from agent.nodes.collect_intent import _llm_extract_time_prefs
    dep, ret = await _llm_extract_time_prefs("随便")
    assert dep is None
    assert ret is None


@pytest.mark.asyncio
async def test_parse_confirm_reply_confirm(mocker):
    mock_msg = MagicMock()
    mock_msg.content = '{"action": "confirm", "updates": {}}'
    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value=mock_msg)
    mocker.patch("agent.nodes.collect_intent.get_llm", return_value=mock_llm)

    from agent.nodes.collect_intent import _parse_confirm_reply
    result = await _parse_confirm_reply("好的没问题", {})
    assert result["action"] == "confirm"


@pytest.mark.asyncio
async def test_parse_confirm_reply_modify(mocker):
    mock_msg = MagicMock()
    mock_msg.content = '{"action": "modify", "updates": {"duration_days": 5}}'
    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value=mock_msg)
    mocker.patch("agent.nodes.collect_intent.get_llm", return_value=mock_llm)

    from agent.nodes.collect_intent import _parse_confirm_reply
    result = await _parse_confirm_reply("改成5天吧", {"duration_days": 7})
    assert result["action"] == "modify"
    assert result["updates"]["duration_days"] == 5


@pytest.mark.asyncio
async def test_run_full_flow_interrupt_sequence(mocker):
    """Integration: run() fires interrupts in correct order for full flow."""
    mocker.patch("agent.nodes.collect_intent._llm_extract",
                 new_callable=AsyncMock,
                 return_value={"destination": "川西", "origin": "苏州",
                               "duration_days": 7, "interests": []})
    mocker.patch("agent.nodes.collect_intent._llm_generate_tags",
                 new_callable=AsyncMock, return_value=["自然风光", "徒步"])
    mocker.patch("agent.nodes.collect_intent._llm_extract_time_prefs",
                 new_callable=AsyncMock, return_value=("上午", None))
    mocker.patch("agent.nodes.collect_intent._parse_confirm_reply",
                 new_callable=AsyncMock, return_value={"action": "confirm", "updates": {}})

    interrupt_replies = [
        {"text": "自然风光、徒步"},           # select_interests
        {"text": ""},                       # depart_date skip
        {"text": "上午出发随意"},             # time_pref
        {"text": "确认"},                    # confirm
    ]
    mock_interrupt = mocker.patch(
        "agent.nodes.collect_intent.interrupt",
        side_effect=interrupt_replies,
    )
    mock_tools = MagicMock()
    mock_tools.__getitem__ = MagicMock(return_value=MagicMock(
        lookup=AsyncMock(return_value=["PVG"])
    ))
    config = {"configurable": {"tools": mock_tools}}

    from agent.nodes.collect_intent import run
    result = await run(
        {"raw_message": "想去川西，苏州出发，7天", "errors": [], "warnings": []},
        config,
    )

    interrupt_types = [c[0][0]["type"] for c in mock_interrupt.call_args_list]
    assert interrupt_types == [
        "select_interests",
        "collect_intent",   # depart_date
        "collect_intent",   # time_pref
        "confirm_intent",
    ]
    assert result["destination"] == "川西"
    assert result["depart_time_pref"] == "上午"
    assert result["return_time_pref"] is None
