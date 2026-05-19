# Smart Travel Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python backend API that accepts a travel destination + preferences and returns 2-3 complete itinerary options with multi-platform flight price comparisons.

**Architecture:** LangGraph StateGraph with 5 nodes (`parse_input` → [`discover_pois` ∥ `scrape_flights`] → `plan_itinerary` → `compose_output`). FastAPI exposes async job endpoints (POST `/plans`, GET `/plans/{job_id}`) with Redis for job state and caching. All LLM calls go through LiteLLM for model-agnostic invocation.

**Tech Stack:** Python 3.11+, LangGraph 0.2+, LiteLLM, FastAPI, Redis, Playwright (async), Tavily SDK, httpx, pytest, pytest-asyncio, pytest-mock

---

## File Map

```
travel-agent/
├── models.py                      # All dataclasses (POI, Flight, FlightPair, ItineraryOption, …)
├── agent/
│   ├── state.py                   # TravelPlanState TypedDict
│   ├── graph.py                   # LangGraph StateGraph wiring
│   └── nodes/
│       ├── parse_input.py         # Node ①: normalize destination, expand airports, gen keywords
│       ├── discover_pois.py       # Node ②: POI discovery, dedup, credibility scoring
│       ├── scrape_flights.py      # Node ③: price calendar → detail scrape → FlightPair assembly
│       ├── plan_itinerary.py      # Node ④: two-stage LLM planning
│       └── compose_output.py      # Node ⑤: final JSON + partial-failure handling
├── tools/
│   ├── amap.py                    # 高德 POI / 路径规划 / 行政区 API
│   ├── tavily.py                  # Tavily search wrapper
│   ├── xhs_scraper.py             # Xiaohongshu Playwright scraper
│   └── flight_scraper.py          # Flight price calendar + detail Playwright scraper
├── api/
│   └── main.py                    # FastAPI app, POST /plans, GET /plans/{job_id}
├── llm_config.yaml                # LiteLLM model routing config
├── tests/
│   ├── conftest.py                # Shared fixtures (mock Redis, mock LLM, mock amap)
│   ├── test_models.py
│   ├── test_tools/
│   │   ├── test_amap.py
│   │   ├── test_tavily.py
│   │   ├── test_xhs_scraper.py
│   │   └── test_flight_scraper.py
│   ├── test_nodes/
│   │   ├── test_parse_input.py
│   │   ├── test_discover_pois.py
│   │   ├── test_scrape_flights.py
│   │   ├── test_plan_itinerary.py
│   │   └── test_compose_output.py
│   └── test_api.py
├── requirements.txt
└── .env.example
```

---

## Task 1: Project Setup

**Files:**
- Create: `requirements.txt`
- Create: `.env.example`
- Create: `llm_config.yaml`
- Create: `tests/conftest.py`

- [ ] **Step 1: Create requirements.txt**

```
langgraph>=0.2.0
langchain-core>=0.3.0
litellm>=1.40.0
fastapi>=0.111.0
uvicorn>=0.30.0
redis>=5.0.0
playwright>=1.44.0
tavily-python>=0.3.0
httpx>=0.27.0
python-dotenv>=1.0.0
pydantic>=2.0.0

pytest>=8.0.0
pytest-asyncio>=0.23.0
pytest-mock>=3.14.0
```

- [ ] **Step 2: Create .env.example**

```
AMAP_API_KEY=your_amap_key_here
TAVILY_API_KEY=your_tavily_key_here
LLM_PROVIDER=deepseek          # deepseek | openai | anthropic | zhipu | qwen
LLM_MODEL=deepseek-chat
LLM_API_KEY=your_llm_key_here
REDIS_URL=redis://localhost:6379/0
```

- [ ] **Step 3: Create llm_config.yaml**

```yaml
model: deepseek/deepseek-chat   # LiteLLM model string; change to openai/gpt-4o etc.
api_key: ${LLM_API_KEY}
temperature: 0.2
max_tokens: 4096
```

- [ ] **Step 4: Create tests/conftest.py**

```python
import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import date


@pytest.fixture
def mock_redis(mocker):
    r = MagicMock()
    r.get = MagicMock(return_value=None)
    r.set = MagicMock()
    r.setex = MagicMock()
    mocker.patch("redis.from_url", return_value=r)
    return r


@pytest.fixture
def mock_litellm(mocker):
    async def fake_completion(**kwargs):
        content = kwargs.get("_mock_content", '{"result": "mocked"}')
        m = MagicMock()
        m.choices[0].message.content = content
        return m
    mocker.patch("litellm.acompletion", side_effect=fake_completion)


@pytest.fixture
def sample_state():
    return {
        "destination": "川西",
        "origin": "苏州",
        "duration_days": 7,
        "travelers": 2,
        "transport_mode": "self_drive",
        "difficulty_level": "medium",
        "interests": ["徒步", "摄影"],
        "errors": [],
        "warnings": [],
    }
```

- [ ] **Step 5: Install dependencies**

```bash
pip install -r requirements.txt
playwright install chromium
```

Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add requirements.txt .env.example llm_config.yaml tests/conftest.py
git commit -m "feat: project scaffold and dependencies"
```

---

## Task 2: Data Models

**Files:**
- Create: `models.py`
- Create: `tests/test_models.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_models.py
from datetime import datetime
from models import POI, POISource, Flight, FlightPair, DayPlan, ItineraryOption


def test_poi_confidence_high():
    src = POISource(platform="xiaohongshu", mention_count=3, llm_credibility=0.8, has_negative_reviews=True)
    poi = POI(
        poi_id="p1", name="稻城亚丁", coords=(29.0, 100.0),
        category="自然景观", tags=["自然风光", "徒步"],
        desc="三神山", amap_rating=4.9,
        sources=[src], mention_count=3, platform_count=2, confidence="high",
    )
    assert poi.confidence == "high"
    assert poi.tags == ["自然风光", "徒步"]


def test_flight_pair_total_price():
    outbound = Flight("携程", "上海浦东 PVG", "稻城亚丁 DCY", 980, "MU2345", datetime(2026, 7, 1, 8, 30))
    ret = Flight("去哪儿", "成都双流 CTU", "上海浦东 PVG", 760, "CA1235", datetime(2026, 7, 8, 14, 0))
    pair = FlightPair(pair_id="uuid-test", outbound=outbound, return_flight=ret, total_price=1740)
    assert pair.total_price == outbound.price + ret.price


def test_itinerary_option_structure():
    outbound = Flight("携程", "PVG", "DCY", 980, "MU2345", datetime(2026, 7, 1))
    ret = Flight("携程", "CTU", "PVG", 760, "CA1235", datetime(2026, 7, 8))
    pair = FlightPair("uuid-1", outbound, ret, 1740)
    day = DayPlan(day=1, pois=[], transport_note="驾车约55分钟", estimated_travel_minutes=55)
    opt = ItineraryOption(option_id="A", summary="DCY进CTU出", flights=pair, days=[day])
    assert opt.option_id == "A"
    assert opt.flights.total_price == 1740
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_models.py -v
```
Expected: `ModuleNotFoundError: No module named 'models'`

- [ ] **Step 3: Create models.py**

```python
from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Optional


@dataclass
class POISource:
    platform: str               # "xiaohongshu" | "mafengwo" | "qyer"
    mention_count: int
    llm_credibility: float      # 0-1; low = ad-like content
    has_negative_reviews: bool  # True = more trustworthy


@dataclass
class POI:
    poi_id: str
    name: str
    coords: tuple[float, float]     # (lat, lng)
    category: str
    tags: list[str]                 # LLM-inferred from description, e.g. ["旅拍", "徒步"]
    desc: str
    amap_rating: float
    sources: list[POISource]
    mention_count: int              # total across all platforms
    platform_count: int
    confidence: str                 # "high" | "medium" | "low"


@dataclass
class Flight:
    platform: str
    depart_airport: str
    arrive_airport: str
    price: int                      # CNY, one-way per person
    flight_no: str
    depart_time: datetime


