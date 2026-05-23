# UI 全面重设计 + 流式进度 + Bug 修复 · 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把全部 7 个页面改为极光暗色设计（方案 A），进度页改为 Perplexity 风格流式展示，同时修复时段偏好未生效和费用标签误导两个 Bug。

**Architecture:** 后端新增 3 种 SSE 事件（`flight_found` / `poi_found` / `stream_text`），通过 `config["configurable"]["progress_emit"]` 注入到各节点；前端 `useSSE.js` 消费新事件，`ProgressView.vue` 全新流式 UI，其余视图只改样式不动逻辑。

**Tech Stack:** Vue 3 (Options → Composition API 不变), Python 3.12, LangChain `astream`, Redis Streams, pytest-asyncio

**Spec:** `docs/superpowers/specs/2026-05-23-ui-redesign-streaming-design.md`

---

## 文件清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `agent/nodes/scrape_flights.py` | 修改 | 修复 `_assemble_flight_pairs` + 发 `flight_found` |
| `agent/nodes/discover_pois.py` | 修改 | 发 `poi_found` 事件 |
| `agent/nodes/plan_itinerary.py` | 修改 | 新增流式叙述 `_stream_narrative` + 发 `stream_text` |
| `worker/tasks.py` | 修改 | `make_node_wrapper` 注入 `progress_emit` 到 config |
| `tests/test_nodes/test_scrape_flights.py` | 修改 | 更新+新增时段偏好测试 |
| `frontend/src/style.css` | 重写 | 换 Aurora 暗色 design token |
| `frontend/src/App.vue` | 修改 | TopBar 四步带标签进度条 |
| `frontend/src/components/ChatView.vue` | 修改 | Hero + 对话气泡 Aurora 化 |
| `frontend/src/components/SelectInterests.vue` | 修改 | 毛玻璃标签 |
| `frontend/src/components/ConfirmIntent.vue` | 修改 | 毛玻璃卡片 |
| `frontend/src/composables/useSSE.js` | 修改 | 处理 3 种新事件 |
| `frontend/src/components/ProgressView.vue` | 重写 | 流式 UI：航班卡 + POI chips + 文字流 |
| `frontend/src/components/PlanReview.vue` | 修改 | Aurora 卡片 + 费用标签修复 |
| `frontend/src/components/ResultView.vue` | 修改 | Aurora 卡片 + 费用标签修复 |

---

## Task 1：修复 `_assemble_flight_pairs` 时段偏好丢失

**Files:**
- Modify: `agent/nodes/scrape_flights.py`
- Modify: `tests/test_nodes/test_scrape_flights.py`

- [ ] **Step 1：写失败测试**

在 `tests/test_nodes/test_scrape_flights.py` 末尾添加：

```python
def make_flight(hour: int, airport_pair: tuple[str, str], price: int = 800, flight_no: str = "MU1") -> Flight:
    dep, arr = airport_pair
    return Flight(
        platform="test", depart_airport=dep, arrive_airport=arr,
        price=price, flight_no=flight_no,
        depart_time=datetime(2026, 7, 1, hour, 0),
    )


def test_assemble_pairs_time_pref_wins_over_price():
    """When depart_time_pref='上午', the first returned pair's outbound should depart in the morning."""
    # 三个去程：下午贵、早上贵、早上便宜
    out_afternoon = make_flight(14, ("CAN", "LXA"), price=500, flight_no="Z1")
    out_morning_exp = make_flight(9,  ("CAN", "LXA"), price=900, flight_no="Z2")
    out_morning_cheap = make_flight(8, ("CAN", "LXA"), price=600, flight_no="Z3")
    ret = make_flight(16, ("LXA", "CAN"), price=600, flight_no="R1")

    pairs = _assemble_flight_pairs(
        [out_afternoon, out_morning_exp, out_morning_cheap],
        [ret],
        depart_time_pref="上午",
    )

    # 第一个 pair 必须是上午出发（不能是最便宜的下午班）
    assert pairs[0].outbound.depart_time.hour < 12
    # 所有 pair 都有效
    for p in pairs:
        assert p.return_flight.depart_airport == p.outbound.arrive_airport


def test_assemble_pairs_max_3():
    """返回数量上限为 3。"""
    outbounds = [make_flight(h, ("CAN", "LXA"), flight_no=f"O{h}") for h in range(6, 12)]
    ret = make_flight(16, ("LXA", "CAN"), flight_no="R1")
    pairs = _assemble_flight_pairs(outbounds, [ret], depart_time_pref=None)
    assert len(pairs) <= 3


def test_assemble_pairs_no_pref_unchanged_behavior():
    """无偏好时行为与原来一致：有效配对，pair_id 不为空。"""
    out1 = make_flight(7, ("PVG", "DCY"), flight_no="A1")
    out2 = make_flight(9, ("PVG", "CTU"), flight_no="A2")
    ret1 = make_flight(16, ("DCY", "PVG"), flight_no="B1")
    ret2 = make_flight(18, ("CTU", "PVG"), flight_no="B2")
    pairs = _assemble_flight_pairs([out1, out2], [ret1, ret2])
    assert len(pairs) == 2
    for p in pairs:
        assert p.pair_id
        assert p.return_flight.depart_airport == p.outbound.arrive_airport
```

- [ ] **Step 2：运行测试确认失败**

```
cd D:\project\python\travel_agent
pytest tests/test_nodes/test_scrape_flights.py::test_assemble_pairs_time_pref_wins_over_price -v
```

期望：`FAILED` （`_assemble_flight_pairs` 不接受 `depart_time_pref` 参数）

- [ ] **Step 3：替换 `_assemble_flight_pairs` 实现**

在 `agent/nodes/scrape_flights.py` 中，将 `_assemble_flight_pairs` 函数**整体替换**为：

```python
def _assemble_flight_pairs(
    outbound_flights: list,
    return_flights: list,
    depart_time_pref: str | None = None,
    return_time_pref: str | None = None,
    max_pairs: int = 3,
) -> list[FlightPair]:
    """Return up to max_pairs FlightPairs ordered by time preference, then price.

    Replaces the old cheapest-only logic that discarded time preference sorting.
    """
    ranked_out = _rank_by_time_pref(outbound_flights, depart_time_pref)
    ranked_ret = _rank_by_time_pref(return_flights, return_time_pref)

    ret_by_airport: dict[str, list] = {}
    for ret in ranked_ret:
        ret_by_airport.setdefault(ret.depart_airport, []).append(ret)

    pairs: list[FlightPair] = []
    seen_flight_no: set[str] = set()

    for out in ranked_out:
        if len(pairs) >= max_pairs:
            break
        if out.flight_no in seen_flight_no:
            continue
        rets = ret_by_airport.get(out.arrive_airport, [])
        if not rets:
            continue
        best_ret = rets[0]  # already sorted by return time preference
        pairs.append(FlightPair(
            pair_id=str(uuid.uuid4()),
            outbound=out,
            return_flight=best_ret,
            total_price=out.price + best_ret.price,
        ))
        seen_flight_no.add(out.flight_no)

    return pairs
```

- [ ] **Step 4：更新 `run()` 调用点**

在 `scrape_flights.py` 的 `run()` 函数中，找到这两行并**删除**：

```python
outbound_flights = _rank_by_time_pref(outbound_flights, state.get("depart_time_pref"))
...
return_flights = _rank_by_time_pref(return_flights, state.get("return_time_pref"))
```

将 `_assemble_flight_pairs` 调用改为：

```python
flight_pairs = _assemble_flight_pairs(
    outbound_flights,
    return_flights,
    depart_time_pref=state.get("depart_time_pref"),
    return_time_pref=state.get("return_time_pref"),
)
```

