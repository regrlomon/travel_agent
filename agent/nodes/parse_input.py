import json
import os
from datetime import date, timedelta
import litellm
from agent.state import TravelPlanState
from tools.amap import get_district_codes


async def _llm_parse_destination(destination: str, origin: str) -> dict:
    """Ask LLM to expand destination into region info. Returns city names (not codes)."""
    prompt = f"""You are a Chinese travel expert. Given the destination "{destination}" (departing from "{origin}"):
Return JSON with these keys:
- region: human-readable description (e.g. "甘孜州+阿坝州")
- city_names: list of Chinese administrative district names (e.g. ["甘孜藏族自治州","阿坝藏族羌族自治州"])
- destination_airports: IATA codes of airports serving this area (e.g. ["CTU","TFU","DCY","KGT"])
- origin_airports: IATA codes for airports near "{origin}" (e.g. ["PVG","SHA","NKG"])
- search_keywords: 3-5 Chinese search queries for travel content (e.g. ["川西 攻略","稻城亚丁 游记"])

Return only valid JSON, no markdown."""

    resp = await litellm.acompletion(
        model=os.getenv("LLM_MODEL", "deepseek/deepseek-chat"),
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
    )
    return json.loads(resp.choices[0].message.content)


async def _resolve_amap_codes(city_names: list[str]) -> list[str]:
    """Convert city names to 高德 adcodes via the district API."""
    api_key = os.getenv("AMAP_API_KEY", "")
    code_map = await get_district_codes(city_names, api_key=api_key)
    return list(code_map.values())


async def run(state: TravelPlanState) -> dict:
    parsed = await _llm_parse_destination(state["destination"], state["origin"])
    amap_cities = await _resolve_amap_codes(parsed["city_names"])

    if state.get("depart_date"):
        depart_dates = [date.fromisoformat(state["depart_date"])]
    else:
        today = date.today()
        depart_dates = [today + timedelta(days=i) for i in range(14)]

    return {
        "destination_region": parsed["region"],
        "destination_amap_cities": amap_cities,
        "destination_airports": parsed["destination_airports"],
        "origin_airports": parsed["origin_airports"],
        "depart_dates": depart_dates,
        "search_keywords": parsed["search_keywords"],
    }