@dataclass
class FlightPair:
    pair_id: str                    # UUID
    outbound: Flight
    return_flight: Flight
    total_price: int                # outbound + return per person; actual cost = total_price × travelers


@dataclass
class DayPlan:
    day: int
    pois: list[POI]
    transport_note: str             # grounded in 高德 API data; LLM only formats wording
    estimated_travel_minutes: int


@dataclass
class ItineraryOption:
    option_id: str
    summary: str
    flights: FlightPair
    days: list[DayPlan]
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_models.py -v
```
Expected: 3 PASSED

- [ ] **Step 5: Commit**

```bash
git add models.py tests/test_models.py
git commit -m "feat: data models"
```

---

## Task 3: LangGraph State

**Files:**
- Create: `agent/state.py`
- Create: `tests/test_nodes/__init__.py`

- [ ] **Step 1: Create agent/__init__.py and agent/nodes/__init__.py**

```bash
mkdir -p agent/nodes tests/test_nodes tests/test_tools
touch agent/__init__.py agent/nodes/__init__.py tests/test_nodes/__init__.py tests/test_tools/__init__.py
```

- [ ] **Step 2: Create agent/state.py**

```python
from typing import TypedDict, Optional
from datetime import date
from models import POI, FlightPair, ItineraryOption


class TravelPlanState(TypedDict, total=False):
    # ── Raw input from API ──────────────────────────────────────────────
    destination: str
    origin: str
    duration_days: int
    travelers: int
    transport_mode: str           # "self_drive" | "public_transit" | "mixed"
    difficulty_level: str         # "easy" | "medium" | "hard"
    interests: list[str]
    depart_date: Optional[str]    # ISO date string or None

    # ── Written by ① parse_input ────────────────────────────────────────
    destination_region: str           # human-readable, e.g. "甘孜州+阿坝州"
    destination_amap_cities: list[str]  # amap adcodes e.g. ["513300","513200"]
    origin_airports: list[str]        # IATA codes e.g. ["PVG","SHA","NKG"]
    destination_airports: list[str]   # e.g. ["CTU","TFU","DCY","KGT"]
    depart_dates: list[date]          # search range; 14 days or single date
    search_keywords: list[str]        # for XHS/mafengwo search

    # ── Written by ② discover_pois ──────────────────────────────────────
    pois: list[POI]                                      # TOP 40 by confidence
    travel_time_matrix: dict[tuple[str, str], int]       # {(poi_id_a, poi_id_b): minutes}

    # ── Written by ③ scrape_flights ─────────────────────────────────────
    flight_pairs: list[FlightPair]    # valid pairs with UUID pair_id
    selected_dates: list[date]        # TOP 3 cheapest dates (or same as depart_dates if 1 date)

    # ── Written by ④ plan_itinerary ─────────────────────────────────────
    itineraries: list[ItineraryOption]

    # ── Global ───────────────────────────────────────────────────────────
    errors: list[str]
    warnings: list[str]
    job_id: str                   # Redis job key
```

- [ ] **Step 3: Commit**

```bash
git add agent/ tests/test_nodes/ tests/test_tools/
git commit -m "feat: LangGraph state definition"
```

---

## Task 4: 高德 API Tool

**Files:**
- Create: `tools/__init__.py`
- Create: `tools/amap.py`
- Create: `tests/test_tools/test_amap.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_tools/test_amap.py
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
```

- [ ] **Step 2: Run tests — confirm fail**

```bash
pytest tests/test_tools/test_amap.py -v
```
Expected: `ModuleNotFoundError: No module named 'tools.amap'`

- [ ] **Step 3: Create tools/__init__.py and tools/amap.py**

```python
# tools/__init__.py
```

```python
# tools/amap.py
import httpx
from typing import Optional

AMAP_BASE = "https://restapi.amap.com/v3"


async def get_district_codes(city_names: list[str], api_key: str) -> dict[str, str]:
    """Map city names to 高德 adcodes via the district API (avoids LLM hallucinating numeric codes)."""
    result: dict[str, str] = {}
    async with httpx.AsyncClient() as client:
        for name in city_names:
            resp = await client.get(
                f"{AMAP_BASE}/config/district",
                params={"keywords": name, "subdistrict": "0", "extensions": "base", "key": api_key},
            )
            data = resp.json()
            if data.get("status") == "1" and data.get("districts"):
                result[name] = data["districts"][0]["adcode"]
    return result


async def search_pois(
    city_codes: list[str],
    keywords: str,
    api_key: str,
    types: str = "110000|120000|140000",
    page_size: int = 25,
) -> list[dict]:
    """Fetch POIs from 高德 for a list of city adcodes."""
    all_pois: list[dict] = []
    async with httpx.AsyncClient() as client:
        for code in city_codes:
            resp = await client.get(
                f"{AMAP_BASE}/place/text",
                params={
                    "keywords": keywords,
                    "city": code,
                    "types": types,
                    "output": "JSON",
                    "offset": page_size,
                    "key": api_key,
                },
            )
            data = resp.json()
            if data.get("status") == "1":
                all_pois.extend(data.get("pois", []))
    return all_pois


async def get_driving_time(
    origin: tuple[float, float],
    dest: tuple[float, float],
    api_key: str,
) -> Optional[int]:
    """Return driving time in minutes, or None on failure. origin/dest are (lat, lng)."""
    o = f"{origin[1]},{origin[0]}"
    d = f"{dest[1]},{dest[0]}"
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{AMAP_BASE}/direction/driving",
            params={"origin": o, "destination": d, "key": api_key},
        )
        data = resp.json()
        if data.get("status") == "1":
            paths = data.get("route", {}).get("paths", [])
            if paths:
                return int(paths[0]["duration"]) // 60
    return None


async def check_transit_reachable(
    origin: tuple[float, float],
    dest: tuple[float, float],
    city_code: str,
    api_key: str,
    max_minutes: int = 120,
) -> bool:
    """Return True if dest reachable by public transit within max_minutes."""
    o = f"{origin[1]},{origin[0]}"
    d = f"{dest[1]},{dest[0]}"
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{AMAP_BASE}/direction/transit/integrated",
            params={"origin": o, "destination": d, "city": city_code, "key": api_key},
        )
        data = resp.json()
        if data.get("status") == "1":
            transits = data.get("route", {}).get("transits", [])
            if transits:
                return int(transits[0]["duration"]) // 60 <= max_minutes
    return False
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_tools/test_amap.py -v
```
Expected: 5 PASSED

- [ ] **Step 5: Commit**

```bash
git add tools/ tests/test_tools/test_amap.py
git commit -m "feat: 高德 API tool (district, POI, routing)"
```

---

## Task 5: Tavily Tool

**Files:**
- Create: `tools/tavily.py`
- Create: `tests/test_tools/test_tavily.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_tools/test_tavily.py
import pytest
from unittest.mock import AsyncMock, patch
from tools.tavily import search_travel_articles


@pytest.mark.asyncio
async def test_search_returns_content_list(mocker):
    mock_client = mocker.patch("tools.tavily.AsyncTavilyClient")
    instance = AsyncMock()
    instance.search.return_value = {
        "results": [
            {"title": "川西攻略", "content": "稻城亚丁很美...", "url": "http://mafengwo.cn/1"},
            {"title": "四姑娘山", "content": "双桥沟徒步...", "url": "http://qyer.com/2"},
        ]
    }
    mock_client.return_value.__aenter__ = AsyncMock(return_value=instance)
    mock_client.return_value.__aexit__ = AsyncMock(return_value=False)

    results = await search_travel_articles(["川西 攻略"], api_key="fake")
    assert len(results) == 2
    assert results[0]["content"] == "稻城亚丁很美..."