- [ ] **Step 5：更新旧测试 `test_assemble_flight_pairs_valid_only`**

该测试的 `assert len(pairs) == 2` 依然成立（两条不同航线各返回 1 对）。但调用签名要加默认参数——不需要修改，因为新函数有默认值 `depart_time_pref=None`。直接运行即可。

- [ ] **Step 6：运行全部 scrape_flights 测试**

```
pytest tests/test_nodes/test_scrape_flights.py -v
```

期望：全部 `PASSED`

- [ ] **Step 7：commit**

```
git add agent/nodes/scrape_flights.py tests/test_nodes/test_scrape_flights.py
git commit -m "fix: _assemble_flight_pairs preserves time preference ordering"
```

---

## Task 2：`make_node_wrapper` 注入 `progress_emit` 到 config

**Files:**
- Modify: `worker/tasks.py`

- [ ] **Step 1：修改 `make_node_wrapper`**

将 `worker/tasks.py` 中 `make_node_wrapper` 的 `wrapped` 函数替换为：

```python
@functools.wraps(fn)
async def wrapped(state, config):
    if msg:
        _emit(job_id, {"type": "progress", "node": node_name, "message": msg})
    # Inject synchronous emit partial so nodes can emit mid-execution events
    configurable = dict((config or {}).get("configurable", {}))
    configurable["progress_emit"] = functools.partial(_emit, job_id)
    config = {**(config or {}), "configurable": configurable}
    return await fn(state, config)
```

- [ ] **Step 2：验证现有测试不受影响**

```
pytest tests/test_worker.py -v
```

期望：全部 `PASSED`

- [ ] **Step 3：commit**

```
git add worker/tasks.py
git commit -m "feat: inject progress_emit into node config for mid-execution streaming"
```

---

## Task 3：`scrape_flights` 发送 `flight_found` 事件

**Files:**
- Modify: `agent/nodes/scrape_flights.py`

- [ ] **Step 1：在 `run()` 末尾，`return` 语句前添加 emit 逻辑**

找到 `run()` 中 `if not flight_pairs:` 那段，在它之后、`return` 之前插入：

```python
    # Emit top-3 flight pairs for streaming UI
    emit_fn = (config or {}).get("configurable", {}).get("progress_emit")
    if emit_fn and flight_pairs:
        emit_fn({
            "type": "flight_found",
            "total_found": len(flight_pairs),
            "flights": [
                {
                    "pair_id": fp.pair_id,
                    "outbound_dep": fp.outbound.depart_airport,
                    "outbound_arr": fp.outbound.arrive_airport,
                    "outbound_time": fp.outbound.depart_time.strftime("%H:%M"),
                    "outbound_date": fp.outbound.depart_time.strftime("%Y-%m-%d"),
                    "return_time": fp.return_flight.depart_time.strftime("%H:%M"),
                    "flight_no": fp.outbound.flight_no,
                    "total_price": fp.total_price,
                }
                for fp in flight_pairs[:3]
            ],
        })
```

- [ ] **Step 2：运行测试**

```
pytest tests/test_nodes/test_scrape_flights.py -v
```

期望：全部 `PASSED`（emit_fn 为 None 时静默跳过）

- [ ] **Step 3：commit**

```
git add agent/nodes/scrape_flights.py
git commit -m "feat: emit flight_found SSE event after flight scraping"
```

---

## Task 4：`discover_pois` 发送 `poi_found` 事件

**Files:**
- Modify: `agent/nodes/discover_pois.py`

- [ ] **Step 1：在 `run()` 中 dedup 完成后、构建 travel matrix 前添加 emit**

找到注释 `# 7. Build travel time matrix` 那行，在它**之前**插入：

```python
    # Emit top POIs for streaming UI (after dedup and sort, before slow matrix call)
    emit_fn = (config or {}).get("configurable", {}).get("progress_emit") if config else None
    if emit_fn and pois:
        top_names = [p.name for p in pois[:10]]
        emit_fn({
            "type": "poi_found",
            "total_found": len(pois),
            "pois": top_names,
        })
```

- [ ] **Step 2：运行测试**

```
pytest tests/test_nodes/test_discover_pois.py -v
```

期望：全部 `PASSED`

- [ ] **Step 3：commit**

```
git add agent/nodes/discover_pois.py
git commit -m "feat: emit poi_found SSE event after POI discovery"
```

---

## Task 5：`plan_itinerary` 流式叙述 + `stream_text` 事件

**Files:**
- Modify: `agent/nodes/plan_itinerary.py`

- [ ] **Step 1：在文件顶部 import 区新增**

```python
from langchain_core.messages import HumanMessage  # 已有，确认存在
```

- [ ] **Step 2：在 `_phase1_select` 函数之前新增 `_stream_narrative`**

```python
async def _stream_narrative(
    pois: list,
    pairs: list,
    interests: list[str],
    duration_days: int,
    config,
    emit_fn,
) -> None:
    """Stream a brief natural-language summary via stream_text tokens.

    Called before the JSON-based planning phases so the user sees activity
    immediately. Uses astream() so tokens appear incrementally.
    """
    if emit_fn is None:
        return
    top_poi_names = ", ".join(p.name for p in pois[:6]) or "（待定）"
    flight_hint = ""
    if pairs:
        fp = pairs[0]
        flight_hint = f"，机票约 ¥{fp.total_price}/人，去程 {fp.outbound.depart_time.strftime('%H:%M')} 出发"
    prompt = (
        f"你是旅行规划助手，用2-3句中文自然语言（不用列表，不用JSON）概括以下信息：\n"
        f"- 行程：{duration_days}天\n"
        f"- 用户兴趣：{', '.join(interests) if interests else '综合观光'}\n"
        f"- 已收录景点代表：{top_poi_names}\n"
        f"- 航班情况：{'已找到可选航班' + flight_hint if pairs else '暂无航班数据'}\n"
        f"语气友好，直接输出文字，不要标题或符号。"
    )
    try:
        llm = get_llm(temperature=0.5)
        async for chunk in llm.astream([HumanMessage(content=prompt)], config):
            if chunk.content:
                emit_fn({"type": "stream_text", "token": chunk.content})
    except Exception:
        logger.warning("[plan_itinerary] narrative streaming failed, skipping")
```

- [ ] **Step 3：在 `run()` 中 `_phase1_select` 调用前插入 `_stream_narrative`**

找到 `plan_skeletons = await _phase1_select(...)` 这行，在它**之前**插入：

```python
    progress_emit = (config or {}).get("configurable", {}).get("progress_emit")
    await _stream_narrative(pois, pairs, interests, duration_days, config, progress_emit)
```

- [ ] **Step 4：运行测试**

```
pytest tests/test_nodes/test_plan_itinerary.py -v
```

期望：全部 `PASSED`（`emit_fn=None` 时 `_stream_narrative` 直接返回）

- [ ] **Step 5：commit**

```
git add agent/nodes/plan_itinerary.py
git commit -m "feat: stream narrative text tokens before itinerary planning"
```

---

## Task 6：`useSSE.js` 处理 3 种新事件

**Files:**
- Modify: `frontend/src/composables/useSSE.js`

- [ ] **Step 1：读当前文件确认现有结构**

```
# 确认 useSSE.js 中处理事件的 switch/if 块位置，以便插入新 case
```

- [ ] **Step 2：新增 reactive state**

在现有 `ref` 声明区追加：

```javascript
const streamingFlights = ref([])
const streamingPois    = ref([])
const streamText       = ref('')
const flightsTotalFound = ref(0)
const poisTotalFound    = ref(0)
```

