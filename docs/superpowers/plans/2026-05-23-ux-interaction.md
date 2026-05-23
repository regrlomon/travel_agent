# UX 交互改进实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复四个 UX 问题：AI 自我介绍 + 兴趣标签选择 + 确认卡、后台异常前端可见、航班时刻显示 + 时段偏好排序、节点进度推送。

**Architecture:** 后端新增 `select_interests` / `confirm_intent` 两个 HITL interrupt 类型，补全 `progress` / `error` 事件推送；`scrape_flights` 加纯函数时段排序；前端新增 `SelectInterests.vue` 和 `ConfirmIntent.vue` 两个组件，`ProgressView` 改为三态时间线。

**Tech Stack:** Python 3.11、LangGraph、FastAPI、Celery、Redis、Vue 3 (Composition API)、pytest + pytest-asyncio + pytest-mock

---

## 文件变更清单

| 操作 | 路径 | 职责 |
|---|---|---|
| 修改 | `agent/state.py` | 新增 `depart_time_pref`、`return_time_pref` 字段 |
| 修改 | `agent/nodes/collect_intent.py` | 自我介绍、generate_tags、select_interests、时段偏好、confirm_intent |
| 修改 | `agent/nodes/scrape_flights.py` | 新增 `_parse_time_pref`、`_rank_by_time_pref` |
| 修改 | `agent/nodes/human_review.py` | 新增 `depart_time`、`return_time` 字段，改 message |
| 修改 | `worker/tasks.py` | `PROGRESS_MESSAGES`、`make_node_wrapper`、error emit |
| 修改 | `frontend/src/composables/useSSE.js` | 处理 `select_interests`、`confirm_intent`、`error` |
| 修改 | `frontend/src/App.vue` | 新增 `interests`、`confirm` phase |
| 新增 | `frontend/src/components/SelectInterests.vue` | 多选标签组件 |
| 新增 | `frontend/src/components/ConfirmIntent.vue` | 确认卡组件 |
| 修改 | `frontend/src/components/ProgressView.vue` | 三态时间线 |
| 修改 | `frontend/src/components/PlanReview.vue` | 显示 HH:MM 时刻 |
| 修改 | `tests/test_nodes/test_collect_intent.py` | 新增 greeting / generate_tags / select_interests / time_pref / confirm 测试 |
| 修改 | `tests/test_nodes/test_scrape_flights.py` | 新增 `_parse_time_pref` / `_rank_by_time_pref` 测试 |
| 修改 | `tests/test_nodes/test_human_review.py` | 新增 `depart_time` / `return_time` 字段测试 |
| 修改 | `tests/test_worker.py` | 新增 progress emit / error emit 测试 |

---

## Task 1: 扩展 State 模型

**Files:**
- Modify: `agent/state.py`

- [ ] **Step 1: 新增两个可选字段**

在 `TravelPlanState` 的 `# ── Written by collect_intent` 区块末尾添加：

```python
depart_time_pref: Optional[str]   # 去程时段偏好，自然语言，如 "9点左右"
return_time_pref: Optional[str]   # 返程时段偏好，自然语言，如 "下午出发"
```

- [ ] **Step 2: 验证 import 无误**

```bash
python -c "from agent.state import TravelPlanState; print('ok')"
```

Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add agent/state.py
git commit -m "feat: add depart_time_pref and return_time_pref to state"
```

---

## Task 2: scrape_flights 时段排序

**Files:**
- Modify: `agent/nodes/scrape_flights.py`
- Modify: `tests/test_nodes/test_scrape_flights.py`

- [ ] **Step 1: 写失败测试**

在 `tests/test_nodes/test_scrape_flights.py` 末尾追加：

```python
from agent.nodes.scrape_flights import _parse_time_pref, _rank_by_time_pref
from models import Flight
from datetime import datetime


def _flight(hour: int, minute: int = 0) -> Flight:
    return Flight(
        platform="test", depart_airport="PVG", arrive_airport="CTU",
        price=800, flight_no="MU1",
        depart_time=datetime(2026, 7, 1, hour, minute),
    )


def test_parse_time_pref_morning():
    after, before = _parse_time_pref("上午")
    assert after == 6 * 60
    assert before == 12 * 60


def test_parse_time_pref_afternoon():
    after, before = _parse_time_pref("下午")
    assert after == 12 * 60
    assert before == 18 * 60


def test_parse_time_pref_around_nine():
    after, before = _parse_time_pref("9点左右")
    assert after == 8 * 60
    assert before == 10 * 60


def test_parse_time_pref_not_late():
    result = _parse_time_pref("不要太晚")
    assert result is not None
    after_min, before_min = result
    assert after_min == 0        # no lower bound (fly anytime from midnight)
    assert before_min == 20 * 60  # cap at 20:00


def test_parse_time_pref_no_preference():
    assert _parse_time_pref(None) is None
    assert _parse_time_pref("随意") is None
    assert _parse_time_pref("不限") is None


def test_rank_by_time_pref_sorts_closest_first():
    flights = [_flight(14), _flight(9, 15), _flight(6)]
    ranked = _rank_by_time_pref(flights, "9点左右")
    assert ranked[0].depart_time.hour == 9


def test_rank_by_time_pref_no_pref_unchanged():
    flights = [_flight(14), _flight(9), _flight(6)]
    ranked = _rank_by_time_pref(flights, None)
    assert [f.depart_time.hour for f in ranked] == [14, 9, 6]


def test_rank_by_time_pref_no_hard_filter():
    """Even if no flight is in window, all are returned."""
    flights = [_flight(22), _flight(23)]
    ranked = _rank_by_time_pref(flights, "上午")
    assert len(ranked) == 2
```

- [ ] **Step 2: 运行，确认失败**

```bash
pytest tests/test_nodes/test_scrape_flights.py -k "parse_time_pref or rank_by_time_pref" -v
```

Expected: ImportError 或 FAILED

- [ ] **Step 3: 实现 `_parse_time_pref` 和 `_rank_by_time_pref`**

在 `agent/nodes/scrape_flights.py` 顶部 import 区块后，`_raw_to_flight` 函数前添加：

```python
import re


