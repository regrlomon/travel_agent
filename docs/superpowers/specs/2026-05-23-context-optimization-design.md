# LLM Context Optimization Design

**日期：** 2026-05-23
**状态：** APPROVED
**分支：** master
**上接：** [2026-05-22-travel-agent-refactor-design.md](./2026-05-22-travel-agent-refactor-design.md)

---

## 背景与目标

本设计针对 Travel Agent 的 **LLM 调用成本**进行优化，属于主动架构梳理，无现有线上故障。

**不在本次范围内：**
- LangGraph state 序列化问题（tuple key、sources 字段生命周期）——后续独立处理
- Phase 合并重构（`_phase1` + `_phase2` 合为单次调用）——留作第二阶段

---

## 当前成本分布（每 job 粗估）

| 调用点 | 位置 | 估算 tokens | 问题 |
|--------|------|-------------|------|
| `_score_sources_batch` | `discover_pois` | 2,500–8,000 | 文章数无上限，N×500字符线性增长 |
| `_phase1_select` | `plan_itinerary` | ~1,000 | 已压缩，40行 POI 表 |
| `_phase2_generate` | `plan_itinerary` | 3,000–6,000 | **3次独立调用**，POI 数据重复发送 |
| `parse_input` | `parse_input` | ~500 | 可忽略 |
| **合计** | | **~7,000–15,000** | |

---

## 优化方案

### 方案 A：战术补丁（文章批量控制 + Phase2 批处理合并）

**A-1：`_score_sources_batch` 分块控制**

引入常量：
```python
MAX_SCORE_ARTICLES = 10   # 单批上限
ARTICLE_SNIPPET_LEN = 250 # 截断长度（原 500）
```

超出上限时自动分批，结果合并返回：

```python
async def _score_sources_batch(articles: list[dict]) -> dict[str, dict]:
    if not articles:
        return {}
    result = {}
    for chunk_start in range(0, len(articles), MAX_SCORE_ARTICLES):
        chunk = articles[chunk_start : chunk_start + MAX_SCORE_ARTICLES]
        chunk_result = await _score_chunk(chunk, offset=chunk_start)
        result.update(chunk_result)
    return result

async def _score_chunk(articles: list[dict], offset: int) -> dict[str, dict]:
    """单批 LLM 评分调用，offset 保证 index 在全局列表中连续。"""
    batch_text = "\n---\n".join(
        f"[{offset + i}] ({a['platform']}): {a['content'][:ARTICLE_SNIPPET_LEN]}"
        for i, a in enumerate(articles)
    )
    # ... 原有 prompt + litellm.acompletion ...
```

**A-2：`_phase2_generate` 批处理合并**

新增函数 `_phase2_generate_batch`，替代原来的逐个调用：

```python
async def _phase2_generate_batch(
    skeletons: list[dict],
    poi_map: dict[str, POI],
    pair_map: dict[str, FlightPair],
    travel_time_matrix: dict[str, int],
) -> list[ItineraryOption]:
    # 1. 收集所有方案涉及的 POI（去重合并，只发一次）
    all_poi_ids = {
        pid
        for s in skeletons
        for day in s["days"]
        for pid in day["poi_ids"]
    }
    selected_pois = {pid: poi_map[pid] for pid in all_poi_ids if pid in poi_map}

    # 2. 构建共享 POI 详情和行驶时间（不重复）
    poi_details = "\n".join(
        f"- {p.name} ({p.category}): {p.desc or 'no description'} | tags: {','.join(p.tags)}"
        for p in selected_pois.values()
    )
    # 兼容当前 tuple key 格式（tuple[str, str] → (a, b)）
    # 后续 state 序列化修复后可改为字符串 key 解包
    time_notes = "\n".join(
        f"  {poi_map[a].name if a in poi_map else a} → "
        f"{poi_map[b].name if b in poi_map else b}: {m} min"
        for (a, b), m in travel_time_matrix.items()
        if a in selected_pois and b in selected_pois
    )

    # 3. 一次调用，返回所有方案
    prompt = f"""Generate detailed travel itineraries for {len(skeletons)} plans.

Shared POIs:
{poi_details}

Driving times:
{time_notes or "  (none pre-computed)"}

Plan skeletons:
{json.dumps(skeletons, ensure_ascii=False)}

Return a JSON array of {len(skeletons)} objects, one per plan, in the same order:
[
  {{
    "option_id": "<plan_id>",
    "summary": "<brief description>",
    "days": [
      {{
        "day": <int>,
        "transport_note": "<grounded in driving times>",
        "estimated_travel_minutes": <int>
      }}
    ]
  }}
]
Return only valid JSON, no markdown."""

    resp = await litellm.acompletion(
        model=os.getenv("LLM_MODEL", "deepseek/deepseek-chat"),
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )
    raw_list = json.loads(resp.choices[0].message.content)

    # 4. 按 skeleton 顺序组装 ItineraryOption（index 对齐，不依赖 option_id）
    itineraries = []
    for i, skeleton in enumerate(skeletons):
        raw = raw_list[i] if i < len(raw_list) else {}
        fp = pair_map[skeleton["pair_id"]]
        days = []
        for day_skeleton in skeleton["days"]:
            day_extra = next(
                (d for d in raw.get("days", []) if d["day"] == day_skeleton["day"]), {}
            )
            pois_for_day = [poi_map[pid] for pid in day_skeleton["poi_ids"] if pid in poi_map]
            days.append(DayPlan(
                day=day_skeleton["day"],
                pois=pois_for_day,
                transport_note=day_extra.get("transport_note", ""),
                estimated_travel_minutes=day_extra.get("estimated_travel_minutes", 0),
            ))
        itineraries.append(ItineraryOption(
            option_id=raw.get("option_id", skeleton["plan_id"]),
            summary=raw.get("summary", ""),
            flights=fp,
            days=days,
        ))
    return itineraries
```

