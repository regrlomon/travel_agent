import asyncio
import uuid
from datetime import date
from agent.state import TravelPlanState
from models import Flight, FlightPair
from tools.flight_scraper import scrape_price_calendar, scrape_flight_details

PLATFORMS = ["ctrip", "qunar"]


async def _scrape_calendars(
    origin_airports: list[str],
    dest_airports: list[str],
    date_range: list[date],
    top_n: int = 3,
) -> list[date]:
    """Fetch price calendars for all origin×dest pairs, return top_n cheapest dates."""
    prices: dict[date, int] = {}
    for origin in origin_airports:
        for dest in dest_airports:
            for platform in PLATFORMS:
                cal = await scrape_price_calendar(origin, dest, platform)
                for d, p in cal.items():
                    if d in date_range:
                        prices[d] = min(prices.get(d, p), p)
    sorted_dates = sorted(prices.keys(), key=lambda d: prices[d])
    return sorted_dates[:top_n]


async def _scrape_details(
    origin_airports: list[str],
    dest_airports: list[str],
    selected_dates: list[date],
) -> list[Flight]:
    """Scrape outbound and return flights for selected dates."""
    flights: list[Flight] = []
    for depart_date in selected_dates:
        for origin in origin_airports:
            for dest in dest_airports:
                for platform in PLATFORMS:
                    details = await scrape_flight_details(origin, dest, depart_date, platform)
                    flights.extend(details)
    return flights


def _assemble_flight_pairs(
    outbound_flights: list[Flight],
    return_flights: list[Flight],
    dest_airports: set[str],
) -> list[FlightPair]:
    """Build valid FlightPairs: both outbound.arrive and return.depart must be in dest_airports.
    Keep cheapest per (outbound_airport, return_airport) combination."""
    best: dict[tuple, FlightPair] = {}
    for out in outbound_flights:
        if out.arrive_airport not in dest_airports:
            continue
        for ret in return_flights:
            if ret.depart_airport not in dest_airports:
                continue
            # Return must depart from the same airport as outbound arrives at
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


async def run(state: TravelPlanState) -> dict:
    origin_airports = state["origin_airports"]
    dest_airports = state["destination_airports"]
    depart_dates = state["depart_dates"]
    dest_set = set(dest_airports)
    warnings = list(state.get("warnings", []))

    # Step 1: date selection
    if len(depart_dates) == 1:
        selected_dates = depart_dates
        outbound_dates = depart_dates
    else:
        selected_dates = await _scrape_calendars(origin_airports, dest_airports, depart_dates)
        if not selected_dates:
            selected_dates = depart_dates[:3]
            warnings.append("价格日历爬取失败，使用前3个备选日期")
        outbound_dates = selected_dates

    # Step 2: detail scraping
    from datetime import timedelta
    return_dates = [d + timedelta(days=state["duration_days"]) for d in outbound_dates]
    outbound_flights = await _scrape_details(origin_airports, dest_airports, outbound_dates)
    return_flights = await _scrape_details(dest_airports, origin_airports, return_dates)

    # Step 3: assemble pairs
    flight_pairs = _assemble_flight_pairs(outbound_flights, return_flights, dest_set)

    if not flight_pairs:
        warnings.append("机票数据获取失败，请自行查询各平台")

    return {
        "flight_pairs": flight_pairs,
        "selected_dates": selected_dates,
        "warnings": warnings,
    }
