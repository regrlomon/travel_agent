import json, os
from datetime import date, timedelta
import litellm
from langchain_core.runnables import RunnableConfig
from langgraph.types import interrupt
from agent.state import TravelPlanState


async def _llm_parse_destination(destination: str, origin: str) -> dict:
    prompt = f"""You are a Chinese travel expert. Given destination "{destination}" departing from "{origin}":
Return JSON with:
- region: human-readable string e.g. "甘孜州+阿坝州"
- city_names: list of Chinese admin district names e.g. ["甘孜藏族自治州"]
- destination_airports: IATA codes e.g. ["CTU","DCY"]
- origin_airports: IATA codes near "{origin}" e.g. ["PVG","SHA","NKG"]
- search_keywords: 3-5 Chinese queries e.g. ["川西 攻略"]
Return only valid JSON, no markdown."""
    resp = await litellm.acompletion(
        model=os.getenv("LLM_MODEL", "deepseek/deepseek-chat"),
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
    )
    return json.loads(resp.choices[0].message.content)


async def _apply_corrections(parsed: dict, user_text: str, config: RunnableConfig) -> dict:
    """Single LLM call to apply user's natural-language corrections to parsed params."""
    prompt = f"""Current parsed travel params:
{json.dumps(parsed, ensure_ascii=False)}

User correction: "{user_text}"

Apply the correction and return the updated JSON with the same keys. Only change what the user asked.
Return only valid JSON, no markdown."""
    resp = await litellm.acompletion(
        model=os.getenv("LLM_MODEL", "deepseek/deepseek-chat"),
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
    )
    return json.loads(resp.choices[0].message.content)


def _expand_dates(depart_date: str | None) -> list[date]:
    if depart_date:
        return [date.fromisoformat(depart_date)]
    today = date.today()
    return [today + timedelta(days=i) for i in range(14)]


async def run(state: TravelPlanState, config: RunnableConfig) -> dict:
    tools = config["configurable"]["tools"]
    parsed = await _llm_parse_destination(state["destination"], state["origin"])

    code_map = await tools["amap"].get_district_codes(parsed["city_names"])
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

    return {
        "destination_region": parsed["region"],
        "destination_amap_cities": amap_cities,
        "destination_airports": parsed["destination_airports"],
        "origin_airports": parsed["origin_airports"],
        "depart_dates": _expand_dates(state.get("depart_date")),
        "search_keywords": parsed["search_keywords"],
    }