- [ ] **Step 3：在事件处理 switch 中新增 3 个 case**

找到处理 `'progress'` 的地方，在同一 switch（或 if-else）里添加：

```javascript
case 'flight_found':
  streamingFlights.value  = data.flights ?? []
  flightsTotalFound.value = data.total_found ?? 0
  break

case 'poi_found':
  streamingPois.value  = data.pois ?? []
  poisTotalFound.value = data.total_found ?? 0
  break

case 'stream_text':
  streamText.value += data.token ?? ''
  break
```

- [ ] **Step 4：在 `startChat` 函数中重置新 state**

找到 `startChat` 或等价的开始新规划函数，在重置 `progressItems` 的位置同时重置：

```javascript
streamingFlights.value  = []
streamingPois.value     = []
streamText.value        = ''
flightsTotalFound.value = 0
poisTotalFound.value    = 0
```

- [ ] **Step 5：将新 state 加入 return 对象**

```javascript
return {
  // ... 现有字段 ...
  streamingFlights, streamingPois, streamText,
  flightsTotalFound, poisTotalFound,
}
```

- [ ] **Step 6：在浏览器开发者工具验证**

启动后端（或用 mock），触发一次规划，打开 Network → EventStream，确认出现 `flight_found` / `poi_found` / `stream_text` 事件。（后端改造完成后验证，当前 step 只需确认 JS 不报错。）

- [ ] **Step 7：commit**

```
git add frontend/src/composables/useSSE.js
git commit -m "feat: handle flight_found, poi_found, stream_text SSE events"
```

---

## Task 7：重写 `style.css` Design Token

**Files:**
- Modify: `frontend/src/style.css`

- [ ] **Step 1：将 `:root` 变量块替换为 Aurora 暗色 token**

```css
:root {
  --bg-base:        #080c14;
  --bg-surface:     #0d1320;
  --bg-elevated:    #111827;
  --bg-glass:       rgba(255, 255, 255, 0.05);
  --bg-input:       rgba(255, 255, 255, 0.06);
  --border:         rgba(255, 255, 255, 0.10);
  --border-subtle:  rgba(255, 255, 255, 0.06);
  --text-primary:   #e6edf3;
  --text-secondary: #8b949e;
  --text-muted:     #484f58;
  --accent:         #6c3bd5;
  --accent-end:     #1a6feb;
  --accent-hover:   #a78bfa;
  --accent-cyan:    #22d3ee;
  --success:        #3fb950;
  --warning:        #d29922;
  --error:          #f85149;
  --radius-sm:      6px;
  --radius-md:      14px;
  --radius-lg:      20px;
  --radius-full:    9999px;
}
```

- [ ] **Step 2：替换 `body` / `html` 基础样式**

```css
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

html, body {
  height: 100%;
  background: var(--bg-base);
  color: var(--text-primary);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
  font-size: 15px;
  line-height: 1.6;
  -webkit-font-smoothing: antialiased;
}

#app { height: 100%; display: flex; flex-direction: column; }
```

- [ ] **Step 3：替换全局共用组件样式**