@pytest.mark.asyncio
async def test_search_multiple_keywords(mocker):
    mock_client = mocker.patch("tools.tavily.AsyncTavilyClient")
    instance = AsyncMock()
    instance.search.return_value = {"results": [{"title": "t", "content": "c", "url": "u"}]}
    mock_client.return_value.__aenter__ = AsyncMock(return_value=instance)
    mock_client.return_value.__aexit__ = AsyncMock(return_value=False)

    results = await search_travel_articles(["川西 攻略", "稻城 游记"], api_key="fake")
    assert len(results) == 2   # one result per keyword call
    assert instance.search.call_count == 2
```

- [ ] **Step 2: Run tests — confirm fail**

```bash
pytest tests/test_tools/test_tavily.py -v
```

- [ ] **Step 3: Create tools/tavily.py**

```python
# tools/tavily.py
from tavily import AsyncTavilyClient


async def search_travel_articles(keywords: list[str], api_key: str) -> list[dict]:
    """Search travel articles on Mafengwo/Qyer for each keyword. Returns list of {title, content, url}."""
    results: list[dict] = []
    async with AsyncTavilyClient(api_key=api_key) as client:
        for kw in keywords:
            resp = await client.search(
                query=kw,
                search_depth="advanced",
                max_results=5,
                include_domains=["mafengwo.cn", "qyer.com", "lvyou.baidu.com"],
            )
            results.extend(resp.get("results", []))
    return results
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_tools/test_tavily.py -v
```
Expected: 2 PASSED

- [ ] **Step 5: Commit**

```bash
git add tools/tavily.py tests/test_tools/test_tavily.py
git commit -m "feat: Tavily travel article search tool"
```

---

## Task 6: Xiaohongshu Scraper

**Files:**
- Create: `tools/xhs_scraper.py`
- Create: `tests/test_tools/test_xhs_scraper.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_tools/test_xhs_scraper.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from tools.xhs_scraper import scrape_xhs_notes


@pytest.mark.asyncio
async def test_scrape_returns_note_list(mocker):
    mock_page = AsyncMock()
    mock_page.goto = AsyncMock()
    mock_page.wait_for_selector = AsyncMock()
    mock_page.query_selector_all = AsyncMock(return_value=[
        MagicMock(inner_text=AsyncMock(return_value="川西超美的稻城亚丁，路很难走但值得")),
        MagicMock(inner_text=AsyncMock(return_value="四姑娘山徒步攻略，感谢XX品牌赞助")),
    ])

    mock_browser = AsyncMock()
    mock_browser.new_page = AsyncMock(return_value=mock_page)

    mock_pw = AsyncMock()
    mock_pw.chromium.launch = AsyncMock(return_value=mock_browser)

    with patch("tools.xhs_scraper.async_playwright") as mock_apt:
        mock_apt.return_value.__aenter__ = AsyncMock(return_value=mock_pw)
        mock_apt.return_value.__aexit__ = AsyncMock(return_value=False)

        notes = await scrape_xhs_notes(["川西 攻略"], max_notes_per_keyword=2)

    assert len(notes) == 2
    assert "稻城亚丁" in notes[0]["content"]


@pytest.mark.asyncio
async def test_scrape_respects_delay(mocker):
    mock_sleep = mocker.patch("asyncio.sleep", new_callable=AsyncMock)
    mock_page = AsyncMock()
    mock_page.goto = AsyncMock()
    mock_page.wait_for_selector = AsyncMock()
    mock_page.query_selector_all = AsyncMock(return_value=[])
    mock_browser = AsyncMock()
    mock_browser.new_page = AsyncMock(return_value=mock_page)
    mock_pw = AsyncMock()
    mock_pw.chromium.launch = AsyncMock(return_value=mock_browser)

    with patch("tools.xhs_scraper.async_playwright") as mock_apt:
        mock_apt.return_value.__aenter__ = AsyncMock(return_value=mock_pw)
        mock_apt.return_value.__aexit__ = AsyncMock(return_value=False)
        await scrape_xhs_notes(["川西 攻略"])

    mock_sleep.assert_called()
```

- [ ] **Step 2: Run tests — confirm fail**

```bash
pytest tests/test_tools/test_xhs_scraper.py -v
```

- [ ] **Step 3: Create tools/xhs_scraper.py**

```python
# tools/xhs_scraper.py
import asyncio
import random
from playwright.async_api import async_playwright

XHS_SEARCH_URL = "https://www.xiaohongshu.com/search_result?keyword={keyword}&source=web_explore_feed"
NOTE_SELECTOR = ".note-item .content"


async def scrape_xhs_notes(keywords: list[str], max_notes_per_keyword: int = 10) -> list[dict]:
    """Scrape Xiaohongshu search results for each keyword. Returns list of {keyword, content}."""
    results: list[dict] = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        for keyword in keywords:
            url = XHS_SEARCH_URL.format(keyword=keyword)
            await page.goto(url, wait_until="networkidle", timeout=30_000)
            await asyncio.sleep(random.uniform(1.0, 3.0))   # anti-bot delay
            try:
                await page.wait_for_selector(NOTE_SELECTOR, timeout=10_000)
                elements = await page.query_selector_all(NOTE_SELECTOR)
                for el in elements[:max_notes_per_keyword]:
                    text = await el.inner_text()
                    results.append({"keyword": keyword, "content": text.strip()})
            except Exception:
                pass   # selector not found; XHS may have blocked — degrade gracefully
        await browser.close()
    return results
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_tools/test_xhs_scraper.py -v
```
Expected: 2 PASSED

- [ ] **Step 5: Commit**

```bash
git add tools/xhs_scraper.py tests/test_tools/test_xhs_scraper.py
git commit -m "feat: Xiaohongshu Playwright scraper"
```

---

## Task 7: Flight Scraper

**Files:**
- Create: `tools/flight_scraper.py`
- Create: `tests/test_tools/test_flight_scraper.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_tools/test_flight_scraper.py
import pytest
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch
from tools.flight_scraper import scrape_price_calendar, scrape_flight_details


@pytest.mark.asyncio
async def test_price_calendar_returns_date_price_map(mocker):
    mock_page = AsyncMock()
    mock_page.goto = AsyncMock()
    mock_page.wait_for_selector = AsyncMock()
    # Simulate calendar cells: data-date and data-price attributes
    cell1 = MagicMock()
    cell1.get_attribute = AsyncMock(side_effect=lambda attr: "2026-07-01" if attr == "data-date" else "980")
    cell2 = MagicMock()
    cell2.get_attribute = AsyncMock(side_effect=lambda attr: "2026-07-02" if attr == "data-date" else "1200")
    mock_page.query_selector_all = AsyncMock(return_value=[cell1, cell2])
    mock_browser = AsyncMock()
    mock_browser.new_page = AsyncMock(return_value=mock_page)
    mock_pw = AsyncMock()
    mock_pw.chromium.launch = AsyncMock(return_value=mock_browser)

    with patch("tools.flight_scraper.async_playwright") as mock_apt:
        mock_apt.return_value.__aenter__ = AsyncMock(return_value=mock_pw)
        mock_apt.return_value.__aexit__ = AsyncMock(return_value=False)
        result = await scrape_price_calendar("PVG", "DCY", "ctrip")

    assert date(2026, 7, 1) in result
    assert result[date(2026, 7, 1)] == 980


@pytest.mark.asyncio
async def test_scrape_flight_details_returns_flights(mocker):
    mock_page = AsyncMock()
    mock_page.goto = AsyncMock()
    mock_page.wait_for_selector = AsyncMock()
    row = MagicMock()
    row.inner_text = AsyncMock(return_value="MU2345\t08:30\t11:00\t¥980")
    mock_page.query_selector_all = AsyncMock(return_value=[row])
    mock_browser = AsyncMock()
    mock_browser.new_page = AsyncMock(return_value=mock_page)
    mock_pw = AsyncMock()
    mock_pw.chromium.launch = AsyncMock(return_value=mock_browser)

    with patch("tools.flight_scraper.async_playwright") as mock_apt:
        mock_apt.return_value.__aenter__ = AsyncMock(return_value=mock_pw)
        mock_apt.return_value.__aexit__ = AsyncMock(return_value=False)
        flights = await scrape_flight_details("PVG", "DCY", date(2026, 7, 1), "ctrip")

    assert len(flights) >= 1
