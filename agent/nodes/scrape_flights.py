import asyncio
import logging
import re
import uuid
from datetime import date, datetime, timedelta

from langchain_core.runnables import RunnableConfig

from agent.state import TravelPlanState
from models import Flight, FlightPair

logger = logging.getLogger(__name__)


def _parse_time_pref(pref: str | None) -> tuple[int, int] | None:
    """Map a natural-language time preference to a (after_min, before_min) window.

    Returns None if no preference or unrecognised.
    Minutes are measured from midnight (e.g. 9:00 = 540).
    """
    if not pref:
        return None
    p = pref.strip()

    # Skip keywords
    if any(kw in p for kw in ("随意", "不限", "无所谓", "都行", "不要求")):
        return None

    # Around N o'clock: "9点左右" / "9点"
    m = re.search(r"(\d{1,2})[点:：]", p)
    if m:
        h = int(m.group(1))
        return max(0, (h - 1) * 60), min(24 * 60, (h + 1) * 60)

    # Named periods
    if any(kw in p for kw in ("早上", "上午", "早班")):
        return 6 * 60, 12 * 60
    if any(kw in p for kw in ("中午",)):
        return 11 * 60, 13 * 60
    if any(kw in p for kw in ("下午",)):
        return 12 * 60, 18 * 60
    if any(kw in p for kw in ("傍晚", "晚上", "夜班")):
        return 17 * 60, 22 * 60

    # Relative constraints
    if any(kw in p for kw in ("不要太早", "别太早", "不太早")):
        return 8 * 60, 23 * 60
    if any(kw in p for kw in ("不要太晚", "别太晚", "不太晚")):
        return 0, 20 * 60

    return None


def _rank_by_time_pref(flights: list, pref: str | None) -> list:
    """Return flights sorted by proximity to time preference window midpoint.

    No flights are removed — only re-ordered.
    """
    window = _parse_time_pref(pref)
    if window is None:
        return flights
    after_min, before_min = window
    midpoint = (after_min + before_min) / 2

    def _distance(flight) -> float:
        t = flight.depart_time
        flight_min = t.hour * 60 + t.minute
        return abs(flight_min - midpoint)

    return sorted(flights, key=_distance)


def _raw_to_flight(raw: dict, depart_date: date) -> Flight:
    dep_dt = datetime.combine(
        depart_date,
        datetime.strptime(raw["dep"], "%H:%M").time(),
    )
    return Flight(
        platform=raw.get("source", "unknown"),
        depart_airport=raw.get("dep_ap", ""),
        arrive_airport=raw.get("arr_ap", ""),
        price=raw["price"],
        flight_no=raw["flight"],
        depart_time=dep_dt,
    )


def _assemble_flight_pairs(
    outbound_flights: list[Flight],
    return_flights: list[Flight],
    depart_time_pref: str | None = None,
    return_time_pref: str | None = None,
    max_pairs: int = 3,
) -> list[FlightPair]:
    """Return up to max_pairs FlightPairs ordered by time preference, then price.

    Replaces the old cheapest-only logic that discarded time preference sorting.
    """
    ranked_out = _rank_by_time_pref(outbound_flights, depart_time_pref)
    ranked_ret = _rank_by_time_pref(return_flights, return_time_pref)

    ret_by_airport: dict[str, list] = {}
    for ret in ranked_ret:
        ret_by_airport.setdefault(ret.depart_airport, []).append(ret)

    pairs: list[FlightPair] = []
    seen_flight_no: set[str] = set()
    seen_ret_no: set[str] = set()

    for out in ranked_out:
        if len(pairs) >= max_pairs:
            break
        if out.flight_no in seen_flight_no:
            continue
        rets = ret_by_airport.get(out.arrive_airport, [])
        if not rets:
            continue
        best_ret = rets[0]  # already sorted by return time preference
        if best_ret.flight_no in seen_ret_no:
            continue
        pairs.append(FlightPair(
            pair_id=str(uuid.uuid4()),
            outbound=out,
            return_flight=best_ret,
            total_price=out.price + best_ret.price,
        ))
        seen_flight_no.add(out.flight_no)
        seen_ret_no.add(best_ret.flight_no)

    return pairs


