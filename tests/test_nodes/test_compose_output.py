from datetime import datetime
from agent.nodes.compose_output import run, _group_flights_comparison


def make_pair(pair_id, out_airport, ret_airport, out_price, ret_price, platform):
    from models import Flight, FlightPair
    out = Flight(platform, out_airport, "DCY", out_price, "MU1", datetime(2026, 7, 1))
    ret = Flight(platform, "DCY", ret_airport, ret_price, "CA1", datetime(2026, 7, 8))
    return FlightPair(pair_id, out, ret, out_price + ret_price)


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
    poi = POI("p1", "稻城亚丁", (28.67, 100.3), "自然", [], "desc", 4.9, [], 3, 2, "high")
    pair = make_pair("u1", "PVG", "PVG", 980, 760, "ctrip")
    day = DayPlan(1, [poi], "驾车55分钟", 55)
    itin = ItineraryOption("A", "summary", pair, [day])
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
    poi = POI("p1", "稻城亚丁", (28.67, 100.3), "自然", [], "desc", 4.9, [], 3, 2, "high")
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
