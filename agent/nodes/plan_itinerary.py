import json
import os
import litellm
from langchain_core.runnables import RunnableConfig
from agent.state import TravelPlanState
from models import POI, FlightPair, DayPlan, ItineraryOption


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


async def _phase1_select(pois: list[POI], pairs: list[FlightPair], interests: list[str], duration_days: int,
                          user_flight_choice=None, user_poi_prefs=None) -> list[dict]:
    """Phase 1: compressed tables → LLM selects POIs per plan per day."""
    poi_table = _build_poi_table(pois)
    flight_table = _build_flight_table(pairs)

    user_context = ""
    if user_flight_choice:
        user_context += f"\nUser preferred flight: {user_flight_choice}"
    if user_poi_prefs:
        user_context += f"\nUser POI preferences: {user_poi_prefs}"

    prompt = f"""You are a travel planner. Given the POI list and flight options below, create 2-3 travel plans.

Interests: {', '.join(interests)}
Trip duration: {duration_days} days{user_context}

POIs:
{poi_table}

Flight pairs:
{flight_table}

For EACH plan, assign a different FlightPair and select appropriate POIs per day (consider entry airport location for day 1).
Return a JSON array of plans:
[
  {{
    "plan_id": "A",
    "pair_id": "<uuid>",
    "days": [
      {{"day": 1, "poi_ids": ["<poi_id>", ...]}},
      ...
    ]
  }}
]
Return only valid JSON, no markdown."""

    resp = await litellm.acompletion(
        model=os.getenv("LLM_MODEL", "deepseek/deepseek-chat"),
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
    )
    return json.loads(resp.choices[0].message.content)


async def _phase2_generate(
    plan_skeleton: dict,
    poi_map: dict[str, POI],
    pair_map: dict[str, FlightPair],
    travel_time_matrix: dict[tuple[str, str], int],
) -> ItineraryOption:
    """Phase 2: full objects for selected items → LLM generates detailed day plans."""
    fp = pair_map[plan_skeleton["pair_id"]]
    selected_pois = {pid: poi_map[pid] for day in plan_skeleton["days"] for pid in day["poi_ids"] if pid in poi_map}

    poi_details = "\n".join(
        f"- {p.name} ({p.category}): {p.desc or 'no description'} | tags: {','.join(p.tags)}"
        for p in selected_pois.values()
    )
    time_notes = "\n".join(
        f"  {poi_map[a].name if a in poi_map else a} → {poi_map[b].name if b in poi_map else b}: {m} min drive"
        for (a, b), m in travel_time_matrix.items()
        if a in selected_pois and b in selected_pois
    )

    prompt = f"""Generate a detailed travel itinerary for plan {plan_skeleton['plan_id']}.

Flight: {fp.outbound.depart_airport}→{fp.outbound.arrive_airport} (outbound) / {fp.return_flight.depart_airport}→{fp.return_flight.arrive_airport} (return)

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

    resp = await litellm.acompletion(
        model=os.getenv("LLM_MODEL", "deepseek/deepseek-chat"),
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )
    raw = json.loads(resp.choices[0].message.content)

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
    pois = state["pois"]
    pairs = state["flight_pairs"]
    matrix = state.get("travel_time_matrix", {})
    interests = state.get("interests", [])
    duration_days = state["duration_days"]
    user_flight_choice = state.get("user_flight_choice")
    user_poi_prefs = state.get("user_poi_prefs")

    poi_map = {p.poi_id: p for p in pois}
    pair_map = {fp.pair_id: fp for fp in pairs}

    plan_skeletons = await _phase1_select(
        pois, pairs, interests, duration_days, user_flight_choice, user_poi_prefs
    )

    itineraries = []
    for skeleton in plan_skeletons:
        if skeleton.get("pair_id") not in pair_map:
            continue
        option = await _phase2_generate(skeleton, poi_map, pair_map, matrix)
        itineraries.append(option)

    return {"itineraries": itineraries}