def _parse_time_pref(pref: str | None) -> tuple[int, int] | None:
    """Map a natural-language time preference to a (after_min, before_min) window.

    Returns None if no preference or unrecognised.
    Minutes are measured from midnight (e.g. 9:00 = 540).
    """
    if not pref:
        return None
    p = pref.strip()

    # Skip keywords
    if any(kw in p for kw in ("随意", "不限", "无所谓", "都行", "不要求")):
        return None

    # Around N o'clock: "9点左右" / "9点"
    m = re.search(r"(\d{1,2})[点:：]", p)
    if m:
        h = int(m.group(1))
        return (h - 1) * 60, (h + 1) * 60

    # Named periods
    if any(kw in p for kw in ("早上", "上午", "早班")):
        return 6 * 60, 12 * 60
    if any(kw in p for kw in ("中午",)):
        return 11 * 60, 13 * 60
    if any(kw in p for kw in ("下午",)):
        return 12 * 60, 18 * 60
    if any(kw in p for kw in ("傍晚", "晚上", "夜班")):
        return 17 * 60, 22 * 60

    # Relative constraints
    if any(kw in p for kw in ("不要太早", "别太早", "不太早")):
        return 8 * 60, 23 * 60
    if any(kw in p for kw in ("不要太晚", "别太晚", "不太晚")):
        return 0, 20 * 60

    return None


def _rank_by_time_pref(flights: list, pref: str | None) -> list:
    """Return flights sorted by proximity to time preference window midpoint.

    No flights are removed — only re-ordered.
    """
    window = _parse_time_pref(pref)
    if window is None:
        return flights
    after_min, before_min = window
    midpoint = (after_min + before_min) / 2

    def _distance(flight) -> float:
        t = flight.depart_time
        flight_min = t.hour * 60 + t.minute
        return abs(flight_min - midpoint)

    return sorted(flights, key=_distance)
```

- [ ] **Step 4: 在 `run()` 中读取时段偏好并调用排序**

找到 `run()` 中 `outbound_flights = await _scrape_details(...)` 和 `return_flights = await _scrape_details(...)` 后，各加一行：

```python
outbound_flights = await _scrape_details(origin_city, dest_city, best_date, flight_client)
outbound_flights = _rank_by_time_pref(outbound_flights, state.get("depart_time_pref"))

return_flights = await _scrape_details(dest_city, origin_city, return_date, flight_client)
return_flights = _rank_by_time_pref(return_flights, state.get("return_time_pref"))
```

- [ ] **Step 5: 运行测试，确认通过**

```bash
pytest tests/test_nodes/test_scrape_flights.py -v
```

Expected: all PASSED

- [ ] **Step 6: Commit**

```bash
git add agent/nodes/scrape_flights.py tests/test_nodes/test_scrape_flights.py
git commit -m "feat: add time-preference ranking for outbound and return flights"
```

---

## Task 3: human_review 展示完整航班时刻

**Files:**
- Modify: `agent/nodes/human_review.py`
- Modify: `tests/test_nodes/test_human_review.py`

- [ ] **Step 1: 写失败测试**

在 `test_human_review.py` 的 `test_format_plans_for_display_returns_list` 下方添加：

```python
def test_format_plans_includes_depart_and_return_time():
    from agent.nodes.human_review import _format_plans_for_display
    itinerary = _make_itinerary()
    result = _format_plans_for_display([itinerary])
    plan = result[0]
    # depart_time and return_time must be HH:MM strings
    assert "depart_time" in plan
    assert "return_time" in plan
    assert plan["depart_time"] == "00:00"   # datetime(2026, 7, 1) → 00:00
    assert plan["return_time"] == "00:00"   # datetime(2026, 7, 8) → 00:00


def test_format_plans_depart_date_includes_time():
    from agent.nodes.human_review import _format_plans_for_display
    itinerary = _make_itinerary()
    result = _format_plans_for_display([itinerary])
    # depart_date should now include HH:MM
    assert ":" in result[0]["depart_date"]  # "2026-07-01 00:00"
```

- [ ] **Step 2: 运行，确认失败**

```bash
pytest tests/test_nodes/test_human_review.py -k "depart_time or return_time or depart_date_includes" -v
```

Expected: FAILED (KeyError / AssertionError)

- [ ] **Step 3: 更新 `_format_plans_for_display`**

在 `human_review.py` 的 `_format_plans_for_display` 函数中，将 `plans.append({...})` 替换为：

```python
depart_time_str = fp.outbound.depart_time.strftime("%H:%M") if fp else ""
return_time_str = fp.return_flight.depart_time.strftime("%H:%M") if fp else ""
depart_date_str = fp.outbound.depart_time.strftime("%Y-%m-%d %H:%M") if fp else ""

flight_info = (
    f"{fp.outbound.depart_airport}→{fp.outbound.arrive_airport} "
    f"{depart_time_str} ¥{fp.total_price}/人"
    if fp else "待定（请自行查询）"
)

plans.append({
    "option_id":   itin.option_id,
    "summary":     itin.summary,
    "flight":      flight_info,
    "depart_date": depart_date_str,
    "depart_time": depart_time_str,
    "return_time": return_time_str,
    "days":        days_summary,
})
```

- [ ] **Step 4: 更新 `run()` 中的 interrupt message**

```python
user_reply = interrupt({
    "type":    "review_plan",
    "message": f"帮你规划了 {len(plans)} 套方案，每套搭配了不同航班供参考，可以告诉我想调整出发时间或行程安排。",
    "plans":   plans,
})
```

- [ ] **Step 5: 运行所有 human_review 测试**

```bash
pytest tests/test_nodes/test_human_review.py -v
```

Expected: all PASSED

- [ ] **Step 6: Commit**

```bash
git add agent/nodes/human_review.py tests/test_nodes/test_human_review.py
git commit -m "feat: add depart_time/return_time HH:MM to plan cards"
```

---

## Task 4: worker/tasks.py — progress 事件 + error 事件

**Files:**
- Modify: `worker/tasks.py`
- Modify: `tests/test_worker.py`

- [ ] **Step 1: 写失败测试**

在 `test_worker.py` 末尾追加：

```python
def test_make_node_wrapper_emits_progress(mocker):
    mock_r = MagicMock()
    mocker.patch("worker.tasks.r", mock_r)
    from worker.tasks import make_node_wrapper

    called = []

    async def fake_node(state, config):
        called.append(True)
        return {}

    # Simulate the module path that node_wrapper uses
    fake_node.__module__ = "agent.nodes.discover_pois"

    wrapped = make_node_wrapper("job-test")(fake_node)

    import asyncio
    asyncio.run(wrapped({}, {}))

    assert called == [True]
    mock_r.xadd.assert_called_once()
    data = json.loads(mock_r.xadd.call_args[0][1]["data"])
    assert data["type"] == "progress"
    assert data["node"] == "discover_pois"
    assert "景点" in data["message"]


