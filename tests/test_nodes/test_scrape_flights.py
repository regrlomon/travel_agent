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
    out1 = Flight("ctrip", "PVG", "DCY", 980, "MU1", datetime(2026, 7, 1))
    out2 = Flight("ctrip", "PVG", "CTU", 650, "MU2", datetime(2026, 7, 1))
    ret1 = Flight("ctrip", "DCY", "PVG", 760, "CA1", datetime(2026, 7, 8))
    ret2 = Flight("ctrip", "CTU", "PVG", 600, "CA2", datetime(2026, 7, 8))
    ret_invalid = Flight("ctrip", "SHA", "PVG", 500, "CA3", datetime(2026, 7, 8))  # SHA not in dest_airports

    dest_airports = {"DCY", "CTU"}
    pairs = _assemble_flight_pairs([out1, out2], [ret1, ret2, ret_invalid], dest_airports)

    # Only pairs where both outbound.arrive and return.depart are in dest_airports
    for p in pairs:
        assert p.outbound.arrive_airport in dest_airports
        assert p.return_flight.depart_airport in dest_airports
    assert len(pairs) == 2  # out1+ret1, out2+ret2 (cheapest per combo)
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
