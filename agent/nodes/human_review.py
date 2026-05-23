import json, os
import logging
from datetime import datetime
import litellm
from langchain_core.runnables import RunnableConfig
from langgraph.types import interrupt
from agent.state import TravelPlanState
from agent import extract_json
from models import Flight, FlightPair, DayPlan, POI, ItineraryOption

logger = logging.getLogger(__name__)


def _rebuild_flight(f: dict) -> Flight:
    dt = f["depart_time"]
    if isinstance(dt, str):
        dt = datetime.fromisoformat(dt)
    return Flight(
        platform=f.get("platform", ""),
        depart_airport=f.get("depart_airport", ""),
        arrive_airport=f.get("arrive_airport", ""),
        price=f.get("price", 0),
        flight_no=f.get("flight_no", ""),
        depart_time=dt,
    )


def _rebuild_itineraries(raw: list) -> list[ItineraryOption]:
    """Reconstruct ItineraryOption dataclasses after Redis checkpoint deserialization."""
    result = []
    for item in raw:
        if not isinstance(item, dict):
            result.append(item)
            continue

        fp = None
        fd = item.get("flights")
        if isinstance(fd, dict):
            fp = FlightPair(
                pair_id=fd.get("pair_id", ""),
                outbound=_rebuild_flight(fd["outbound"]),
                return_flight=_rebuild_flight(fd["return_flight"]),
                total_price=fd.get("total_price", 0),
            )

        days = []
        for d in item.get("days", []):
            if not isinstance(d, dict):
                days.append(d)
                continue
            pois = [
                POI(
                    poi_id=p.get("poi_id", ""),
                    name=p.get("name", ""),
                    coords=tuple(p.get("coords", [0.0, 0.0])),
                    category=p.get("category", ""),
                    tags=p.get("tags", []),
                    desc=p.get("desc", ""),
                    amap_rating=p.get("amap_rating", 0.0),
                    sources=p.get("sources", []),
                    mention_count=p.get("mention_count", 0),
                    platform_count=p.get("platform_count", 0),
                    confidence=p.get("confidence", "low"),
                ) if isinstance(p, dict) else p
                for p in d.get("pois", [])
            ]
            days.append(DayPlan(
                day=d.get("day", 0),
                pois=pois,
                transport_note=d.get("transport_note", ""),
                estimated_travel_minutes=d.get("estimated_travel_minutes", 0),
            ))

        result.append(ItineraryOption(
            option_id=item.get("option_id", ""),
            summary=item.get("summary", ""),
            flights=fp,
            days=days,
        ))
    return result


def _format_plans_for_display(itineraries: list[ItineraryOption]) -> list[dict]:
    """Serialize itineraries into compact summaries for the interrupt payload."""
    plans = []
    for itin in itineraries:
        fp = itin.flights
        days_summary = [
            {"day": d.day, "pois": [p.name for p in d.pois], "note": d.transport_note}
            for d in itin.days
        ]
        flight_info = (
            f"{fp.outbound.depart_airport}→{fp.outbound.arrive_airport} ¥{fp.total_price}/人"
            if fp else "待定（请自行查询）"
        )
        depart_date = (
            fp.outbound.depart_time.strftime("%Y-%m-%d") if fp else ""
        )
        plans.append({
            "option_id":  itin.option_id,
            "summary":    itin.summary,
            "flight":     flight_info,
            "depart_date": depart_date,
            "days":       days_summary,
        })
    return plans


async def _parse_user_reply(user_text: str, plans: list[dict], config: RunnableConfig) -> dict:
    plan_ids = [p["option_id"] for p in plans]
    prompt = f"""User replied to travel plans: "{user_text}"
Available plan IDs: {plan_ids}

Extract:
- selected_option_id: which plan the user chose (e.g. "A", "B") or "" if unclear
- adjustment_notes: any specific preferences or changes mentioned, or ""

Return JSON: {{"selected_option_id": "...", "adjustment_notes": "..."}}
Return only valid JSON, no markdown."""
    logger.info("[llm_input] _parse_user_reply chars=%d\n%s", len(prompt), prompt)
    resp = await litellm.acompletion(
        model=os.getenv("LLM_MODEL", "deepseek/deepseek-chat"),
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
    )
    logger.info("[llm_output] _parse_user_reply\n%s", resp.choices[0].message.content)
    return json.loads(extract_json(resp.choices[0].message.content or ""))


async def run(state: TravelPlanState, config: RunnableConfig) -> dict:
    itineraries = _rebuild_itineraries(state.get("itineraries", []))
    plans = _format_plans_for_display(itineraries)

    user_reply = interrupt({
        "type":    "review_plan",
        "message": f"帮你规划了 {len(plans)} 个方案，你看哪个合适，或者有想调整的？",
        "plans":   plans,
    })

    parsed = await _parse_user_reply(
        user_text=user_reply.get("text", ""),
        plans=plans,
        config=config,
    )

    return {
        "selected_option_id": parsed.get("selected_option_id") or None,
        "adjustment_notes":   parsed.get("adjustment_notes") or None,
        # keep legacy fields so compose_output doesn't break
        "user_flight_choice": parsed.get("selected_option_id") or None,
        "user_poi_prefs":     parsed.get("adjustment_notes") or None,
    }
