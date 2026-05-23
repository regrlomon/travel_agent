# POI 缓存 + Prompt 重构设计

**日期**: 2026-05-23  
**范围**: XHS/Amap 数据缓存、LLM 提取替换为字符串匹配、plan_itinerary prompt 重构

---

## 背景

当前每次用户请求都会：
1. 调用高德 API 获取 POI
2. 抓取 XHS/Tavily 文章
3. 用 LLM 批量提取文章中的 POI 名称（`_score_sources_batch`）

这导致重复 API 调用和不必要的 LLM 消耗。同时 `_build_poi_table` 传给 LLM 的字段（`confidence`、坐标）信息量低，而 `mention_count`、`amap_rating`、`has_negative` 等有效信号反而没有传入。

---

## 设计目标

1. 缓存高德和 XHS 数据，避免重复请求
2. 用字符串匹配替换 LLM 提取 POI 名称
3. 重构 plan_itinerary prompt，传入真正有用的信号
4. 根据用户偏好处理有差评的 POI，并在行程备注中告知用户

---

## 模块一：`tools/xhs_cache.py`（新建）

### 表结构

```sql
CREATE TABLE poi_cache (
    city_key   TEXT NOT NULL,     -- 高德 adcode，多城市用"|"拼接，如 "310100" 或 "510100|513300"
    category   TEXT NOT NULL,     -- 景点 | 美食 | 娱乐
    source     TEXT NOT NULL,     -- amap | xhs
    cached_at  TEXT NOT NULL,     -- ISO datetime
    data       TEXT NOT NULL,     -- JSON blob
    PRIMARY KEY (city_key, category, source)
)
```

### data 字段结构

**source=amap**：
```json
[{"name": "外滩", "location": "121.49,31.23", "type": "景点", "biz_ext": {"rating": "4.8"}}, ...]
```

**source=xhs**：
```json
{"外滩": {"mention_count": 20, "has_negative": false}, "城隍庙": {"mention_count": 8, "has_negative": true}}
```

### TTL

- amap：30 天（POI 数据变化慢）
- xhs：7 天（用户评价实时性要求较高）

### 未配置时行为

读取 `XHS_CACHE_DB` 环境变量。未设置时：
- `get()` 返回 `None`（视为未命中，走正常流程）
- `set()` 为 no-op

调用方无需感知是否配置了缓存。

### 接口

```python
def get(city_key: str, category: str, source: str) -> dict | list | None
def set(city_key: str, category: str, source: str, data: dict | list)
```

---

## 模块二：`discover_pois.py` 改动

### 固定 category 关键词

```python
AMAP_CATEGORIES = ["景点", "美食", "娱乐"]

CATEGORY_KEYWORDS = {
    "景点": "{region} 景点攻略",
    "美食": "{region} 美食推荐",
    "娱乐": "{region} 娱乐活动",
}
```

`region` 来自 `state["destination_region"]`，在 `discover_pois.run()` 内部构造，不依赖 `parse_input` 生成的 keywords。

### 高德查询扩展

`search_pois` 的 `types` 参数扩展，一次请求覆盖景点 + 餐饮 + 娱乐：

```python
types = "110000|120000|140000|050000|080000"
```

### 缓存流程

```
city_key = "|".join(sorted(city_codes))

for category in AMAP_CATEGORIES:

    # Amap
    amap_data = cache.get(city_key, category, "amap")
    if not amap_data:
        amap_data = await _fetch_amap_pois(city_codes, category)
        cache.set(city_key, category, "amap", amap_data)

    # XHS
    xhs_data = cache.get(city_key, category, "xhs")
    if not xhs_data:
        keyword = CATEGORY_KEYWORDS[category].format(region=region)
        articles = await _fetch_article_pois([keyword])
        known_names = [p["name"] for p in amap_data]
        xhs_data = _match_pois_in_articles(articles, known_names)
        cache.set(city_key, category, "xhs", xhs_data)

    merge(amap_data, xhs_data) → pois 列表
```

### 字符串匹配（替换 `_score_sources_batch`）

```python
NEGATIVE_KW = ["排队", "坑", "不推荐", "踩雷", "失望", "太贵", "避雷", "后悔"]
AD_KW = ["合作", "探店", "种草推广", "联系我", "私信"]

def _match_pois_in_articles(articles: list[dict], known_names: list[str]) -> dict[str, dict]:
    result = {}
    for article in articles:
        text = article["content"]
        if any(kw in text for kw in AD_KW):
            continue
        has_negative = any(kw in text for kw in NEGATIVE_KW)
        for name in known_names:
            if name in text:
                if name not in result:
                    result[name] = {"mention_count": 0, "has_negative": False}
                result[name]["mention_count"] += 1
                if has_negative:
                    result[name]["has_negative"] = True
    return result
```

**局限**：`has_negative` 是文章级别，非 POI 级别。当前阶段可接受。

### 删除

- `_score_sources_batch` 函数整体删除

---

## 模块三：`plan_itinerary.py` 改动

### 新增 `_preprocess_pois()`

```
输入：pois: list[POI], interests: list[str]

逻辑：
  偏好判断：interests 含 "小众"/"安静"/"冷门" → niche_mode=True
  
  for each poi:
    if poi.has_negative:
      if niche_mode → 从列表中移除
      else → 保留，标记 warning=True

输出：处理后的 pois 列表
```

### 更新 `_build_poi_table()`

```
旧列：poi_id | name | category | confidence | region | tags
新列：poi_id | name | category | mention_count | amap_rating | warning | tags
```

`warning` 列：有差评显示 `⚠️`，否则为空。

### 更新 `_phase1_select` prompt 说明段

```
字段说明：
- mention_count: XHS/马蜂窝提及次数，越高越热门
- amap_rating: 高德评分（0-5）
- ⚠️: 近期用户评价中出现差评
```

### 更新 `_phase2_generate` prompt 指令

```
如果某 POI 标记了 ⚠️，在该天的 transport_note 中加一句提示，
示例："灵隐寺近期反馈排队较长，建议早上8点前到达"
```

---

## 模块四：`parse_input.py` + `state.py` 改动

### `parse_input.py`

`_llm_parse_destination` prompt 删除 `search_keywords` 字段：

```python
# 删除
- search_keywords: 3-5 Chinese queries e.g. ["川西 攻略"]

# 返回只剩
- region
- city_names
```

### `state.py`

删除字段：

```python
search_keywords: list[str]  # 删除
```

---

## 改动范围汇总

| 模块 | 类型 | 说明 |
|---|---|---|
| `tools/xhs_cache.py` | 新建 | SQLite 缓存，三字段联合主键 |
| `agent/nodes/discover_pois.py` | 修改 | 缓存接入 + 字符串匹配 + 固定关键词 |
| `agent/nodes/plan_itinerary.py` | 修改 | `_preprocess_pois` + prompt 重构 |
| `agent/nodes/parse_input.py` | 修改 | 删除 `search_keywords` 生成 |
| `agent/state.py` | 修改 | 删除 `search_keywords` 字段 |
| `tools/amap.py` | 修改 | `types` 参数扩展 |

---

## 不在本次范围内

- `has_negative` POI 级别细粒度分析（需要 NER 或 LLM）
- 用户历史偏好记录
- 大众点评等额外数据源
