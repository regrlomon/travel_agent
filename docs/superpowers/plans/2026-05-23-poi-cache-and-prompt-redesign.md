# POI 缓存 + Prompt 重构 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用 SQLite 缓存高德/XHS 数据，用字符串匹配替换 LLM POI 提取，重构 plan_itinerary prompt 以使用 mention_count/amap_rating/has_negative 信号。

**Architecture:** 新建 `tools/xhs_cache.py` 作为无副作用的 SQLite 工具；`discover_pois.py` 按 category 循环查缓存，未命中时调 API + 字符串匹配；`plan_itinerary.py` 新增 `_preprocess_pois` 做确定性过滤，再把结构化信号传给 LLM。

**Tech Stack:** Python 3.11, sqlite3 (stdlib), pytest, pytest-asyncio, pytest-mock

---

## File Map

| 文件 | 操作 | 说明 |
|---|---|---|
| `models.py` | 修改 | POI 增加 `has_negative`, `warning` 字段 |
| `tools/xhs_cache.py` | 新建 | SQLite 缓存，三字段联合主键 |
| `tools/amap.py` | 修改 | 新增 `CATEGORY_TYPES` 常量，`search_pois` 接受 `types` 覆盖 |
| `agent/nodes/discover_pois.py` | 修改 | 删 `_score_sources_batch`，加 `_match_pois_in_articles`，改 `run()` |
| `agent/state.py` | 修改 | 删 `search_keywords` 字段 |
| `agent/nodes/parse_input.py` | 修改 | LLM prompt 删 `search_keywords` |
| `agent/nodes/plan_itinerary.py` | 修改 | 加 `_preprocess_pois`，改 `_build_poi_table`，改两个 prompt |
| `tests/test_nodes/test_discover_pois.py` | 修改 | 更新 mock 和 make_state |
| `tests/test_nodes/test_plan_itinerary.py` | 修改 | 更新 make_poi，加新测试 |
| `tests/test_nodes/test_parse_input.py` | 修改 | 验证不再返回 search_keywords |
| `tests/test_tools/test_xhs_cache.py` | 新建 | 缓存单元测试 |

---

## Task 1: POI 模型增加 `has_negative` 和 `warning` 字段

**Files:**
- Modify: `models.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_models.py — 在文件末尾追加
def test_poi_has_negative_defaults_false():
    from models import POI
    p = POI(poi_id="x", name="外滩", coords=(31.0, 121.0), category="景点",
            desc="", amap_rating=4.5, mention_count=1, platform_count=1, confidence="medium")
    assert p.has_negative is False
    assert p.warning is False
```

- [ ] **Step 2: 运行，确认失败**

```
pytest tests/test_models.py::test_poi_has_negative_defaults_false -v
```

Expected: `FAILED` — `POI` 没有 `has_negative` 字段。

- [ ] **Step 3: 修改 `models.py`**

在 `POI` 类里加两行（放在 `confidence: str` 之后）：

```python
class POI(BaseModel):
    poi_id: str
    name: str
    coords: tuple[float, float]
    category: str
    tags: list[str] = []
    desc: str
    amap_rating: float
    sources: list[POISource] = []
    mention_count: int
    platform_count: int
    confidence: str
    has_negative: bool = False   # ← 新增
    warning: bool = False        # ← 新增
```

- [ ] **Step 4: 运行，确认通过**

```
pytest tests/test_models.py -v
```

Expected: 全部 PASS。

- [ ] **Step 5: 提交**

```
git add models.py tests/test_models.py
git commit -m "feat: add has_negative and warning fields to POI model"
```

---

## Task 2: 新建 `tools/xhs_cache.py`

**Files:**
- Create: `tools/xhs_cache.py`
- Create: `tests/test_tools/test_xhs_cache.py`

- [ ] **Step 1: 写失败测试**

新建 `tests/test_tools/test_xhs_cache.py`：

