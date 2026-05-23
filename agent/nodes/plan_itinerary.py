import json
import logging
from typing import Optional
from json_repair import repair_json
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from agent.state import TravelPlanState
from agent import extract_json
from agent.llm import get_llm
from models import POI, FlightPair, DayPlan, ItineraryOption

logger = logging.getLogger(__name__)


def _build_poi_table(pois: list[POI]) -> str:
    lines = ["poi_id | name | category | confidence | region | tags"]
    for p in pois:
        tags = ",".join(p.tags) if p.tags else "-"
        lines.append(f"{p.poi_id} | {p.name} | {p.category} | {p.confidence} | ({p.coords[0]:.2f},{p.coords[1]:.2f}) | {tags}")
    return "\n".join(lines)


def _build_flight_table(pairs: list[FlightPair]) -> str:
    lines = ["pair_id | outbound_route | return_route | date | total_price_per_person"]
    for fp in pairs:
        lines.append(
            f"{fp.pair_id} | {fp.outbound.depart_airport}→{fp.outbound.arrive_airport} | "
            f"{fp.return_flight.depart_airport}→{fp.return_flight.arrive_airport} | "
            f"{fp.outbound.depart_time.date()} | ¥{fp.total_price}"
        )
    return "\n".join(lines)


async def _stream_narrative(
    pois: list,
    pairs: list,
    interests: list[str],
    duration_days: int,
    config,
    emit_fn,
) -> None:
    """Stream a brief natural-language summary via stream_text tokens before JSON planning."""
    if emit_fn is None:
        return
    top_poi_names = ", ".join(p.name for p in pois[:6]) or "（待定）"
    flight_hint = ""
    if pairs:
        fp = pairs[0]
        flight_hint = f"，机票约 ¥{fp.total_price}/人，去程 {fp.outbound.depart_time.strftime('%H:%M')} 出发"
    prompt = (
        f"你是旅行规划助手，用2-3句中文自然语言（不用列表，不用JSON）概括以下信息：\n"
        f"- 行程：{duration_days}天\n"
        f"- 用户兴趣：{', '.join(interests) if interests else '综合观光'}\n"
        f"- 已收录景点代表：{top_poi_names}\n"
        f"- 航班情况：{'已找到可选航班' + flight_hint if pairs else '暂无航班数据'}\n"
        f"语气友好，直接输出文字，不要标题或符号。"
    )
    try:
        llm = get_llm(temperature=0.5)
        async for chunk in llm.astream([HumanMessage(content=prompt)], config):
            if chunk.content:
                emit_fn({"type": "stream_text", "token": chunk.content})
    except Exception:
        logger.warning("[plan_itinerary] narrative streaming failed, skipping")


async def _phase1_select(pois: list[POI], pairs: list[FlightPair], interests: list[str], duration_days: int,
                          user_flight_choice=None, user_poi_prefs=None, config=None) -> list[dict]:
    poi_table = _build_poi_table(pois)

    user_context = ""
    if user_flight_choice:
        user_context += f"\nUser preferred flight: {user_flight_choice}"
    if user_poi_prefs:
        user_context += f"\nUser POI preferences: {user_poi_prefs}"

    if pairs:
        flight_section = f"Flight pairs:\n{_build_flight_table(pairs)}\n\nFor EACH plan, assign a different FlightPair (use its pair_id)."
        pair_id_field = '"pair_id": "<uuid>",'
    else:
        flight_section = "No flight data available. Set pair_id to null for all plans."
        pair_id_field = '"pair_id": null,'

    prompt = f"""You are a travel planner. Create 2-3 travel plans.

Interests: {', '.join(interests)}
Trip duration: {duration_days} days{user_context}

POIs:
{poi_table}

{flight_section}
Return a JSON array of plans:
[
  {{
    "plan_id": "A",
    {pair_id_field}
    "days": [
      {{"day": 1, "poi_ids": ["<poi_id>", ...]}},
      ...
    ]
  }}
]
Return only valid JSON, no markdown."""

    logger.info("[llm_input] _phase1_select pois=%d pairs=%d chars=%d\n%s", len(pois), len(pairs), len(prompt), prompt)
    try:
        llm = get_llm(temperature=0.3)
        msg = await llm.ainvoke([HumanMessage(content=prompt)], config)
    except Exception:
        logger.exception("LLM call failed in _phase1_select, pois=%d pairs=%d", len(pois), len(pairs))
        raise
    logger.info("[llm_output] _phase1_select\n%s", msg.content)
    try:
        return json.loads(repair_json(extract_json(msg.content)))
    except json.JSONDecodeError:
        logger.error("JSON parse failed in _phase1_select, raw=%r", msg.content)
        raise