def test_run_plan_emits_error_on_exception(mocker):
    mock_r = MagicMock()
    mocker.patch("worker.tasks.r", mock_r)

    async def _boom():
        raise RuntimeError("test failure")

    mocker.patch("worker.tasks.asyncio.run", side_effect=RuntimeError("test failure"))

    from worker.tasks import run_plan
    with pytest.raises(RuntimeError):
        run_plan("job-err", {})

    calls = [json.loads(c[0][1]["data"]) for c in mock_r.xadd.call_args_list]
    error_calls = [c for c in calls if c.get("type") == "error"]
    assert len(error_calls) == 1
    assert "RuntimeError" in error_calls[0]["message"]
```

- [ ] **Step 2: 运行，确认失败**

```bash
pytest tests/test_worker.py -k "node_wrapper or emits_error" -v
```

Expected: ImportError 或 FAILED

- [ ] **Step 3: 实现 `PROGRESS_MESSAGES` 和 `make_node_wrapper`**

在 `worker/tasks.py` 中，`STREAM_KEY` 定义下方添加：

```python
import functools

PROGRESS_MESSAGES = {
    "parse_input":    "正在解析出行需求...",
    "discover_pois":  "正在搜索目的地景点...",
    "scrape_flights": "正在查询航班价格...",
    "plan_itinerary": "正在规划行程方案（约 1-2 分钟）...",
    "compose_output": "正在整理最终行程...",
}


def make_node_wrapper(job_id: str):
    def wrapper(fn):
        node_name = fn.__module__.split(".")[-1]
        msg = PROGRESS_MESSAGES.get(node_name)

        @functools.wraps(fn)
        async def wrapped(state, config):
            # Only emit for compute nodes (not in PROGRESS_MESSAGES → msg is None).
            # HITL nodes (collect_intent, human_review) are intentionally absent.
            # LangGraph checkpointing ensures completed compute nodes never re-run
            # on resume, so no double-fire risk for this graph topology.
            if msg:
                _emit(job_id, {"type": "progress", "node": node_name, "message": msg})
            return await fn(state, config)

        return wrapped
    return wrapper
```

- [ ] **Step 4: 在 `run_plan` 和 `resume_plan` 中传入 `node_wrapper` 并补 error emit**

`run_plan` 改为：

```python
@celery_app.task(bind=True, max_retries=0)
def run_plan(self, job_id: str, initial_state: dict):
    async def _run():
        async with AsyncRedisSaver.from_conn_string(REDIS_URL) as checkpointer:
            await checkpointer.asetup()
            graph = build_compiled_graph(checkpointer, node_wrapper=make_node_wrapper(job_id))
            return await graph.ainvoke(initial_state, config=_build_config(job_id))

    try:
        _handle_result(job_id, asyncio.run(_run()))
    except Exception as exc:
        logger.exception("[job=%s] run_plan failed", job_id)
        _emit(job_id, {"type": "error", "message": f"规划失败，请稍后重试（{type(exc).__name__}）"})
        raise
```

`resume_plan` 同样修改 `build_compiled_graph` 和 except 块：

```python
@celery_app.task(bind=True, max_retries=1)
def resume_plan(self, job_id: str, user_text: str, interrupt_id: str):
    lock_key = f"job:{job_id}:resume:{interrupt_id}"
    if not r.set(lock_key, "1", nx=True, ex=300):
        return

    async def _run():
        async with AsyncRedisSaver.from_conn_string(REDIS_URL) as checkpointer:
            await checkpointer.asetup()
            graph = build_compiled_graph(checkpointer, node_wrapper=make_node_wrapper(job_id))
            return await graph.ainvoke(
                Command(resume={"text": user_text}), config=_build_config(job_id)
            )

    try:
        _handle_result(job_id, asyncio.run(_run()))
    except Exception as exc:
        logger.exception("[job=%s] resume_plan failed", job_id)
        _emit(job_id, {"type": "error", "message": f"规划失败，请稍后重试（{type(exc).__name__}）"})
        raise
```

- [ ] **Step 5: 运行测试**

```bash
pytest tests/test_worker.py -v
```

Expected: all PASSED

- [ ] **Step 6: Commit**

```bash
git add worker/tasks.py tests/test_worker.py
git commit -m "feat: emit progress events per node and error events on exception"
```

---

## Task 5: collect_intent — 自我介绍 + 首次问候

**Files:**
- Modify: `agent/nodes/collect_intent.py`
- Modify: `tests/test_nodes/test_collect_intent.py`

- [ ] **Step 1: 写失败测试**

在 `test_collect_intent.py` 末尾追加：

```python
@pytest.mark.asyncio
async def test_llm_build_reply_includes_intro_when_empty(mocker):
    """_llm_build_reply prompt must request self-introduction when collected={}."""
    mock_msg = MagicMock()
    mock_msg.content = "我是小Z助手，你想去哪儿？"
    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value=mock_msg)
    mocker.patch("agent.nodes.collect_intent.get_llm", return_value=mock_llm)

    reply = await _llm_build_reply({})
    prompt_sent = mock_llm.ainvoke.call_args[0][0][0].content
    assert "自我介绍" in prompt_sent or "小Z" in prompt_sent


@pytest.mark.asyncio
async def test_empty_raw_message_triggers_hardcoded_greeting(mocker):
    """When raw_message is empty, first interrupt must contain hardcoded greeting with '小Z助手'."""
    greeting_reply = {"text": "川西7天，苏州出发"}
    confirm_reply  = {"text": "确认"}

    mock_interrupt = mocker.patch(
        "agent.nodes.collect_intent.interrupt",
        side_effect=[
            greeting_reply,   # greeting → user sends full intent
            {"text": "自然风光、徒步"},  # select_interests
            {"text": ""},             # depart_date skip
            {"text": ""},             # time_pref skip
            confirm_reply,            # confirm
        ],
    )
    mocker.patch("agent.nodes.collect_intent._llm_extract",
                 new_callable=AsyncMock,
                 return_value={"destination": "川西", "origin": "苏州",
                               "duration_days": 7, "interests": []})
    mocker.patch("agent.nodes.collect_intent._llm_generate_tags",
                 new_callable=AsyncMock, return_value=["自然风光", "徒步"])
    mocker.patch("agent.nodes.collect_intent._llm_extract_time_prefs",
                 new_callable=AsyncMock, return_value=(None, None))
    mocker.patch("agent.nodes.collect_intent._parse_confirm_reply",
                 new_callable=AsyncMock, return_value={"action": "confirm", "updates": {}})

    mock_tools = MagicMock()
    mock_tools.__getitem__ = MagicMock(return_value=MagicMock(
        lookup=AsyncMock(return_value=["PVG"])
    ))
    config = {"configurable": {"tools": mock_tools}}

    from agent.nodes.collect_intent import run
    await run({"raw_message": "", "errors": [], "warnings": []}, config)

    first_call = mock_interrupt.call_args_list[0][0][0]
    assert first_call["type"] == "collect_intent"
    # Greeting must be hardcoded (deterministic), not LLM-generated
    assert "小Z助手" in first_call["message"]
    assert "搜景点" in first_call["message"] or "帮你" in first_call["message"]
