import json, os
import logging
from datetime import date, timedelta
import litellm
from langchain_core.runnables import RunnableConfig
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

    # collect_intent already resolved origin airports via AirportsClient;
    # only fall back to LLM-parsed airports if not set
    origin_airports = state.get("origin_airports") or parsed["origin_airports"]

    return {
        "destination_region":       parsed["region"],
        "destination_amap_cities":  amap_cities,
        "destination_airports":     parsed["destination_airports"],
        "origin_airports":          origin_airports,
        "depart_dates":             _expand_dates(state.get("depart_date")),
        "search_keywords":          parsed["search_keywords"],
    }

