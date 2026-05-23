# agent/nodes/discover_pois.py
import asyncio
import json
import logging
import math
import os
import re
import uuid
from typing import Optional
from langchain_core.runnables import RunnableConfig
from agent.state import TravelPlanState
from agent import extract_json
from agent.llm import get_llm
from models import POI, POISource

logger = logging.getLogger(__name__)

EARTH_RADIUS_KM = 6371.0
MAX_POIS = 40
MAX_MATRIX_DISTANCE_KM = 50.0

_NEGATIVE_KW = ["排队", "坑", "不推荐", "踩雷", "失望", "太贵", "避雷", "后悔", "人太多"]
_AD_KW = ["合作", "探店", "种草推广", "联系我", "私信", "带货"]

AMAP_CATEGORIES = ["景点", "美食", "娱乐"]
CATEGORY_KEYWORDS = {
    "景点": "{region} 景点攻略",
    "美食": "{region} 美食推荐",
    "娱乐": "{region} 娱乐活动",
}


def _clean_content(title: str, content: str) -> str:
    """规范化文章文本：合并标题+正文，去除噪音。"""
    text = f"{title} {content}" if title else content
    text = re.sub(r'#\S+', '', text)         # hashtags
    text = re.sub(r'@\S+', '', text)         # @mentions
    text = re.sub(r'https?://\S+', '', text) # URLs
    text = re.sub(r'\s+', ' ', text)         # 折叠空白
    return text.strip()


def _haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1 = math.radians(a[0]), math.radians(a[1])
    lat2, lon2 = math.radians(b[0]), math.radians(b[1])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(h))


def _dedup_pois(pois: list[POI], radius_m: float = 200.0) -> list[POI]:
    """Merge POIs within radius_m metres of each other."""
    merged: list[POI] = []
    for poi in pois:
        close = None
        for m in merged:
            if _haversine_km(poi.coords, m.coords) * 1000 <= radius_m or poi.name == m.name:
                close = m
                break
        if close:
            close.mention_count += poi.mention_count
            close.sources.extend(poi.sources)
            close.sources = close.sources[:40]
        else:
            merged.append(poi)
    return merged


def _match_pois_in_articles(articles: list[dict], known_names: list[str]) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for article in articles:
        text = article["content"]
        if any(kw in text for kw in _AD_KW):
            continue
        has_negative = any(kw in text for kw in _NEGATIVE_KW)
        for name in known_names:
            if name in text:
                if name not in result:
                    result[name] = {"mention_count": 0, "has_negative": False}
                result[name]["mention_count"] += 1
                if has_negative:
                    result[name]["has_negative"] = True
    return result


def _compute_confidence(mention_count: int, platform_count: int, amap_only: bool = False) -> str:
    if mention_count >= 3 and platform_count >= 2:
        return "high"
    if amap_only:
        return "medium"
    return "low"


async def _fetch_amap_pois(city_codes: list[str], keywords: str = "景点", tools: dict | None = None) -> list[dict]:
    try:
        if tools is not None:
            return await tools["amap"].search_pois(city_codes, keywords)
        from tools.amap import search_pois
        return await search_pois(city_codes, keywords, api_key=os.getenv("AMAP_API_KEY", ""))
    except Exception:
        logger.exception("高德 search_pois failed, city_codes=%r keywords=%r", city_codes, keywords)
        raise


async def _fetch_article_pois(keywords: list[str], tools: dict | None = None) -> list[dict]:
    """Fetch raw article text from XHS and Tavily, return as list of {platform, content}."""
    results = []
    if tools is not None:
        try:
            xhs_notes = await tools["xhs"].scrape_notes(keywords)
        except Exception:
            logger.exception("XHS scrape_notes failed, keywords=%r", keywords)
            raise
        results.extend(
            {"platform": "xiaohongshu", "content": _clean_content(n.get("title", ""), n["content"])}
            for n in xhs_notes
        )
        try:
            tavily = await tools["tavily"].search_travel_articles(keywords)
        except Exception:
            logger.exception("Tavily search failed, keywords=%r", keywords)
            raise
        results.extend(
            {"platform": "mafengwo", "content": _clean_content(a.get("title", ""), a["content"])}
            for a in tavily
        )
    else:
        from tools.xhs_tool import search_xhs, DEFAULT_COUNT
        from tools.tavily import search_travel_articles
        cookie = os.getenv("XHS_COOKIE", "")
        for keyword in keywords:
            notes = await asyncio.to_thread(search_xhs, keyword, DEFAULT_COUNT, True, cookie)
            results.extend(
                {"platform": "xiaohongshu", "content": _clean_content(n.get("title", ""), n["content"])}
                for n in notes
            )
        tavily = await search_travel_articles(keywords, api_key=os.getenv("TAVILY_API_KEY", ""))
        results.extend(
            {"platform": "mafengwo", "content": _clean_content(a.get("title", ""), a["content"])}
            for a in tavily
        )
    return results