```css
/* ── Aurora blobs (背景装饰，各页面共用) ── */
.aurora { position: absolute; inset: 0; pointer-events: none; overflow: hidden; z-index: 0; }
.aurora-blob {
  position: absolute; border-radius: 50%;
  filter: blur(90px); opacity: 0.22;
  animation: aurora-drift 10s ease-in-out infinite alternate;
}
.aurora-blob:nth-child(1) { width: 700px; height: 500px; background: radial-gradient(#6c3bd5, transparent); top: -150px; left: -150px; }
.aurora-blob:nth-child(2) { width: 600px; height: 400px; background: radial-gradient(#1a6feb, transparent); top: 80px; right: -100px; animation-delay: -4s; }
.aurora-blob:nth-child(3) { width: 500px; height: 350px; background: radial-gradient(#0e9f6e, transparent); bottom: 0; left: 25%; animation-delay: -7s; }
@keyframes aurora-drift { 0% { transform: translate(0, 0); } 100% { transform: translate(30px, 20px); } }

/* ── TopBar ── */
.topbar {
  background: rgba(13, 19, 32, 0.95);
  backdrop-filter: blur(12px);
  border-bottom: 1px solid var(--border);
  padding: 0 28px;
  height: 56px;
  display: flex; align-items: center; justify-content: space-between;
  flex-shrink: 0; position: relative; z-index: 10;
}
.topbar-brand { font-weight: 700; font-size: 13px; color: var(--accent-hover); letter-spacing: 0.5px; }

/* ── 四步进度条 ── */
.stepper { display: flex; align-items: center; gap: 0; }
.step-item { display: flex; align-items: center; gap: 6px; }
.step-dot {
  width: 28px; height: 28px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-size: 12px; font-weight: 700; flex-shrink: 0; transition: all 0.3s;
}
.step-dot.done   { background: var(--success); color: #fff; }
.step-dot.active { background: linear-gradient(135deg, var(--accent), var(--accent-end)); color: #fff; box-shadow: 0 0 14px rgba(108, 59, 213, 0.5); }
.step-dot.pending { background: rgba(255,255,255,.07); color: var(--text-muted); border: 1px solid var(--border); }
.step-label { font-size: 11px; font-weight: 600; transition: color 0.3s; }
.step-label.done    { color: var(--success); }
.step-label.active  { color: var(--accent-hover); }
.step-label.pending { color: var(--text-muted); }
.step-line { width: 28px; height: 1px; background: var(--border); margin: 0 4px; transition: background 0.3s; }
.step-line.done { background: var(--success); }

/* ── 内容区 ── */
.view { flex: 1; overflow-y: auto; position: relative; }

/* ── 气泡 ── */
.chat-messages {
  max-width: 720px; margin: 0 auto;
  padding: 24px 24px 0;
  display: flex; flex-direction: column; gap: 14px;
}
.bubble-row { display: flex; gap: 10px; align-items: flex-end; }
.bubble-row.user { flex-direction: row-reverse; }

.bubble-avatar {
  width: 36px; height: 36px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-size: 13px; font-weight: 700; flex-shrink: 0;
}
.bubble-avatar.ai-avatar   { background: linear-gradient(135deg, var(--accent), var(--accent-end)); color: #fff; }
.bubble-avatar.user-avatar { background: rgba(255,255,255,.08); border: 1px solid var(--border); color: var(--text-muted); font-size: 11px; }

.bubble {
  max-width: 70%; padding: 12px 16px;
  font-size: 14px; line-height: 1.7; border-radius: var(--radius-md);
}
.bubble.ai   { background: var(--bg-glass); border: 1px solid var(--border); border-bottom-left-radius: 4px; }
.bubble.user { background: linear-gradient(135deg, var(--accent), var(--accent-end)); color: #fff; border-bottom-right-radius: 4px; }

/* ── 输入栏 ── */
.input-bar {
  max-width: 720px; margin: 16px auto; padding: 0 24px;
  display: flex; gap: 10px; align-items: center;
}
.input-bar input {
  flex: 1;
  background: var(--bg-input); border: 1px solid var(--border);
  border-radius: var(--radius-full); padding: 12px 20px;
  font-size: 14px; color: var(--text-primary); outline: none;
  transition: border-color 0.2s, box-shadow 0.2s;
}
.input-bar input::placeholder { color: var(--text-muted); }
.input-bar input:focus { border-color: rgba(108,59,213,.7); box-shadow: 0 0 0 3px rgba(108,59,213,.12); }

.btn-send {
  width: 42px; height: 42px; border-radius: 50%;
  background: linear-gradient(135deg, var(--accent), var(--accent-end));
  border: none; cursor: pointer; color: #fff; font-size: 17px;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0; transition: opacity 0.2s;
}
.btn-send:hover { opacity: 0.85; }
.btn-send:disabled { background: rgba(255,255,255,.08); cursor: not-allowed; opacity: 1; }

/* ── Plan cards (PlanReview) ── */
.review-view  { max-width: 860px; margin: 32px auto; padding: 0 24px; }
.review-title { font-size: 20px; font-weight: 700; margin-bottom: 6px; }
.review-subtitle { font-size: 13px; color: var(--text-secondary); margin-bottom: 24px; }

.plan-cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 16px; margin-bottom: 24px; }
.plan-card {
  background: var(--bg-glass); border: 1px solid var(--border);
  border-radius: var(--radius-lg); padding: 20px; cursor: pointer;
  transition: border-color 0.2s, background 0.2s, box-shadow 0.2s;
}
.plan-card:hover { border-color: rgba(108,59,213,.4); background: rgba(108,59,213,.06); }
.plan-card.selected {
  border-color: var(--accent);
  background: rgba(108,59,213,.12);
  box-shadow: 0 0 0 1px var(--accent), 0 8px 32px rgba(108,59,213,.2);
}
.plan-option-id  { font-size: 11px; font-weight: 700; color: #7c3aed; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 8px; }
.plan-summary    { font-size: 14px; font-weight: 700; color: var(--text-primary); margin-bottom: 12px; line-height: 1.4; }

.plan-flight-block {
  background: rgba(255,255,255,.04); border-radius: 10px;
  padding: 10px 12px; margin-bottom: 12px;
}
.plan-flight-label { font-size: 11px; color: var(--text-muted); margin-bottom: 6px; }
.plan-flight-row { display: flex; align-items: center; justify-content: space-between; }
.plan-flight-time { font-size: 20px; font-weight: 700; color: var(--text-primary); }
.plan-flight-city { font-size: 11px; color: var(--text-secondary); margin-bottom: 2px; }
.plan-flight-arrow { color: var(--text-muted); font-size: 14px; }

.plan-price { font-size: 15px; font-weight: 700; color: var(--accent-cyan); margin-top: 10px; }
.plan-price-label { font-size: 11px; color: var(--text-muted); font-weight: 400; }
.plan-days-new { display: flex; flex-direction: column; gap: 4px; }
.plan-day-row  { font-size: 12px; color: var(--text-muted); }
.plan-day-row span { color: var(--text-secondary); }
.plan-selected-badge {
  display: inline-flex; align-items: center; gap: 4px;
  background: rgba(108,59,213,.2); border: 1px solid rgba(108,59,213,.4);
  border-radius: var(--radius-full); padding: 3px 10px;
  font-size: 11px; color: var(--accent-hover); margin-top: 8px;
}

/* ── Result view ── */
.result-view { max-width: 800px; margin: 32px auto; padding: 0 24px 48px; }
.result-header { margin-bottom: 28px; }
.result-title { font-size: 24px; font-weight: 800; background: linear-gradient(135deg,#fff,#c4b5fd,#67e8f9); -webkit-background-clip:text; -webkit-text-fill-color:transparent; background-clip:text; }
.result-sub { font-size: 13px; color: var(--text-secondary); margin-top: 4px; }

.itinerary-card { background: var(--bg-glass); border: 1px solid var(--border); border-radius: var(--radius-lg); overflow: hidden; margin-bottom: 16px; }
.itin-top { background: linear-gradient(135deg,rgba(108,59,213,.2),rgba(26,111,235,.15)); border-bottom:1px solid var(--border-subtle); padding: 20px 24px; display:flex; justify-content:space-between; align-items:flex-start; }
.itin-option { font-size:11px; color:var(--accent-hover); font-weight:700; text-transform:uppercase; letter-spacing:1px; }
.itin-name   { font-size:17px; font-weight:700; margin-top:2px; }
.itin-price  { font-size:26px; font-weight:800; color:var(--accent-cyan); }
.itin-price-label { font-size:11px; color:var(--text-muted); text-align:right; margin-top:2px; }

.itin-flight-strip { padding:14px 24px; border-bottom:1px solid var(--border-subtle); display:flex; align-items:center; gap:16px; font-size:13px; color:var(--text-secondary); flex-wrap:wrap; }

.itin-days { padding:16px 24px; display:flex; flex-direction:column; gap:12px; }
.day-row   { display:flex; gap:14px; align-items:flex-start; }
.day-badge { min-width:44px; padding:4px 10px; border-radius:8px; text-align:center; background:rgba(108,59,213,.15); border:1px solid rgba(108,59,213,.3); font-size:11px; font-weight:700; color:var(--accent-hover); }
.day-pois  { display:flex; flex-wrap:wrap; gap:6px; }
.poi-chip  { background:var(--bg-glass); border:1px solid var(--border); border-radius:var(--radius-full); padding:4px 12px; font-size:12px; color:var(--text-secondary); }
.day-note  { font-size:12px; color:var(--text-muted); margin-top:4px; }

.warning-box { background:rgba(210,153,34,.1); border:1px solid var(--warning); border-radius:var(--radius-sm); padding:10px 14px; font-size:13px; color:var(--warning); margin-bottom:20px; }
```

- [ ] **Step 3：在浏览器确认 http://localhost:5174/ 背景变为 `#080c14`（极暗蓝黑），无报错**

- [ ] **Step 4：commit**

```
git add frontend/src/style.css
git commit -m "feat: apply Aurora dark design tokens to style.css"
```

---

## Task 8：TopBar 四步进度条（App.vue）

**Files:**
- Modify: `frontend/src/App.vue`

- [ ] **Step 1：替换 `<header class="topbar">` 内容**

```html
<header class="topbar">
  <span class="topbar-brand">✈ TRAVEL AI</span>
  <div class="stepper">
    <div class="step-item">
      <div class="step-dot" :class="stepClass(1)">
        <span v-if="stepClass(1) === 'done'">✓</span>
        <span v-else>1</span>
      </div>
      <span class="step-label" :class="stepClass(1)">告诉我</span>
    </div>
    <div class="step-line" :class="{ done: stepClass(1) === 'done' }"></div>
    <div class="step-item">
      <div class="step-dot" :class="stepClass(2)">
        <span v-if="stepClass(2) === 'done'">✓</span>
        <span v-else>2</span>
      </div>
      <span class="step-label" :class="stepClass(2)">规划中</span>
    </div>
    <div class="step-line" :class="{ done: stepClass(2) === 'done' }"></div>
    <div class="step-item">
      <div class="step-dot" :class="stepClass(3)">
        <span v-if="stepClass(3) === 'done'">✓</span>
        <span v-else>3</span>
      </div>
      <span class="step-label" :class="stepClass(3)">选方案</span>
    </div>
    <div class="step-line" :class="{ done: stepClass(3) === 'done' }"></div>
    <div class="step-item">
      <div class="step-dot" :class="stepClass(4)">
        <span v-if="stepClass(4) === 'done'">✓</span>
        <span v-else>4</span>
      </div>
      <span class="step-label" :class="stepClass(4)">出发</span>
    </div>
  </div>
</header>
```

- [ ] **Step 2：更新 `stepClass()` 函数**

```javascript
function stepClass(n) {
  const map = { idle: 0, chat: 1, interests: 1, confirm: 1, progress: 2, review: 3, done: 4, error: 0 }
  const current = map[phase.value] ?? 0
  if (n < current) return 'done'
  if (n === current) return 'active'
  return 'pending'
}
```