**`run()` 调用方改动：**
```python
# 原来（3次循环调用）
itineraries = []
for skeleton in plan_skeletons:
    if skeleton.get("pair_id") not in pair_map:
        continue
    option = await _phase2_generate(skeleton, poi_map, pair_map, matrix)
    itineraries.append(option)

# 改后（1次批调用）
valid_skeletons = [s for s in plan_skeletons if s.get("pair_id") in pair_map]
itineraries = await _phase2_generate_batch(valid_skeletons, poi_map, pair_map, matrix)
```

---

### 方案 B：数据源头过滤

**B-1：文章预筛（`_prefilter_articles`）**

在 `_fetch_article_pois` 之后、`_score_sources_batch` 之前插入轻量规则过滤：

```python
MAX_ARTICLES_FOR_SCORING = 15  # 进入 LLM 评分的文章上限

def _prefilter_articles(
    articles: list[dict],
    keywords: list[str],
    max_count: int = MAX_ARTICLES_FOR_SCORING,
) -> list[dict]:
    """纯规则过滤，不调 LLM。按关键词命中数 + 文章长度排序，截取 top-N。"""
    def score(a: dict) -> float:
        text = a["content"].lower()
        keyword_hits = sum(kw.lower() in text for kw in keywords)
        length_bonus = min(len(text) / 500, 1.0)
        return keyword_hits + length_bonus

    return sorted(articles, key=score, reverse=True)[:max_count]
```

调用位置（`discover_pois.run`）：
```python
articles = await _fetch_article_pois(keywords, tools=tools)
articles = _prefilter_articles(articles, keywords)  # 新增截流
scores = await _score_sources_batch(articles)
```

**B-2：`MAX_POIS` 从 40 降至 25**

```python
# discover_pois.py
MAX_POIS = 25  # 原 40
```

POI 已按 confidence 降序排列，前 25 均为高/中置信度数据，`duration_days × 6` 条足够规划使用。Phase1 POI 表从 40 行降至 25 行，减少 ~37% 表格 token。

---

## 预计收益汇总

| 优化点 | token 变化 | 调用次数变化 |
|--------|------------|-------------|
| A-1 文章截断 500→250 | -50% per article | 不变 |
| A-1 文章分批上限 10 | 防峰值，20篇→2批×1,500 | +1（当文章>10时） |
| A-2 Phase2 合并 | POI 数据从 3份→1份（-60%） | -2 |
| B-1 文章预筛 15 上限 | 进入 LLM 的文章量可控 | 不变 |
| B-2 MAX_POIS=25 | Phase1 表 -37% | 不变 |
| **合计** | **-50% ~ -65%** | **-2 次** |

---

## 文件变更清单

| 文件 | 变更内容 |
|------|---------|
| `agent/nodes/discover_pois.py` | 新增 `_score_chunk`，改写 `_score_sources_batch` 为分批；新增 `_prefilter_articles`；`MAX_POIS` 改为 25；`MAX_ARTICLES_FOR_SCORING`、`ARTICLE_SNIPPET_LEN` 常量 |
| `agent/nodes/plan_itinerary.py` | 新增 `_phase2_generate_batch`；`run()` 改用批调用；可保留旧 `_phase2_generate` 供测试对比 |

---

## 测试策略

- `test_discover_pois.py`：验证文章数 > 10 时分批调用且 index 连续；验证预筛保留关键词命中最高的文章
- `test_plan_itinerary.py`：验证 batch 输出的 `ItineraryOption` 数量和 `option_id` 与输入 skeleton 对齐；mock LLM 返回短数组时的 fallback 行为

---

## 遗留问题（下次处理）

1. **LangGraph state 序列化**：`travel_time_matrix` 使用 `tuple[str, str]` key，JSON 不支持，需改为 `"poi_a:poi_b"` 字符串 key
2. **`POI.sources` 字段生命周期**：confidence 计算后应清空，减少 checkpoint 体积
3. **Phase 合并重构**：`_phase1_select` + `_phase2_generate_batch` 进一步合并为单次调用（第二阶段）
