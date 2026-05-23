import pytest
from unittest.mock import AsyncMock, patch
from langgraph.checkpoint.memory import MemorySaver


def test_graph_builds_without_error():
    from agent.graph import build_compiled_graph
    graph = build_compiled_graph(MemorySaver())
    assert graph is not None


def test_graph_has_human_review_node():
    from agent.graph import build_compiled_graph
    graph = build_compiled_graph(MemorySaver())
    assert "human_review" in graph.get_graph().nodes


@pytest.mark.asyncio
async def test_graph_runs_with_mocked_nodes(mocker):
    mocker.patch("agent.nodes.collect_intent.run", new_callable=AsyncMock, return_value={
        "raw_message": "川西自驾7天", "collected": {},
    })
    mocker.patch("agent.nodes.parse_input.run", new_callable=AsyncMock, return_value={
        "destination_region": "甘孜州", "destination_amap_cities": ["513300"],
        "destination_airports": ["CTU"], "origin_airports": ["PVG"],
        "depart_dates": [], "search_keywords": ["川西"],
    })
    mocker.patch("agent.nodes.discover_pois.run", new_callable=AsyncMock, return_value={
        "pois": [], "travel_time_matrix": {}
    })
    mocker.patch("agent.nodes.scrape_flights.run", new_callable=AsyncMock, return_value={
        "flight_pairs": [], "selected_dates": [], "warnings": []
    })
    mocker.patch("agent.nodes.human_review.run", new_callable=AsyncMock, return_value={
        "user_flight_choice": None, "user_poi_prefs": None
    })
    mocker.patch("agent.nodes.plan_itinerary.run", new_callable=AsyncMock, return_value={
        "itineraries": []
    })
    mocker.patch("agent.nodes.compose_output.run", return_value={
        "status": "ok", "itineraries": [], "flights_comparison": [], "warnings": [], "errors": []
    })

    from agent.graph import build_compiled_graph
    from langgraph.checkpoint.memory import MemorySaver
    graph = build_compiled_graph(MemorySaver())
    result = await graph.ainvoke(
        {"raw_message": "川西自驾7天", "errors": [], "warnings": [], "job_id": "test"},
        config={"configurable": {"thread_id": "test", "tools": {}}},
    )
    assert result is not None
