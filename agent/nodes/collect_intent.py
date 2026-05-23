import json
import logging
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.types import interrupt
from agent.state import TravelPlanState
from agent import extract_json
from agent.llm import get_llm

logger = logging.getLogger(__name__)


def _is_complete(collected: dict) -> bool:
    return bool(
        collected.get("destination")
        and collected.get("origin")
        and collected.get("duration_days")
    )


async def _llm_extract(user_text: str, current: dict, config=None) -> dict:
    prompt = f"""You are helping collect travel intent. Extract any travel info from the user message.

Current collected info: {json.dumps(current, ensure_ascii=False)}
User message: "{user_text}"

Extract and return JSON with these keys (only include keys mentioned in message, keep existing values):
- destination: string (e.g. "川西", "西藏")
- origin: string (e.g. "苏州", "北京")
- duration_days: integer
- interests: list of strings (e.g. ["自然风光", "徒步"])
- depart_date: string ISO date or null

Return only valid JSON, no markdown."""
    logger.info("[llm_input] _llm_extract chars=%d\n%s", len(prompt), prompt)
    llm = get_llm(temperature=0.1)
    msg = await llm.ainvoke([HumanMessage(content=prompt)], config)
    content = msg.content if isinstance(msg.content, str) else ""
    logger.info("[llm_output] _llm_extract\n%s", content)
    try:
        extracted = json.loads(extract_json(content))
    except (json.JSONDecodeError, ValueError):
        logger.warning("[llm_extract] JSON parse failed, returning current: %r", content)
        return {**current}
    merged = {**current}
    for k, v in extracted.items():
        if v is not None and v != [] and v != "":
            merged[k] = v
    return merged


async def _llm_build_reply(collected: dict, config=None) -> str:
    missing = []
    if not collected.get("destination"):
        missing.append("目的地")
    if not collected.get("origin"):
        missing.append("出发城市")
    if not collected.get("duration_days"):
        missing.append("出行天数")

    prompt = f"""你是小Z助手，正在帮用户规划旅行，需要追问缺少的信息。

已知信息：{json.dumps(collected, ensure_ascii=False)}
还需要问：{missing}

写一句中文问句，风格要求：
- 像朋友发微信，直接问，不废话
- 禁止：太棒了、不错哦、好的呢、超级、魅力、波浪号（～）、感叹号堆叠
- 禁止句首加任何感叹词或捧场词
- 如果已知目的地，直接用它；如果目的地模糊，顺带提1-2个具体地方供参考
- 可以在一句话里问多个缺失项
- 不超过30字

只输出那一句话，不加任何解释。"""
    llm = get_llm(temperature=0.7)
    msg = await llm.ainvoke([HumanMessage(content=prompt)], config)
    return msg.content.strip()


async def _llm_generate_tags(destination: str) -> list[str]:
    prompt = f"""为旅行目的地「{destination}」生成 6-10 个旅行兴趣标签。

要求：
- 贴合该目的地的特色（地理、文化、活动）
- 每个标签 2-6 个汉字
- 返回 JSON 数组，不加任何解释

例如：["自然风光", "徒步", "摄影", "藏族文化", "温泉", "星空观测"]

只返回 JSON 数组。"""
    llm = get_llm(temperature=0.5)
    msg = await llm.ainvoke([HumanMessage(content=prompt)])
    try:
        tags = json.loads(extract_json(msg.content))
        if isinstance(tags, list):
            return [str(t) for t in tags if t]
    except (json.JSONDecodeError, ValueError):
        logger.warning("[collect_intent] _llm_generate_tags parse failed: %r", msg.content)
    return []


async def _llm_extract_time_prefs(user_text: str) -> tuple[str | None, str | None]:
    prompt = f"""从用户的消息里提取去程和返程的出发时段偏好。

用户消息："{user_text}"

返回 JSON：
{{"depart_time_pref": "原文时段描述或 null", "return_time_pref": "原文时段描述或 null"}}

示例输入："去程9点，返程下午随意"
示例输出：{{"depart_time_pref": "9点左右", "return_time_pref": "下午"}}

如果没有明确说偏好就返回 null。只返回 JSON，不加解释。"""
    llm = get_llm(temperature=0.1)
    msg = await llm.ainvoke([HumanMessage(content=prompt)])
    try:
        data = json.loads(extract_json(msg.content))
        return data.get("depart_time_pref") or None, data.get("return_time_pref") or None
    except (json.JSONDecodeError, ValueError):
        return None, None