async def _build_travel_time_matrix(pois: list[POI], tools: dict | None = None) -> dict[str, int]:
    """Compute driving times using batch API: one concurrent request per destination POI.
    Reduces API calls from O(n²) individual calls to O(n) concurrent batch calls.
    """
    # Build work list: (dest_index, [(origin_index, origin_poi)])
    work = []
    for j, dest in enumerate(pois):
        close_origins = [
            (i, pois[i])
            for i in range(j)
            if _haversine_km(pois[i].coords, dest.coords) <= MAX_MATRIX_DISTANCE_KM
        ]
        if close_origins:
            work.append((j, dest, close_origins))

    if not work:
        return {}

    async def fetch_one(dest, origins_with_idx):
        coords = [poi.coords for _, poi in origins_with_idx]
        try:
            if tools is not None:
                return await tools["amap"].get_driving_time_batch(coords, dest.coords)
            else:
                from tools.amap import get_driving_time_batch
                return await get_driving_time_batch(coords, dest.coords, api_key=os.getenv("AMAP_API_KEY", ""))
        except Exception:
            logger.exception("高德 get_driving_time_batch failed, dest=%r", dest.poi_id)
            return [None] * len(origins_with_idx)

    results = await asyncio.gather(*[fetch_one(dest, origins) for _, dest, origins in work])

    matrix: dict[str, int] = {}
    for (_, dest, origins_with_idx), times in zip(work, results):
        for (_, origin), minutes in zip(origins_with_idx, times):
            if minutes is not None:
                matrix[f"{origin.poi_id[:8]}|{dest.poi_id[:8]}"] = minutes

    logger.info("[travel_time_matrix] %d pairs via %d concurrent batch calls", len(matrix), len(work))
    return matrix


async def run(state: TravelPlanState, config: RunnableConfig = None) -> dict:
    logger.info("[discover_pois] start, city_codes=%r keywords=%r", state.get("destination_amap_cities"), state.get("search_keywords"))
    tools = config["configurable"]["tools"] if config else None
    city_codes = state["destination_amap_cities"]
    keywords = state.get("search_keywords", [])

    # 1. Fetch raw POIs from 高德
    raw_amap = await _fetch_amap_pois(city_codes, tools=tools)

    # 2. Fetch articles (note: string matching extraction replaces LLM batch scoring)
    articles = await _fetch_article_pois(keywords, tools=tools)

    # 3. Build POI objects from 高德 data
    pois: list[POI] = []
    for raw in raw_amap:
        loc = raw.get("location", "0,0").split(",")
        coords = (float(loc[1]), float(loc[0]))  # lat, lng
        p = POI(
            poi_id=str(uuid.uuid4()),
            name=raw["name"],
            coords=coords,
            category=raw.get("type", "景点"),
            tags=[],
            desc=raw.get("address", "") if isinstance(raw.get("address"), str) else "",
            amap_rating=float(raw.get("biz_ext", {}).get("rating") or 0),
            sources=[],
            mention_count=1,
            platform_count=1,
            confidence="medium",  # amap_only default
        )
        pois.append(p)

    # 4. Recompute confidence for all POIs
    for p in pois:
        p.confidence = _compute_confidence(
            p.mention_count,
            p.platform_count,
            amap_only=(p.amap_rating > 0 and not p.sources),
        )

    # 5. Dedup and truncate to TOP 40
    pois = _dedup_pois(pois)
    pois.sort(key=lambda p: ({"high": 0, "medium": 1, "low": 2}[p.confidence], -p.amap_rating))
    pois = pois[:MAX_POIS]

    # Emit top POIs for streaming UI (after dedup and sort, before slow matrix call)
    emit_fn = (config or {}).get("configurable", {}).get("progress_emit") if config else None
    if emit_fn and pois:
        top_names = [p.name for p in pois[:10]]
        emit_fn({
            "type": "poi_found",
            "total_found": len(pois),
            "pois": top_names,
        })

    # 6. Build travel time matrix (only adjacent pairs ≤50km)
    matrix = await _build_travel_time_matrix(pois, tools=tools)

    logger.info("[discover_pois] done, pois=%d matrix_pairs=%d", len(pois), len(matrix))
    return {"pois": pois, "travel_time_matrix": matrix}
