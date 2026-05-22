# agent/nodes/discover_pois.py
import asyncio
import json
import math
import os
import uuid
from typing import Optional
import litellm
from agent.state import TravelPlanState
from models import POI, POISource
from tools.amap import search_pois, get_driving_time
from tools.tavily import search_travel_articles
from tools.xhs_tool import search_xhs, DEFAULT_COUNT

EARTH_RADIUS_KM = 6371.0
MAX_POIS = 40
MAX_MATRIX_DISTANCE_KM = 50.0


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
        else:
            merged.append(poi)
    return merged


def _compute_confidence(mention_count: int, platform_count: int, amap_only: bool = False) -> str:
    if mention_count >= 3 and platform_count >= 2:
        return "high"
    if amap_only:
        return "medium"
    return "low"


async def _fetch_amap_pois(city_codes: list[str], keywords: str = "景点") -> list[dict]:
    return await search_pois(city_codes, keywords, api_key=os.getenv("AMAP_API_KEY", ""))


async def _fetch_article_pois(keywords: list[str]) -> list[dict]:
    """Fetch raw article text from XHS and Tavily, return as list of {platform, content}."""
    results = []
    cookie = os.getenv("XHS_COOKIE", "")
    for keyword in keywords:
        notes = await asyncio.to_thread(search_xhs, keyword, DEFAULT_COUNT, True, cookie)
        results.extend({"platform": "xiaohongshu", "content": n["content"]} for n in notes)
    tavily = await search_travel_articles(keywords, api_key=os.getenv("TAVILY_API_KEY", ""))
    results.extend({"platform": "mafengwo", "content": a["content"]} for a in tavily)
    return results


async def _score_sources_batch(articles: list[dict]) -> dict[str, dict]:
    """Batch-score all articles in one LLM call. Returns {article_index: {credibility, has_negative, pois}}."""
    if not articles:
        return {}
    batch_text = "\n---\n".join(f"[{i}] ({a['platform']}): {a['content'][:500]}" for i, a in enumerate(articles))
    prompt = f"""You are analyzing travel articles for credibility and POI extraction.

For each article below (numbered [0], [1], etc.), output a JSON array where each element has:
- index: article number
- credibility: float 0-1 (low = ad/promotional content, high = genuine travel notes with complaints/details)
- has_negative_reviews: bool
- poi_names: list of attraction names mentioned
- poi_tags: list of tags inferred (choose from: 旅拍, 自然风光, 徒步, 爬山, 人文古迹, 美食, 休闲)

Articles:
{batch_text}

Return only a JSON array, no markdown."""
    resp = await litellm.acompletion(
        model=os.getenv("LLM_MODEL", "deepseek/deepseek-chat"),
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
    )
    scored = json.loads(resp.choices[0].message.content)
    return {str(item["index"]): item for item in scored}


async def _build_travel_time_matrix(pois: list[POI]) -> dict[tuple[str, str], int]:
    """Compute driving times only for POI pairs within MAX_MATRIX_DISTANCE_KM."""
    matrix: dict[tuple[str, str], int] = {}
    api_key = os.getenv("AMAP_API_KEY", "")
    for i, a in enumerate(pois):
        for j, b in enumerate(pois):
            if i >= j:
                continue
            if _haversine_km(a.coords, b.coords) <= MAX_MATRIX_DISTANCE_KM:
                minutes = await get_driving_time(a.coords, b.coords, api_key=api_key)
                if minutes is not None:
                    matrix[(a.poi_id, b.poi_id)] = minutes
                    matrix[(b.poi_id, a.poi_id)] = minutes
    return matrix


async def run(state: TravelPlanState) -> dict:
    city_codes = state["destination_amap_cities"]
    keywords = state.get("search_keywords", [])

    # 1. Fetch raw POIs from 高德
    raw_amap = await _fetch_amap_pois(city_codes)

    # 2. Fetch articles; score and extract POI names in one LLM batch call
    articles = await _fetch_article_pois(keywords)
    scores = await _score_sources_batch(articles)

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
            desc=raw.get("address", ""),
            amap_rating=float(raw.get("biz_ext", {}).get("rating") or 0),
            sources=[],
            mention_count=1,
            platform_count=1,
            confidence="medium",  # amap_only default
        )
        pois.append(p)

    # 4. Merge article POIs into the list
    for idx, article in enumerate(articles):
        score_data = scores.get(str(idx), {})
        for poi_name in score_data.get("poi_names", []):
            src = POISource(
                platform=article["platform"],
                mention_count=1,
                llm_credibility=score_data.get("credibility", 0.5),
                has_negative_reviews=score_data.get("has_negative_reviews", False),
            )
            existing = next((p for p in pois if p.name == poi_name), None)
            if existing:
                existing.sources.append(src)
                existing.mention_count += 1
                existing.platform_count = len({s.platform for s in existing.sources}) + 1
                existing.tags = list(set(existing.tags + score_data.get("poi_tags", [])))
            else:
                pois.append(POI(
                    poi_id=str(uuid.uuid4()),
                    name=poi_name,
                    coords=(0.0, 0.0),
                    category="景点",
                    tags=score_data.get("poi_tags", []),
                    desc="",
                    amap_rating=0.0,
                    sources=[src],
                    mention_count=1,
                    platform_count=1,
                    confidence="low",
                ))

    # 5. Recompute confidence for all POIs
    for p in pois:
        p.confidence = _compute_confidence(
            p.mention_count,
            p.platform_count,
            amap_only=(p.amap_rating > 0 and not p.sources),
        )

    # 6. Dedup and truncate to TOP 40
    pois = _dedup_pois(pois)
    pois.sort(key=lambda p: ({"high": 0, "medium": 1, "low": 2}[p.confidence], -p.amap_rating))
    pois = pois[:MAX_POIS]

    # 7. Build travel time matrix (only adjacent pairs ≤50km)
    matrix = await _build_travel_time_matrix(pois)

    return {"pois": pois, "travel_time_matrix": matrix}
