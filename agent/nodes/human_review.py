import json
import logging
import os

import litellm
from langchain_core.runnables import RunnableConfig
from langgraph.types import interrupt

from agent.state import TravelPlanState
from agent import extract_json
from models import FlightPair, POI

logger = logging.getLogger(__name__)


def _format_flights(pairs: list[FlightPair]) -> list[dict]:
    return [
        {
            "pair_id": fp.pair_id,
            "outbound": f"{fp.outbound.depart_airport}→{fp.outbound.arrive_airport} {fp.outbound.depart_time.strftime('%Y-%m-%d')} ¥{fp.outbound.price}",
            "return": f"{fp.return_flight.depart_airport}→{fp.return_flight.arrive_airport} ¥{fp.return_flight.price}",
            "total_price": fp.total_price,
            "platform": fp.outbound.platform,
        }
        for fp in pairs
    ]


def _format_pois(pois: list[POI]) -> list[dict]:
    return [
        {"name": p.name, "category": p.category, "confidence": p.confidence, "tags": p.tags}
        for p in pois[:15]
    ]


async def _parse_review_reply(
    user_text: str,
    flight_pairs: list[FlightPair],
    config: RunnableConfig,
) -> dict:
    """Extract flight_choice and poi_prefs from user's natural language reply."""
    pairs_info = json.dumps(_format_flights(flight_pairs), ensure_ascii=False)
    prompt = f"""User said: "{user_text}"
Available flights: {pairs_info}

Extract:
- flight_choice: the pair_id the user chose (or "" if unclear/confirmed all)
- poi_prefs: any POI preferences mentioned (or "" if none)

Return JSON: {{"flight_choice": "...", "poi_prefs": "..."}}
Return only valid JSON, no markdown."""
    try:
        resp = await litellm.acompletion(
            model=os.getenv("LLM_MODEL", "deepseek/deepseek-chat"),
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
        )
    except Exception:
        logger.exception("LLM call failed in _parse_review_reply, user_text=%r", user_text)
        raise
    try:
        return json.loads(extract_json(resp.choices[0].message.content))
    except json.JSONDecodeError:
        logger.error("JSON parse failed in _parse_review_reply, raw=%r", resp.choices[0].message.content)
        raise


async def run(state: TravelPlanState, config: RunnableConfig) -> dict:
    logger.info("[human_review] start, flights=%d pois=%d",
                len(state.get("flight_pairs", [])), len(state.get("pois", [])))
    flights_summary = _format_flights(state.get("flight_pairs", []))
    poi_summary = _format_pois(state.get("pois", []))

    user_reply = interrupt({
        "type": "review_flights_pois",
        "flights_summary": flights_summary,
        "poi_summary": poi_summary,
        "message": "已找到以上航班和景点，有偏好吗？（或直接说确认，帮我安排）",
    })

    choice = await _parse_review_reply(
        user_text=user_reply.get("text", ""),
        flight_pairs=state.get("flight_pairs", []),
        config=config,
    )

    logger.info("[human_review] done, flight_choice=%r poi_prefs=%r",
                choice.get("flight_choice"), choice.get("poi_prefs"))
    return {
        "user_flight_choice": choice.get("flight_choice") or None,
        "user_poi_prefs": choice.get("poi_prefs") or None,
    }
