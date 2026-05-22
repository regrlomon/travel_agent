import json, os
import logging
from datetime import date, timedelta
import litellm
from langchain_core.runnables import RunnableConfig
from langgraph.types import interrupt
from agent.state import TravelPlanState
from agent import extract_json

logger = logging.getLogger(__name__)


async def _llm_parse_destination(destination: str, origin: str) -> dict:
    prompt = f"""You are a Chinese travel expert. Given destination "{destination}" departing from "{origin}":
Return JSON with:
- region: human-readable string e.g. "甘孜州+阿坝州"
- city_names: list of Chinese admin district names e.g. ["甘孜藏族自治州"]
- destination_airports: city-level IATA codes e.g. ["CTU","DCY"] — use city codes like CTU (成都), not airport codes like TFU
- origin_airports: city-level IATA codes near "{origin}" e.g. ["BJS","NKG"] — use city codes like BJS (北京), SHA (上海), NOT airport codes like PEK/PKX/PVG/SHA-airport
- search_keywords: 3-5 Chinese queries e.g. ["川西 攻略"]
Return only valid JSON, no markdown."""
    try:
        resp = await litellm.acompletion(
            model=os.getenv("LLM_MODEL", "deepseek/deepseek-chat"),
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
        )
    except Exception:
        logger.exception("LLM call failed in _llm_parse_destination, destination=%r origin=%r", destination, origin)
        raise
    try:
        return json.loads(extract_json(resp.choices[0].message.content))
    except json.JSONDecodeError:
        logger.error("JSON parse failed in _llm_parse_destination, raw=%r", resp.choices[0].message.content)
        raise


async def _apply_corrections(parsed: dict, user_text: str, config: RunnableConfig) -> dict:
    """Single LLM call to apply user's natural-language corrections to parsed params."""
    prompt = f"""Current parsed travel params:
{json.dumps(parsed, ensure_ascii=False)}

User correction: "{user_text}"

Apply the correction and return the updated JSON with the same keys. Only change what the user asked.
Return only valid JSON, no markdown."""
    try:
        resp = await litellm.acompletion(
            model=os.getenv("LLM_MODEL", "deepseek/deepseek-chat"),
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
        )
    except Exception:
        logger.exception("LLM call failed in _apply_corrections, user_text=%r", user_text)
        raise
    try:
        return json.loads(extract_json(resp.choices[0].message.content))
    except json.JSONDecodeError:
        logger.error("JSON parse failed in _apply_corrections, raw=%r", resp.choices[0].message.content)
        raise


def _expand_dates(depart_date: str | None) -> list[date]:
    if depart_date:
        return [date.fromisoformat(depart_date)]
    today = date.today()
    return [today + timedelta(days=i) for i in range(14)]


async def run(state: TravelPlanState, config: RunnableConfig) -> dict:
    logger.info("[parse_input] start, destination=%r origin=%r", state.get("destination"), state.get("origin"))
    tools = config["configurable"]["tools"]
    parsed = await _llm_parse_destination(state["destination"], state["origin"])

    try:
        code_map = await tools["amap"].get_district_codes(parsed["city_names"])
    except Exception:
        logger.exception("高德 get_district_codes failed, city_names=%r", parsed["city_names"])
        raise
    amap_cities = list(code_map.values())

    user_reply = interrupt({
        "type": "confirm_params",
        "message": (
            f"已解析：出发 {parsed['origin_airports']}，"
            f"目的地 {parsed['destination_airports']}，共 {state['duration_days']} 天。"
            "有需要修改吗？"
        ),
        "parsed": parsed,
    })

    if user_reply.get("text"):
        parsed = await _apply_corrections(parsed, user_reply["text"], config)

    result = {
        "destination_region": parsed["region"],
        "destination_amap_cities": amap_cities,
        "destination_airports": parsed["destination_airports"],
        "origin_airports": parsed["origin_airports"],
        "depart_dates": _expand_dates(state.get("depart_date")),
        "search_keywords": parsed["search_keywords"],
    }
    logger.info("[parse_input] done, region=%r airports=%r", result["destination_region"], result["destination_airports"])
    return result