async def _phase2_generate(
    plan_skeleton: dict,
    poi_map: dict[str, POI],
    pair_map: dict[str, FlightPair],
    travel_time_matrix: dict[str, int],
    config=None,
) -> ItineraryOption:
    fp: Optional[FlightPair] = pair_map.get(plan_skeleton.get("pair_id"))
    selected_pois = {pid: poi_map[pid] for day in plan_skeleton["days"] for pid in day["poi_ids"] if pid in poi_map}
    short_to_poi = {pid[:8]: poi for pid, poi in poi_map.items()}
    selected_short = {pid[:8] for pid in selected_pois}

    poi_details = "\n".join(
        f"- {p.name} ({p.category}): {p.desc or 'no description'} | tags: {','.join(p.tags)}"
        for p in selected_pois.values()
    )
    time_notes = "\n".join(
        f"  {short_to_poi[a].name} → {short_to_poi[b].name}: {m} min drive"
        for key, m in travel_time_matrix.items()
        for a, b in [key.split("|", 1)]
        if a in selected_short and b in selected_short and a in short_to_poi and b in short_to_poi
    )

    flight_line = (
        f"Flight: {fp.outbound.depart_airport}→{fp.outbound.arrive_airport} (outbound) / "
        f"{fp.return_flight.depart_airport}→{fp.return_flight.arrive_airport} (return)"
        if fp else "Flight: unavailable, please book separately"
    )

    prompt = f"""Generate a detailed travel itinerary for plan {plan_skeleton['plan_id']}.

{flight_line}

Selected POIs:
{poi_details}

Driving times (from 高德 API):
{time_notes or "  (no pre-computed times for this selection)"}

Day plan assignments: {json.dumps(plan_skeleton['days'])}

Return JSON:
{{
  "option_id": "{plan_skeleton['plan_id']}",
  "summary": "<brief description>",
  "days": [
    {{
      "day": <int>,
      "transport_note": "<ground in driving times above, e.g. '驾车约55分钟'>",
      "estimated_travel_minutes": <int from driving times>
    }}
  ]
}}
Return only valid JSON, no markdown."""

    logger.info("[llm_input] _phase2_generate plan_id=%r chars=%d\n%s", plan_skeleton.get("plan_id"), len(prompt), prompt)
    try:
        llm = get_llm(temperature=0.2)
        msg = await llm.ainvoke([HumanMessage(content=prompt)], config)
    except Exception:
        logger.exception("LLM call failed in _phase2_generate, plan_id=%r", plan_skeleton.get("plan_id"))
        raise
    logger.info("[llm_output] _phase2_generate plan_id=%r\n%s", plan_skeleton.get("plan_id"), msg.content)
    try:
        raw = json.loads(repair_json(extract_json(msg.content or "")))
    except (json.JSONDecodeError, ValueError):
        logger.warning("JSON parse failed in _phase2_generate plan_id=%r, using fallback", plan_skeleton.get("plan_id"))
        raw = {}

    days = []
    for day_skeleton in plan_skeleton["days"]:
        day_extra = next((d for d in raw.get("days", []) if d["day"] == day_skeleton["day"]), {})
        pois_for_day = [poi_map[pid] for pid in day_skeleton["poi_ids"] if pid in poi_map]
        days.append(DayPlan(
            day=day_skeleton["day"],
            pois=pois_for_day,
            transport_note=day_extra.get("transport_note", ""),
            estimated_travel_minutes=day_extra.get("estimated_travel_minutes", 0),
        ))

    return ItineraryOption(
        option_id=raw.get("option_id", plan_skeleton["plan_id"]),
        summary=raw.get("summary", ""),
        flights=fp,
        days=days,
    )


async def run(state: TravelPlanState, config: RunnableConfig = None) -> dict:
    logger.info("[plan_itinerary] start, pois=%d pairs=%d", len(state.get("pois", [])), len(state.get("flight_pairs", [])))
    pois = state["pois"]
    pairs = state["flight_pairs"]
    matrix = state.get("travel_time_matrix", {})
    interests = state.get("interests", [])
    duration_days = state["duration_days"]
    user_flight_choice = state.get("user_flight_choice")
    user_poi_prefs = state.get("user_poi_prefs")

    poi_map = {p.poi_id: p for p in pois}
    pair_map = {fp.pair_id: fp for fp in pairs}

    progress_emit = (config or {}).get("configurable", {}).get("progress_emit")
    await _stream_narrative(pois, pairs, interests, duration_days, config, progress_emit)

    plan_skeletons = await _phase1_select(
        pois, pairs, interests, duration_days, user_flight_choice, user_poi_prefs, config=config
    )

    itineraries = []
    for skeleton in plan_skeletons:
        if pairs and skeleton.get("pair_id") not in pair_map:
            continue
        option = await _phase2_generate(skeleton, poi_map, pair_map, matrix, config=config)
        itineraries.append(option)

    logger.info("[plan_itinerary] done, itineraries=%d", len(itineraries))
    return {"itineraries": itineraries}
