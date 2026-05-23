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

    # 选填：出发日期，问一次，用户可跳过
    if not collected.get("depart_date"):
        user_reply = interrupt({
            "type": "collect_intent",
            "message": "出发时间定了吗？没定的话我帮你查最近7天哪天最便宜。",
        })
        collected = await _llm_extract(user_reply.get("text", ""), collected, config)

    origin_airports = await tools["airports"].lookup(collected["origin"])

    return {
        "destination":    collected["destination"],
        "origin":         collected["origin"],
        "duration_days":  int(collected["duration_days"]),
        "interests":      collected.get("interests", []),
        "depart_date":    collected.get("depart_date"),
        "origin_airports": origin_airports,
    }