```python
import pytest
import importlib


def _reload_cache(monkeypatch, db_path=None):
    """重新加载模块以使 env var 生效。"""
    if db_path:
        monkeypatch.setenv("XHS_CACHE_DB", db_path)
    else:
        monkeypatch.delenv("XHS_CACHE_DB", raising=False)
    import tools.xhs_cache as m
    importlib.reload(m)
    return m


def test_get_returns_none_when_not_configured(monkeypatch):
    cache = _reload_cache(monkeypatch)
    assert cache.get("310100", "景点", "xhs") is None


def test_set_is_noop_when_not_configured(monkeypatch):
    cache = _reload_cache(monkeypatch)
    cache.set("310100", "景点", "xhs", {"外滩": {"mention_count": 5, "has_negative": False}})
    # 不应抛出异常


def test_cache_roundtrip(tmp_path, monkeypatch):
    cache = _reload_cache(monkeypatch, str(tmp_path / "cache.db"))
    data = {"外滩": {"mention_count": 10, "has_negative": False}}
    cache.set("310100", "景点", "xhs", data)
    assert cache.get("310100", "景点", "xhs") == data


def test_cache_miss_returns_none(tmp_path, monkeypatch):
    cache = _reload_cache(monkeypatch, str(tmp_path / "cache.db"))
    assert cache.get("310100", "美食", "xhs") is None


def test_cache_expired_returns_none(tmp_path, monkeypatch):
    from datetime import datetime, timedelta
    cache = _reload_cache(monkeypatch, str(tmp_path / "cache.db"))
    data = {"外滩": {"mention_count": 5, "has_negative": False}}
    cache.set("310100", "景点", "xhs", data)

    # 手动把 cached_at 改成 31 天前
    import sqlite3
    conn = sqlite3.connect(str(tmp_path / "cache.db"))
    old_ts = (datetime.now() - timedelta(days=31)).isoformat()
    conn.execute("UPDATE poi_cache SET cached_at = ? WHERE city_key = '310100'", (old_ts,))
    conn.commit()

    assert cache.get("310100", "景点", "xhs") is None


def test_amap_ttl_is_30_days(tmp_path, monkeypatch):
    from datetime import datetime, timedelta
    cache = _reload_cache(monkeypatch, str(tmp_path / "cache.db"))
    data = [{"name": "外滩"}]
    cache.set("310100", "景点", "amap", data)

    import sqlite3
    conn = sqlite3.connect(str(tmp_path / "cache.db"))
    old_ts = (datetime.now() - timedelta(days=29)).isoformat()
    conn.execute("UPDATE poi_cache SET cached_at = ? WHERE city_key = '310100'", (old_ts,))
    conn.commit()

    # amap TTL=30天，29天前的数据仍有效
    assert cache.get("310100", "景点", "amap") == data


def test_insert_or_replace_overwrites(tmp_path, monkeypatch):
    cache = _reload_cache(monkeypatch, str(tmp_path / "cache.db"))
    cache.set("310100", "景点", "xhs", {"外滩": {"mention_count": 5, "has_negative": False}})
    cache.set("310100", "景点", "xhs", {"外滩": {"mention_count": 99, "has_negative": True}})
    result = cache.get("310100", "景点", "xhs")
    assert result["外滩"]["mention_count"] == 99
```

- [ ] **Step 2: 运行，确认失败**

```
pytest tests/test_tools/test_xhs_cache.py -v
```

Expected: `ERROR` — `tools.xhs_cache` 模块不存在。

- [ ] **Step 3: 实现 `tools/xhs_cache.py`**

```python
import json
import os
import sqlite3
from datetime import datetime, timedelta

_TTL = {"amap": timedelta(days=30), "xhs": timedelta(days=7)}

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS poi_cache (
    city_key   TEXT NOT NULL,
    category   TEXT NOT NULL,
    source     TEXT NOT NULL,
    cached_at  TEXT NOT NULL,
    data       TEXT NOT NULL,
    PRIMARY KEY (city_key, category, source)
)
"""


def _db_path() -> str | None:
    return os.getenv("XHS_CACHE_DB")


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path())
    conn.execute(_CREATE_SQL)
    return conn


def get(city_key: str, category: str, source: str) -> dict | list | None:
    if not _db_path():
        return None
    row = _conn().execute(
        "SELECT cached_at, data FROM poi_cache WHERE city_key=? AND category=? AND source=?",
        (city_key, category, source),
    ).fetchone()
    if not row:
        return None
    age = datetime.now() - datetime.fromisoformat(row[0])
    if age > _TTL[source]:
        return None
    return json.loads(row[1])


def set(city_key: str, category: str, source: str, data: dict | list) -> None:
    if not _db_path():
        return
    conn = _conn()
    conn.execute(
        "INSERT OR REPLACE INTO poi_cache VALUES (?,?,?,?,?)",
        (city_key, category, source, datetime.now().isoformat(), json.dumps(data, ensure_ascii=False)),
    )
    conn.commit()
```