```

- [ ] **Step 2: 运行，确认失败**

```bash
pytest tests/test_nodes/test_collect_intent.py -k "intro or greeting" -v
```

Expected: FAILED / ImportError

- [ ] **Step 3: 修改 `run()` — 空 raw_message 时发 hardcoded 欢迎语**

在 `collect_intent.py` 的 `run()` 函数开头，`raw = state.get("raw_message", "")` 之后插入：

```python
raw = state.get("raw_message", "")

# When the user opens the app without typing, send a hardcoded greeting.
# This must NOT go through the LLM — determinism matters here.
if not raw:
    greeting_reply = interrupt({
        "type":    "collect_intent",
        "message": "我是小Z助手，可以帮你搜景点、查机票、排行程。你想去哪儿玩？从哪儿出发，打算玩几天？",
    })
    raw = greeting_reply.get("text", "")
```

同时更新 `_llm_build_reply` prompt，非首次追问时不再加自我介绍（已有首次 hardcode，`_llm_build_reply` 仅用于 collected 不完整时的追问）：

```python
async def _llm_build_reply(collected: dict) -> str:
    missing = []
    if not collected.get("destination"):
        missing.append("目的地")
    if not collected.get("origin"):
        missing.append("出发城市")
    if not collected.get("duration_days"):
        missing.append("出行天数")

    prompt = f"""你是小Z助手，正在帮用户规划旅行，需要追问缺少的信息。

已知信息：{json.dumps(collected, ensure_ascii=False)}
还需要问：{missing}

写一句中文问句，风格要求：
- 像朋友发微信，直接问，不废话
- 禁止：太棒了、不错哦、好的呢、超级、魅力、波浪号（～）、感叹号堆叠
- 禁止句首加任何感叹词或捧场词
- 如果已知目的地，直接用它；如果目的地模糊，顺带提1-2个具体地方供参考
- 可以在一句话里问多个缺失项
- 不超过30字

只输出那一句话，不加任何解释。"""
    llm = get_llm(temperature=0.7)
    msg = await llm.ainvoke([HumanMessage(content=prompt)])
    return msg.content.strip()
```

- [ ] **Step 4: 运行测试**

```bash
pytest tests/test_nodes/test_collect_intent.py -k "intro or greeting" -v
```

Expected: PASSED

- [ ] **Step 5: Commit**

```bash
git add agent/nodes/collect_intent.py tests/test_nodes/test_collect_intent.py
git commit -m "feat: add small-z self-introduction on first collect_intent message"
```

---

## Task 6: collect_intent — 动态兴趣标签 + select_interests

**Files:**
- Modify: `agent/nodes/collect_intent.py`
- Modify: `tests/test_nodes/test_collect_intent.py`

- [ ] **Step 1: 写失败测试**

在 `test_collect_intent.py` 末尾追加：

```python
@pytest.mark.asyncio
async def test_llm_generate_tags_returns_list(mocker):
    mock_msg = MagicMock()
    mock_msg.content = '["自然风光", "徒步", "寺庙朝圣", "高原摄影"]'
    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value=mock_msg)
    mocker.patch("agent.nodes.collect_intent.get_llm", return_value=mock_llm)

    from agent.nodes.collect_intent import _llm_generate_tags
    tags = await _llm_generate_tags("川西")
    assert isinstance(tags, list)
    assert len(tags) >= 4
    assert all(isinstance(t, str) for t in tags)


@pytest.mark.asyncio
async def test_llm_generate_tags_falls_back_on_bad_json(mocker):
    mock_msg = MagicMock()
    mock_msg.content = "sorry I can't"
    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value=mock_msg)
    mocker.patch("agent.nodes.collect_intent.get_llm", return_value=mock_llm)

    from agent.nodes.collect_intent import _llm_generate_tags
    tags = await _llm_generate_tags("川西")
    assert isinstance(tags, list)  # empty list fallback, not exception
```

- [ ] **Step 2: 运行，确认失败**

```bash
pytest tests/test_nodes/test_collect_intent.py -k "generate_tags" -v
```

Expected: ImportError

- [ ] **Step 3: 实现 `_llm_generate_tags`**

在 `collect_intent.py` 中，`_llm_build_reply` 函数后添加：

```python
async def _llm_generate_tags(destination: str) -> list[str]:
    prompt = f"""为旅行目的地「{destination}」生成 6-10 个旅行兴趣标签。

要求：
- 贴合该目的地的特色（地理、文化、活动）
- 每个标签 2-6 个汉字
- 返回 JSON 数组，不加任何解释

例如：["自然风光", "徒步", "摄影", "藏族文化", "温泉", "星空观测"]

只返回 JSON 数组。"""
    llm = get_llm(temperature=0.5)
    msg = await llm.ainvoke([HumanMessage(content=prompt)])
    try:
        tags = json.loads(extract_json(msg.content))
        if isinstance(tags, list):
            return [str(t) for t in tags if t]
    except (json.JSONDecodeError, ValueError):
        logger.warning("[collect_intent] _llm_generate_tags parse failed: %r", msg.content)
    return []
```

- [ ] **Step 4: 在 `run()` 中插入 `select_interests` interrupt**

在 `run()` 函数内，`while not _is_complete(collected):` 循环结束后、出发日期问题前，插入：

```python
# 动态生成兴趣标签，展示给用户多选
candidate_tags = await _llm_generate_tags(collected["destination"])
preselected = collected.get("interests", [])
user_reply = interrupt({
    "type":        "select_interests",
    "message":     "你对哪些感兴趣？选几个帮你优先安排（也可以跳过）",
    "tags":        candidate_tags,
    "preselected": preselected,
})
raw_selection = user_reply.get("text", "").strip()
if raw_selection:
    # Frontend sends "自然风光、徒步、寺庙朝圣" — split directly, no LLM needed
    selected = [t.strip() for t in raw_selection.replace(",", "、").split("、") if t.strip()]
    if selected:
        collected["interests"] = selected
