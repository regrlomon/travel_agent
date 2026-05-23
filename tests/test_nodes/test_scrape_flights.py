import pytest
from datetime import date, datetime
from unittest.mock import AsyncMock
from agent.nodes.scrape_flights import run, _assemble_flight_pairs, _parse_time_pref, _rank_by_time_pref
from models import Flight


def make_state():
    return {
        "origin_airports": ["PVG", "NKG"],
        "destination_airports": ["CTU", "DCY"],
        "depart_dates": [date(2026, 7, 1), date(2026, 7, 2), date(2026, 7, 3)],
        "duration_days": 7,
        "errors": [], "warnings": [], "job_id": "test",
    }


def test_assemble_flight_pairs_valid_only():
    out1 = Flight(platform="ctrip", depart_airport="PVG", arrive_airport="DCY", price=980, flight_no="MU1", depart_time=datetime(2026, 7, 1))
    out2 = Flight(platform="ctrip", depart_airport="PVG", arrive_airport="CTU", price=650, flight_no="MU2", depart_time=datetime(2026, 7, 1))
    ret1 = Flight(platform="ctrip", depart_airport="DCY", arrive_airport="PVG", price=760, flight_no="CA1", depart_time=datetime(2026, 7, 8))
    ret2 = Flight(platform="ctrip", depart_airport="CTU", arrive_airport="PVG", price=600, flight_no="CA2", depart_time=datetime(2026, 7, 8))
    ret_invalid = Flight(platform="ctrip", depart_airport="SHA", arrive_airport="PVG", price=500, flight_no="CA3", depart_time=datetime(2026, 7, 8))  # SHA不匹配任何出发地

    pairs = _assemble_flight_pairs([out1, out2], [ret1, ret2, ret_invalid])

    # Only pairs where ret.depart_airport == out.arrive_airport
    for p in pairs:
        assert p.return_flight.depart_airport == p.outbound.arrive_airport
    assert len(pairs) == 2  # out1+ret1, out2+ret2
    assert all(p.pair_id for p in pairs)  # UUID assigned


@pytest.mark.asyncio
async def test_run_skips_calendar_for_single_date(mocker):
    single_date_state = {**make_state(), "depart_dates": [date(2026, 7, 1)]}
    mock_calendar = mocker.patch("agent.nodes.scrape_flights._scrape_calendars", new_callable=AsyncMock, return_value=[])
    mocker.patch("agent.nodes.scrape_flights._scrape_details", new_callable=AsyncMock, return_value=[])

    await run(single_date_state)
    mock_calendar.assert_not_called()


@pytest.mark.asyncio
async def test_run_warns_when_no_flights(mocker):
    mocker.patch("agent.nodes.scrape_flights._scrape_calendars", new_callable=AsyncMock, return_value=[date(2026, 7, 1)])
    mocker.patch("agent.nodes.scrape_flights._scrape_details", new_callable=AsyncMock, return_value=[])
    state = make_state()
    result = await run(state)
    assert result["flight_pairs"] == []
    assert len(result["warnings"]) > 0


def _flight(hour: int, minute: int = 0) -> Flight:
    return Flight(
        platform="test", depart_airport="PVG", arrive_airport="CTU",
        price=800, flight_no="MU1",
        depart_time=datetime(2026, 7, 1, hour, minute),
    )


def test_parse_time_pref_morning():
    after, before = _parse_time_pref("上午")
    assert after == 6 * 60
    assert before == 12 * 60


def test_parse_time_pref_afternoon():
    after, before = _parse_time_pref("下午")
    assert after == 12 * 60
    assert before == 18 * 60


def test_parse_time_pref_around_nine():
    after, before = _parse_time_pref("9点左右")
    assert after == 8 * 60
    assert before == 10 * 60


def test_parse_time_pref_not_late():
    result = _parse_time_pref("不要太晚")
    assert result is not None
    after_min, before_min = result
    assert after_min == 0        # no lower bound (fly anytime from midnight)
    assert before_min == 20 * 60  # cap at 20:00


def test_parse_time_pref_no_preference():
    assert _parse_time_pref(None) is None
    assert _parse_time_pref("") is None
    assert _parse_time_pref("随意") is None
    assert _parse_time_pref("不限") is None


def test_rank_by_time_pref_sorts_closest_first():
    flights = [_flight(14), _flight(9, 15), _flight(6)]
    ranked = _rank_by_time_pref(flights, "9点左右")
    assert ranked[0].depart_time.hour == 9


def test_rank_by_time_pref_no_pref_unchanged():
    flights = [_flight(14), _flight(9), _flight(6)]
    ranked = _rank_by_time_pref(flights, None)
    assert [f.depart_time.hour for f in ranked] == [14, 9, 6]


def test_rank_by_time_pref_no_hard_filter():
    """Even if no flight is in window, all are returned."""
    flights = [_flight(22), _flight(23)]
    ranked = _rank_by_time_pref(flights, "上午")
    assert len(ranked) == 2


def make_flight(hour: int, airport_pair: tuple[str, str], price: int = 800, flight_no: str = "MU1") -> Flight:
    dep, arr = airport_pair
    return Flight(
        platform="test", depart_airport=dep, arrive_airport=arr,
        price=price, flight_no=flight_no,
        depart_time=datetime(2026, 7, 1, hour, 0),
    )


def test_assemble_pairs_time_pref_wins_over_price():
    """When depart_time_pref='上午', the first returned pair's outbound should depart in the morning."""
    out_afternoon = make_flight(14, ("CAN", "LXA"), price=500, flight_no="Z1")
    out_morning_exp = make_flight(9,  ("CAN", "LXA"), price=900, flight_no="Z2")
    out_morning_cheap = make_flight(8, ("CAN", "LXA"), price=600, flight_no="Z3")
    ret = make_flight(16, ("LXA", "CAN"), price=600, flight_no="R1")

    pairs = _assemble_flight_pairs(
        [out_afternoon, out_morning_exp, out_morning_cheap],
        [ret],
        depart_time_pref="上午",
    )

    assert pairs[0].outbound.depart_time.hour < 12
    for p in pairs:
        assert p.return_flight.depart_airport == p.outbound.arrive_airport


def test_assemble_pairs_max_3():
    """返回数量上限为 3。"""
    outbounds = [make_flight(h, ("CAN", "LXA"), flight_no=f"O{h}") for h in range(6, 12)]
    ret = make_flight(16, ("LXA", "CAN"), flight_no="R1")
    pairs = _assemble_flight_pairs(outbounds, [ret], depart_time_pref=None)
    assert len(pairs) <= 3


def test_assemble_pairs_no_pref_unchanged_behavior():
    """无偏好时：有效配对，pair_id 不为空。"""
    out1 = make_flight(7, ("PVG", "DCY"), flight_no="A1")
    out2 = make_flight(9, ("PVG", "CTU"), flight_no="A2")
    ret1 = make_flight(16, ("DCY", "PVG"), flight_no="B1")
    ret2 = make_flight(18, ("CTU", "PVG"), flight_no="B2")
    pairs = _assemble_flight_pairs([out1, out2], [ret1, ret2])
    assert len(pairs) == 2
    for p in pairs:
        assert p.pair_id
        assert p.return_flight.depart_airport == p.outbound.arrive_airport