- [ ] **Step 4: 运行，确认通过**

```
pytest tests/test_tools/test_xhs_cache.py -v
```

Expected: 全部 PASS。

- [ ] **Step 5: 提交**

```
git add tools/xhs_cache.py tests/test_tools/test_xhs_cache.py
git commit -m "feat: add SQLite POI cache (tools/xhs_cache.py)"
```

---

## Task 3: `tools/amap.py` 新增 `CATEGORY_TYPES`

**Files:**
- Modify: `tools/amap.py`
- Modify: `tests/test_tools/test_amap.py`

- [ ] **Step 1: 查看现有 amap 测试**

```
cat tests/test_tools/test_amap.py
```

- [ ] **Step 2: 写失败测试**

在 `tests/test_tools/test_amap.py` 末尾追加：

```python
def test_category_types_covers_all_categories():
    from tools.amap import CATEGORY_TYPES
    assert "景点" in CATEGORY_TYPES
    assert "美食" in CATEGORY_TYPES
    assert "娱乐" in CATEGORY_TYPES
    # 景点必须包含风景名胜类型码
    assert "110000" in CATEGORY_TYPES["景点"]
    # 美食必须包含餐饮类型码
    assert "050000" in CATEGORY_TYPES["美食"]
```

- [ ] **Step 3: 运行，确认失败**

```
pytest tests/test_tools/test_amap.py::test_category_types_covers_all_categories -v
```

Expected: `FAILED` — `CATEGORY_TYPES` 不存在。

- [ ] **Step 4: 修改 `tools/amap.py`**

在文件顶部 `AMAP_BASE` 常量下方加：

```python
CATEGORY_TYPES: dict[str, str] = {
    "景点": "110000|120000|140000",
    "美食": "050000",
    "娱乐": "080000",
}
```

`search_pois` 签名不变，调用方通过 `types` 参数传入对应值。

- [ ] **Step 5: 运行，确认通过**

```
pytest tests/test_tools/test_amap.py -v
```

Expected: 全部 PASS。

- [ ] **Step 6: 提交**

```
git add tools/amap.py tests/test_tools/test_amap.py
git commit -m "feat: add CATEGORY_TYPES to amap tool"
```

---

## Task 4: `discover_pois.py` — 用字符串匹配替换 LLM 提取

**Files:**
- Modify: `agent/nodes/discover_pois.py`
- Modify: `tests/test_nodes/test_discover_pois.py`

- [ ] **Step 1: 写失败测试**

在 `tests/test_nodes/test_discover_pois.py` 末尾追加：

```python
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
    assert result["西湖"]["has_negative"] is True   # 同篇文章，文章级判断
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
```

- [ ] **Step 2: 运行，确认失败**

```
pytest tests/test_nodes/test_discover_pois.py::test_match_pois_counts_mentions -v
```

Expected: `FAILED` — `_match_pois_in_articles` 不存在。

- [ ] **Step 3: 在 `discover_pois.py` 中加入新函数，删除旧函数**

在文件顶部常量区（`MAX_POIS` 下方）加：

```python
_NEGATIVE_KW = ["排队", "坑", "不推荐", "踩雷", "失望", "太贵", "避雷", "后悔", "人太多"]
_AD_KW = ["合作", "探店", "种草推广", "联系我", "私信", "带货"]

AMAP_CATEGORIES = ["景点", "美食", "娱乐"]
CATEGORY_KEYWORDS = {
    "景点": "{region} 景点攻略",
    "美食": "{region} 美食推荐",
    "娱乐": "{region} 娱乐活动",
}
```