- [ ] **Step 3：在浏览器验证进度条正常显示，四步带标签，当前步骤发光**

- [ ] **Step 4：commit**

```
git add frontend/src/App.vue
git commit -m "feat: replace step dots with labeled 4-step progress bar"
```

---

## Task 9：ChatView.vue Aurora 化（Hero + 对话）

**Files:**
- Modify: `frontend/src/components/ChatView.vue`

- [ ] **Step 1：替换整个 `<template>`**

```html
<template>
  <div class="view chat-view">
    <!-- Aurora background -->
    <div class="aurora">
      <div class="aurora-blob"></div>
      <div class="aurora-blob"></div>
      <div class="aurora-blob"></div>
    </div>

    <!-- Hero: 无消息时 -->
    <div v-if="messages.length === 0" class="hero">
      <div class="hero-eyebrow">
        <span class="hero-pulse"></span>AI 国内旅行规划助手
      </div>
      <h1 class="hero-title">去你一直<br>想去的地方</h1>
      <p class="hero-sub">一句话描述你的旅行想法，AI 自动匹配国内机票与行程方案</p>

      <div class="input-bar hero-input">
        <input
          v-model="draft"
          placeholder="比如「7月去西藏看星空，从广州出发，5天」"
          @keydown.enter.prevent="send"
          ref="inputEl"
        />
        <button class="btn-send" @click="send" :disabled="!draft.trim()">→</button>
      </div>

      <div class="hero-chips">
        <span v-for="s in suggestions" :key="s.label" class="hero-chip" @click="fillSuggestion(s.text)">
          {{ s.label }}
        </span>
      </div>
    </div>

    <!-- 对话气泡 -->
    <div v-else class="chat-messages">
      <div v-for="(msg, i) in messages" :key="i" class="bubble-row" :class="msg.role">
        <div class="bubble-avatar" :class="msg.role === 'ai' ? 'ai-avatar' : 'user-avatar'">
          {{ msg.role === 'ai' ? 'AI' : '我' }}
        </div>
        <div class="bubble" :class="msg.role">{{ msg.text }}</div>
      </div>

      <div v-if="waiting" class="bubble-row ai">
        <div class="bubble-avatar ai-avatar">AI</div>
        <div class="bubble ai typing-bubble">
          <span class="typing-dot"></span>
          <span class="typing-dot"></span>
          <span class="typing-dot"></span>
        </div>
      </div>
    </div>

    <!-- 输入栏：对话时显示 -->
    <div v-if="messages.length > 0" class="input-bar">
      <input
        v-model="draft"
        placeholder="继续输入…"
        @keydown.enter.prevent="send"
        :disabled="waiting"
        ref="inputEl"
      />
      <button class="btn-send" @click="send" :disabled="!draft.trim() || waiting">→</button>
    </div>
  </div>
</template>
```

- [ ] **Step 2：替换 `<script setup>`**

```javascript
<script setup>
import { ref, nextTick } from 'vue'

const props = defineProps({ messages: Array, waiting: Boolean })
const emit = defineEmits(['send'])

const draft  = ref('')
const inputEl = ref(null)

const suggestions = [
  { label: '🏔 西藏·星空徒步', text: '想去西藏看星空，7月，从广州出发，5天' },
  { label: '🌊 三亚·亲子海岛', text: '三亚亲子游，8月，从北京出发，4天' },
  { label: '🎭 大理·慢生活',   text: '大理慢生活，5月，从上海出发，7天' },
  { label: '🏞 张家界·奇峰',  text: '张家界，国庆，从广州出发，5天' },
  { label: '🌸 成都·美食',    text: '成都美食之旅，下个月，从北京出发，4天' },
]

function send() {
  const text = draft.value.trim()
  if (!text) return
  draft.value = ''
  emit('send', text)
  nextTick(() => inputEl.value?.focus())
}

function fillSuggestion(text) {
  draft.value = text
  nextTick(() => inputEl.value?.focus())
}
</script>
```

- [ ] **Step 3：替换 `<style scoped>`**

```css
<style scoped>
.chat-view { display: flex; flex-direction: column; height: 100%; }

/* Hero */
.hero {
  flex: 1; position: relative; z-index: 2;
  display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  text-align: center; gap: 24px; padding: 48px 24px 0;
}
.hero-eyebrow {
  display: inline-flex; align-items: center; gap: 8px;
  background: rgba(255,255,255,.07); border: 1px solid rgba(255,255,255,.15);
  border-radius: 20px; padding: 6px 16px; font-size: 12px; color: #9ca3af;
}
.hero-pulse {
  width: 6px; height: 6px; border-radius: 50%; background: #22d3ee;
  animation: pulse 2s ease-in-out infinite;
}
@keyframes pulse { 0%,100%{opacity:1;transform:scale(1)} 50%{opacity:.5;transform:scale(.8)} }

.hero-title {
  font-size: clamp(40px, 7vw, 68px); font-weight: 800; line-height: 1.1;
  background: linear-gradient(135deg, #fff 0%, #c4b5fd 50%, #67e8f9 100%);
  -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text;
}
.hero-sub { font-size: 15px; color: #6b7280; max-width: 420px; }

.hero-input { max-width: 580px; width: 100%; margin: 0; padding: 0; }

.hero-chips { display: flex; flex-wrap: wrap; justify-content: center; gap: 8px; max-width: 580px; }
.hero-chip {
  background: rgba(255,255,255,.06); border: 1px solid rgba(255,255,255,.12);
  border-radius: 20px; padding: 7px 16px; font-size: 13px; color: #9ca3af;
  cursor: pointer; transition: all .2s;
}
.hero-chip:hover { background: rgba(255,255,255,.12); color: #e5e7eb; border-color: rgba(255,255,255,.25); }

/* Chat messages */
.chat-messages { flex: 1; position: relative; z-index: 2; }

/* Typing */
.typing-bubble {
  display: flex; gap: 5px; align-items: center;
  padding: 14px 18px;
}
.typing-dot {
  width: 7px; height: 7px; border-radius: 50%; background: #a78bfa;
  animation: blink 1.2s infinite;
}
.typing-dot:nth-child(2) { animation-delay: .2s; }
.typing-dot:nth-child(3) { animation-delay: .4s; }
@keyframes blink { 0%,80%,100%{opacity:.2} 40%{opacity:1} }
</style>
```

- [ ] **Step 4：浏览器验证 Hero 页极光背景 + 渐变标题正常，气泡样式更新**

- [ ] **Step 5：commit**

```
git add frontend/src/components/ChatView.vue
git commit -m "feat: Aurora hero page and chat bubbles redesign"
```

---

## Task 10：SelectInterests.vue 毛玻璃标签

**Files:**
- Modify: `frontend/src/components/SelectInterests.vue`

- [ ] **Step 1：替换整个 `<style scoped>`**

```css
<style scoped>
.interests-view {
  display: flex; flex-direction: column;
  height: 100%; padding: 32px 24px 24px;
  position: relative; z-index: 2;
}
.interests-title { font-size: 22px; font-weight: 700; margin-bottom: 6px; }
.interests-sub { font-size: 14px; color: var(--text-secondary); margin-bottom: 24px; }

.tag-grid { display: flex; flex-wrap: wrap; gap: 10px; flex: 1; align-content: flex-start; max-width: 600px; }

.tag-chip {
  padding: 9px 18px; border-radius: 22px;
  border: 1px solid var(--border); background: var(--bg-glass);
  font-size: 14px; color: var(--text-secondary); cursor: pointer; transition: all .2s;
}
.tag-chip:hover { background: rgba(255,255,255,.1); color: var(--text-primary); }
.tag-chip.selected {
  background: linear-gradient(135deg, rgba(108,59,213,.3), rgba(26,111,235,.3));
  border-color: rgba(108,59,213,.6); color: #c4b5fd;
  box-shadow: 0 0 12px rgba(108,59,213,.2);
}

.interests-actions { display: flex; gap: 10px; margin-top: auto; max-width: 600px; }
.btn-skip {
  flex: 1; padding: 13px; border-radius: 12px;
  border: 1px solid var(--border); background: var(--bg-glass);
  color: var(--text-secondary); font-size: 14px; cursor: pointer; transition: all .2s;
}
.btn-skip:hover { background: rgba(255,255,255,.08); }
</style>
```