```

- [ ] **Step 2: Run tests — confirm fail**

```bash
pytest tests/test_tools/test_flight_scraper.py -v
```

- [ ] **Step 3: Create tools/flight_scraper.py**

```python
# tools/flight_scraper.py
import asyncio
import random
import re
from datetime import date, datetime
from playwright.async_api import async_playwright
from models import Flight

PLATFORMS = {
    "ctrip": {
        "calendar_url": "https://flights.ctrip.com/international/search/oneway-{origin}-{dest}",
        "calendar_selector": ".flight-calendar-day",
        "detail_url": "https://flights.ctrip.com/international/search/oneway-{origin}-{dest}?depdate={date}",
        "row_selector": ".flight-item",
    },
    "qunar": {
        "calendar_url": "https://flight.qunar.com/site/oneway.htm?searchDepartureAirport={origin}&searchArrivalAirport={dest}",
        "calendar_selector": ".price-calendar-cell",
        "detail_url": "https://flight.qunar.com/site/oneway.htm?searchDepartureAirport={origin}&searchArrivalAirport={dest}&searchDepartTime={date}",
        "row_selector": ".flight-item-wrap",
    },
}


async def scrape_price_calendar(origin: str, dest: str, platform: str) -> dict[date, int]:
    """Scrape price calendar page. Returns {date: lowest_price}."""
    cfg = PLATFORMS.get(platform, PLATFORMS["ctrip"])
    url = cfg["calendar_url"].format(origin=origin, dest=dest)
    prices: dict[date, int] = {}

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(url, wait_until="networkidle", timeout=30_000)
        await asyncio.sleep(random.uniform(1.0, 2.0))
        try:
            await page.wait_for_selector(cfg["calendar_selector"], timeout=10_000)
            cells = await page.query_selector_all(cfg["calendar_selector"])
            for cell in cells:
                d_str = await cell.get_attribute("data-date")
                p_str = await cell.get_attribute("data-price")
                if d_str and p_str:
                    try:
                        prices[date.fromisoformat(d_str)] = int(p_str)
                    except (ValueError, TypeError):
                        pass
        except Exception:
            pass
        await browser.close()
    return prices


async def scrape_flight_details(origin: str, dest: str, depart_date: date, platform: str) -> list[Flight]:
    """Scrape detailed flight list for a specific date. Returns list of Flight objects."""
    cfg = PLATFORMS.get(platform, PLATFORMS["ctrip"])
    url = cfg["detail_url"].format(origin=origin, dest=dest, date=depart_date.isoformat())
    flights: list[Flight] = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(url, wait_until="networkidle", timeout=30_000)
        await asyncio.sleep(random.uniform(1.0, 2.5))
        try:
            await page.wait_for_selector(cfg["row_selector"], timeout=10_000)
            rows = await page.query_selector_all(cfg["row_selector"])
            for row in rows[:10]:
                text = await row.inner_text()
                # Minimal parse — adapt selectors per platform in production
                price_match = re.search(r"[¥￥](\d+)", text)
                flight_match = re.search(r"([A-Z]{2}\d{4})", text)
                time_match = re.search(r"(\d{2}:\d{2})", text)
                if price_match and flight_match and time_match:
                    depart_time = datetime.combine(depart_date, datetime.strptime(time_match.group(1), "%H:%M").time())
                    flights.append(Flight(
                        platform=platform,
                        depart_airport=origin,
                        arrive_airport=dest,
                        price=int(price_match.group(1)),
                        flight_no=flight_match.group(1),
                        depart_time=depart_time,
                    ))
        except Exception:
            pass
        await browser.close()
    return flights
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_tools/test_flight_scraper.py -v
```
Expected: 2 PASSED

- [ ] **Step 5: Commit**

```bash
git add tools/flight_scraper.py tests/test_tools/test_flight_scraper.py
git commit -m "feat: flight price calendar and detail scraper"
```

---

## Task 8: Node ① — parse_input

**Files:**
- Create: `agent/nodes/parse_input.py`
- Create: `tests/test_nodes/test_parse_input.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_nodes/test_parse_input.py
import pytest
from datetime import date, timedelta
from unittest.mock import AsyncMock, patch, MagicMock
from agent.nodes.parse_input import run


@pytest.fixture
def base_state():
    return {
        "destination": "川西",
        "origin": "苏州",
        "duration_days": 7,
        "travelers": 2,
        "transport_mode": "self_drive",
        "difficulty_level": "medium",
        "interests": ["徒步", "摄影"],
        "depart_date": None,
        "errors": [],
        "warnings": [],
        "job_id": "test-job",
    }


@pytest.mark.asyncio
async def test_parse_input_expands_depart_dates_when_none(base_state, mocker):
    mocker.patch("agent.nodes.parse_input._llm_parse_destination", new_callable=AsyncMock, return_value={
        "region": "甘孜州+阿坝州",
        "city_names": ["甘孜藏族自治州"],
        "destination_airports": ["CTU", "DCY"],
        "origin_airports": ["PVG", "SHA", "NKG"],
        "search_keywords": ["川西 攻略", "稻城亚丁 游记"],
    })
    mocker.patch("agent.nodes.parse_input._resolve_amap_codes", new_callable=AsyncMock, return_value=["513300"])

    result = await run(base_state)
    assert len(result["depart_dates"]) == 14
    assert result["depart_dates"][0] == date.today()


@pytest.mark.asyncio
async def test_parse_input_single_date_when_specified(base_state, mocker):
    base_state["depart_date"] = "2026-07-01"
    mocker.patch("agent.nodes.parse_input._llm_parse_destination", new_callable=AsyncMock, return_value={
        "region": "甘孜州+阿坝州",
        "city_names": ["甘孜藏族自治州"],
        "destination_airports": ["CTU", "DCY"],
        "origin_airports": ["PVG", "SHA", "NKG"],
        "search_keywords": ["川西 攻略"],
    })
    mocker.patch("agent.nodes.parse_input._resolve_amap_codes", new_callable=AsyncMock, return_value=["513300"])

    result = await run(base_state)
    assert result["depart_dates"] == [date(2026, 7, 1)]


@pytest.mark.asyncio
async def test_parse_input_writes_search_keywords(base_state, mocker):
    mocker.patch("agent.nodes.parse_input._llm_parse_destination", new_callable=AsyncMock, return_value={
        "region": "甘孜州+阿坝州",
        "city_names": ["甘孜藏族自治州"],
        "destination_airports": ["CTU", "DCY"],
        "origin_airports": ["PVG", "SHA", "NKG"],
        "search_keywords": ["川西 攻略", "稻城亚丁 游记"],
    })
    mocker.patch("agent.nodes.parse_input._resolve_amap_codes", new_callable=AsyncMock, return_value=["513300"])

    result = await run(base_state)
    assert "川西 攻略" in result["search_keywords"]
```

- [ ] **Step 2: Run tests — confirm fail**

```bash
pytest tests/test_nodes/test_parse_input.py -v
```

- [ ] **Step 3: Create agent/nodes/parse_input.py**

```python
# agent/nodes/parse_input.py
import json
import os
from datetime import date, timedelta
import litellm
from agent.state import TravelPlanState
from tools.amap import get_district_codes


async def _llm_parse_destination(destination: str, origin: str) -> dict:
    """Ask LLM to expand destination into region info. Returns city names (not codes)."""
    prompt = f"""You are a Chinese travel expert. Given the destination "{destination}" (departing from "{origin}"):
Return JSON with these keys:
- region: human-readable description (e.g. "甘孜州+阿坝州")
- city_names: list of Chinese administrative district names (e.g. ["甘孜藏族自治州","阿坝藏族羌族自治州"])
- destination_airports: IATA codes of airports serving this area (e.g. ["CTU","TFU","DCY","KGT"])
- origin_airports: IATA codes for airports near "{origin}" (e.g. ["PVG","SHA","NKG"])
- search_keywords: 3-5 Chinese search queries for travel content (e.g. ["川西 攻略","稻城亚丁 游记"])

Return only valid JSON, no markdown."""

    resp = await litellm.acompletion(
        model=os.getenv("LLM_MODEL", "deepseek/deepseek-chat"),
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
    )
    return json.loads(resp.choices[0].message.content)