```

- [ ] **Step 5: 运行所有 collect_intent 测试**

```bash
pytest tests/test_nodes/test_collect_intent.py -v
```

Expected: all PASSED

- [ ] **Step 6: Commit**

```bash
git add agent/nodes/collect_intent.py tests/test_nodes/test_collect_intent.py
git commit -m "feat: add dynamic interest tag generation and select_interests interrupt"
```

---

## Task 7: collect_intent — 时段偏好 + confirm_intent

**Files:**
- Modify: `agent/nodes/collect_intent.py`
- Modify: `tests/test_nodes/test_collect_intent.py`

- [ ] **Step 1: 写失败测试**

在 `test_collect_intent.py` 末尾追加：

```python
@pytest.mark.asyncio
async def test_llm_extract_time_prefs_parses_both(mocker):
    mock_msg = MagicMock()
    mock_msg.content = '{"depart_time_pref": "9点左右", "return_time_pref": "下午出发"}'
    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value=mock_msg)
    mocker.patch("agent.nodes.collect_intent.get_llm", return_value=mock_llm)

    from agent.nodes.collect_intent import _llm_extract_time_prefs
    dep, ret = await _llm_extract_time_prefs("去程9点，返程下午")
    assert dep == "9点左右"
    assert ret == "下午出发"


@pytest.mark.asyncio
async def test_llm_extract_time_prefs_returns_none_on_skip(mocker):
    mock_msg = MagicMock()
    mock_msg.content = '{"depart_time_pref": null, "return_time_pref": null}'
    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value=mock_msg)
    mocker.patch("agent.nodes.collect_intent.get_llm", return_value=mock_llm)

    from agent.nodes.collect_intent import _llm_extract_time_prefs
    dep, ret = await _llm_extract_time_prefs("随便")
    assert dep is None
    assert ret is None


@pytest.mark.asyncio
async def test_parse_confirm_reply_confirm(mocker):
    mock_msg = MagicMock()
    mock_msg.content = '{"action": "confirm", "updates": {}}'
    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value=mock_msg)
    mocker.patch("agent.nodes.collect_intent.get_llm", return_value=mock_llm)

    from agent.nodes.collect_intent import _parse_confirm_reply
    result = await _parse_confirm_reply("好的没问题", {})
    assert result["action"] == "confirm"


@pytest.mark.asyncio
async def test_parse_confirm_reply_modify(mocker):
    mock_msg = MagicMock()
    mock_msg.content = '{"action": "modify", "updates": {"duration_days": 5}}'
    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value=mock_msg)
    mocker.patch("agent.nodes.collect_intent.get_llm", return_value=mock_llm)

    from agent.nodes.collect_intent import _parse_confirm_reply
    result = await _parse_confirm_reply("改成5天吧", {"duration_days": 7})
    assert result["action"] == "modify"
    assert result["updates"]["duration_days"] == 5
```

- [ ] **Step 2: 运行，确认失败**

```bash
pytest tests/test_nodes/test_collect_intent.py -k "time_prefs or parse_confirm" -v
```

Expected: ImportError

- [ ] **Step 3: 实现 `_llm_extract_time_prefs` 和 `_parse_confirm_reply`**

在 `collect_intent.py` 的 `_llm_generate_tags` 后追加：

```python
async def _llm_extract_time_prefs(user_text: str) -> tuple[str | None, str | None]:
    prompt = f"""从用户的消息里提取去程和返程的出发时段偏好。

用户消息："{user_text}"

返回 JSON：
{{"depart_time_pref": "原文时段描述或 null", "return_time_pref": "原文时段描述或 null"}}

示例输入："去程9点，返程下午随意"
示例输出：{{"depart_time_pref": "9点左右", "return_time_pref": "下午"}}

如果没有明确说偏好就返回 null。只返回 JSON，不加解释。"""
    llm = get_llm(temperature=0.1)
    msg = await llm.ainvoke([HumanMessage(content=prompt)])
    try:
        data = json.loads(extract_json(msg.content))
        return data.get("depart_time_pref") or None, data.get("return_time_pref") or None
    except (json.JSONDecodeError, ValueError):
        return None, None


async def _parse_confirm_reply(user_text: str, current: dict) -> dict:
    prompt = f"""用户正在确认出行信息。分析用户的回复意图。

当前信息：{json.dumps(current, ensure_ascii=False)}
用户回复："{user_text}"

返回 JSON：
{{"action": "confirm" 或 "modify", "updates": {{字段: 新值}} 或 {{}}}}

- 如果用户表示"好的/确认/没问题/可以"之类，action = "confirm"，updates = {{}}
- 如果用户提到修改任何字段，action = "modify"，updates 里放要改的字段

只返回 JSON。"""
    llm = get_llm(temperature=0.1)
    msg = await llm.ainvoke([HumanMessage(content=prompt)])
    try:
        return json.loads(extract_json(msg.content))
    except (json.JSONDecodeError, ValueError):
        return {"action": "confirm", "updates": {}}
```

- [ ] **Step 4: 在 `run()` 中追加时段偏好问题和 confirm_intent 循环**

> ⚠️ Task 6 已在 `select_interests` 块之后、`# 选填：出发日期` 注释之前插入了标签选择代码。本步骤**仅替换从 `# 选填：出发日期` 注释到函数末尾的部分**，不碰 Task 6 的代码块。

将 `run()` 函数中从 `# 选填：出发日期` 注释到函数结尾的部分替换为：