- [ ] **Step 2：在 `<template>` 中把底部按钮区 class 换成 `interests-actions`**

找到：
```html
<div class="input-bar" style="margin-top: auto;">
```
替换为：
```html
<div class="interests-actions">
```

并把 `btn-send` 的 inline style 去掉，只保留 class：
```html
<button class="btn-send" @click="confirm" :disabled="selected.size === 0">
  确认 ({{ selected.size }}) →
</button>
```

- [ ] **Step 3：在 `<template>` 顶层 `<div>` 内加 aurora（父组件已通过 .view 管理，这里只需保证 z-index:2）**

在 `.interests-view` 内第一行加：
```html
<div class="aurora" style="position:absolute;inset:0;z-index:0">
  <div class="aurora-blob"></div>
  <div class="aurora-blob"></div>
</div>
```

- [ ] **Step 4：浏览器验证选中标签呈现紫色渐变发光效果**

- [ ] **Step 5：commit**

```
git add frontend/src/components/SelectInterests.vue
git commit -m "feat: glass tag chips for SelectInterests"
```

---

## Task 11：ConfirmIntent.vue 毛玻璃卡片

**Files:**
- Modify: `frontend/src/components/ConfirmIntent.vue`

- [ ] **Step 1：替换 `<style scoped>` 全部内容**

```css
<style scoped>
.confirm-view {
  display: flex; align-items: center; justify-content: center;
  padding: 24px 16px; height: 100%; position: relative;
}
.aurora-wrap { position: absolute; inset: 0; z-index: 0; overflow: hidden; }
.aurora-wrap .aurora-blob:nth-child(1) { opacity:.15; }
.aurora-wrap .aurora-blob:nth-child(2) { opacity:.12; }

.confirm-card {
  width: 100%; max-width: 480px;
  background: var(--bg-glass); backdrop-filter: blur(32px);
  border: 1px solid var(--border); border-radius: var(--radius-lg);
  padding: 32px; position: relative; z-index: 2;
  box-shadow: 0 24px 64px rgba(0,0,0,.4);
}
.confirm-badge { font-size: 11px; color: var(--accent-hover); font-weight: 700; letter-spacing: .5px; margin-bottom: 8px; }
.confirm-title { font-size: 20px; font-weight: 700; margin-bottom: 4px; }
.confirm-hint  { font-size: 13px; color: var(--text-secondary); margin-bottom: 20px; }

.info-list { display: flex; flex-direction: column; gap: 8px; margin-bottom: 14px; }
.info-row {
  display: flex; justify-content: space-between; align-items: center;
  background: rgba(255,255,255,.04); border: 1px solid rgba(255,255,255,.07);
  border-radius: 10px; padding: 11px 14px;
}
.info-key { font-size: 13px; color: var(--text-secondary); display: flex; align-items: center; gap: 6px; }
.info-val { font-size: 13px; font-weight: 600; }

.time-prefs { display: flex; flex-direction: column; gap: 6px; margin-bottom: 20px; }
.time-pref-row {
  padding: 9px 14px; background: rgba(108,59,213,.12);
  border: 1px solid rgba(108,59,213,.4); border-radius: 10px;
  font-size: 13px; color: var(--accent-hover);
  display: flex; align-items: center; gap: 8px;
}

.confirm-input-bar { display: flex; gap: 8px; }
.confirm-input-bar input {
  flex: 1; padding: 11px 14px;
  border: 1px solid var(--border); border-radius: 10px;
  font-size: 13px; background: var(--bg-input); color: var(--text-primary); outline: none;
  transition: border-color .2s;
}
.confirm-input-bar input::placeholder { color: var(--text-muted); }
.confirm-input-bar input:focus { border-color: rgba(108,59,213,.7); }
.confirm-input-bar .btn-confirm {
  background: linear-gradient(135deg, var(--accent), var(--accent-end));
  border: none; border-radius: 10px; padding: 11px 18px;
  color: #fff; font-size: 13px; font-weight: 600; cursor: pointer;
  white-space: nowrap; transition: opacity .2s;
}
.confirm-input-bar .btn-confirm:hover { opacity: .85; }
</style>
```

- [ ] **Step 2：更新 `<template>` 中的信息行加上 emoji key**

将各 `.info-row` 的 `info-key` span 内容改为：

```html
<span class="info-key">📍 目的地</span>
<span class="info-key">🛫 出发地</span>
<span class="info-key">🗓 天数</span>
<span class="info-key">📅 出发日期</span>
<span class="info-key">❤ 兴趣</span>
```

并把确认按钮的 class 改为 `btn-confirm`（同时删除 `btn-send` 依赖）：

```html
<button class="btn-confirm" @click="confirm">确认，开始规划 →</button>
```

在 `.confirm-view` 内最顶部加：

```html
<div class="aurora-wrap">
  <div class="aurora-blob"></div>
  <div class="aurora-blob"></div>
</div>
```

- [ ] **Step 3：浏览器验证卡片呈现毛玻璃效果**

- [ ] **Step 4：commit**

```
git add frontend/src/components/ConfirmIntent.vue
git commit -m "feat: glass card redesign for ConfirmIntent"
```

---

## Task 12：ProgressView.vue 全新流式 UI

**Files:**
- Modify: `frontend/src/components/ProgressView.vue`

这是改动最大的组件，需要接收 `streamingFlights` / `streamingPois` / `streamText` props。

- [ ] **Step 1：更新 App.vue 中 ProgressView 的 props 传递**

在 `App.vue` 中找到 `<ProgressView>` 标签，加入新 props：

```html
<ProgressView
  v-else-if="phase === 'progress'"
  :items="progressItems"
  :streaming-flights="streamingFlights"
  :streaming-pois="streamingPois"
  :stream-text="streamText"
  :flights-total-found="flightsTotalFound"
  :pois-total-found="poisTotalFound"
/>
```

在 `<script setup>` 中解构新字段：

```javascript
const {
  phase, messages, progressItems, reviewData, finalResult, error,
  confirmData, interestsData,
  streamingFlights, streamingPois, streamText, flightsTotalFound, poisTotalFound,
  startChat, sendReply,
} = useSSE()
```

- [ ] **Step 2：替换整个 `ProgressView.vue`**

