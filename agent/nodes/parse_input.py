import json
import logging
from datetime import date, timedelta
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from agent.state import TravelPlanState
from agent import extract_json
from agent.llm import get_llm

logger = logging.getLogger(__name__)


def _city_to_iata(city: str) -> list[str]:
    """城市名 → city-level IATA code，查 flight tool 的静态表。"""
    from tools.flight_tool.scraper import CITY_CODES
    # 优先精确匹配，再做前缀匹配（处理"北京市"→"北京"）
    if city in CITY_CODES:
        return [CITY_CODES[city]]
    for name, code in CITY_CODES.items():
        if city.startswith(name) or name.startswith(city):
            return [code]
    return []


async def _llm_parse_destination(destination: str, origin: str, config=None) -> dict:
    prompt = f"""You are a Chinese travel expert. Given destination "{destination}" departing from "{origin}":
Return JSON with:
- region: human-readable string e.g. "甘孜州+阿坝州"
- city_names: list of Chinese admin district names e.g. ["甘孜藏族自治州"]
Return only valid JSON, no markdown."""
    logger.info("[llm_input] _llm_parse_destination chars=%d\n%s", len(prompt), prompt)
    try:
        llm = get_llm(temperature=0.1)
        msg = await llm.ainvoke([HumanMessage(content=prompt)], config)
    except Exception:
        logger.exception("LLM call failed in _llm_parse_destination, destination=%r origin=%r", destination, origin)
        raise
    logger.info("[llm_output] _llm_parse_destination\n%s", msg.content)
    try:
        return json.loads(extract_json(msg.content))
    except json.JSONDecodeError:
        logger.error("JSON parse failed in _llm_parse_destination, raw=%r", msg.content)
        raise


def _expand_dates(depart_date: str | None) -> list[date]:
    if depart_date:
        return [date.fromisoformat(depart_date)]
    today = date.today()
    return [today + timedelta(days=i) for i in range(7)]


async def run(state: TravelPlanState, config: RunnableConfig) -> dict:
    tools = config["configurable"]["tools"]
    parsed = await _llm_parse_destination(state["destination"], state["origin"], config)

    code_map = await tools["amap"].get_district_codes(parsed["city_names"])
    amap_cities = list(code_map.values())

    destination_airports = _city_to_iata(state["destination"])
    if not destination_airports:
        logger.warning("destination %r not found in CITY_CODES", state["destination"])

    # collect_intent already resolved origin airports via AirportsClient;
    # only fall back to city lookup if not set
    origin_airports = state.get("origin_airports") or _city_to_iata(state["origin"])
    if not origin_airports:
        logger.warning("origin %r not found in CITY_CODES", state["origin"])

    return {
        "destination_region":       parsed["region"],
        "destination_amap_cities":  amap_cities,
        "destination_airports":     destination_airports,
        "origin_airports":          origin_airports,
        "depart_dates":             _expand_dates(state.get("depart_date")),
    }
