from datetime import datetime
from agent.nodes.compose_output import run, _group_flights_comparison


def make_pair(pair_id, out_airport, ret_airport, out_price, ret_price, platform):
    from models import Flight, FlightPair
    out = Flight(platform=platform, depart_airport=out_airport, arrive_airport="DCY", price=out_price, flight_no="MU1", depart_time=datetime(2026, 7, 1))
    ret = Flight(platform=platform, depart_airport="DCY", arrive_airport=ret_airport, price=ret_price, flight_no="CA1", depart_time=datetime(2026, 7, 8))
    return FlightPair(pair_id=pair_id, outbound=out, return_flight=ret, total_price=out_price + ret_price)


def test_group_flights_comparison_groups_by_route():
    pairs = [
        make_pair("uuid-1", "PVG", "PVG", 980, 760, "ctrip"),
        make_pair("uuid-2", "PVG", "PVG", 1200, 820, "qunar"),
    ]
    groups = _group_flights_comparison(pairs)
    assert len(groups) == 1
    assert len(groups[0]["options"]) == 2
    assert groups[0]["route"] == "PVG → DCY"


def test_run_no_pois_returns_error():
    state = {
        "pois": [],
        "flight_pairs": [],
        "itineraries": [],
        "errors": [],
        "warnings": [],
        "origin": "苏州",
        "origin_airports": ["PVG", "SHA", "NKG"],
    }
    result = run(state)
    assert result["status"] == "error"
    assert "景点" in result["error"]


def test_run_no_flights_degrades_gracefully():
    from models import POI, ItineraryOption, FlightPair, Flight, DayPlan
    poi = POI(poi_id="p1", name="稻城亚丁", coords=(28.67, 100.3), category="自然", tags=[], desc="desc", amap_rating=4.9, sources=[], mention_count=3, platform_count=2, confidence="high")
    pair = make_pair("u1", "PVG", "PVG", 980, 760, "ctrip")
    day = DayPlan(day=1, pois=[poi], transport_note="驾车55分钟", estimated_travel_minutes=55)
    itin = ItineraryOption(option_id="A", summary="summary", flights=pair, days=[day])
    state = {
        "pois": [poi],
        "flight_pairs": [],
        "itineraries": [itin],
        "errors": [],
        "warnings": [],
        "origin": "苏州",
        "origin_airports": ["PVG"],
    }
    result = run(state)
    assert result["status"] == "ok"
    assert len(result["warnings"]) > 0


def test_run_origin_expansion_warning():
    from models import POI
    poi = POI(poi_id="p1", name="稻城亚丁", coords=(28.67, 100.3), category="自然", tags=[], desc="desc", amap_rating=4.9, sources=[], mention_count=3, platform_count=2, confidence="high")
    state = {
        "pois": [poi],
        "flight_pairs": [],
        "itineraries": [],
        "errors": [],
        "warnings": [],
        "origin": "苏州",
        "origin_airports": ["PVG", "SHA", "NKG"],
    }
    result = run(state)
    assert any("苏州" in w for w in result["warnings"])
