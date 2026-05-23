from datetime import datetime
from models import POI, POISource, Flight, FlightPair, DayPlan, ItineraryOption


def test_poi_confidence_high():
    src = POISource(platform="xiaohongshu", mention_count=3, llm_credibility=0.8, has_negative_reviews=True)
    poi = POI(
        poi_id="p1", name="稻城亚丁", coords=(29.0, 100.0),
        category="自然景观", tags=["自然风光", "徒步"],
        desc="三神山", amap_rating=4.9,
        sources=[src], mention_count=3, platform_count=2, confidence="high",
    )
    assert poi.confidence == "high"
    assert poi.tags == ["自然风光", "徒步"]


def test_flight_pair_total_price():
    outbound = Flight(platform="携程", depart_airport="上海浦东 PVG", arrive_airport="稻城亚丁 DCY", price=980, flight_no="MU2345", depart_time=datetime(2026, 7, 1, 8, 30))
    ret = Flight(platform="去哪儿", depart_airport="成都双流 CTU", arrive_airport="上海浦东 PVG", price=760, flight_no="CA1235", depart_time=datetime(2026, 7, 8, 14, 0))
    pair = FlightPair(pair_id="uuid-test", outbound=outbound, return_flight=ret, total_price=1740)
    assert pair.total_price == outbound.price + ret.price


def test_itinerary_option_structure():
    outbound = Flight(platform="携程", depart_airport="PVG", arrive_airport="DCY", price=980, flight_no="MU2345", depart_time=datetime(2026, 7, 1))
    ret = Flight(platform="携程", depart_airport="CTU", arrive_airport="PVG", price=760, flight_no="CA1235", depart_time=datetime(2026, 7, 8))
    pair = FlightPair(pair_id="uuid-1", outbound=outbound, return_flight=ret, total_price=1740)
    day = DayPlan(day=1, pois=[], transport_note="驾车约55分钟", estimated_travel_minutes=55)
    opt = ItineraryOption(option_id="A", summary="DCY进CTU出", flights=pair, days=[day])
    assert opt.option_id == "A"
    assert opt.flights.total_price == 1740