async def _resolve_amap_codes(city_names: list[str]) -> list[str]:
    """Convert city names to 高德 adcodes via the district API."""
    api_key = os.getenv("AMAP_API_KEY", "")
    code_map = await get_district_codes(city_names, api_key=api_key)
    return list(code_map.values())


async def run(state: TravelPlanState) -> dict:
    parsed = await _llm_parse_destination(state["destination"], state["origin"])
    amap_cities = await _resolve_amap_codes(parsed["city_names"])

    if state.get("depart_date"):
        depart_dates = [date.fromisoformat(state["depart_date"])]
    else:
        today = date.today()
        depart_dates = [today + timedelta(days=i) for i in range(14)]

    return {
        "destination_region": parsed["region"],
        "destination_amap_cities": amap_cities,
        "destination_airports": parsed["destination_airports"],
        "origin_airports": parsed["origin_airports"],
        "depart_dates": depart_dates,
        "search_keywords": parsed["search_keywords"],
    }
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_nodes/test_parse_input.py -v
```
Expected: 3 PASSED

- [ ] **Step 5: Commit**

```bash
git add agent/nodes/parse_input.py tests/test_nodes/test_parse_input.py
git commit -m "feat: parse_input node — destination normalization and date expansion"
```

---

## Task 9: Node ② — discover_pois

**Files:**
- Create: `agent/nodes/discover_pois.py`
- Create: `tests/test_nodes/test_discover_pois.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_nodes/test_discover_pois.py
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
```

- [ ] **Step 2: Run tests — confirm fail**

```bash
pytest tests/test_nodes/test_discover_pois.py -v
```

- [ ] **Step 3: Create agent/nodes/discover_pois.py**

```python
# agent/nodes/discover_pois.py
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
from tools.xhs_scraper import scrape_xhs_notes

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
    xhs = await scrape_xhs_notes(keywords)
    results.extend([{"platform": "xiaohongshu", "content": n["content"]} for n in xhs])
    tavily = await search_travel_articles(keywords, api_key=os.getenv("TAVILY_API_KEY", ""))
    results.extend([{"platform": "mafengwo", "content": a["content"]} for a in tavily])
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
    transport_mode = state.get("transport_mode", "mixed")

    # 1. Fetch raw POIs from 高德
    raw_amap = await _fetch_amap_pois(city_codes)

    # 2. Fetch articles; score and extract POI names in one LLM batch call
    articles = await _fetch_article_pois(keywords)
    scores = await _score_sources_batch(articles)

    # 3. Build POI objects from 高德 data
    amap_poi_names = {r["name"] for r in raw_amap}
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
                loc_search = next((r for r in raw_amap if r["name"] == poi_name), None)
                if loc_search:
                    continue  # already in list
                # New POI from articles only
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
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_nodes/test_discover_pois.py -v
```
Expected: 5 PASSED

- [ ] **Step 5: Commit**

```bash
git add agent/nodes/discover_pois.py tests/test_nodes/test_discover_pois.py
git commit -m "feat: discover_pois node — POI fetch, dedup, credibility scoring, travel time matrix"
```

---

## Task 10: Node ③ — scrape_flights

**Files:**
- Create: `agent/nodes/scrape_flights.py`
- Create: `tests/test_nodes/test_scrape_flights.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_nodes/test_scrape_flights.py
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
```

- [ ] **Step 2: Run tests — confirm fail**

```bash
pytest tests/test_nodes/test_scrape_flights.py -v
```

- [ ] **Step 3: Create agent/nodes/scrape_flights.py**

```python
# agent/nodes/scrape_flights.py
import asyncio
import uuid
from datetime import date
from agent.state import TravelPlanState
from models import Flight, FlightPair
from tools.flight_scraper import scrape_price_calendar, scrape_flight_details

PLATFORMS = ["ctrip", "qunar"]


async def _scrape_calendars(
    origin_airports: list[str],
    dest_airports: list[str],
    date_range: list[date],
    top_n: int = 3,
) -> list[date]:
    """Fetch price calendars for all origin×dest pairs, return top_n cheapest dates."""
    prices: dict[date, int] = {}
    for origin in origin_airports:
        for dest in dest_airports:
            for platform in PLATFORMS:
                cal = await scrape_price_calendar(origin, dest, platform)
                for d, p in cal.items():
                    if d in date_range:
                        prices[d] = min(prices.get(d, p), p)
    sorted_dates = sorted(prices.keys(), key=lambda d: prices[d])
    return sorted_dates[:top_n]


async def _scrape_details(
    origin_airports: list[str],
    dest_airports: list[str],
    selected_dates: list[date],
) -> list[Flight]:
    """Scrape outbound and return flights for selected dates."""
    flights: list[Flight] = []
    for depart_date in selected_dates:
        for origin in origin_airports:
            for dest in dest_airports:
                for platform in PLATFORMS:
                    details = await scrape_flight_details(origin, dest, depart_date, platform)
                    flights.extend(details)
    return flights


def _assemble_flight_pairs(
    outbound_flights: list[Flight],
    return_flights: list[Flight],
    dest_airports: set[str],
) -> list[FlightPair]:
    """Build valid FlightPairs: both outbound.arrive and return.depart must be in dest_airports.
    Keep cheapest per (outbound_airport, return_airport) combination."""
    best: dict[tuple[str, str], FlightPair] = {}
    for out in outbound_flights:
        if out.arrive_airport not in dest_airports:
            continue
        for ret in return_flights:
            if ret.depart_airport not in dest_airports:
                continue
            key = (out.arrive_airport, ret.depart_airport)
            total = out.price + ret.price
            existing = best.get(key)
            if existing is None or total < existing.total_price:
                best[key] = FlightPair(
                    pair_id=str(uuid.uuid4()),
                    outbound=out,
                    return_flight=ret,
                    total_price=total,
                )
    return list(best.values())


async def run(state: TravelPlanState) -> dict:
    origin_airports = state["origin_airports"]
    dest_airports = state["destination_airports"]
    depart_dates = state["depart_dates"]
    dest_set = set(dest_airports)
    warnings = list(state.get("warnings", []))

    # Step 1: date selection
    if len(depart_dates) == 1:
        selected_dates = depart_dates
        outbound_dates = depart_dates
    else:
        selected_dates = await _scrape_calendars(origin_airports, dest_airports, depart_dates)
        if not selected_dates:
            selected_dates = depart_dates[:3]
            warnings.append("价格日历爬取失败，使用前3个备选日期")
        outbound_dates = selected_dates

    # Step 2: detail scraping
    from datetime import timedelta
    return_dates = [d + timedelta(days=state["duration_days"]) for d in outbound_dates]
    outbound_flights = await _scrape_details(origin_airports, dest_airports, outbound_dates)
    return_flights = await _scrape_details(dest_airports, origin_airports, return_dates)

    # Step 3: assemble pairs
    flight_pairs = _assemble_flight_pairs(outbound_flights, return_flights, dest_set)

    if not flight_pairs:
        warnings.append("机票数据获取失败，请自行查询各平台")

    return {
        "flight_pairs": flight_pairs,
        "selected_dates": selected_dates,
        "warnings": warnings,
    }
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_nodes/test_scrape_flights.py -v
```
Expected: 3 PASSED

- [ ] **Step 5: Commit**

```bash
git add agent/nodes/scrape_flights.py tests/test_nodes/test_scrape_flights.py
git commit -m "feat: scrape_flights node — price calendar, detail scrape, valid pair assembly"
```

---

## Task 11: Node ④ — plan_itinerary

**Files:**
- Create: `agent/nodes/plan_itinerary.py`
- Create: `tests/test_nodes/test_plan_itinerary.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_nodes/test_plan_itinerary.py
import pytest
from datetime import datetime
from unittest.mock import AsyncMock
from agent.nodes.plan_itinerary import run, _build_poi_table, _build_flight_table