```vue
<template>
  <div class="view progress-view">
    <div class="aurora">
      <div class="aurora-blob"></div>
      <div class="aurora-blob"></div>
      <div class="aurora-blob"></div>
    </div>

    <div class="progress-inner">
      <!-- 状态行 -->
      <div class="status-bar">
        <span class="status-dot"></span>
        <span class="status-text">AI 正在为你规划行程…</span>
      </div>

      <!-- 四步时间线 -->
      <ul class="timeline">
        <li v-for="(step, idx) in allSteps" :key="step.node" class="tl-item" :class="step.state">
          <div class="tl-track">
            <div class="tl-dot">
              <svg v-if="step.state === 'completed'" viewBox="0 0 16 16" fill="currentColor" width="14" height="14">
                <path d="M13.5 3.5L6 11 2.5 7.5l-1 1L6 13l8.5-8.5z"/>
              </svg>
              <div v-else-if="step.state === 'active'" class="spinner"></div>
            </div>
            <div v-if="idx < allSteps.length - 1" class="tl-line" :class="{ done: step.state === 'completed' }"></div>
          </div>
          <div class="tl-body">
            <div class="tl-label">{{ step.label }}</div>
            <div v-if="step.state === 'active' && step.message" class="tl-msg">{{ step.message }}</div>
          </div>
        </li>
      </ul>

      <!-- 流式内容区 -->
      <div class="stream-area">

        <!-- 航班卡 -->
        <transition-group name="slide-in" tag="div" v-if="streamingFlights.length" class="flights-section">
          <div class="flights-header" key="flights-header">
            <span class="stream-label">✈ 航班</span>
            <span class="stream-count">共找到 {{ flightsTotalFound }} 个，为你筛选最优 {{ streamingFlights.length }} 个</span>
          </div>
          <div v-for="f in streamingFlights" :key="f.pair_id" class="flight-card">
            <div class="flight-side">
              <div class="flight-city">{{ f.outbound_dep }}</div>
              <div class="flight-time">{{ f.outbound_time }}</div>
            </div>
            <div class="flight-middle">
              <div class="flight-no">{{ f.flight_no }}</div>
              <div class="flight-arrow">→</div>
              <div class="flight-date">{{ f.outbound_date }}</div>
            </div>
            <div class="flight-side right">
              <div class="flight-city">{{ f.outbound_arr }}</div>
              <div class="flight-time">{{ f.return_time }}</div>
            </div>
            <div class="flight-price">¥{{ f.total_price }}</div>
          </div>
        </transition-group>

        <!-- POI chips -->
        <div v-if="streamingPois.length" class="pois-section">
          <div class="stream-label">
            📍 景点
            <span class="stream-count">共收录 {{ poisTotalFound }} 个，评分最高的</span>
          </div>
          <transition-group name="chip-pop" tag="div" class="poi-chips">
            <span v-for="poi in streamingPois" :key="poi" class="poi-chip-stream">{{ poi }}</span>
          </transition-group>
        </div>

        <!-- 流式文字 -->
        <div v-if="streamText" class="narrative-section">
          <div class="stream-label">💡 行程分析</div>
          <div class="narrative-text">{{ streamText }}<span class="cursor-blink">▌</span></div>
        </div>

      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  items:             { type: Array,  default: () => [] },
  streamingFlights:  { type: Array,  default: () => [] },
  streamingPois:     { type: Array,  default: () => [] },
  streamText:        { type: String, default: '' },
  flightsTotalFound: { type: Number, default: 0 },
  poisTotalFound:    { type: Number, default: 0 },
})

const STEPS = [
  { node: 'parse_input',    label: '解析出行需求' },
  { node: 'discover_pois',  label: '搜索景点 / 查询航班' },
  { node: 'plan_itinerary', label: '规划行程方案' },
  { node: 'compose_output', label: '整理最终行程' },
]
const NODE_TO_SLOT = {
  parse_input: 'parse_input', discover_pois: 'discover_pois',
  scrape_flights: 'discover_pois', plan_itinerary: 'plan_itinerary',
  compose_output: 'compose_output',
}

const allSteps = computed(() => {
  const reached = new Set((props.items || []).map(i => NODE_TO_SLOT[i.node]).filter(Boolean))
  const lastNode = props.items?.length ? NODE_TO_SLOT[props.items[props.items.length - 1].node] : null
  const lastMsg  = props.items?.length ? props.items[props.items.length - 1].message : ''
  return STEPS.map((s, idx) => {
    let state = 'pending'
    if (reached.has(s.node)) state = s.node === lastNode ? 'active' : 'completed'
    return { ...s, state, message: state === 'active' ? lastMsg : '', last: idx === STEPS.length - 1 }
  })
})
</script>

<style scoped>
.progress-view { display: flex; flex-direction: column; height: 100%; }
.progress-inner {
  position: relative; z-index: 2;
  max-width: 680px; width: 100%; margin: 48px auto;
  padding: 0 24px; display: flex; flex-direction: column; gap: 32px;
}

/* 状态行 */
.status-bar { display: flex; align-items: center; gap: 10px; font-size: 13px; color: var(--text-secondary); }
.status-dot {
  width: 8px; height: 8px; border-radius: 50%; background: var(--accent-hover);
  animation: pulse 1.5s ease-in-out infinite;
}
@keyframes pulse { 0%,100%{opacity:1;transform:scale(1)} 50%{opacity:.5;transform:scale(.8)} }

/* 时间线 */
.timeline { list-style: none; display: flex; flex-direction: column; }
.tl-item  { display: flex; gap: 14px; }
.tl-track { display: flex; flex-direction: column; align-items: center; width: 36px; flex-shrink: 0; }
.tl-dot {
  width: 36px; height: 36px; border-radius: 50%; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
}
.completed .tl-dot { background: linear-gradient(135deg, var(--success), #2da44e); color: #fff; }
.active    .tl-dot { background: linear-gradient(135deg, var(--accent), var(--accent-end)); box-shadow: 0 0 20px rgba(108,59,213,.5); }
.pending   .tl-dot { background: rgba(255,255,255,.05); border: 1px solid var(--border); }
.tl-line { flex: 1; width: 2px; background: var(--border); min-height: 20px; margin: 4px 0; transition: background .3s; }
.tl-line.done { background: linear-gradient(to bottom, var(--success), var(--border)); }
.tl-body { padding-top: 8px; padding-bottom: 20px; flex: 1; }
.tl-label { font-size: 14px; font-weight: 600; }
.active .tl-label   { color: var(--accent-hover); }
.pending .tl-label  { color: var(--text-muted); }
.tl-msg   { font-size: 12px; color: var(--text-secondary); margin-top: 3px; }

.spinner {
  width: 18px; height: 18px; border: 2px solid rgba(255,255,255,.3);
  border-top-color: #fff; border-radius: 50%; animation: spin .8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* 流式内容 */
.stream-area { display: flex; flex-direction: column; gap: 20px; }
.stream-label { font-size: 12px; font-weight: 700; color: var(--text-muted); text-transform: uppercase; letter-spacing: 1px; margin-bottom: 10px; }
.stream-count { font-size: 11px; color: var(--text-muted); font-weight: 400; margin-left: 8px; text-transform: none; letter-spacing: 0; }

/* 航班卡 */
.flights-section { display: flex; flex-direction: column; gap: 8px; }
.flight-card {
  background: var(--bg-glass); border: 1px solid var(--border);
  border-radius: 14px; padding: 14px 18px;
  display: flex; align-items: center; gap: 16px;
  transition: border-color .2s;
}
.flight-card:hover { border-color: rgba(108,59,213,.3); }
.flight-side   { min-width: 60px; }
.flight-side.right { text-align: right; }
.flight-city   { font-size: 11px; color: var(--text-muted); }
.flight-time   { font-size: 20px; font-weight: 700; }
.flight-middle { flex: 1; text-align: center; }
.flight-no     { font-size: 11px; color: var(--text-muted); margin-bottom: 2px; }
.flight-arrow  { font-size: 16px; color: var(--text-muted); }
.flight-date   { font-size: 11px; color: var(--text-muted); margin-top: 2px; }
.flight-price  { font-size: 18px; font-weight: 700; color: var(--accent-cyan); margin-left: auto; }

/* POI chips */
.pois-section { }
.poi-chips    { display: flex; flex-wrap: wrap; gap: 8px; }
.poi-chip-stream {
  background: var(--bg-glass); border: 1px solid var(--border);
  border-radius: var(--radius-full); padding: 6px 14px;
  font-size: 13px; color: var(--text-secondary);
}

/* 叙述文字 */
.narrative-section { }
.narrative-text { font-size: 15px; line-height: 1.8; color: var(--text-secondary); }
.cursor-blink   { animation: blink .8s step-end infinite; color: var(--accent-hover); }
@keyframes blink { 50%{opacity:0} }

/* 动画 */
.slide-in-enter-active { transition: opacity .4s, transform .4s; }
.slide-in-enter-from   { opacity: 0; transform: translateX(-12px); }
.chip-pop-enter-active { transition: opacity .3s, transform .3s; }
.chip-pop-enter-from   { opacity: 0; transform: scale(.88); }
</style>
```

