import asyncio
import logging
import uuid
from datetime import date, datetime, timedelta

from langchain_core.runnables import RunnableConfig

from agent.state import TravelPlanState
from models import Flight, FlightPair

logger = logging.getLogger(__name__)


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
) -> list[FlightPair]:
    """Build cheapest FlightPair per route combo from outbound and return lists."""
    best: dict[tuple, FlightPair] = {}
    for out in outbound_flights:
        for ret in return_flights:
            if ret.depart_airport != out.arrive_airport:
                continue
            key = (out.depart_airport, out.arrive_airport)
            total = out.price + ret.price
            existing = best.get(key)
            if existing is None or total < existing.total_price:
                best[key] = FlightPair(
                    pair_id=str(uuid.uuid4()),
                    outbound=out,
                    return_flight=ret,
                    total_price=total,
                )
    return list(best.values())


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

    flight_pairs = _assemble_flight_pairs(outbound_flights, return_flights)

    if not flight_pairs:
        warnings.append("机票数据获取失败，请自行查询各平台")

    logger.info("[scrape_flights] done, pairs=%d best_date=%s", len(flight_pairs), best_date)
    return {
        "flight_pairs": flight_pairs,
        "selected_dates": selected_dates,
        "warnings": warnings,
    }