添加新函数（放在 `_dedup_pois` 之后）：

```python
def _match_pois_in_articles(articles: list[dict], known_names: list[str]) -> dict[str, dict]:
    """字符串匹配：在文章中找已知POI名称，统计mention_count和has_negative。"""
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
```

删除整个 `_score_sources_batch` 函数（约第 118-149 行）。

- [ ] **Step 4: 运行新测试，确认通过**

```
pytest tests/test_nodes/test_discover_pois.py::test_match_pois_counts_mentions tests/test_nodes/test_discover_pois.py::test_match_pois_skips_ad_articles tests/test_nodes/test_discover_pois.py::test_match_pois_empty_articles -v
```

Expected: 全部 PASS。

- [ ] **Step 5: 提交**

```
git add agent/nodes/discover_pois.py tests/test_nodes/test_discover_pois.py
git commit -m "feat: replace LLM batch extraction with string matching in discover_pois"
```

---

## Task 5: `discover_pois.py` — 更新 `run()` 接入缓存

**Files:**
- Modify: `agent/nodes/discover_pois.py`
- Modify: `tests/test_nodes/test_discover_pois.py`

- [ ] **Step 1: 更新 `run()` 函数**

将 `discover_pois.py` 中的 `run()` 函数完整替换为：

```python
async def run(state: TravelPlanState, config: RunnableConfig = None) -> dict:
    logger.info("[discover_pois] start, city_codes=%r region=%r",
                state.get("destination_amap_cities"), state.get("destination_region"))
    tools = config["configurable"]["tools"] if config else None
    city_codes = state["destination_amap_cities"]
    region = state.get("destination_region", "")
    city_key = "|".join(sorted(city_codes))

    from tools.amap import CATEGORY_TYPES
    import tools.xhs_cache as cache

    all_amap_raws: list[dict] = []
    xhs_mentions: dict[str, dict] = {}

    for category in AMAP_CATEGORIES:
        # ── Amap ──────────────────────────────────────────────────────────
        amap_data = cache.get(city_key, category, "amap")
        if not amap_data:
            amap_data = await _fetch_amap_pois(
                city_codes, keywords=category,
                types=CATEGORY_TYPES[category], tools=tools
            )
            cache.set(city_key, category, "amap", amap_data)
        all_amap_raws.extend(amap_data)

        # ── XHS ───────────────────────────────────────────────────────────
        xhs_data = cache.get(city_key, category, "xhs")
        if not xhs_data:
            keyword = CATEGORY_KEYWORDS[category].format(region=region)
            articles = await _fetch_article_pois([keyword], tools=tools)
            known_names = [r["name"] for r in amap_data]
            xhs_data = _match_pois_in_articles(articles, known_names)
            cache.set(city_key, category, "xhs", xhs_data)

        for name, data in xhs_data.items():
            if name in xhs_mentions:
                xhs_mentions[name]["mention_count"] += data["mention_count"]
                xhs_mentions[name]["has_negative"] = (
                    xhs_mentions[name]["has_negative"] or data["has_negative"]
                )
            else:
                xhs_mentions[name] = dict(data)

    # ── Build POI objects ─────────────────────────────────────────────────
    pois: list[POI] = []
    seen_names: set[str] = set()
    for raw in all_amap_raws:
        name = raw["name"]
        if name in seen_names:
            continue
        seen_names.add(name)
        loc = raw.get("location", "0,0").split(",")
        coords = (float(loc[1]), float(loc[0]))
        mention_data = xhs_mentions.get(name, {"mention_count": 0, "has_negative": False})
        p = POI(
            poi_id=str(uuid.uuid4()),
            name=name,
            coords=coords,
            category=raw.get("type", "景点"),
            tags=[],
            desc=raw.get("address", ""),
            amap_rating=float(raw.get("biz_ext", {}).get("rating") or 0),
            sources=[],
            mention_count=mention_data["mention_count"] + 1,
            platform_count=2 if mention_data["mention_count"] > 0 else 1,
            confidence="medium",
            has_negative=mention_data["has_negative"],
        )
        pois.append(p)

    # ── Confidence, dedup, truncate ───────────────────────────────────────
    for p in pois:
        p.confidence = _compute_confidence(
            p.mention_count,
            p.platform_count,
            amap_only=(p.platform_count == 1),
        )
    pois = _dedup_pois(pois)
    pois.sort(key=lambda p: ({"high": 0, "medium": 1, "low": 2}[p.confidence], -p.amap_rating))
    pois = pois[:MAX_POIS]

    matrix = await _build_travel_time_matrix(pois, tools=tools)
    logger.info("[discover_pois] done, pois=%d matrix_pairs=%d", len(pois), len(matrix))
    return {"pois": pois, "travel_time_matrix": matrix}
```

