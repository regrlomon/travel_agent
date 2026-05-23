import json, os
import logging
from datetime import date
import litellm
from langchain_core.runnables import RunnableConfig
from langgraph.types import interrupt
from agent.state import TravelPlanState
from agent import extract_json

logger = logging.getLogger(__name__)

_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_current_date",
            "description": "Returns today's date in YYYY-MM-DD format.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    }
]


def _dispatch_tool(name: str) -> str:
    if name == "get_current_date":
        return date.today().isoformat()
    return ""


def _is_complete(collected: dict) -> bool:
    return bool(
        collected.get("destination")
        and collected.get("origin")
        and collected.get("duration_days")
    )


async def _llm_extract(user_text: str, current: dict) -> dict:
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

    messages = [{"role": "user", "content": prompt}]
    logger.info("[llm_input] _llm_extract chars=%d\n%s", len(prompt), prompt)

    while True:
        resp = await litellm.acompletion(
            model=os.getenv("LLM_MODEL", "deepseek/deepseek-chat"),
            messages=messages,
            tools=_TOOLS,
            tool_choice="auto",
            temperature=0.1,
        )
        msg = resp.choices[0].message

        if msg.tool_calls:
            messages.append({
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [tc.model_dump() for tc in msg.tool_calls],
            })
            for tc in msg.tool_calls:
                result = _dispatch_tool(tc.function.name)
                logger.info("[tool_call] %s → %s", tc.function.name, result)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                })
        else:
            content = msg.content or ""
            logger.info("[llm_output] _llm_extract\n%s", content)
            try:
                extracted = json.loads(extract_json(content))
            except (json.JSONDecodeError, ValueError):
                logger.warning("[llm_extract] failed to parse response, returning current collected")
                return {**current}
            merged = {**current}
            for k, v in extracted.items():
                if v is not None and v != [] and v != "":
                    merged[k] = v
            return merged


async def _llm_build_reply(collected: dict) -> str:
    missing = []
    if not collected.get("destination"):
        missing.append("目的地")
    if not collected.get("origin"):
        missing.append("出发城市")
    if not collected.get("duration_days"):
        missing.append("出行天数")

    prompt = f"""You are a friendly Chinese travel assistant. The user wants to plan a trip.

Already collected: {json.dumps(collected, ensure_ascii=False)}
Still need: {missing}

Write ONE natural, warm reply in Chinese that:
1. Acknowledges what you already know (if anything)
2. Asks for the missing info in a conversational way (can ask multiple things in one sentence)
3. If destination is vague or unknown, offer 2-3 suggestions based on the style mentioned

Keep it under 60 characters. Be friendly, not robotic. No bullet points."""
    logger.info("[llm_input] _llm_build_reply chars=%d\n%s", len(prompt), prompt)
    resp = await litellm.acompletion(
        model=os.getenv("LLM_MODEL", "deepseek/deepseek-chat"),
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
    )
    logger.info("[llm_output] _llm_build_reply\n%s", resp.choices[0].message.content)
    return resp.choices[0].message.content.strip()


async def run(state: TravelPlanState, config: RunnableConfig) -> dict:
    tools = config["configurable"]["tools"]
    collected: dict = {}

    raw = state.get("raw_message", "")
    if raw:
        collected = await _llm_extract(raw, collected)

    while not _is_complete(collected):
        reply_text = await _llm_build_reply(collected)
        user_reply = interrupt({
            "type": "collect_intent",
            "message": reply_text,
        })
        collected = await _llm_extract(user_reply.get("text", ""), collected)

    # 选填：出发日期，问一次，用户可跳过
    if not collected.get("depart_date"):
        user_reply = interrupt({
            "type": "collect_intent",
            "message": "什么时候出发呀？不确定的话我帮你查最近7天最便宜的～",
        })
        collected = await _llm_extract(user_reply.get("text", ""), collected)

    origin_airports = await tools["airports"].lookup(collected["origin"])

    return {
        "destination":    collected["destination"],
        "origin":         collected["origin"],
        "duration_days":  int(collected["duration_days"]),
        "interests":      collected.get("interests", []),
        "depart_date":    collected.get("depart_date"),
        "origin_airports": origin_airports,
    }