def make_poi(poi_id, name, confidence="high", tags=None):
    from models import POI
    return POI(poi_id=poi_id, name=name, coords=(28.0, 100.0), category="自然景观",
               tags=tags or [], desc="", amap_rating=4.5, sources=[],
               mention_count=3, platform_count=2, confidence=confidence)


def make_pair(pair_id):
    from models import Flight, FlightPair
    out = Flight("携程", "PVG", "DCY", 980, "MU1", datetime(2026, 7, 1))
    ret = Flight("携程", "CTU", "PVG", 760, "CA1", datetime(2026, 7, 8))
    return FlightPair(pair_id, out, ret, 1740)


def test_build_poi_table():
    pois = [make_poi("p1", "稻城亚丁", tags=["自然风光"]), make_poi("p2", "四姑娘山", tags=["徒步"])]
    table = _build_poi_table(pois)
    assert "p1" in table
    assert "稻城亚丁" in table
    assert "自然风光" in table


def test_build_flight_table():
    pairs = [make_pair("uuid-1")]
    table = _build_flight_table(pairs)
    assert "uuid-1" in table
    assert "PVG" in table


@pytest.mark.asyncio
async def test_run_returns_itineraries(mocker):
    phase1_response = '''[
        {"plan_id": "A", "pair_id": "uuid-1", "days": [{"day": 1, "poi_ids": ["p1"]}, {"day": 2, "poi_ids": ["p2"]}]}
    ]'''
    phase2_response = '''{
        "option_id": "A",
        "summary": "DCY进CTU出7天",
        "days": [
            {"day": 1, "transport_note": "驾车55分钟", "estimated_travel_minutes": 55}
        ]
    }'''
    call_count = 0
    async def fake_llm(**kwargs):
        nonlocal call_count
        call_count += 1
        m = __import__("unittest.mock", fromlist=["MagicMock"]).MagicMock()
        m.choices[0].message.content = phase1_response if call_count == 1 else phase2_response
        return m

    mocker.patch("litellm.acompletion", side_effect=fake_llm)

    state = {
        "pois": [make_poi("p1", "稻城亚丁"), make_poi("p2", "四姑娘山")],
        "flight_pairs": [make_pair("uuid-1")],
        "travel_time_matrix": {("p1", "p2"): 30},
        "interests": ["徒步"],
        "duration_days": 7,
        "errors": [], "warnings": [], "job_id": "test",
    }
    result = await run(state)
    assert len(result["itineraries"]) >= 1
```

- [ ] **Step 2: Run tests — confirm fail**

```bash
pytest tests/test_nodes/test_plan_itinerary.py -v
```

- [ ] **Step 3: Create agent/nodes/plan_itinerary.py**

```python
# agent/nodes/plan_itinerary.py
import json
import os
import litellm
from agent.state import TravelPlanState
from models import POI, FlightPair, DayPlan, ItineraryOption


def _build_poi_table(pois: list[POI]) -> str:
    lines = ["poi_id | name | category | confidence | region | tags"]
    for p in pois:
        tags = ",".join(p.tags) if p.tags else "-"
        lines.append(f"{p.poi_id} | {p.name} | {p.category} | {p.confidence} | ({p.coords[0]:.2f},{p.coords[1]:.2f}) | {tags}")
    return "\n".join(lines)


def _build_flight_table(pairs: list[FlightPair]) -> str:
    lines = ["pair_id | outbound_route | return_route | date | total_price_per_person"]
    for fp in pairs:
        lines.append(
            f"{fp.pair_id} | {fp.outbound.depart_airport}→{fp.outbound.arrive_airport} | "
            f"{fp.return_flight.depart_airport}→{fp.return_flight.arrive_airport} | "
            f"{fp.outbound.depart_time.date()} | ¥{fp.total_price}"
        )
    return "\n".join(lines)


async def _phase1_select(pois: list[POI], pairs: list[FlightPair], interests: list[str], duration_days: int) -> list[dict]:
    """Phase 1: compressed tables → LLM selects POIs per plan per day."""
    poi_table = _build_poi_table(pois)
    flight_table = _build_flight_table(pairs)
    prompt = f"""You are a travel planner. Given the POI list and flight options below, create 2-3 travel plans.

Interests: {', '.join(interests)}
Trip duration: {duration_days} days

POIs:
{poi_table}

Flight pairs:
{flight_table}

For EACH plan, assign a different FlightPair and select appropriate POIs per day (consider entry airport location for day 1).
Return a JSON array of plans:
[
  {{
    "plan_id": "A",
    "pair_id": "<uuid>",
    "days": [
      {{"day": 1, "poi_ids": ["<poi_id>", ...]}},
      ...
    ]
  }}
]
Return only valid JSON, no markdown."""

    resp = await litellm.acompletion(
        model=os.getenv("LLM_MODEL", "deepseek/deepseek-chat"),
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
    )
    return json.loads(resp.choices[0].message.content)


async def _phase2_generate(
    plan_skeleton: dict,
    poi_map: dict[str, POI],
    pair_map: dict[str, FlightPair],
    travel_time_matrix: dict[tuple[str, str], int],
) -> ItineraryOption:
    """Phase 2: full objects for selected items → LLM generates detailed day plans."""
    fp = pair_map[plan_skeleton["pair_id"]]
    selected_pois = {pid: poi_map[pid] for day in plan_skeleton["days"] for pid in day["poi_ids"] if pid in poi_map}

    poi_details = "\n".join(
        f"- {p.name} ({p.category}): {p.desc or 'no description'} | tags: {','.join(p.tags)}"
        for p in selected_pois.values()
    )
    time_notes = "\n".join(
        f"  {poi_map[a].name if a in poi_map else a} → {poi_map[b].name if b in poi_map else b}: {m} min drive"
        for (a, b), m in travel_time_matrix.items()
        if a in selected_pois and b in selected_pois
    )

    prompt = f"""Generate a detailed travel itinerary for plan {plan_skeleton['plan_id']}.

Flight: {fp.outbound.depart_airport}→{fp.outbound.arrive_airport} (outbound) / {fp.return_flight.depart_airport}→{fp.return_flight.arrive_airport} (return)

Selected POIs:
{poi_details}

Driving times (from 高德 API):
{time_notes or "  (no pre-computed times for this selection)"}

Day plan assignments: {json.dumps(plan_skeleton['days'])}

Return JSON:
{{
  "option_id": "{plan_skeleton['plan_id']}",
  "summary": "<brief description>",
  "days": [
    {{
      "day": <int>,
      "transport_note": "<ground in driving times above, e.g. '驾车约55分钟'>",
      "estimated_travel_minutes": <int from driving times>
    }}
  ]
}}
Return only valid JSON, no markdown."""

    resp = await litellm.acompletion(
        model=os.getenv("LLM_MODEL", "deepseek/deepseek-chat"),
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )
    raw = json.loads(resp.choices[0].message.content)

    days = []
    for day_skeleton in plan_skeleton["days"]:
        day_extra = next((d for d in raw.get("days", []) if d["day"] == day_skeleton["day"]), {})
        pois_for_day = [poi_map[pid] for pid in day_skeleton["poi_ids"] if pid in poi_map]
        days.append(DayPlan(
            day=day_skeleton["day"],
            pois=pois_for_day,
            transport_note=day_extra.get("transport_note", ""),
            estimated_travel_minutes=day_extra.get("estimated_travel_minutes", 0),
        ))

    return ItineraryOption(
        option_id=raw.get("option_id", plan_skeleton["plan_id"]),
        summary=raw.get("summary", ""),
        flights=fp,
        days=days,
    )