```python
    # 选填：出发日期，问一次，用户可跳过
    if not collected.get("depart_date"):
        user_reply = interrupt({
            "type": "collect_intent",
            "message": "出发时间定了吗？没定的话我帮你查最近7天哪天最便宜。",
        })
        collected = await _llm_extract(user_reply.get("text", ""), collected)

    # 选填：去程 + 返程时段偏好
    time_reply = interrupt({
        "type": "collect_intent",
        "message": "去程大概想几点出发？返程呢，比如有些人会想最后一天玩到下午再飞。",
    })
    depart_pref, return_pref = await _llm_extract_time_prefs(time_reply.get("text", ""))

    # confirm_intent 循环：直到用户确认
    while True:
        summary = {
            "destination":  collected["destination"],
            "origin":       collected["origin"],
            "duration_days": int(collected["duration_days"]),
            "interests":    collected.get("interests", []),
        }
        if collected.get("depart_date"):
            summary["depart_date"] = collected["depart_date"]
        if depart_pref:
            summary["depart_time_pref"] = depart_pref
        if return_pref:
            summary["return_time_pref"] = return_pref

        confirm_reply = interrupt({
            "type":    "confirm_intent",
            "summary": summary,
        })
        parsed = await _parse_confirm_reply(confirm_reply.get("text", ""), summary)
        if parsed.get("action") == "confirm":
            break
        # merge updates and re-loop
        for k, v in parsed.get("updates", {}).items():
            if v is not None:
                collected[k] = v
        # re-extract time prefs if user mentioned them in update
        if any(kw in confirm_reply.get("text", "") for kw in ("点", "上午", "下午", "晚上", "早")):
            depart_pref, return_pref = await _llm_extract_time_prefs(confirm_reply.get("text", ""))

    origin_airports = await tools["airports"].lookup(collected["origin"])

    return {
        "destination":      collected["destination"],
        "origin":           collected["origin"],
        "duration_days":    int(collected["duration_days"]),
        "interests":        collected.get("interests", []),
        "depart_date":      collected.get("depart_date"),
        "depart_time_pref": depart_pref,
        "return_time_pref": return_pref,
        "origin_airports":  origin_airports,
    }
```

- [ ] **Step 5: 补充多 interrupt 集成测试**

在 `test_collect_intent.py` 末尾追加，验证完整 `run()` 流程按正确顺序触发所有 interrupt：

```python
@pytest.mark.asyncio
async def test_run_full_flow_interrupt_sequence(mocker):
    """Integration: run() fires interrupts in correct order for full flow."""
    mocker.patch("agent.nodes.collect_intent._llm_extract",
                 new_callable=AsyncMock,
                 return_value={"destination": "川西", "origin": "苏州",
                               "duration_days": 7, "interests": []})
    mocker.patch("agent.nodes.collect_intent._llm_generate_tags",
                 new_callable=AsyncMock, return_value=["自然风光", "徒步"])
    mocker.patch("agent.nodes.collect_intent._llm_extract_time_prefs",
                 new_callable=AsyncMock, return_value=("上午", None))
    mocker.patch("agent.nodes.collect_intent._parse_confirm_reply",
                 new_callable=AsyncMock, return_value={"action": "confirm", "updates": {}})

    interrupt_replies = [
        {"text": ""},                       # depart_date skip
        {"text": "自然风光、徒步"},           # select_interests
        {"text": "上午出发随意"},             # time_pref
        {"text": "确认"},                    # confirm
    ]
    mock_interrupt = mocker.patch(
        "agent.nodes.collect_intent.interrupt",
        side_effect=interrupt_replies,
    )
    mock_tools = MagicMock()
    mock_tools.__getitem__ = MagicMock(return_value=MagicMock(
        lookup=AsyncMock(return_value=["PVG"])
    ))
    config = {"configurable": {"tools": mock_tools}}

    from agent.nodes.collect_intent import run
    result = await run(
        {"raw_message": "想去川西，苏州出发，7天", "errors": [], "warnings": []},
        config,
    )

    interrupt_types = [c[0][0]["type"] for c in mock_interrupt.call_args_list]
    assert interrupt_types == [
        "select_interests",
        "collect_intent",   # depart_date
        "collect_intent",   # time_pref
        "confirm_intent",
    ]
    assert result["destination"] == "川西"
    assert result["depart_time_pref"] == "上午"
    assert result["return_time_pref"] is None
```

- [ ] **Step 6: 运行所有 collect_intent 测试**

```bash
pytest tests/test_nodes/test_collect_intent.py -v
```

Expected: all PASSED

- [ ] **Step 7: Commit**

```bash
git add agent/nodes/collect_intent.py tests/test_nodes/test_collect_intent.py
git commit -m "feat: add time pref question and confirm_intent loop in collect_intent"
```

---

## Task 8: useSSE.js + App.vue — 新 phase 接入

**Files:**
- Modify: `frontend/src/composables/useSSE.js`
- Modify: `frontend/src/App.vue`

- [ ] **Step 1: 更新 `useSSE.js`**

将 `hitl_request` 处理块替换为：

```js
if (msg.type === 'hitl_request') {
  interruptId = msg.interrupt_id
  const d = msg.data
  if (d.type === 'collect_intent') {
    phase.value = 'chat'
    messages.value.push({ role: 'ai', text: d.message })
  } else if (d.type === 'select_interests') {
    phase.value = 'interests'
    interestsData.value = d
  } else if (d.type === 'confirm_intent') {
    phase.value = 'confirm'
    confirmData.value = d.summary
  } else if (d.type === 'review_plan') {
    phase.value = 'review'
    reviewData.value = d
  }
} else if (msg.type === 'progress') {
  phase.value = 'progress'
  progressItems.value.push(msg)
} else if (msg.type === 'done') {
  finalResult.value = msg.result
  phase.value = 'done'
  eventSource.close()
} else if (msg.type === 'error') {
  error.value = msg.message
  phase.value = 'error'
  eventSource.close()
}
```

在 `useSSE` 函数顶部新增两个 ref，并在 return 里导出：

```js
const confirmData   = ref(null)
const interestsData = ref(null)
// ... 已有的 ref ...

// startChat 里重置它们
confirmData.value   = null
interestsData.value = null

return {
  phase, messages, progressItems, reviewData, finalResult, error,
  confirmData, interestsData,
  startChat, sendReply,
}
```

- [ ] **Step 2: 更新 `App.vue`**

在 `<script setup>` 中解构新增字段：

```js
const {
  phase, messages, progressItems, reviewData, finalResult, error,
  confirmData, interestsData,
  startChat, sendReply,
} = useSSE()
```

在模板中 `<PlanReview>` 前插入两个新视图：

```html
<SelectInterests
  v-else-if="phase === 'interests'"
  :data="interestsData"
  @reply="onReply"
/>
<ConfirmIntent
  v-else-if="phase === 'confirm'"
  :data="confirmData"
  @reply="onReply"
/>
```

在 `<script setup>` 顶部新增 import：

```js
import SelectInterests from './components/SelectInterests.vue'
import ConfirmIntent   from './components/ConfirmIntent.vue'
```

更新 `stepClass` 的映射：