async def _scrape_calendars(
    origin_city: str,
    dest_city: str,
    candidate_dates: list[date],
    flight_client,
) -> list[date]:
    """Query multiple dates concurrently and return dates that have flights, sorted by price."""
    results = await asyncio.gather(
        *[flight_client.search_flights(origin_city, dest_city, d.isoformat()) for d in candidate_dates],
        return_exceptions=True,
    )
    priced: list[tuple[int, date]] = []
    for d, result in zip(candidate_dates, results):
        if isinstance(result, Exception) or result.get("status") != "success":
            continue
        flights = result.get("merged", [])
        if flights:
            min_price = min(f["price"] for f in flights)
            priced.append((min_price, d))
    priced.sort()
    return [d for _, d in priced]


async def _scrape_details(
    origin_city: str,
    dest_city: str,
    chosen_date: date,
    flight_client,
) -> list[Flight]:
    """Fetch full flight list for a single date."""
    result = await flight_client.search_flights(origin_city, dest_city, chosen_date.isoformat())
    if result.get("status") != "success":
        return []
    return [_raw_to_flight(f, chosen_date) for f in result.get("merged", [])]


async def run(state: TravelPlanState, config: RunnableConfig = None) -> dict:
    logger.info("[scrape_flights] start, origin=%r dest=%r dates=%d",
                state.get("origin_airports"), state.get("destination_airports"), len(state.get("depart_dates", [])))
    origin_airports: list[str] = state["origin_airports"]
    dest_airports: list[str] = state["destination_airports"]
    depart_dates: list[date] = state["depart_dates"]
    warnings: list[str] = list(state.get("warnings", []))

    # Resolve tool client — fall back to direct import if no config
    if config is not None:
        flight_client = config["configurable"]["tools"]["flight"]
        city_codes = flight_client.city_codes
    else:
        from tools.flight_tool.scraper import CITY_CODES as city_codes
        from tools.flight_tool.tool import FlightClient
        flight_client = FlightClient()

    airport_to_city: dict[str, str] = {v: k for k, v in city_codes.items()}

    def _resolve(code: str) -> str | None:
        return airport_to_city.get(code)

    origin_cities = [c for c in (_resolve(a) for a in origin_airports) if c]
    dest_cities = [c for c in (_resolve(a) for a in dest_airports) if c]

    if not origin_cities:
        warnings.append(f"出发机场 {origin_airports} 不在支持列表，跳过机票查询")
        return {"flight_pairs": [], "selected_dates": depart_dates[:1], "warnings": warnings}
    if not dest_cities:
        warnings.append(f"目的地机场 {dest_airports} 不在支持列表，跳过机票查询")
        return {"flight_pairs": [], "selected_dates": depart_dates[:1], "warnings": warnings}

    origin_city = origin_cities[0]
    dest_city = dest_cities[0]

    # When multiple candidate dates: use calendar scrape to pick cheapest date
    candidate_dates = depart_dates[:3]
    if len(candidate_dates) > 1:
        sorted_dates = await _scrape_calendars(origin_city, dest_city, candidate_dates, flight_client)
        best_date = sorted_dates[0] if sorted_dates else candidate_dates[0]
    else:
        best_date = candidate_dates[0]

    selected_dates = [best_date]

    outbound_flights = await _scrape_details(origin_city, dest_city, best_date, flight_client)
    return_date = best_date + timedelta(days=state["duration_days"])
    return_flights = await _scrape_details(dest_city, origin_city, return_date, flight_client)

    flight_pairs = _assemble_flight_pairs(
        outbound_flights,
        return_flights,
        depart_time_pref=state.get("depart_time_pref"),
        return_time_pref=state.get("return_time_pref"),
    )

    if not flight_pairs:
        warnings.append("机票数据获取失败，请自行查询各平台")

    # Emit top-3 flight pairs for streaming UI
    emit_fn = (config or {}).get("configurable", {}).get("progress_emit")
    if emit_fn and flight_pairs:
        emit_fn({
            "type": "flight_found",
            "total_found": len(flight_pairs),
            "flights": [
                {
                    "pair_id": fp.pair_id,
                    "outbound_dep": fp.outbound.depart_airport,
                    "outbound_arr": fp.outbound.arrive_airport,
                    "outbound_time": fp.outbound.depart_time.strftime("%H:%M"),
                    "outbound_date": fp.outbound.depart_time.strftime("%Y-%m-%d"),
                    "return_time": fp.return_flight.depart_time.strftime("%H:%M"),
                    "flight_no": fp.outbound.flight_no,
                    "total_price": fp.total_price,
                }
                for fp in flight_pairs[:3]
            ],
        })

    logger.info("[scrape_flights] done, pairs=%d best_date=%s", len(flight_pairs), best_date)
    return {
        "flight_pairs": flight_pairs,
        "selected_dates": selected_dates,
        "warnings": warnings,
    }