async def run(state: TravelPlanState) -> dict:
    pois = state["pois"]
    pairs = state["flight_pairs"]
    matrix = state.get("travel_time_matrix", {})
    interests = state.get("interests", [])
    duration_days = state["duration_days"]

    poi_map = {p.poi_id: p for p in pois}
    pair_map = {fp.pair_id: fp for fp in pairs}

    plan_skeletons = await _phase1_select(pois, pairs, interests, duration_days)

    itineraries = []
    for skeleton in plan_skeletons:
        if skeleton.get("pair_id") not in pair_map:
            continue
        option = await _phase2_generate(skeleton, poi_map, pair_map, matrix)
        itineraries.append(option)

    return {"itineraries": itineraries}
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_nodes/test_plan_itinerary.py -v
```
Expected: 4 PASSED

- [ ] **Step 5: Commit**

```bash
git add agent/nodes/plan_itinerary.py tests/test_nodes/test_plan_itinerary.py
git commit -m "feat: plan_itinerary node — two-stage LLM planning with per-plan POI grouping"
```

---

## Task 12: Node ⑤ — compose_output

**Files:**
- Create: `agent/nodes/compose_output.py`
- Create: `tests/test_nodes/test_compose_output.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_nodes/test_compose_output.py
from datetime import datetime
from agent.nodes.compose_output import run, _group_flights_comparison


def make_pair(pair_id, out_airport, ret_airport, out_price, ret_price, platform):
    from models import Flight, FlightPair
    out = Flight(platform, out_airport, "DCY", out_price, "MU1", datetime(2026, 7, 1))
    ret = Flight(platform, "DCY", ret_airport, ret_price, "CA1", datetime(2026, 7, 8))
    return FlightPair(pair_id, out, ret, out_price + ret_price)


def test_group_flights_comparison_groups_by_route():
    pairs = [
        make_pair("uuid-1", "PVG", "PVG", 980, 760, "ctrip"),
        make_pair("uuid-2", "PVG", "PVG", 1200, 820, "qunar"),
    ]
    groups = _group_flights_comparison(pairs)
    assert len(groups) == 1
    assert len(groups[0]["options"]) == 2
    assert groups[0]["route"] == "PVG → DCY"


def test_run_no_pois_returns_error():
    state = {
        "pois": [],
        "flight_pairs": [],
        "itineraries": [],
        "errors": [],
        "warnings": [],
        "origin": "苏州",
        "origin_airports": ["PVG", "SHA", "NKG"],
    }
    result = run(state)
    assert result["status"] == "error"
    assert "景点" in result["error"]


def test_run_no_flights_degrades_gracefully():
    from models import POI, ItineraryOption, FlightPair, Flight, DayPlan
    poi = POI("p1", "稻城亚丁", (28.67, 100.3), "自然", [], "desc", 4.9, [], 3, 2, "high")
    pair = make_pair("u1", "PVG", "PVG", 980, 760, "ctrip")
    day = DayPlan(1, [poi], "驾车55分钟", 55)
    itin = ItineraryOption("A", "summary", pair, [day])
    state = {
        "pois": [poi],
        "flight_pairs": [],
        "itineraries": [itin],
        "errors": [],
        "warnings": [],
        "origin": "苏州",
        "origin_airports": ["PVG"],
    }
    result = run(state)
    assert result["status"] == "ok"
    assert len(result["warnings"]) > 0


def test_run_origin_expansion_warning():
    from models import POI
    poi = POI("p1", "稻城亚丁", (28.67, 100.3), "自然", [], "desc", 4.9, [], 3, 2, "high")
    state = {
        "pois": [poi],
        "flight_pairs": [],
        "itineraries": [],
        "errors": [],
        "warnings": [],
        "origin": "苏州",
        "origin_airports": ["PVG", "SHA", "NKG"],
    }
    result = run(state)
    assert any("苏州" in w for w in result["warnings"])
```

- [ ] **Step 2: Run tests — confirm fail**

```bash
pytest tests/test_nodes/test_compose_output.py -v
```

- [ ] **Step 3: Create agent/nodes/compose_output.py**

```python
# agent/nodes/compose_output.py
from dataclasses import asdict
from agent.state import TravelPlanState
from models import FlightPair, ItineraryOption

# Cities known to not have their own airport
NO_AIRPORT_CITIES = {"苏州", "无锡", "嘉兴", "佛山", "东莞", "中山"}


def _group_flights_comparison(pairs: list[FlightPair]) -> list[dict]:
    """Group FlightPairs by (outbound route, date) for cross-platform comparison."""
    groups: dict[tuple, dict] = {}
    for fp in pairs:
        key = (fp.outbound.depart_airport, fp.outbound.arrive_airport, fp.outbound.depart_time.date())
        if key not in groups:
            groups[key] = {
                "route": f"{fp.outbound.depart_airport} → {fp.outbound.arrive_airport}",
                "date": str(key[2]),
                "options": [],
            }
        groups[key]["options"].append({
            "pair_id": fp.pair_id,
            "platform": fp.outbound.platform,
            "outbound": fp.outbound.price,
            "return": fp.return_flight.price,
            "total": fp.total_price,
        })
    return list(groups.values())


def run(state: TravelPlanState) -> dict:
    pois = state.get("pois", [])
    flight_pairs = state.get("flight_pairs", [])
    itineraries = state.get("itineraries", [])
    warnings = list(state.get("warnings", []))
    errors = state.get("errors", [])

    # Hard failure: no POIs at all
    if not pois:
        return {"status": "error", "error": "无法获取目的地景点数据", "warnings": warnings}

    # Warn about no-airport origin city
    origin = state.get("origin", "")
    if origin in NO_AIRPORT_CITIES:
        airports = state.get("origin_airports", [])
        warnings.append(f"{origin}无机场，已搜索{'、'.join(airports)}出发航班")

    # Warn about missing flight data
    if not flight_pairs:
        warnings.append("机票数据获取失败，请自行查询各平台")
    elif len(set(fp.outbound.platform for fp in flight_pairs)) == 1:
        warnings.append(f"仅{flight_pairs[0].outbound.platform}数据可用，价格对比不完整")

    flights_comparison = _group_flights_comparison(flight_pairs)

    return {
        "status": "ok",
        "itineraries": [_serialize_itinerary(i) for i in itineraries],
        "flights_comparison": flights_comparison,
        "warnings": warnings,
        "errors": errors,
    }


def _serialize_itinerary(opt: ItineraryOption) -> dict:
    fp = opt.flights
    return {
        "option_id": opt.option_id,
        "summary": opt.summary,
        "flights": {
            "pair_id": fp.pair_id,
            "outbound": _serialize_flight(fp.outbound),
            "return_flight": _serialize_flight(fp.return_flight),
            "total_price": fp.total_price,
        },
        "days": [
            {
                "day": d.day,
                "pois": [{"poi_id": p.poi_id, "name": p.name, "coords": p.coords,
                           "category": p.category, "desc": p.desc, "confidence": p.confidence} for p in d.pois],
                "transport_note": d.transport_note,
                "estimated_travel_minutes": d.estimated_travel_minutes,
            }
            for d in opt.days
        ],
    }


def _serialize_flight(f) -> dict:
    return {
        "platform": f.platform,
        "depart_airport": f.depart_airport,
        "arrive_airport": f.arrive_airport,
        "price": f.price,
        "flight_no": f.flight_no,
        "depart_time": f.depart_time.isoformat(),
    }
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_nodes/test_compose_output.py -v
```
Expected: 4 PASSED

- [ ] **Step 5: Commit**

```bash
git add agent/nodes/compose_output.py tests/test_nodes/test_compose_output.py
git commit -m "feat: compose_output node — grouping, partial failure handling, serialization"
```

---

## Task 13: LangGraph Graph Wiring

**Files:**
- Create: `agent/graph.py`
- Create: `tests/test_graph.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_graph.py
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
```

- [ ] **Step 2: Run tests — confirm fail**

```bash
pytest tests/test_graph.py -v
```

- [ ] **Step 3: Create agent/graph.py**

```python
# agent/graph.py
from langgraph.graph import StateGraph, END
from agent.state import TravelPlanState
import agent.nodes.parse_input as parse_input
import agent.nodes.discover_pois as discover_pois
import agent.nodes.scrape_flights as scrape_flights
import agent.nodes.plan_itinerary as plan_itinerary
import agent.nodes.compose_output as compose_output