```js
const map = { idle: 0, chat: 1, interests: 1, confirm: 1, progress: 2, review: 3, done: 4, error: 0 }
```

- [ ] **Step 3: 手动验证编译无报错**

```bash
cd frontend && npm run build 2>&1 | tail -5
```

Expected: `✓ built in` 无 error

- [ ] **Step 4: Commit**

```bash
git add frontend/src/composables/useSSE.js frontend/src/App.vue
git commit -m "feat: wire up interests/confirm/error phases in frontend"
```

---

## Task 9: SelectInterests.vue — 多选标签组件

**Files:**
- Create: `frontend/src/components/SelectInterests.vue`

- [ ] **Step 1: 创建组件**

```vue
<template>
  <div class="view interests-view">
    <h2 class="interests-title">{{ data.message }}</h2>
    <p class="interests-sub">点选感兴趣的，也可以直接跳过</p>

    <div class="tag-grid">
      <button
        v-for="tag in data.tags"
        :key="tag"
        class="tag-chip"
        :class="{ selected: selected.has(tag) }"
        @click="toggle(tag)"
      >
        {{ tag }}
      </button>
    </div>

    <div class="input-bar" style="margin-top: auto;">
      <button class="btn-skip" @click="skip">跳过</button>
      <button class="btn-send" @click="confirm" :disabled="selected.size === 0">
        确认 ({{ selected.size }}) →
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'

const props = defineProps({ data: Object })
const emit = defineEmits(['reply'])

const selected = ref(new Set(props.data?.preselected ?? []))

function toggle(tag) {
  if (selected.value.has(tag)) {
    selected.value.delete(tag)
  } else {
    selected.value.add(tag)
  }
  selected.value = new Set(selected.value)
}

function confirm() {
  emit('reply', [...selected.value].join('、'))
}

function skip() {
  emit('reply', '')
}
</script>

<style scoped>
.interests-view {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 24px 16px 16px;
}
.interests-title { font-size: 20px; font-weight: 700; margin-bottom: 6px; }
.interests-sub   { font-size: 14px; color: var(--text-secondary); margin-bottom: 20px; }

.tag-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  flex: 1;
  align-content: flex-start;
}

.tag-chip {
  padding: 8px 16px;
  border-radius: 20px;
  border: 1.5px solid var(--border);
  background: transparent;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.15s;
  color: var(--text-primary);
}
.tag-chip.selected {
  background: var(--accent);
  color: #fff;
  border-color: var(--accent);
}

.btn-skip {
  padding: 11px 16px;
  background: var(--surface-2);
  color: var(--text-secondary);
  border: none;
  border-radius: 8px;
  font-size: 14px;
  cursor: pointer;
}
</style>
```

- [ ] **Step 2: 验证编译**

```bash
cd frontend && npm run build 2>&1 | tail -5
```

Expected: no error

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/SelectInterests.vue
git commit -m "feat: add SelectInterests multi-tag component"
```

---

## Task 10: ConfirmIntent.vue — 确认卡组件

**Files:**
- Create: `frontend/src/components/ConfirmIntent.vue`

- [ ] **Step 1: 创建组件**

```vue
<template>
  <div class="view confirm-view">
    <div class="confirm-card">
      <p class="confirm-label">小Z助手</p>
      <h2 class="confirm-title">帮你确认一下出行信息</h2>
      <p class="confirm-sub">没问题就点确认，或者告诉我哪里要改</p>

      <div class="info-rows">
        <div class="info-row">
          <span class="info-key">目的地</span>
          <span class="info-val">{{ data.destination }}</span>
        </div>
        <div class="info-row">
          <span class="info-key">出发地</span>
          <span class="info-val">{{ data.origin }}</span>
        </div>
        <div class="info-row">
          <span class="info-key">天数</span>
          <span class="info-val">{{ data.duration_days }} 天</span>
        </div>
        <div v-if="data.depart_date" class="info-row">
          <span class="info-key">出发时间</span>
          <span class="info-val">{{ data.depart_date }}</span>
        </div>
        <div v-if="data.interests?.length" class="info-row">
          <span class="info-key">兴趣</span>
          <span class="info-val">{{ data.interests.join('、') }}</span>
        </div>
      </div>

      <!-- 时段偏好：仅在有值时显示 -->
      <div v-if="data.depart_time_pref || data.return_time_pref" class="time-prefs">
        <div v-if="data.depart_time_pref" class="time-pref-row">
          ✓ 去程优先安排 {{ data.depart_time_pref }} 的航班
        </div>
        <div v-if="data.return_time_pref" class="time-pref-row">
          ✓ 返程 {{ data.return_time_pref }}
        </div>
      </div>

      <div class="confirm-input-bar">
        <input
          v-model="draft"
          placeholder="有要改的吗？直接说，或直接点确认"
          @keydown.enter.prevent="confirm"
        />
        <button class="btn-send" @click="confirm">确认，开始规划 →</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'

const props = defineProps({ data: Object })
const emit = defineEmits(['reply'])

const draft = ref('')

function confirm() {
  // Send draft text if user typed a modification; otherwise send "确认"
  emit('reply', draft.value.trim() || '确认')
  draft.value = ''
}
</script>

<style scoped>
.confirm-view {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px 16px;
  height: 100%;
}
.confirm-card {
  width: 100%;
  max-width: 480px;
  background: var(--surface);
  border-radius: 12px;
  padding: 24px;
  box-shadow: 0 2px 12px rgba(0,0,0,.08);
}
.confirm-label { font-size: 12px; color: var(--accent); font-weight: 600; margin-bottom: 6px; }
.confirm-title { font-size: 20px; font-weight: 700; margin-bottom: 4px; }
.confirm-sub   { font-size: 13px; color: var(--text-secondary); margin-bottom: 16px; }

.info-rows { display: flex; flex-direction: column; gap: 8px; margin-bottom: 14px; }
.info-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 12px;
  background: var(--surface-2);
  border-radius: 8px;
}
.info-key { font-size: 13px; color: var(--text-secondary); }
.info-val { font-size: 13px; font-weight: 600; }

.time-prefs {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 20px;
}
.time-pref-row {
  padding: 9px 12px;
  background: #eef2ff;
  border-radius: 8px;
  font-size: 13px;
  color: #4338ca;
}