- [ ] **Step 3：浏览器触发一次完整规划，观察航班卡滑入、POI chips 冒出、文字流式出现**

- [ ] **Step 4：commit**

```
git add frontend/src/components/ProgressView.vue frontend/src/App.vue
git commit -m "feat: streaming progress view with flights, POIs and narrative text"
```

---

## Task 13：PlanReview.vue 卡片重设计 + 费用标签修复

**Files:**
- Modify: `frontend/src/components/PlanReview.vue`

- [ ] **Step 1：替换 `<template>` 中的 plan-card 内容**

将现有 `.plan-card` 内部替换为：

```html
<div
  v-for="plan in data.plans"
  :key="plan.option_id"
  class="plan-card"
  :class="{ selected: selected === plan.option_id }"
  @click="selected = plan.option_id"
>
  <div class="plan-option-id">方案 {{ plan.option_id }}</div>
  <div class="plan-summary">{{ plan.summary }}</div>

  <!-- 去程航班 -->
  <div class="plan-flight-block">
    <div class="plan-flight-label">✈ 去程</div>
    <div class="plan-flight-row">
      <div>
        <div class="plan-flight-city">出发</div>
        <div class="plan-flight-time">{{ plan.depart_time || '--:--' }}</div>
      </div>
      <div class="plan-flight-arrow">→</div>
      <div style="text-align:right">
        <div class="plan-flight-city">到达</div>
        <div class="plan-flight-time">{{ plan.flight || '' }}</div>
      </div>
    </div>
  </div>

  <!-- 返程 -->
  <div v-if="plan.return_time" class="plan-flight-block" style="margin-bottom:12px">
    <div class="plan-flight-label">✈ 返程 {{ plan.return_time }}</div>
  </div>

  <!-- 每日行程预览 -->
  <div class="plan-days-new">
    <div v-for="day in plan.days.slice(0, 3)" :key="day.day" class="plan-day-row">
      Day {{ day.day }} · <span>{{ day.pois.join(' · ') }}</span>
    </div>
    <div v-if="plan.days.length > 3" class="plan-day-row" style="color:var(--text-muted)">
      …共 {{ plan.days.length }} 天
    </div>
  </div>

  <!-- 费用（机票标签修复）-->
  <div class="plan-price">
    机票 ¥{{ plan.total_price ?? '—' }} <span class="plan-price-label">/ 人</span>
  </div>

  <div v-if="selected === plan.option_id" class="plan-selected-badge">✓ 已选</div>
</div>
```

- [ ] **Step 2：删除 `<style scoped>` 中的旧样式（已全部移至 style.css），保留空标签**

```css
<style scoped>
/* styles moved to style.css */
</style>
```

- [ ] **Step 3：浏览器验证卡片选中时紫色渐变高亮，价格显示为"机票 ¥X / 人"**

- [ ] **Step 4：commit**

```
git add frontend/src/components/PlanReview.vue
git commit -m "feat: Aurora plan cards + fix flight-only price label"
```

---

## Task 14：ResultView.vue 重设计 + 费用标签修复

**Files:**
- Modify: `frontend/src/components/ResultView.vue`

- [ ] **Step 1：替换整个 `<template>`**

```html
<template>
  <div class="view result-view-wrap">
    <div class="aurora">
      <div class="aurora-blob"></div>
      <div class="aurora-blob"></div>
    </div>

    <div class="result-view">
      <div class="result-header">
        <h2 class="result-title">你的行程 🎉</h2>
        <p class="result-sub">{{ result.itineraries?.length }} 套方案 · 点击展开详情</p>
      </div>

      <div v-if="result.warnings?.length" class="warning-box">
        <div v-for="w in result.warnings" :key="w">⚠ {{ w }}</div>
      </div>

      <div v-if="!result.itineraries?.length" style="color:var(--text-secondary);font-size:14px">
        暂无行程方案，请检查警告信息。
      </div>

      <div v-for="itin in result.itineraries" :key="itin.option_id" class="itinerary-card">
        <!-- 卡头 -->
        <div class="itin-top">
          <div>
            <div class="itin-option">方案 {{ itin.option_id }}</div>
            <div class="itin-name">{{ itin.summary }}</div>
          </div>
          <div style="text-align:right">
            <div class="itin-price">¥{{ itin.flights?.total_price ?? '—' }}</div>
            <div class="itin-price-label">机票 / 人<br>住宿·餐饮另计</div>
          </div>
        </div>

        <!-- 航班摘要条 -->
        <div v-if="itin.flights" class="itin-flight-strip">
          <span>✈</span>
          <span>去程：{{ itin.flights.outbound.depart_airport }} {{ itin.flights.outbound.depart_time?.slice(11,16) }} → {{ itin.flights.outbound.arrive_airport }}</span>
          <span style="margin-left:auto">返程：{{ itin.flights.return_flight?.depart_airport }} {{ itin.flights.return_flight?.depart_time?.slice(11,16) }} → {{ itin.flights.return_flight?.arrive_airport }}</span>
        </div>

        <!-- 每日行程 -->
        <div class="itin-days">
          <div v-for="day in itin.days" :key="day.day" class="day-row">
            <div class="day-badge">Day {{ day.day }}</div>
            <div>
              <div class="day-pois">
                <span v-for="poi in day.pois" :key="poi.poi_id" class="poi-chip">{{ poi.name }}</span>
              </div>
              <div v-if="day.transport_note" class="day-note">{{ day.transport_note }}</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
```

- [ ] **Step 2：`<style scoped>` 清空（所有样式已在 style.css）**

```css
<style scoped>
.result-view-wrap { display: flex; flex-direction: column; }
</style>
```

- [ ] **Step 3：浏览器验证最终行程卡价格区显示"机票 / 人 + 住宿·餐饮另计"小字**

- [ ] **Step 4：commit**

```
git add frontend/src/components/ResultView.vue
git commit -m "feat: Aurora result cards + clarify flight-only cost label"
```

---

## 自检清单

- [ ] `pytest tests/test_nodes/test_scrape_flights.py -v` 全绿
- [ ] `pytest tests/test_nodes/ -v` 全绿（其他 node 测试不受影响）
- [ ] 浏览器打开 http://localhost:5174/，Hero 页极光背景正常
- [ ] TopBar 进度条四步带标签，当前步发光
- [ ] 完整规划流程：chat → interests → confirm → progress（流式内容出现）→ review（Aurora 卡片）→ result（费用标签正确）
- [ ] 时段偏好：填入"想要早上出发"，最终 PlanReview 中第一张卡的去程时间应在 12:00 前
- [ ] 费用标签：PlanReview 和 ResultView 均显示"机票 ¥X/人"，ResultView 有"住宿·餐饮另计"小字
