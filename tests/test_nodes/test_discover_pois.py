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
    src = POISource(platform="xiaohongshu", mention_count=1, llm_credibility=0.8, has_negative_reviews=True)
    p1 = POI(poi_id="id1", name="稻城亚丁", coords=(28.670, 100.300), category="自然", tags=[], desc="desc", amap_rating=4.9, sources=[src], mention_count=1, platform_count=1, confidence="medium")
    p2 = POI(poi_id="id2", name="稻城亚丁景区", coords=(28.671, 100.301), category="自然", tags=[], desc="desc2", amap_rating=4.8, sources=[src], mention_count=1, platform_count=1, confidence="medium")
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
    mocker.patch("agent.nodes.discover_pois._build_travel_time_matrix", new_callable=AsyncMock, return_value={})

    result = await run(make_state())
    assert len(result["pois"]) >= 1
    assert "travel_time_matrix" in result


def test_match_pois_counts_mentions():
    from agent.nodes.discover_pois import _match_pois_in_articles
    articles = [
        {"platform": "xiaohongshu", "content": "今天去了西湖，断桥真的超美，推荐！"},
        {"platform": "xiaohongshu", "content": "断桥排队好长，有点失望，西湖还行"},
    ]
    result = _match_pois_in_articles(articles, ["西湖", "断桥", "雷峰塔"])
    assert result["西湖"]["mention_count"] == 2
    assert result["断桥"]["mention_count"] == 2
    assert result["断桥"]["has_negative"] is True
    assert result["西湖"]["has_negative"] is True
    assert "雷峰塔" not in result


def test_match_pois_skips_ad_articles():
    from agent.nodes.discover_pois import _match_pois_in_articles
    articles = [
        {"platform": "xiaohongshu", "content": "灵隐寺探店合作联系我，风景很美"},
    ]
    result = _match_pois_in_articles(articles, ["灵隐寺"])
    assert "灵隐寺" not in result


def test_match_pois_empty_articles():
    from agent.nodes.discover_pois import _match_pois_in_articles
    result = _match_pois_in_articles([], ["西湖"])
    assert result == {}