.confirm-input-bar { display: flex; gap: 8px; }
.confirm-input-bar input {
  flex: 1;
  padding: 10px 12px;
  border: 1.5px solid var(--border);
  border-radius: 8px;
  font-size: 13px;
  background: var(--surface);
  color: var(--text-primary);
}
</style>
```

- [ ] **Step 2: 验证编译**

```bash
cd frontend && npm run build 2>&1 | tail -5
```

Expected: no error

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/ConfirmIntent.vue
git commit -m "feat: add ConfirmIntent card component"
```

---

## Task 11: ProgressView.vue — 三态时间线

**Files:**
- Modify: `frontend/src/components/ProgressView.vue`

- [ ] **Step 1: 替换整个组件**

```vue
<template>
  <div class="view progress-view">
    <p class="progress-title">正在为你规划行程</p>
    <ul class="timeline">
      <li
        v-for="step in allSteps"
        :key="step.node"
        class="timeline-item"
        :class="step.state"
      >
        <div class="tl-dot">
          <svg v-if="step.state === 'completed'" viewBox="0 0 16 16" fill="currentColor">
            <path d="M13.5 3.5L6 11 2.5 7.5l-1 1L6 13l8.5-8.5z"/>
          </svg>
          <div v-else-if="step.state === 'active'" class="spinner"></div>
        </div>
        <div class="tl-connector" v-if="!step.last"></div>
        <div class="tl-body">
          <div class="tl-label">{{ step.label }}</div>
          <div v-if="step.state === 'active'" class="tl-msg">{{ step.message }}</div>
        </div>
      </li>
    </ul>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({ items: Array })

const STEPS = [
  { node: 'parse_input',   label: '解析出行需求' },
  { node: 'discover_pois', label: '搜索景点 / 查询航班' },   // discover_pois & scrape_flights 并行
  { node: 'plan_itinerary', label: '规划行程方案' },
  { node: 'compose_output', label: '整理最终行程' },
]

// scrape_flights maps to the same slot as discover_pois
const NODE_TO_SLOT = {
  parse_input:    'parse_input',
  discover_pois:  'discover_pois',
  scrape_flights: 'discover_pois',
  plan_itinerary: 'plan_itinerary',
  compose_output: 'compose_output',
}

const allSteps = computed(() => {
  const reached = new Set((props.items || []).map(i => NODE_TO_SLOT[i.node]).filter(Boolean))
  const lastNode = props.items?.length
    ? NODE_TO_SLOT[props.items[props.items.length - 1].node]
    : null
  const lastMsg = props.items?.length
    ? props.items[props.items.length - 1].message
    : ''

  return STEPS.map((s, idx) => {
    let state = 'pending'
    if (reached.has(s.node)) {
      state = s.node === lastNode ? 'active' : 'completed'
    }
    return { ...s, state, message: state === 'active' ? lastMsg : '', last: idx === STEPS.length - 1 }
  })
})
</script>

<style scoped>
.progress-view { padding: 40px 24px; }
.progress-title { font-size: 18px; font-weight: 700; margin-bottom: 24px; }

.timeline { list-style: none; padding: 0; margin: 0; }
.timeline-item {
  display: flex;
  gap: 12px;
  position: relative;
  padding-bottom: 20px;
}
.timeline-item.pending { opacity: 0.35; }

.tl-dot {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1;
}
.completed .tl-dot { background: var(--accent); color: #fff; }
.completed .tl-dot svg { width: 14px; height: 14px; }
.active .tl-dot { border: 2px solid var(--accent); }
.pending .tl-dot { border: 2px solid var(--border); }

.tl-connector {
  position: absolute;
  left: 11px;
  top: 24px;
  bottom: 0;
  width: 2px;
  background: var(--border);
}

.tl-body { padding-top: 2px; }
.tl-label { font-size: 14px; font-weight: 600; }
.active .tl-label { color: var(--accent); }
.tl-msg  { font-size: 12px; color: var(--text-secondary); margin-top: 2px; }

.spinner {
  width: 16px;
  height: 16px;
  border: 2px solid var(--accent);
  border-top-color: transparent;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  margin: 1px;
}
@keyframes spin { to { transform: rotate(360deg); } }
</style>
```

- [ ] **Step 2: 验证编译**

```bash
cd frontend && npm run build 2>&1 | tail -5
```

Expected: no error

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/ProgressView.vue
git commit -m "feat: three-state timeline in ProgressView (completed/active/pending)"
```

---

## Task 12: PlanReview.vue — 展示 HH:MM 航班时刻

**Files:**
- Modify: `frontend/src/components/PlanReview.vue`

- [ ] **Step 1: 更新航班显示区块**

将 `<div class="plan-flight">` 那一行替换为：

```html
<div class="plan-flight">
  <span>✈ 去程 <strong>{{ plan.depart_time || '--:--' }}</strong></span>
  <span class="flight-route">{{ plan.flight }}</span>
</div>
<div v-if="plan.return_time" class="plan-flight plan-flight-return">
  ✈ 返程 <strong>{{ plan.return_time }}</strong>
</div>
```

在 `<style scoped>` 末尾追加：

```css
.plan-flight { font-size: 13px; color: var(--text-secondary); margin-bottom: 4px; }
.plan-flight strong { font-size: 15px; color: var(--text-primary); font-weight: 700; }
.plan-flight-return { margin-bottom: 10px; }
.flight-route { margin-left: 8px; }
```

- [ ] **Step 2: 验证编译**

```bash
cd frontend && npm run build 2>&1 | tail -5
```

Expected: no error

- [ ] **Step 3: 运行后台全部 Python 测试，确保无回归**

```bash
pytest tests/ -v --tb=short 2>&1 | tail -20
```

Expected: all PASSED

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/PlanReview.vue
git commit -m "feat: display HH:MM departure/return times on plan cards"
```

---

## 验收清单

运行完所有任务后逐项手动确认：

- [ ] 打开前端，不输入任何内容直接发送 → 第一条 AI 消息包含"小Z助手"
- [ ] 完整输入目的地/出发地/天数后 → 出现标签多选界面
- [ ] 选择标签后 → 出现出发时间询问、时段偏好询问、confirm 卡
- [ ] confirm 卡中填"去程9点，返程下午" → 显示两行蓝色提示
- [ ] confirm 卡中填"改成5天" → 重新进入确认循环
- [ ] 后台人为抛异常 → 前端显示 error 提示（而非无限 loading）
- [ ] Progress 时间线：已完成步骤打勾，当前步骤转圈，后续步骤半透明
- [ ] 方案卡显示去程时刻（如 09:15）和返程时刻（如 14:30）
- [ ] 偏好"上午"的用户，09:15 的航班排在 14:30 之前