async def _parse_confirm_reply(user_text: str, current: dict) -> dict:
    prompt = f"""用户正在确认出行信息。分析用户的回复意图。

当前信息：{json.dumps(current, ensure_ascii=False)}
用户回复："{user_text}"

返回 JSON：
{{"action": "confirm" 或 "modify", "updates": {{字段: 新值}} 或 {{}}}}

- 如果用户表示"好的/确认/没问题/可以"之类，action = "confirm"，updates = {{}}
- 如果用户提到修改任何字段，action = "modify"，updates 里放要改的字段

只返回 JSON。"""
    llm = get_llm(temperature=0.1)
    msg = await llm.ainvoke([HumanMessage(content=prompt)])
    try:
        return json.loads(extract_json(msg.content))
    except (json.JSONDecodeError, ValueError):
        return {"action": "confirm", "updates": {}}


async def run(state: TravelPlanState, config: RunnableConfig) -> dict:
    tools = config["configurable"]["tools"]
    collected: dict = {}

    raw = state.get("raw_message", "")

    # When the user opens the app without typing, send a hardcoded greeting.
    # This must NOT go through the LLM — determinism matters here.
    if not raw:
        greeting_reply = interrupt({
            "type":    "collect_intent",
            "message": "我是小Z助手，可以帮你搜景点、查机票、排行程。你想去哪儿玩？从哪儿出发，打算玩几天？",
        })
        raw = greeting_reply.get("text", "")

    if raw:
        collected = await _llm_extract(raw, collected, config)

    while not _is_complete(collected):
        reply_text = await _llm_build_reply(collected, config)
        user_reply = interrupt({
            "type": "collect_intent",
            "message": reply_text,
        })
        collected = await _llm_extract(user_reply.get("text", ""), collected, config)

    # 动态生成兴趣标签，展示给用户多选
    candidate_tags = await _llm_generate_tags(collected["destination"])
    preselected = collected.get("interests", [])
    user_reply = interrupt({
        "type":        "select_interests",
        "message":     "你对哪些感兴趣？选几个帮你优先安排（也可以跳过）",
        "tags":        candidate_tags,
        "preselected": preselected,
    })
    raw_selection = user_reply.get("text", "").strip()
    if raw_selection:
        # Frontend sends "自然风光、徒步、寺庙朝圣" — split directly, no LLM needed
        selected = [t.strip() for t in raw_selection.replace(",", "、").split("、") if t.strip()]
        if selected:
            collected["interests"] = selected

    # 选填：出发日期，问一次，用户可跳过
    if not collected.get("depart_date"):
        user_reply = interrupt({
            "type": "collect_intent",
            "message": "出发时间定了吗？没定的话我帮你查最近7天哪天最便宜。",
        })
        collected = await _llm_extract(user_reply.get("text", ""), collected, config)

    # 选填：去程 + 返程时段偏好
    time_reply = interrupt({
        "type": "collect_intent",
        "message": "去程大概想几点出发？返程呢，比如有些人会想最后一天玩到下午再飞。",
    })
    depart_pref, return_pref = await _llm_extract_time_prefs(time_reply.get("text", ""))

    # confirm_intent 循环：直到用户确认
    while True:
        summary = {
            "destination":  collected["destination"],
            "origin":       collected["origin"],
            "duration_days": int(collected["duration_days"]),
            "interests":    collected.get("interests", []),
        }
        if collected.get("depart_date"):
            summary["depart_date"] = collected["depart_date"]
        if depart_pref:
            summary["depart_time_pref"] = depart_pref
        if return_pref:
            summary["return_time_pref"] = return_pref

        confirm_reply = interrupt({
            "type":    "confirm_intent",
            "summary": summary,
        })
        parsed = await _parse_confirm_reply(confirm_reply.get("text", ""), summary)
        if parsed.get("action") == "confirm":
            break
        # merge updates and re-loop
        for k, v in parsed.get("updates", {}).items():
            if v is not None:
                collected[k] = v
        # re-extract time prefs if user mentioned them in update
        if any(kw in confirm_reply.get("text", "") for kw in ("点", "上午", "下午", "晚上", "早")):
            depart_pref, return_pref = await _llm_extract_time_prefs(confirm_reply.get("text", ""))

    origin_airports = await tools["airports"].lookup(collected["origin"])

    return {
        "destination":      collected["destination"],
        "origin":           collected["origin"],
        "duration_days":    int(collected["duration_days"]),
        "interests":        collected.get("interests", []),
        "depart_date":      collected.get("depart_date"),
        "depart_time_pref": depart_pref,
        "return_time_pref": return_pref,
        "origin_airports":  origin_airports,
    }
