import json
import logging
from langchain_core.runnables import RunnableConfig
from langgraph.types import interrupt
from agent.state import TravelPlanState
from agent import extract_json
from agent.llm import get_llm
from agent.nodes._rebuild import rebuild_itineraries
from models import ItineraryOption

logger = logging.getLogger(__name__)


def _format_plans_for_display(itineraries: list[ItineraryOption]) -> list[dict]:
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
        depart_date = fp.outbound.depart_time.strftime("%Y-%m-%d") if fp else ""
        plans.append({
            "option_id":   itin.option_id,
            "summary":     itin.summary,
            "flight":      flight_info,
            "depart_date": depart_date,
            "days":        days_summary,
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
    llm = get_llm(temperature=0.1)
    resp = await llm.ainvoke([{"role": "user", "content": prompt}])
    logger.info("[llm_output] _parse_user_reply\n%s", resp.content)
    return json.loads(extract_json(resp.content))


async def run(state: TravelPlanState, config: RunnableConfig) -> dict:
    itineraries = rebuild_itineraries(state.get("itineraries", []))
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
        "user_flight_choice": parsed.get("selected_option_id") or None,
        "user_poi_prefs":     parsed.get("adjustment_notes") or None,
    }
