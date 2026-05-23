import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from tools.amap import get_district_codes, search_pois, get_driving_time, check_transit_reachable


@pytest.fixture
def mock_httpx_get():
    with patch("httpx.AsyncClient") as MockClient:
        client = MagicMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = client
        yield client


@pytest.mark.asyncio
async def test_get_district_codes(mock_httpx_get):
    mock_httpx_get.get = AsyncMock(return_value=MagicMock(
        json=lambda: {"status": "1", "districts": [{"adcode": "513300", "name": "甘孜藏族自治州"}]}
    ))
    result = await get_district_codes(["甘孜藏族自治州"], api_key="fake")
    assert result == {"甘孜藏族自治州": "513300"}


@pytest.mark.asyncio
async def test_search_pois_returns_list(mock_httpx_get):
    mock_httpx_get.get = AsyncMock(return_value=MagicMock(
        json=lambda: {"status": "1", "pois": [{"id": "1", "name": "稻城亚丁", "location": "100.3,28.67", "type": "风景名胜", "biz_ext": {"rating": "4.9"}}]}
    ))
    pois = await search_pois(["513300"], "景点", api_key="fake")
    assert len(pois) == 1
    assert pois[0]["name"] == "稻城亚丁"


@pytest.mark.asyncio
async def test_get_driving_time_returns_minutes(mock_httpx_get):
    mock_httpx_get.get = AsyncMock(return_value=MagicMock(
        json=lambda: {"status": "1", "route": {"paths": [{"duration": "3300"}]}}
    ))
    minutes = await get_driving_time((28.67, 100.3), (30.07, 102.72), api_key="fake")
    assert minutes == 55


@pytest.mark.asyncio
async def test_check_transit_reachable_true(mock_httpx_get):
    mock_httpx_get.get = AsyncMock(return_value=MagicMock(
        json=lambda: {"status": "1", "route": {"transits": [{"duration": "4200"}]}}
    ))
    ok = await check_transit_reachable((28.67, 100.3), (30.07, 102.72), "513300", api_key="fake")
    assert ok is True


@pytest.mark.asyncio
async def test_check_transit_reachable_false_over_limit(mock_httpx_get):
    mock_httpx_get.get = AsyncMock(return_value=MagicMock(
        json=lambda: {"status": "1", "route": {"transits": [{"duration": "10800"}]}}
    ))
    ok = await check_transit_reachable((28.67, 100.3), (30.07, 102.72), "513300", api_key="fake")
    assert ok is False


def test_category_types_covers_all_categories():
    from tools.amap import CATEGORY_TYPES
    assert "景点" in CATEGORY_TYPES
    assert "美食" in CATEGORY_TYPES
    assert "娱乐" in CATEGORY_TYPES
    assert "110000" in CATEGORY_TYPES["景点"]
    assert "050000" in CATEGORY_TYPES["美食"]