同时更新 `_fetch_amap_pois` 签名，增加 `types` 参数：

```python
async def _fetch_amap_pois(city_codes: list[str], keywords: str = "景点",
                            types: str = "110000|120000|140000",
                            tools: dict | None = None) -> list[dict]:
    try:
        if tools is not None:
            return await tools["amap"].search_pois(city_codes, keywords, types=types)
        from tools.amap import search_pois
        return await search_pois(city_codes, keywords, api_key=os.getenv("AMAP_API_KEY", ""), types=types)
    except Exception:
        logger.exception("高德 search_pois failed, city_codes=%r keywords=%r", city_codes, keywords)
        raise
```

- [ ] **Step 2: 更新 `AmapClient.search_pois` 支持 types 参数**

在 `tools/amap.py` 的 `AmapClient.search_pois` 加 `types` 参数透传：

```python
@traceable(name="amap_search_pois")
async def search_pois(self, city_codes: list[str], keywords: str = "景点",
                      types: str = "110000|120000|140000") -> list[dict]:
    return await search_pois(city_codes, keywords, api_key=self.api_key, types=types)
```

- [ ] **Step 3: 更新 `test_discover_pois.py` 中的 `make_state` 和 `test_run`**

将 `make_state()` 中的 `"search_keywords"` 行删除，并重写 `test_run_returns_pois_and_matrix`：

```python
def make_state():
    return {
        "destination_amap_cities": ["513300"],
        "destination_region": "甘孜州",
        "transport_mode": "self_drive",
        "difficulty_level": "medium",
        "interests": ["徒步"],
        "job_id": "test",
        "errors": [],
        "warnings": [],
    }


@pytest.mark.asyncio
async def test_run_returns_pois_and_matrix(mocker):
    mocker.patch("agent.nodes.discover_pois._fetch_amap_pois", new_callable=AsyncMock,
                 return_value=[
                     {"name": "稻城亚丁", "location": "100.3,28.67",
                      "type": "110000", "address": "四川", "biz_ext": {"rating": "4.9"}}
                 ])
    mocker.patch("agent.nodes.discover_pois._fetch_article_pois", new_callable=AsyncMock,
                 return_value=[])
    mocker.patch("agent.nodes.discover_pois._build_travel_time_matrix", new_callable=AsyncMock,
                 return_value={})
    mocker.patch("tools.xhs_cache.get", return_value=None)
    mocker.patch("tools.xhs_cache.set", return_value=None)

    result = await run(make_state())
    assert len(result["pois"]) >= 1
    assert result["pois"][0].name == "稻城亚丁"
    assert "travel_time_matrix" in result
```

- [ ] **Step 4: 运行所有 discover_pois 测试**

```
pytest tests/test_nodes/test_discover_pois.py -v
```

Expected: 全部 PASS。

- [ ] **Step 5: 提交**

```
git add agent/nodes/discover_pois.py tools/amap.py tests/test_nodes/test_discover_pois.py
git commit -m "feat: integrate cache and string matching into discover_pois.run()"
```

---

## Task 6: 删除 `search_keywords` — `state.py` + `parse_input.py`

**Files:**
- Modify: `agent/state.py`
- Modify: `agent/nodes/parse_input.py`
- Modify: `tests/test_nodes/test_parse_input.py`

