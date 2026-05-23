import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def test_amap_client_has_required_methods():
    from tools.amap import AmapClient
    client = AmapClient(api_key="fake")
    assert hasattr(client, "get_district_codes")
    assert hasattr(client, "search_pois")
    assert hasattr(client, "get_driving_time")
    assert hasattr(client, "check_transit_reachable")


def test_tavily_client_has_required_methods():
    from tools.tavily import TavilyClient
    client = TavilyClient(api_key="fake")
    assert hasattr(client, "search_travel_articles")


def test_xhs_client_has_required_methods():
    from tools.xhs_tool import XhsClient
    client = XhsClient()
    assert hasattr(client, "scrape_notes")


def test_flight_client_has_required_methods():
    from tools.flight_tool.tool import FlightClient
    client = FlightClient()
    assert hasattr(client, "search_flights")
    assert hasattr(client, "city_codes")


@pytest.mark.asyncio
async def test_amap_client_delegates_to_module_function(mocker):
    mock_fn = mocker.patch("tools.amap.get_district_codes", new_callable=AsyncMock,
                           return_value={"甘孜藏族自治州": "513300"})
    from tools.amap import AmapClient
    client = AmapClient(api_key="test_key")
    result = await client.get_district_codes(["甘孜藏族自治州"])
    assert result == {"甘孜藏族自治州": "513300"}
    mock_fn.assert_called_once_with(["甘孜藏族自治州"], api_key="test_key")


@pytest.mark.asyncio
async def test_tavily_client_delegates_to_module_function(mocker):
    mock_fn = mocker.patch("tools.tavily.search_travel_articles", new_callable=AsyncMock,
                           return_value=[{"content": "川西攻略"}])
    from tools.tavily import TavilyClient
    client = TavilyClient(api_key="test_key")
    result = await client.search_travel_articles(["川西 攻略"])
    assert len(result) == 1
    mock_fn.assert_called_once_with(["川西 攻略"], api_key="test_key")


@pytest.mark.asyncio
async def test_flight_client_delegates_to_run_async(mocker):
    mock_fn = mocker.patch("tools.flight_tool.tool.run_async", new_callable=AsyncMock,
                           return_value={"status": "success", "merged": []})
    from tools.flight_tool.tool import FlightClient
    client = FlightClient()
    result = await client.search_flights("上海", "成都", "2026-07-01")
    assert result["status"] == "success"
    mock_fn.assert_called_once()


def test_build_tools_returns_all_keys():
    from agent.tools_container import build_tools
    tools = build_tools(overrides={
        "amap": "mock_amap",
        "tavily": "mock_tavily",
        "xhs": "mock_xhs",
        "flight": "mock_flight",
    })
    assert set(tools.keys()) == {"amap", "tavily", "xhs", "flight", "airports"}


def test_build_tools_override_replaces_default():
    from agent.tools_container import build_tools
    mock = object()
    tools = build_tools(overrides={"amap": mock})
    assert tools["amap"] is mock
