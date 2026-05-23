import pytest
from datetime import date
from unittest.mock import AsyncMock
from agent.nodes.scrape_flights import run, _assemble_flight_pairs


def make_state():
    return {
        "origin_airports": ["PVG", "NKG"],
        "destination_airports": ["CTU", "DCY"],
        "depart_dates": [date(2026, 7, 1), date(2026, 7, 2), date(2026, 7, 3)],
        "duration_days": 7,
        "errors": [], "warnings": [], "job_id": "test",
    }


def test_assemble_flight_pairs_valid_only():
    from models import Flight
    from datetime import datetime
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