- [ ] **Step 1: 写失败测试**

在 `tests/test_nodes/test_parse_input.py` 末尾追加：

```python
@pytest.mark.asyncio
async def test_run_does_not_return_search_keywords(mocker):
    mocker.patch(
        "agent.nodes.parse_input._llm_parse_destination",
        new_callable=AsyncMock,
        return_value={"region": "上海", "city_names": ["上海市"]},
    )
    mock_tools = {
        "amap": AsyncMock(),
    }
    mock_tools["amap"].get_district_codes = AsyncMock(return_value={"上海市": "310100"})
    config = {"configurable": {"tools": mock_tools}}
    state = {"destination": "上海", "origin": "北京", "errors": [], "warnings": []}
    result = await run(state, config)
    assert "search_keywords" not in result
    assert "destination_region" in result
    assert result["destination_amap_cities"] == ["310100"]
```

- [ ] **Step 2: 运行，确认当前测试状态**

```
pytest tests/test_nodes/test_parse_input.py -v
```

记录当前是否有 `search_keywords` 相关断言需要同时更新。

- [ ] **Step 3: 修改 `parse_input.py` 的 LLM prompt**

将 `_llm_parse_destination` 中的 prompt 改为：

```python
prompt = f"""You are a Chinese travel expert. Given destination "{destination}" departing from "{origin}":
Return JSON with:
- region: human-readable string e.g. "甘孜州+阿坝州"
- city_names: list of Chinese admin district names e.g. ["甘孜藏族自治州"]
Return only valid JSON, no markdown."""
```

将 `run()` 返回值中删除 `"search_keywords"` 行：

```python
return {
    "destination_region":       parsed["region"],
    "destination_amap_cities":  amap_cities,
    "destination_airports":     destination_airports,
    "origin_airports":          origin_airports,
    "depart_dates":             _expand_dates(state.get("depart_date")),
    # "search_keywords" 已删除
}
```

- [ ] **Step 4: 修改 `agent/state.py`**

删除 `search_keywords: list[str]` 这一行。

- [ ] **Step 5: 运行测试**

```
pytest tests/test_nodes/test_parse_input.py -v
```

Expected: 全部 PASS（包括新增的测试）。

- [ ] **Step 6: 提交**

```
git add agent/state.py agent/nodes/parse_input.py tests/test_nodes/test_parse_input.py
git commit -m "feat: remove search_keywords from state and parse_input LLM prompt"
```

---

## Task 7: `plan_itinerary.py` — `_preprocess_pois` + 更新 `_build_poi_table`

**Files:**
- Modify: `agent/nodes/plan_itinerary.py`
- Modify: `tests/test_nodes/test_plan_itinerary.py`

- [ ] **Step 1: 更新 `make_poi` 辅助函数，加新字段**

在 `tests/test_nodes/test_plan_itinerary.py` 中将 `make_poi` 改为：

```python
def make_poi(poi_id, name, confidence="high", tags=None,
             mention_count=3, amap_rating=4.5, has_negative=False, warning=False):
    from models import POI
    return POI(poi_id=poi_id, name=name, coords=(28.0, 100.0), category="自然景观",
               tags=tags or [], desc="", amap_rating=amap_rating, sources=[],
               mention_count=mention_count, platform_count=2, confidence=confidence,
               has_negative=has_negative, warning=warning)
```

- [ ] **Step 2: 写失败测试**

在 `tests/test_nodes/test_plan_itinerary.py` 末尾追加：

