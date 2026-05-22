# agent/nodes/compose_output.py
from agent.state import TravelPlanState
from models import FlightPair, ItineraryOption

# Cities known to not have their own airport
NO_AIRPORT_CITIES = {"苏州", "无锡", "嘉兴", "佛山", "东莞", "中山"}


def _group_flights_comparison(pairs: list[FlightPair]) -> list[dict]:
    """Group FlightPairs by (outbound route, date) for cross-platform comparison."""
    groups: dict[tuple, dict] = {}
    for fp in pairs:
        key = (fp.outbound.depart_airport, fp.outbound.arrive_airport, fp.outbound.depart_time.date())
        if key not in groups:
            groups[key] = {
                "route": f"{fp.outbound.depart_airport} → {fp.outbound.arrive_airport}",
                "date": str(key[2]),
                "options": [],
            }
        groups[key]["options"].append({
            "pair_id": fp.pair_id,
            "platform": fp.outbound.platform,
            "outbound": fp.outbound.price,
            "return": fp.return_flight.price,
            "total": fp.total_price,
        })
    return list(groups.values())


def run(state: TravelPlanState, config=None) -> dict:
    pois = state.get("pois", [])
    flight_pairs = state.get("flight_pairs", [])
    itineraries = state.get("itineraries", [])
    warnings = list(state.get("warnings", []))
    errors = state.get("errors", [])

    # Hard failure: no POIs at all
    if not pois:
        return {"status": "error", "error": "无法获取目的地景点数据", "warnings": warnings}

    # Warn about no-airport origin city
    origin = state.get("origin", "")
    if origin in NO_AIRPORT_CITIES:
        airports = state.get("origin_airports", [])
        warnings.append(f"{origin}无机场，已搜索{'、'.join(airports)}出发航班")

    # Warn about missing flight data
    if not flight_pairs:
        warnings.append("机票数据获取失败，请自行查询各平台")
    elif len(set(fp.outbound.platform for fp in flight_pairs)) == 1:
        warnings.append(f"仅{flight_pairs[0].outbound.platform}数据可用，价格对比不完整")

    flights_comparison = _group_flights_comparison(flight_pairs)

    return {
        "status": "ok",
        "itineraries": [_serialize_itinerary(i) for i in itineraries],
        "flights_comparison": flights_comparison,
        "warnings": warnings,
        "errors": errors,
    }


def _serialize_itinerary(opt: ItineraryOption) -> dict:
    fp = opt.flights
    return {
        "option_id": opt.option_id,
        "summary": opt.summary,
        "flights": {
            "pair_id": fp.pair_id,
            "outbound": _serialize_flight(fp.outbound),
            "return_flight": _serialize_flight(fp.return_flight),
            "total_price": fp.total_price,
        },
        "days": [
            {
                "day": d.day,
                "pois": [{"poi_id": p.poi_id, "name": p.name, "coords": p.coords,
                           "category": p.category, "desc": p.desc, "confidence": p.confidence} for p in d.pois],
                "transport_note": d.transport_note,
                "estimated_travel_minutes": d.estimated_travel_minutes,
            }
            for d in opt.days
        ],
    }


def _serialize_flight(f) -> dict:
    return {
        "platform": f.platform,
        "depart_airport": f.depart_airport,
        "arrive_airport": f.arrive_airport,
        "price": f.price,
        "flight_no": f.flight_no,
        "depart_time": f.depart_time.isoformat(),
    }
