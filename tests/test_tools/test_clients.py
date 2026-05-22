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