```python
def test_build_poi_table_includes_mention_and_rating():
    from agent.nodes.plan_itinerary import _build_poi_table
    poi = make_poi("p1", "外滩", mention_count=15, amap_rating=4.8)
    table = _build_poi_table([poi])
    assert "15" in table
    assert "4.8" in table
    assert "confidence" not in table
    assert "region" not in table


def test_build_poi_table_shows_warning_emoji():
    from agent.nodes.plan_itinerary import _build_poi_table
    poi = make_poi("p1", "灵隐寺", warning=True)
    table = _build_poi_table([poi])
    assert "⚠️" in table


def test_preprocess_pois_niche_mode_filters_negative():
    from agent.nodes.plan_itinerary import _preprocess_pois
    p_ok = make_poi("p1", "断桥", has_negative=False)
    p_bad = make_poi("p2", "灵隐寺", has_negative=True)
    result = _preprocess_pois([p_ok, p_bad], interests=["小众", "安静"])
    names = [p.name for p in result]
    assert "断桥" in names
    assert "灵隐寺" not in names


def test_preprocess_pois_popular_mode_keeps_negative_with_warning():
    from agent.nodes.plan_itinerary import _preprocess_pois
    p_bad = make_poi("p1", "灵隐寺", has_negative=True)
    result = _preprocess_pois([p_bad], interests=["热门景点", "网红打卡"])
    assert len(result) == 1
    assert result[0].warning is True


def test_preprocess_pois_default_keeps_negative_with_warning():
    from agent.nodes.plan_itinerary import _preprocess_pois
    p_bad = make_poi("p1", "灵隐寺", has_negative=True)
    result = _preprocess_pois([p_bad], interests=["历史文化"])
    assert len(result) == 1
    assert result[0].warning is True
```

- [ ] **Step 3: 运行，确认失败**

```
pytest tests/test_nodes/test_plan_itinerary.py::test_build_poi_table_includes_mention_and_rating tests/test_nodes/test_plan_itinerary.py::test_preprocess_pois_niche_mode_filters_negative -v
```

Expected: `FAILED`。

- [ ] **Step 4: 实现 `_preprocess_pois` 和更新 `_build_poi_table`**

在 `plan_itinerary.py` 中，将 `_build_poi_table` 替换为：

```python
def _build_poi_table(pois: list[POI]) -> str:
    lines = ["poi_id | name | category | mention_count | amap_rating | warning | tags"]
    for p in pois:
        tags = ",".join(p.tags) if p.tags else "-"
        warn = "⚠️" if p.warning else ""
        lines.append(
            f"{p.poi_id} | {p.name} | {p.category} | {p.mention_count} "
            f"| {p.amap_rating} | {warn} | {tags}"
        )
    return "\n".join(lines)
```

在 `_build_poi_table` 之前新增 `_preprocess_pois`：

```python
_NICHE_KEYWORDS = {"小众", "安静", "冷门", "人少", "清净"}
_POPULAR_KEYWORDS = {"热门", "网红", "必去", "打卡", "著名"}


def _preprocess_pois(pois: list[POI], interests: list[str]) -> list[POI]:
    interest_set = set(interests)
    niche_mode = bool(interest_set & _NICHE_KEYWORDS)

    result = []
    for p in pois:
        if p.has_negative and niche_mode:
            continue
        if p.has_negative:
            p.warning = True
        result.append(p)
    return result
```

- [ ] **Step 5: 运行全部 plan_itinerary 测试**

```
pytest tests/test_nodes/test_plan_itinerary.py -v
```

Expected: 全部 PASS。

- [ ] **Step 6: 提交**

```
git add agent/nodes/plan_itinerary.py tests/test_nodes/test_plan_itinerary.py
git commit -m "feat: add _preprocess_pois and update _build_poi_table with new signals"
```

---

## Task 8: `plan_itinerary.py` — 更新两个 LLM prompt

**Files:**
- Modify: `agent/nodes/plan_itinerary.py`
- Modify: `tests/test_nodes/test_plan_itinerary.py`

- [ ] **Step 1: 更新 `_phase1_select` 函数**

将 `_phase1_select` 的 prompt 中 POI 表格说明段替换为：

```python
prompt = f"""You are a travel planner. Create 2-3 travel plans.

Interests: {', '.join(interests)}
Trip duration: {duration_days} days{user_context}

POI field guide:
- mention_count: times mentioned in XHS/travel articles (higher = more popular)
- amap_rating: 高德 rating 0-5
- ⚠️: recent user complaints (crowds, disappointment, etc.)

POIs:
{poi_table}

{flight_section}
Return a JSON array of plans:
[
  {{
    "plan_id": "A",
    {pair_id_field}
    "days": [
      {{"day": 1, "poi_ids": ["<poi_id>", ...]}},
      ...
    ]
  }}
]
Return only valid JSON, no markdown."""
```

