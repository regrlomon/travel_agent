import pytest
from unittest.mock import AsyncMock, patch
from agent.graph import build_graph


@pytest.mark.asyncio
async def test_graph_builds_without_error():
    graph = build_graph()
    assert graph is not None


@pytest.mark.asyncio
async def test_graph_runs_with_mocked_nodes(mocker):
    mocker.patch("agent.nodes.parse_input.run", new_callable=AsyncMock, return_value={
        "destination_region": "甘孜州",
        "destination_amap_cities": ["513300"],
        "destination_airports": ["CTU", "DCY"],
        "origin_airports": ["PVG"],
        "depart_dates": [],
        "search_keywords": ["川西 攻略"],
    })
    mocker.patch("agent.nodes.discover_pois.run", new_callable=AsyncMock, return_value={
        "pois": [], "travel_time_matrix": {}
    })
    mocker.patch("agent.nodes.scrape_flights.run", new_callable=AsyncMock, return_value={
        "flight_pairs": [], "selected_dates": [], "warnings": []
    })
    mocker.patch("agent.nodes.plan_itinerary.run", new_callable=AsyncMock, return_value={
        "itineraries": []
    })
    mocker.patch("agent.nodes.compose_output.run", return_value={
        "status": "ok", "itineraries": [], "flights_comparison": [], "warnings": [], "errors": []
    })

    graph = build_graph()
    result = await graph.ainvoke({
        "destination": "川西", "origin": "苏州", "duration_days": 7,
        "travelers": 2, "transport_mode": "self_drive", "difficulty_level": "medium",
        "interests": ["徒步"], "depart_date": None,
        "errors": [], "warnings": [], "job_id": "test",
    })
    assert result is not None