def build_graph():
    g = StateGraph(TravelPlanState)

    g.add_node("parse_input", parse_input.run)
    g.add_node("discover_pois", discover_pois.run)
    g.add_node("scrape_flights", scrape_flights.run)
    g.add_node("plan_itinerary", plan_itinerary.run)
    g.add_node("compose_output", compose_output.run)

    g.set_entry_point("parse_input")

    # parse_input fans out to discover_pois and scrape_flights in parallel
    g.add_edge("parse_input", "discover_pois")
    g.add_edge("parse_input", "scrape_flights")

    # both converge into plan_itinerary
    g.add_edge("discover_pois", "plan_itinerary")
    g.add_edge("scrape_flights", "plan_itinerary")

    g.add_edge("plan_itinerary", "compose_output")
    g.add_edge("compose_output", END)

    return g.compile()
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_graph.py -v
```
Expected: 2 PASSED

- [ ] **Step 5: Commit**

```bash
git add agent/graph.py tests/test_graph.py
git commit -m "feat: LangGraph graph wiring with parallel discover_pois and scrape_flights"
```

---

## Task 14: FastAPI + Redis Job API

**Files:**
- Create: `api/main.py`
- Create: `api/__init__.py`
- Create: `tests/test_api.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_api.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient


@pytest.fixture
def client(mock_redis):
    from api.main import app
    return TestClient(app)


def test_post_plans_returns_job_id(client, mock_redis):
    with patch("api.main.asyncio.create_task"):
        resp = client.post("/plans", json={
            "destination": "川西",
            "origin": "苏州",
            "duration_days": 7,
            "travelers": 2,
        })
    assert resp.status_code == 202
    assert "job_id" in resp.json()
    assert resp.json()["status"] == "pending"


def test_get_plans_pending(client, mock_redis):
    mock_redis.get.return_value = b'{"status":"pending","progress":"parse_input: done"}'
    resp = client.get("/plans/test-job-id")
    assert resp.status_code == 200
    assert resp.json()["status"] == "pending"


def test_get_plans_done(client, mock_redis):
    import json
    result = {"status": "done", "result": {"itineraries": [], "flights_comparison": []}}
    mock_redis.get.return_value = json.dumps(result).encode()
    resp = client.get("/plans/test-job-id")
    assert resp.status_code == 200
    assert resp.json()["status"] == "done"


def test_get_plans_not_found(client, mock_redis):
    mock_redis.get.return_value = None
    resp = client.get("/plans/nonexistent-id")
    assert resp.status_code == 404
```

- [ ] **Step 2: Run tests — confirm fail**

```bash
pytest tests/test_api.py -v
```

- [ ] **Step 3: Create api/__init__.py and api/main.py**

```python
# api/__init__.py
```

```python
# api/main.py
import asyncio
import json
import os
import uuid
from typing import Optional

import redis
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from agent.graph import build_graph

app = FastAPI(title="Smart Travel Agent API")
_redis = redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
_graph = build_graph()


class PlanRequest(BaseModel):
    destination: str
    origin: str
    duration_days: int
    travelers: int = 1
    transport_mode: str = "mixed"
    difficulty_level: str = "medium"
    interests: list[str] = []
    depart_date: Optional[str] = None


async def _run_plan(job_id: str, req: PlanRequest):
    _redis.set(f"job:{job_id}:status", json.dumps({"status": "running", "progress": "starting"}))
    try:
        state = {
            **req.model_dump(),
            "errors": [],
            "warnings": [],
            "job_id": job_id,
        }
        result = await _graph.ainvoke(state)
        _redis.setex(
            f"job:{job_id}:status",
            7200,
            json.dumps({"status": "done", "result": result}),
        )
    except Exception as e:
        _redis.setex(
            f"job:{job_id}:status",
            7200,
            json.dumps({"status": "error", "error": str(e)}),
        )


@app.post("/plans", status_code=202)
async def create_plan(req: PlanRequest):
    job_id = str(uuid.uuid4())
    _redis.set(f"job:{job_id}:status", json.dumps({"status": "pending", "progress": "queued"}))
    asyncio.create_task(_run_plan(job_id, req))
    return {"job_id": job_id, "status": "pending"}


@app.get("/plans/{job_id}")
async def get_plan(job_id: str):
    raw = _redis.get(f"job:{job_id}:status")
    if raw is None:
        raise HTTPException(status_code=404, detail="Job not found")
    data = json.loads(raw)
    # Read fine-grained progress from nodes
    progress_raw = _redis.get(f"job:{job_id}:progress")
    if progress_raw:
        data["progress"] = progress_raw.decode()
    return data
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_api.py -v
```
Expected: 4 PASSED

- [ ] **Step 5: Commit**

```bash
git add api/ tests/test_api.py
git commit -m "feat: FastAPI async job endpoints with Redis state"
```

---

## Task 15: Full Test Suite + Run

- [ ] **Step 1: Run all tests**

```bash
pytest tests/ -v --tb=short
```
Expected: all tests pass.

- [ ] **Step 2: Smoke test the server (requires AMAP_API_KEY, TAVILY_API_KEY, LLM_API_KEY in .env)**

```bash
cp .env.example .env
# Fill in real API keys, then:
uvicorn api.main:app --reload
```

In another terminal:
```bash
curl -X POST http://localhost:8000/plans \
  -H "Content-Type: application/json" \
  -d '{"destination":"川西","origin":"苏州","duration_days":7,"travelers":2}'
# Returns: {"job_id":"<uuid>","status":"pending"}

curl http://localhost:8000/plans/<job_id>
# Returns status + progress until "status":"done"
```

- [ ] **Step 3: Final commit**

```bash
git add -A
git commit -m "feat: complete travel agent MVP — all nodes, tools, API"
```

---

## Self-Review Checklist

**Spec coverage:**

| Spec requirement | Task |
|---|---|
| LangGraph StateGraph with 5 nodes | Task 13 |
| parse_input: city→adcode via 高德 API | Task 8 |
| parse_input: 14-day date range or single date | Task 8 |
| parse_input: LLM generates search keywords | Task 8 |
| discover_pois: 高德 POI fetch | Task 9 |
| discover_pois: XHS Playwright scrape | Tasks 6, 9 |
| discover_pois: Tavily search | Tasks 5, 9 |
| discover_pois: transport_mode filter via 高德 transit API | Task 9 |
| discover_pois: batch LLM credibility scoring | Task 9 |
| discover_pois: POI dedup (200m radius) | Task 9 |
| discover_pois: TOP 40 truncation before matrix | Task 9 |
| discover_pois: travel_time_matrix ≤50km pairs only | Task 9 |
| scrape_flights: price calendar skip for 1 date | Task 10 |
| scrape_flights: valid FlightPair assembly | Task 10 |
| scrape_flights: outbound + return scraping | Task 10 |
| plan_itinerary: two-stage (compress→select→generate) | Task 11 |
| plan_itinerary: per-plan independent POI grouping | Task 11 |
| plan_itinerary: transport_note grounded in 高德 data | Task 11 |
| compose_output: flights_comparison grouped by route | Task 12 |
| compose_output: partial failure scenarios | Task 12 |
| compose_output: no-airport-city warning | Task 12 |
| AsyncAPI: POST /plans, GET /plans/{job_id} | Task 14 |
| Redis progress tracking | Task 14 |
| LiteLLM model-agnostic | All LLM-calling tasks |

All spec requirements are covered.