同时在 `run()` 中，在调用 `_phase1_select` 之前插入预处理：

```python
async def run(state: TravelPlanState, config: RunnableConfig = None) -> dict:
    ...
    pois = state["pois"]
    interests = state.get("interests", [])
    
    pois = _preprocess_pois(pois, interests)   # ← 新增
    
    poi_map = {p.poi_id: p for p in pois}
    ...
```

- [ ] **Step 2: 更新 `_phase2_generate` prompt**

在 `_phase2_generate` 的 prompt 中加一段警告指令，放在 `Driving times` 之后：

```python
warning_pois = [p.name for p in selected_pois.values() if p.warning]
warning_instruction = ""
if warning_pois:
    warning_instruction = f"""
Warning POIs (⚠️): {', '.join(warning_pois)}
For each ⚠️ POI in the day plan, add a practical tip in transport_note,
e.g. "灵隐寺近期反馈排队较长，建议早上8点前到达"
"""

prompt = f"""Generate a detailed travel itinerary for plan {plan_skeleton['plan_id']}.

{flight_line}

Selected POIs:
{poi_details}

Driving times (from 高德 API):
{time_notes or "  (no pre-computed times for this selection)"}
{warning_instruction}
Day plan assignments: {json.dumps(plan_skeleton['days'])}
...
"""
```

- [ ] **Step 3: 更新集成测试确认 `_preprocess_pois` 被调用**

在 `tests/test_nodes/test_plan_itinerary.py` 的 `test_run_returns_itineraries` 中，state 的 pois 保持现有数据不变（两个 POI 均无 `has_negative`，预处理不过滤），测试应继续通过。

追加一个测试确认小众模式过滤：

```python
@pytest.mark.asyncio
async def test_run_filters_negative_pois_in_niche_mode(mocker):
    phase1_response = '[{"plan_id": "A", "pair_id": null, "days": [{"day": 1, "poi_ids": ["p1"]}]}]'
    phase2_response = '{"option_id": "A", "summary": "test", "days": [{"day": 1, "transport_note": "", "estimated_travel_minutes": 0}]}'
    call_count = 0

    async def fake_ainvoke(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        m = MagicMock()
        m.content = phase1_response if call_count == 1 else phase2_response
        return m

    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(side_effect=fake_ainvoke)
    mocker.patch("agent.nodes.plan_itinerary.get_llm", return_value=mock_llm)

    state = {
        "pois": [
            make_poi("p1", "断桥", has_negative=False),
            make_poi("p2", "灵隐寺", has_negative=True),
        ],
        "flight_pairs": [],
        "travel_time_matrix": {},
        "interests": ["小众", "安静"],
        "duration_days": 3,
        "errors": [], "warnings": [], "job_id": "test",
    }
    result = await run(state)
    # phase1 prompt 应只包含断桥，灵隐寺被过滤
    first_call_prompt = mock_llm.ainvoke.call_args_list[0][0][0][0].content
    assert "灵隐寺" not in first_call_prompt
    assert "断桥" in first_call_prompt
```

- [ ] **Step 4: 运行全部测试**

```
pytest tests/test_nodes/test_plan_itinerary.py -v
```

Expected: 全部 PASS。

- [ ] **Step 5: 运行完整测试套件**

```
pytest tests/ -v --tb=short
```

Expected: 全部 PASS（或只有需要真实 API 的集成测试跳过）。

- [ ] **Step 6: 提交**

```
git add agent/nodes/plan_itinerary.py tests/test_nodes/test_plan_itinerary.py
git commit -m "feat: update plan_itinerary prompts with POI signals and warning instructions"
```

---

## 完成后验证

```bash
# 全部单元测试
pytest tests/ -v --tb=short

# 确认删除的函数不再被引用
grep -r "_score_sources_batch" agent/ tests/
# Expected: 无输出

# 确认 search_keywords 已从 state 和 parse_input 删除
grep -r "search_keywords" agent/ tests/
# Expected: 无输出
```
