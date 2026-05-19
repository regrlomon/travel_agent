import pytest
from unittest.mock import AsyncMock, patch
from agent.nodes.discover_pois import run, _dedup_pois, _compute_confidence


def make_state():
    return {
        "destination_amap_cities": ["513300"],
        "destination_region": "甘孜州",
        "search_keywords": ["川西 攻略", "稻城亚丁 游记"],
        "transport_mode": "self_drive",
        "difficulty_level": "medium",
        "interests": ["徒步"],
        "job_id": "test",
        "errors": [],
        "warnings": [],
    }


def test_dedup_pois_merges_nearby():
    from models import POI, POISource
    src = POISource("xiaohongshu", 1, 0.8, True)
    p1 = POI("id1", "稻城亚丁", (28.670, 100.300), "自然", [], "desc", 4.9, [src], 1, 1, "medium")
    p2 = POI("id2", "稻城亚丁景区", (28.671, 100.301), "自然", [], "desc2", 4.8, [src], 1, 1, "medium")
    result = _dedup_pois([p1, p2])
    assert len(result) == 1
    assert result[0].mention_count == 2


def test_compute_confidence_high():
    assert _compute_confidence(mention_count=4, platform_count=2) == "high"


def test_compute_confidence_medium():
    assert _compute_confidence(mention_count=1, platform_count=1, amap_only=True) == "medium"


def test_compute_confidence_low():
    assert _compute_confidence(mention_count=1, platform_count=1, amap_only=False) == "low"


@pytest.mark.asyncio
async def test_run_returns_pois_and_matrix(mocker):
    mocker.patch("agent.nodes.discover_pois._fetch_amap_pois", new_callable=AsyncMock, return_value=[
        {"id": "a1", "name": "稻城亚丁", "location": "100.3,28.67", "typecode": "110000", "biz_ext": {"rating": "4.9"}}
    ])
    mocker.patch("agent.nodes.discover_pois._fetch_article_pois", new_callable=AsyncMock, return_value=[])
    mocker.patch("agent.nodes.discover_pois._score_sources_batch", new_callable=AsyncMock, return_value={})
    mocker.patch("agent.nodes.discover_pois._build_travel_time_matrix", new_callable=AsyncMock, return_value={})

    result = await run(make_state())
    assert len(result["pois"]) >= 1
    assert "travel_time_matrix" in result
