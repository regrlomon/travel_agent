# Frontend UX Redesign & Graph Restructure — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the rigid form-based frontend with a conversational chat UI, add a `collect_intent` ReAct node to the LangGraph graph, rewire human_review to run after plan_itinerary, and switch the frontend from WebSocket to SSE + REST.

**Architecture:** A new `collect_intent` node (multi-turn HITL, ReAct) replaces the form. It collects destination/origin/duration through natural conversation, then the graph runs silently through parse_input → discover_pois ‖ scrape_flights → plan_itinerary → human_review (moved here) → compose_output. The frontend uses EventSource (SSE) for server events and fetch POST for HITL replies.

**Tech Stack:** Python/LangGraph/FastAPI (backend), Vue 3/Vite (frontend, no UI framework, pure CSS dark theme).

---

## File Map

**Create:**
- `tools/airports.py` — AirportsClient: city → IATA codes (static dict + LLM fallback)
- `agent/nodes/collect_intent.py` — ReAct conversational intake node
- `tests/test_tools/test_airports.py`
- `tests/test_nodes/test_collect_intent.py`
- `frontend/src/composables/useSSE.js` — EventSource + fetch POST
- `frontend/src/style.css` — global dark theme CSS variables + base styles
- `frontend/src/components/ChatView.vue` — hero input + chat bubble stream
- `frontend/src/components/ProgressView.vue` — silent planning progress
- `frontend/src/components/PlanReview.vue` — complete plan cards + reply input
- `frontend/src/components/ResultView.vue` — final itinerary display

**Modify:**
- `agent/state.py` — add `raw_message`, `origin_airports` (already present but confirm), `selected_option_id`, `adjustment_notes`
- `agent/nodes/parse_input.py` — remove `interrupt()`, skip origin_airports if already in state
- `agent/nodes/human_review.py` — new interrupt type `review_plan`, reads `state["itineraries"]`
- `agent/graph.py` — add collect_intent node, rewire all edges
- `agent/tools_container.py` — add `airports` key
- `api/main.py` — PlanRequest: `message: str` replaces structured fields
- `frontend/src/App.vue` — phase state machine (idle/chat/progress/review/done)
- `frontend/src/main.js` — import style.css
- `frontend/vite.config.js` — add streaming headers to proxy

**Delete:**
- `frontend/src/composables/useWebSocket.js`
- `frontend/src/components/StepConfirm.vue`
- `frontend/src/components/StepProgress.vue`
- `frontend/src/components/StepReview.vue`
- `frontend/src/components/StepResults.vue`

---

## Task 1: State Fields

**Files:**
- Modify: `agent/state.py`

- [ ] **Step 1: Add new fields to TravelPlanState**

Open `agent/state.py` and add these fields:

```python
class TravelPlanState(TypedDict, total=False):
    # ── Raw input from API ──────────────────────────────────────────────
    raw_message: str              # user's first message, passed to collect_intent

    # existing fields stay exactly as-is:
    destination: str
    origin: str
    duration_days: int
    travelers: int
    transport_mode: str
    difficulty_level: str
    interests: list[str]
    depart_date: Optional[str]

    # ── Written by collect_intent ───────────────────────────────────────
    origin_airports: list[str]    # already exists in state, now written by collect_intent

    # ── Written by human_review (moved to after plan_itinerary) ─────────
    selected_option_id: str | None   # which plan the user chose ("A", "B", etc.)
    adjustment_notes: str | None     # free-text adjustments from user

    # ── Written by ① parse_input ────────────────────────────────────────
    destination_region: str
    destination_amap_cities: list[str]
    destination_airports: list[str]
    depart_dates: list[date]
    search_keywords: list[str]

    # ── Written by ② discover_pois ──────────────────────────────────────
    pois: list[POI]
    travel_time_matrix: dict[tuple[str, str], int]

    # ── Written by ③ scrape_flights ─────────────────────────────────────
    flight_pairs: list[FlightPair]
    selected_dates: list[date]

    # ── Written by ④ plan_itinerary ─────────────────────────────────────
    itineraries: list[ItineraryOption]

    # ── Written by human_review (old fields, kept for compose_output) ───
    user_flight_choice: str | None
    user_poi_prefs: str | None

    # ── Global ───────────────────────────────────────────────────────────
    errors: list[str]
    warnings: list[str]
    job_id: str
```

- [ ] **Step 2: Commit**

```bash
git add agent/state.py
git commit -m "feat(state): add raw_message, selected_option_id, adjustment_notes fields"
```

---

## Task 2: AirportsClient Tool

**Files:**
- Create: `tools/airports.py`
- Create: `tests/test_tools/test_airports.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_tools/test_airports.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock
from tools.airports import AirportsClient, AIRPORT_MAP


def test_static_lookup_suzhou():
    client = AirportsClient()
    result = client._static_lookup("苏州")
    assert "PVG" in result
    assert "SHA" in result


def test_static_lookup_beijing():
    client = AirportsClient()
    result = client._static_lookup("北京")
    assert "PEK" in result


def test_static_lookup_unknown_returns_empty():
    client = AirportsClient()
    result = client._static_lookup("某个不存在的城市xyz")
    assert result == []


@pytest.mark.asyncio
async def test_lookup_uses_static_for_known_city():
    client = AirportsClient()
    result = await client.lookup("上海")
    assert "PVG" in result


@pytest.mark.asyncio
async def test_lookup_llm_fallback_for_unknown(mocker):
    mock_resp = MagicMock()
    mock_resp.choices[0].message.content = '["XYZ"]'
    mocker.patch("litellm.acompletion", AsyncMock(return_value=mock_resp))

    client = AirportsClient()
    result = await client.lookup("某小城市")
    assert result == ["XYZ"]
```

- [ ] **Step 2: Run tests — expect FAIL (module not found)**

```bash
cd D:/project/python/travel_agent
python -m pytest tests/test_tools/test_airports.py -v
```

Expected: `ModuleNotFoundError: No module named 'tools.airports'`

- [ ] **Step 3: Implement `tools/airports.py`**

```python
import json, os
import litellm

AIRPORT_MAP: dict[str, list[str]] = {
    "北京":  ["PEK", "PKX"],
    "上海":  ["PVG", "SHA"],
    "苏州":  ["PVG", "SHA", "NKG"],   # 苏州无机场
    "无锡":  ["SHA", "NKG"],
    "南京":  ["NKG"],
    "杭州":  ["HGH"],
    "广州":  ["CAN"],
    "深圳":  ["SZX"],
    "成都":  ["CTU", "TFU"],
    "重庆":  ["CKG"],
    "武汉":  ["WUH"],
    "西安":  ["XIY"],
    "昆明":  ["KMG"],
    "拉萨":  ["LXA"],
    "稻城":  ["DCY"],
    "康定":  ["KGT"],
    "丽江":  ["LJG"],
    "三亚":  ["SYX"],
    "厦门":  ["XMN"],
    "青岛":  ["TAO"],
    "天津":  ["TSN"],
    "哈尔滨": ["HRB"],
    "长沙":  ["CSX"],
    "沈阳":  ["SHE"],
    "大连":  ["DLC"],
    "济南":  ["TNA"],
    "郑州":  ["CGO"],
    "合肥":  ["HFE"],
    "南昌":  ["KHN"],
    "福州":  ["FOC"],
    "贵阳":  ["KWE"],
    "南宁":  ["NNG"],
    "呼和浩特": ["HET"],
    "银川":  ["INC"],
    "西宁":  ["XNN"],
    "兰州":  ["LHW"],
    "乌鲁木齐": ["URC"],
}


class AirportsClient:
    def _static_lookup(self, city: str) -> list[str]:
        for key, airports in AIRPORT_MAP.items():
            if key in city or city in key:
                return airports
        return []

    async def lookup(self, city: str) -> list[str]:
        result = self._static_lookup(city)
        if result:
            return result
        return await self._llm_lookup(city)

    async def _llm_lookup(self, city: str) -> list[str]:
        prompt = (
            f'What are the IATA airport codes for traveling from/to "{city}" in China? '
            f'If no direct airport, list the nearest major airport(s). '
            f'Return only a JSON array of codes, no markdown. Example: ["PVG","SHA"]'
        )
        resp = await litellm.acompletion(
            model=os.getenv("LLM_MODEL", "deepseek/deepseek-chat"),
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
        )
        return json.loads(resp.choices[0].message.content)
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
python -m pytest tests/test_tools/test_airports.py -v
```

Expected: all 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add tools/airports.py tests/test_tools/test_airports.py
git commit -m "feat(tools): add AirportsClient with static lookup + LLM fallback"
```

---

## Task 3: collect_intent Node

**Files:**
- Create: `agent/nodes/collect_intent.py`
- Create: `tests/test_nodes/test_collect_intent.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_nodes/test_collect_intent.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock
from agent.nodes.collect_intent import _is_complete, _llm_extract, _llm_build_reply


def test_is_complete_all_fields():
    assert _is_complete({"destination": "川西", "origin": "苏州", "duration_days": 7}) is True


def test_is_complete_missing_duration():
    assert _is_complete({"destination": "川西", "origin": "苏州"}) is False


def test_is_complete_missing_origin():
    assert _is_complete({"destination": "川西", "duration_days": 7}) is False


def test_is_complete_empty():
    assert _is_complete({}) is False


@pytest.mark.asyncio
async def test_llm_extract_full_sentence(mocker):
    mock_resp = MagicMock()
    mock_resp.choices[0].message.content = (
        '{"destination": "川西", "origin": "苏州", "duration_days": 7, '
        '"interests": ["自然风光"], "depart_date": null}'
    )
    mocker.patch("litellm.acompletion", AsyncMock(return_value=mock_resp))

    result = await _llm_extract("川西7天，苏州出发，喜欢自然风光", {})
    assert result["destination"] == "川西"
    assert result["origin"] == "苏州"
    assert result["duration_days"] == 7
    assert "自然风光" in result["interests"]


@pytest.mark.asyncio
async def test_llm_build_reply_asks_missing(mocker):
    mock_resp = MagicMock()
    mock_resp.choices[0].message.content = "从哪里出发？大概玩几天？"
    mocker.patch("litellm.acompletion", AsyncMock(return_value=mock_resp))

    reply = await _llm_build_reply({"destination": "川西"})
    assert len(reply) > 0
```

- [ ] **Step 2: Run tests — expect FAIL**

```bash
python -m pytest tests/test_nodes/test_collect_intent.py -v
```

Expected: `ImportError: cannot import name '_is_complete'`

- [ ] **Step 3: Implement `agent/nodes/collect_intent.py`**

```python
import json, os
import litellm
from langchain_core.runnables import RunnableConfig
from langgraph.types import interrupt
from agent.state import TravelPlanState


def _is_complete(collected: dict) -> bool:
    return bool(
        collected.get("destination")
        and collected.get("origin")
        and collected.get("duration_days")
    )


async def _llm_extract(user_text: str, current: dict) -> dict:
    prompt = f"""You are helping collect travel intent. Extract any travel info from the user message.

Current collected info: {json.dumps(current, ensure_ascii=False)}
User message: "{user_text}"

Extract and return JSON with these keys (only include keys mentioned in message, keep existing values):
- destination: string (e.g. "川西", "西藏")
- origin: string (e.g. "苏州", "北京")  
- duration_days: integer
- interests: list of strings (e.g. ["自然风光", "徒步"])
- depart_date: string ISO date or null

Return only valid JSON, no markdown."""
    resp = await litellm.acompletion(
        model=os.getenv("LLM_MODEL", "deepseek/deepseek-chat"),
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
    )
    extracted = json.loads(resp.choices[0].message.content)
    merged = {**current}
    for k, v in extracted.items():
        if v is not None and v != [] and v != "":
            merged[k] = v
    return merged


async def _llm_build_reply(collected: dict) -> str:
    missing = []
    if not collected.get("destination"):
        missing.append("目的地")
    if not collected.get("origin"):
        missing.append("出发城市")
    if not collected.get("duration_days"):
        missing.append("出行天数")

    prompt = f"""You are a friendly Chinese travel assistant. The user wants to plan a trip.

Already collected: {json.dumps(collected, ensure_ascii=False)}
Still need: {missing}

Write ONE natural, warm reply in Chinese that:
1. Acknowledges what you already know (if anything)
2. Asks for the missing info in a conversational way (can ask multiple things in one sentence)
3. If destination is vague or unknown, offer 2-3 suggestions based on the style mentioned

Keep it under 60 characters. Be friendly, not robotic. No bullet points."""
    resp = await litellm.acompletion(
        model=os.getenv("LLM_MODEL", "deepseek/deepseek-chat"),
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
    )
    return resp.choices[0].message.content.strip()


async def run(state: TravelPlanState, config: RunnableConfig) -> dict:
    tools = config["configurable"]["tools"]
    collected: dict = {}

    # Process the initial message from API if present
    raw = state.get("raw_message", "")
    if raw:
        collected = await _llm_extract(raw, collected)

    while not _is_complete(collected):
        reply_text = await _llm_build_reply(collected)
        user_reply = interrupt({
            "type": "collect_intent",
            "message": reply_text,
        })
        collected = await _llm_extract(user_reply.get("text", ""), collected)

    # Resolve origin airports accurately via tool
    origin_airports = await tools["airports"].lookup(collected["origin"])

    return {
        "destination":    collected["destination"],
        "origin":         collected["origin"],
        "duration_days":  int(collected["duration_days"]),
        "interests":      collected.get("interests", []),
        "depart_date":    collected.get("depart_date"),
        "origin_airports": origin_airports,
    }
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
python -m pytest tests/test_nodes/test_collect_intent.py -v
```

Expected: all 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add agent/nodes/collect_intent.py tests/test_nodes/test_collect_intent.py
git commit -m "feat(agent): add collect_intent ReAct node with multi-turn HITL"
```

---

## Task 4: parse_input — Remove interrupt, respect state origin_airports

**Files:**
- Modify: `agent/nodes/parse_input.py`

- [ ] **Step 1: Remove the interrupt block and skip origin_airports if already set**

Replace the entire `run()` function in `agent/nodes/parse_input.py`:

```python
async def run(state: TravelPlanState, config: RunnableConfig) -> dict:
    tools = config["configurable"]["tools"]
    parsed = await _llm_parse_destination(state["destination"], state["origin"])

    code_map = await tools["amap"].get_district_codes(parsed["city_names"])
    amap_cities = list(code_map.values())

    # collect_intent already resolved origin airports via AirportsClient;
    # only fall back to LLM-parsed airports if not set
    origin_airports = state.get("origin_airports") or parsed["origin_airports"]

    return {
        "destination_region":       parsed["region"],
        "destination_amap_cities":  amap_cities,
        "destination_airports":     parsed["destination_airports"],
        "origin_airports":          origin_airports,
        "depart_dates":             _expand_dates(state.get("depart_date")),
        "search_keywords":          parsed["search_keywords"],
    }
```

Remove the `_apply_corrections` function and its imports — they are no longer needed.

- [ ] **Step 2: Verify existing tests still pass**

```bash
python -m pytest tests/ -v --ignore=tests/test_tools/test_flight_scraper.py -k "not xhs"
```

Expected: all existing tests PASS (parse_input had no dedicated tests)

- [ ] **Step 3: Commit**

```bash
git add agent/nodes/parse_input.py
git commit -m "refactor(parse_input): remove interrupt and _apply_corrections, respect state origin_airports"
```

---

## Task 5: human_review — New format, reads itineraries

**Files:**
- Modify: `agent/nodes/human_review.py`

- [ ] **Step 1: Rewrite human_review to work after plan_itinerary**

Replace the entire content of `agent/nodes/human_review.py`:

```python
import json, os
import litellm
from langchain_core.runnables import RunnableConfig
from langgraph.types import interrupt
from agent.state import TravelPlanState


def _format_plans_for_display(itineraries: list) -> list[dict]:
    """Serialize itineraries into compact summaries for the interrupt payload."""
    plans = []
    for itin in itineraries:
        fp = itin.flights
        days_summary = [
            {"day": d.day, "pois": [p.name for p in d.pois], "note": d.transport_note}
            for d in itin.days
        ]
        plans.append({
            "option_id":  itin.option_id,
            "summary":    itin.summary,
            "flight":     f"{fp.outbound.depart_airport}→{fp.outbound.arrive_airport} ¥{fp.total_price}/人",
            "depart_date": fp.outbound.depart_time.strftime("%Y-%m-%d"),
            "days":       days_summary,
        })
    return plans


async def _parse_user_reply(user_text: str, plans: list[dict], config: RunnableConfig) -> dict:
    plan_ids = [p["option_id"] for p in plans]
    prompt = f"""User replied to travel plans: "{user_text}"
Available plan IDs: {plan_ids}

Extract:
- selected_option_id: which plan the user chose (e.g. "A", "B") or "" if unclear
- adjustment_notes: any specific preferences or changes mentioned, or ""

Return JSON: {{"selected_option_id": "...", "adjustment_notes": "..."}}
Return only valid JSON, no markdown."""
    resp = await litellm.acompletion(
        model=os.getenv("LLM_MODEL", "deepseek/deepseek-chat"),
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
    )
    return json.loads(resp.choices[0].message.content)


async def run(state: TravelPlanState, config: RunnableConfig) -> dict:
    itineraries = state.get("itineraries", [])
    plans = _format_plans_for_display(itineraries)

    user_reply = interrupt({
        "type":    "review_plan",
        "message": f"帮你规划了 {len(plans)} 个方案，你看哪个合适，或者有想调整的？",
        "plans":   plans,
    })

    parsed = await _parse_user_reply(
        user_text=user_reply.get("text", ""),
        plans=plans,
        config=config,
    )

    return {
        "selected_option_id": parsed.get("selected_option_id") or None,
        "adjustment_notes":   parsed.get("adjustment_notes") or None,
        # keep legacy fields so compose_output doesn't break
        "user_flight_choice": parsed.get("selected_option_id") or None,
        "user_poi_prefs":     parsed.get("adjustment_notes") or None,
    }
```

- [ ] **Step 2: Run full test suite**

```bash
python -m pytest tests/ -v --ignore=tests/test_tools/test_flight_scraper.py -k "not xhs"
```

Expected: all tests PASS

- [ ] **Step 3: Commit**

```bash
git add agent/nodes/human_review.py
git commit -m "refactor(human_review): move after plan_itinerary, show full plans instead of raw data"
```

---

## Task 6: Graph Rewire + API + Tools Container

**Files:**
- Modify: `agent/graph.py`
- Modify: `agent/tools_container.py`
- Modify: `api/main.py`

- [ ] **Step 1: Rewire graph.py**

Replace the entire content of `agent/graph.py`:

```python
from langgraph.graph import StateGraph, END
from agent.state import TravelPlanState
import agent.nodes.collect_intent as collect_intent
import agent.nodes.parse_input    as parse_input
import agent.nodes.discover_pois  as discover_pois
import agent.nodes.scrape_flights as scrape_flights
import agent.nodes.plan_itinerary as plan_itinerary
import agent.nodes.human_review   as human_review
import agent.nodes.compose_output as compose_output


def build_compiled_graph(checkpointer):
    g = StateGraph(TravelPlanState)
    g.add_node("collect_intent", collect_intent.run)
    g.add_node("parse_input",    parse_input.run)
    g.add_node("discover_pois",  discover_pois.run)
    g.add_node("scrape_flights", scrape_flights.run)
    g.add_node("plan_itinerary", plan_itinerary.run)
    g.add_node("human_review",   human_review.run)
    g.add_node("compose_output", compose_output.run)

    g.set_entry_point("collect_intent")
    g.add_edge("collect_intent", "parse_input")
    g.add_edge("parse_input",    "discover_pois")
    g.add_edge("parse_input",    "scrape_flights")
    g.add_edge("discover_pois",  "plan_itinerary")
    g.add_edge("scrape_flights", "plan_itinerary")
    g.add_edge("plan_itinerary", "human_review")
    g.add_edge("human_review",   "compose_output")
    g.add_edge("compose_output", END)

    return g.compile(checkpointer=checkpointer)
```

- [ ] **Step 2: Add airports to tools_container.py**

Replace the content of `agent/tools_container.py`:

```python
import os
from tools.amap import AmapClient
from tools.tavily import TavilyClient
from tools.xhs_tool import XhsClient
from tools.flight_tool.tool import FlightClient
from tools.airports import AirportsClient


def build_tools(overrides: dict | None = None) -> dict:
    defaults = {
        "amap":     AmapClient(api_key=os.getenv("AMAP_API_KEY", "")),
        "tavily":   TavilyClient(api_key=os.getenv("TAVILY_API_KEY", "")),
        "xhs":      XhsClient(),
        "flight":   FlightClient(),
        "airports": AirportsClient(),
    }
    return {**defaults, **(overrides or {})}
```

- [ ] **Step 3: Simplify api/main.py PlanRequest**

In `api/main.py`, replace the `PlanRequest` class and `create_plan` endpoint:

```python
class PlanRequest(BaseModel):
    message: str = ""   # user's first message; empty string triggers AI greeting


@app.post("/plans", status_code=202)
async def create_plan(req: PlanRequest):
    job_id = str(uuid.uuid4())
    initial_state = {
        "raw_message": req.message,
        "errors": [],
        "warnings": [],
        "job_id": job_id,
    }
    run_plan.delay(job_id, initial_state)
    return {"job_id": job_id, "status": "pending"}
```

Also update the import at the top — remove `Optional` from the PlanRequest type hints since they're no longer needed.

- [ ] **Step 4: Update worker/tasks.py run_plan — it already passes request_data as initial_state, verify it works**

Open `worker/tasks.py` and confirm `run_plan` already does:
```python
initial_state = {**request_data, "errors": [], "warnings": [], "job_id": job_id}
```
Since `api/main.py` now constructs `initial_state` itself and passes it to `run_plan.delay(job_id, initial_state)`, update the task signature to match:

```python
@celery_app.task(bind=True, max_retries=0)
def run_plan(self, job_id: str, initial_state: dict):
    with RedisSaver.from_conn_string(os.getenv("REDIS_URL", "redis://localhost:6379/0")) as checkpointer:
        checkpointer.setup()
        graph = build_compiled_graph(checkpointer)
        result = asyncio.run(graph.ainvoke(initial_state, config=_build_config(job_id)))
    _handle_result(job_id, result)
```

- [ ] **Step 5: Run full test suite**

```bash
python -m pytest tests/ -v --ignore=tests/test_tools/test_flight_scraper.py -k "not xhs"
```

Expected: all tests PASS

- [ ] **Step 6: Commit**

```bash
git add agent/graph.py agent/tools_container.py api/main.py worker/tasks.py
git commit -m "feat(graph): add collect_intent, move human_review after plan_itinerary, simplify API entry"
```

---

## Task 7: useSSE.js (Frontend Communication)

**Files:**
- Create: `frontend/src/composables/useSSE.js`
- Delete: `frontend/src/composables/useWebSocket.js`
- Modify: `frontend/vite.config.js`

- [ ] **Step 1: Update vite.config.js to handle SSE streaming**

Replace `frontend/vite.config.js`:

```javascript
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    proxy: {
      '/plans': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        headers: {
          'Cache-Control': 'no-cache',
          'X-Accel-Buffering': 'no',
        },
      },
    },
  },
})
```

- [ ] **Step 2: Create useSSE.js**

Create `frontend/src/composables/useSSE.js`:

```javascript
import { ref } from 'vue'

export function useSSE() {
  const phase = ref('idle')         // idle | chat | progress | review | done | error
  const messages = ref([])          // [{role:'ai'|'user', text:string}]
  const progressItems = ref([])     // [{node, message, pct}]
  const reviewData = ref(null)      // {message, plans:[...]}
  const finalResult = ref(null)     // compose_output result
  const error = ref(null)

  let jobId = null
  let interruptId = null
  let eventSource = null

  async function startChat(userText) {
    messages.value = []
    progressItems.value = []
    reviewData.value = null
    finalResult.value = null
    error.value = null
    phase.value = 'chat'

    if (userText) {
      messages.value.push({ role: 'user', text: userText })
    }

    const resp = await fetch('/plans', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: userText }),
    })
    const data = await resp.json()
    jobId = data.job_id
    _openSSE()
  }

  function _openSSE() {
    if (eventSource) eventSource.close()
    eventSource = new EventSource(`/plans/${jobId}/events`)

    eventSource.onmessage = (e) => {
      const msg = JSON.parse(e.data)

      if (msg.type === 'hitl_request') {
        interruptId = msg.interrupt_id
        if (msg.data.type === 'collect_intent') {
          phase.value = 'chat'
          messages.value.push({ role: 'ai', text: msg.data.message })
        } else if (msg.data.type === 'review_plan') {
          phase.value = 'review'
          reviewData.value = msg.data
        }
      } else if (msg.type === 'progress') {
        phase.value = 'progress'
        progressItems.value.push(msg)
      } else if (msg.type === 'done') {
        finalResult.value = msg.result
        phase.value = 'done'
        eventSource.close()
      }
    }

    eventSource.onerror = () => {
      error.value = '连接中断，请刷新页面重试'
      phase.value = 'error'
      eventSource.close()
    }
  }

  async function sendReply(text) {
    if (!jobId || !interruptId) return

    messages.value.push({ role: 'user', text })

    await fetch(`/plans/${jobId}/reply`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, interrupt_id: interruptId }),
    })

    if (phase.value === 'review') {
      phase.value = 'progress'
    }
    // For chat phase: wait for next SSE hitl_request
  }

  return {
    phase, messages, progressItems, reviewData, finalResult, error,
    startChat, sendReply,
  }
}
```

- [ ] **Step 3: Delete the old WebSocket composable**

```bash
rm frontend/src/composables/useWebSocket.js
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/composables/useSSE.js frontend/vite.config.js
git rm frontend/src/composables/useWebSocket.js
git commit -m "feat(frontend): replace WebSocket with SSE + fetch POST (useSSE.js)"
```

---

## Task 8: Global Dark Theme CSS

**Files:**
- Create: `frontend/src/style.css`
- Modify: `frontend/src/main.js`

- [ ] **Step 1: Create style.css**

Create `frontend/src/style.css`:

```css
:root {
  --bg-base:        #0d1117;
  --bg-surface:     #161b22;
  --bg-elevated:    #1c2128;
  --bg-input:       #21262d;
  --border:         #30363d;
  --border-subtle:  #21262d;
  --text-primary:   #e6edf3;
  --text-secondary: #8b949e;
  --text-muted:     #484f58;
  --accent:         #1f6feb;
  --accent-hover:   #388bfd;
  --accent-text:    #ffffff;
  --success:        #3fb950;
  --warning:        #d29922;
  --error:          #f85149;
  --radius-sm:      6px;
  --radius-md:      12px;
  --radius-lg:      20px;
  --radius-full:    9999px;
}

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

/* ── Top bar ──────────────────────────────── */
.topbar {
  background: var(--bg-surface);
  border-bottom: 1px solid var(--border);
  padding: 0 24px;
  height: 52px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-shrink: 0;
}

.topbar-brand {
  font-weight: 700;
  font-size: 14px;
  color: var(--accent-hover);
  letter-spacing: 0.5px;
}

.stepper {
  display: flex;
  gap: 4px;
  align-items: center;
}

.step-dot {
  width: 28px;
  height: 4px;
  border-radius: 2px;
  background: var(--border);
  transition: background 0.3s;
}

.step-dot.active { background: var(--accent); }
.step-dot.done   { background: var(--success); }

/* ── Main content area ────────────────────── */
.view { flex: 1; overflow-y: auto; }

/* ── Chat bubbles ─────────────────────────── */
.chat-messages {
  max-width: 720px;
  margin: 0 auto;
  padding: 24px 24px 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.bubble-row { display: flex; gap: 10px; align-items: flex-end; }
.bubble-row.user { flex-direction: row-reverse; }

.bubble-avatar {
  width: 30px;
  height: 30px;
  border-radius: 50%;
  background: var(--accent);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 700;
  color: #fff;
  flex-shrink: 0;
}

.bubble {
  max-width: 72%;
  padding: 10px 14px;
  border-radius: var(--radius-md);
  font-size: 14px;
  line-height: 1.6;
}

.bubble.ai {
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-bottom-left-radius: 3px;
  color: var(--text-primary);
}

.bubble.user {
  background: var(--accent);
  border-bottom-right-radius: 3px;
  color: #fff;
}

/* ── Input bar ────────────────────────────── */
.input-bar {
  max-width: 720px;
  margin: 16px auto;
  padding: 0 24px;
  display: flex;
  gap: 10px;
  align-items: center;
}

.input-bar input {
  flex: 1;
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-radius: var(--radius-full);
  padding: 10px 18px;
  font-size: 14px;
  color: var(--text-primary);
  outline: none;
  transition: border-color 0.2s;
}

.input-bar input::placeholder { color: var(--text-muted); }
.input-bar input:focus { border-color: var(--accent); }

.btn-send {
  width: 38px;
  height: 38px;
  border-radius: 50%;
  background: var(--accent);
  border: none;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 16px;
  flex-shrink: 0;
  transition: background 0.2s;
}

.btn-send:hover { background: var(--accent-hover); }
.btn-send:disabled { background: var(--border); cursor: not-allowed; }

/* ── Progress timeline ────────────────────── */
.progress-view {
  max-width: 560px;
  margin: 48px auto;
  padding: 0 24px;
}

.progress-title {
  color: var(--text-secondary);
  font-size: 13px;
  text-transform: uppercase;
  letter-spacing: 1px;
  margin-bottom: 24px;
}

.timeline { list-style: none; display: flex; flex-direction: column; gap: 0; }

.timeline-item {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  padding-bottom: 20px;
  position: relative;
}

.timeline-item::before {
  content: '';
  position: absolute;
  left: 11px;
  top: 24px;
  bottom: 0;
  width: 1px;
  background: var(--border);
}

.timeline-item:last-child::before { display: none; }

.timeline-dot {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: var(--success);
  border: 2px solid var(--bg-base);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  flex-shrink: 0;
  color: #fff;
}

.timeline-dot.pending { background: var(--border); animation: pulse 1.5s infinite; }

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50%       { opacity: 0.4; }
}

.timeline-text { padding-top: 2px; }
.timeline-node { font-size: 12px; color: var(--text-muted); }
.timeline-msg  { font-size: 14px; color: var(--text-primary); }

/* ── Plan review cards ────────────────────── */
.review-view {
  max-width: 800px;
  margin: 32px auto;
  padding: 0 24px;
}

.review-title { font-size: 16px; font-weight: 600; margin-bottom: 8px; }
.review-subtitle { font-size: 13px; color: var(--text-secondary); margin-bottom: 24px; }

.plan-cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 14px; margin-bottom: 24px; }

.plan-card {
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  padding: 16px;
  cursor: pointer;
  transition: border-color 0.2s;
}

.plan-card:hover { border-color: var(--accent); }
.plan-card.selected { border-color: var(--accent); background: #1f6feb18; }

.plan-option-id {
  font-size: 11px;
  font-weight: 700;
  color: var(--accent-hover);
  text-transform: uppercase;
  letter-spacing: 1px;
  margin-bottom: 6px;
}

.plan-summary { font-size: 13px; font-weight: 600; margin-bottom: 8px; }
.plan-flight  { font-size: 12px; color: var(--text-secondary); margin-bottom: 10px; }

.plan-days { display: flex; flex-direction: column; gap: 3px; }
.plan-day  { font-size: 12px; color: var(--text-muted); }

/* ── Result view ──────────────────────────── */
.result-view {
  max-width: 800px;
  margin: 32px auto;
  padding: 0 24px 48px;
}

.result-header { margin-bottom: 24px; }
.result-header h2 { font-size: 20px; font-weight: 700; }
.result-header p  { color: var(--text-secondary); font-size: 13px; margin-top: 4px; }

.warning-box {
  background: #d2992218;
  border: 1px solid var(--warning);
  border-radius: var(--radius-sm);
  padding: 10px 14px;
  font-size: 13px;
  color: var(--warning);
  margin-bottom: 20px;
}

.itinerary-card {
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  padding: 20px;
  margin-bottom: 16px;
}

.itin-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 14px; }
.itin-title  { font-size: 15px; font-weight: 600; }
.itin-flight { font-size: 12px; color: var(--text-secondary); margin-top: 3px; }
.itin-price  { font-size: 16px; font-weight: 700; color: var(--accent-hover); }

.day-list { display: flex; flex-direction: column; gap: 10px; }

.day-row { display: flex; gap: 12px; align-items: flex-start; }
.day-num { font-size: 11px; font-weight: 700; color: var(--accent); min-width: 32px; }
.day-pois { display: flex; flex-wrap: wrap; gap: 5px; }
.poi-chip {
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-radius: var(--radius-full);
  padding: 2px 8px;
  font-size: 12px;
  color: var(--text-secondary);
}
.day-note { font-size: 12px; color: var(--text-muted); margin-top: 4px; }
```

- [ ] **Step 2: Import style.css in main.js**

Replace `frontend/src/main.js`:

```javascript
import { createApp } from 'vue'
import './style.css'
import App from './App.vue'

createApp(App).mount('#app')
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/style.css frontend/src/main.js
git commit -m "feat(frontend): add global dark theme CSS"
```

---

## Task 9: ChatView.vue

**Files:**
- Create: `frontend/src/components/ChatView.vue`
- Delete: `frontend/src/components/StepConfirm.vue`

- [ ] **Step 1: Create ChatView.vue**

Create `frontend/src/components/ChatView.vue`:

```vue
<template>
  <div class="view chat-view">
    <!-- Hero: shown only before first message -->
    <div v-if="messages.length === 0" class="hero">
      <h1 class="hero-title">你想去哪里？</h1>
      <p class="hero-sub">告诉我你的想法，我来帮你搞定机票和行程</p>
    </div>

    <!-- Chat bubbles -->
    <div v-else class="chat-messages">
      <div
        v-for="(msg, i) in messages"
        :key="i"
        class="bubble-row"
        :class="msg.role"
      >
        <div class="bubble-avatar">{{ msg.role === 'ai' ? 'AI' : '我' }}</div>
        <div class="bubble" :class="msg.role">{{ msg.text }}</div>
      </div>

      <!-- Typing indicator while waiting for AI -->
      <div v-if="waiting" class="bubble-row ai">
        <div class="bubble-avatar">AI</div>
        <div class="bubble ai typing">
          <span></span><span></span><span></span>
        </div>
      </div>
    </div>

    <!-- Input bar -->
    <div class="input-bar">
      <input
        v-model="draft"
        :placeholder="messages.length === 0
          ? '随便说，比如「想去西藏看星空，7月，从广州出发」'
          : '继续输入...'"
        @keydown.enter.prevent="send"
        :disabled="waiting"
        ref="inputEl"
      />
      <button class="btn-send" @click="send" :disabled="!draft.trim() || waiting">→</button>
    </div>
  </div>
</template>

<script setup>
import { ref, nextTick } from 'vue'

const props = defineProps({ messages: Array, waiting: Boolean })
const emit = defineEmits(['send'])

const draft = ref('')
const inputEl = ref(null)

function send() {
  const text = draft.value.trim()
  if (!text) return
  draft.value = ''
  emit('send', text)
  nextTick(() => inputEl.value?.focus())
}
</script>

<style scoped>
.chat-view {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.hero {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: 48px 24px 0;
}

.hero-title { font-size: 32px; font-weight: 700; margin-bottom: 10px; }
.hero-sub   { font-size: 15px; color: var(--text-secondary); }

.chat-messages { flex: 1; }

/* typing dots */
.bubble.typing { display: flex; gap: 4px; align-items: center; padding: 12px 14px; }
.bubble.typing span {
  width: 6px; height: 6px; border-radius: 50%;
  background: var(--text-muted);
  animation: blink 1.2s infinite;
}
.bubble.typing span:nth-child(2) { animation-delay: 0.2s; }
.bubble.typing span:nth-child(3) { animation-delay: 0.4s; }

@keyframes blink {
  0%, 80%, 100% { opacity: 0.2; }
  40%           { opacity: 1; }
}
</style>
```

- [ ] **Step 2: Delete old StepConfirm**

```bash
git rm frontend/src/components/StepConfirm.vue
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/ChatView.vue
git commit -m "feat(frontend): add ChatView — hero input + chat bubble stream"
```

---

## Task 10: ProgressView.vue

**Files:**
- Create: `frontend/src/components/ProgressView.vue`
- Delete: `frontend/src/components/StepProgress.vue`

- [ ] **Step 1: Create ProgressView.vue**

Create `frontend/src/components/ProgressView.vue`:

```vue
<template>
  <div class="view progress-view">
    <p class="progress-title">正在规划</p>
    <ul class="timeline">
      <li v-for="(item, i) in items" :key="i" class="timeline-item">
        <div class="timeline-dot">✓</div>
        <div class="timeline-text">
          <div class="timeline-node">{{ item.node }}</div>
          <div class="timeline-msg">{{ item.message }}</div>
        </div>
      </li>
      <li class="timeline-item">
        <div class="timeline-dot pending"></div>
        <div class="timeline-text">
          <div class="timeline-msg" style="color: var(--text-secondary)">处理中...</div>
        </div>
      </li>
    </ul>
  </div>
</template>

<script setup>
defineProps({ items: Array })
</script>
```

- [ ] **Step 2: Delete old StepProgress**

```bash
git rm frontend/src/components/StepProgress.vue
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/ProgressView.vue
git commit -m "feat(frontend): add ProgressView with dark theme timeline"
```

---

## Task 11: PlanReview.vue

**Files:**
- Create: `frontend/src/components/PlanReview.vue`
- Delete: `frontend/src/components/StepReview.vue`
- Delete: `frontend/src/components/StepResults.vue`

- [ ] **Step 1: Create PlanReview.vue**

Create `frontend/src/components/PlanReview.vue`:

```vue
<template>
  <div class="view review-view">
    <h2 class="review-title">行程方案</h2>
    <p class="review-subtitle">{{ data.message }}</p>

    <div class="plan-cards">
      <div
        v-for="plan in data.plans"
        :key="plan.option_id"
        class="plan-card"
        :class="{ selected: selected === plan.option_id }"
        @click="selected = plan.option_id"
      >
        <div class="plan-option-id">方案 {{ plan.option_id }}</div>
        <div class="plan-summary">{{ plan.summary }}</div>
        <div class="plan-flight">✈ {{ plan.flight }}  · {{ plan.depart_date }}</div>
        <div class="plan-days">
          <div v-for="day in plan.days.slice(0, 3)" :key="day.day" class="plan-day">
            Day {{ day.day }}：{{ day.pois.join(' · ') }}
          </div>
          <div v-if="plan.days.length > 3" class="plan-day">...共 {{ plan.days.length }} 天</div>
        </div>
      </div>
    </div>

    <div class="input-bar">
      <input
        v-model="draft"
        :placeholder="selected
          ? `已选方案 ${selected}，有想调整的吗？或直接按确认`
          : '说说你的想法，或选一个方案'"
        @keydown.enter.prevent="confirm"
      />
      <button class="btn-send" @click="confirm">→</button>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'

const props = defineProps({ data: Object })
const emit = defineEmits(['reply'])

const selected = ref('')
const draft = ref('')

function confirm() {
  const text = draft.value.trim() || (selected.value ? `选${selected.value}` : '确认，帮我安排')
  draft.value = ''
  emit('reply', text)
}
</script>
```

- [ ] **Step 2: Delete old step components**

```bash
git rm frontend/src/components/StepReview.vue
git rm frontend/src/components/StepResults.vue
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/PlanReview.vue
git commit -m "feat(frontend): add PlanReview — plan cards + reply input"
```

---

## Task 12: ResultView.vue + App.vue Wiring

**Files:**
- Create: `frontend/src/components/ResultView.vue`
- Modify: `frontend/src/App.vue`

- [ ] **Step 1: Create ResultView.vue**

Create `frontend/src/components/ResultView.vue`:

```vue
<template>
  <div class="view result-view">
    <div class="result-header">
      <h2>你的行程</h2>
      <p>{{ result.itineraries?.length }} 个方案 · 点击查看详情</p>
    </div>

    <div v-if="result.warnings?.length" class="warning-box">
      <div v-for="w in result.warnings" :key="w">⚠ {{ w }}</div>
    </div>

    <div v-if="!result.itineraries?.length" style="color: var(--text-secondary); font-size:14px">
      暂无行程方案，请检查警告信息。
    </div>

    <div
      v-for="itin in result.itineraries"
      :key="itin.option_id"
      class="itinerary-card"
    >
      <div class="itin-header">
        <div>
          <div class="itin-title">方案 {{ itin.option_id }}：{{ itin.summary }}</div>
          <div class="itin-flight">
            {{ itin.flights.outbound.depart_airport }} → {{ itin.flights.outbound.arrive_airport }}
            · {{ itin.flights.outbound.depart_time.slice(0, 10) }}
          </div>
        </div>
        <div class="itin-price">¥{{ itin.flights.total_price }}/人</div>
      </div>

      <div class="day-list">
        <div v-for="day in itin.days" :key="day.day" class="day-row">
          <div class="day-num">Day {{ day.day }}</div>
          <div>
            <div class="day-pois">
              <span v-for="poi in day.pois" :key="poi.poi_id" class="poi-chip">
                {{ poi.name }}
              </span>
            </div>
            <div v-if="day.transport_note" class="day-note">{{ day.transport_note }}</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
defineProps({ result: Object })
</script>
```

- [ ] **Step 2: Rewrite App.vue**

Replace the entire content of `frontend/src/App.vue`:

```vue
<template>
  <div id="app">
    <header class="topbar">
      <span class="topbar-brand">✈ TRAVEL AI</span>
      <div class="stepper">
        <div class="step-dot" :class="stepClass(1)"></div>
        <div class="step-dot" :class="stepClass(2)"></div>
        <div class="step-dot" :class="stepClass(3)"></div>
        <div class="step-dot" :class="stepClass(4)"></div>
      </div>
    </header>

    <ChatView
      v-if="phase === 'idle' || phase === 'chat'"
      :messages="messages"
      :waiting="waiting"
      @send="onSend"
    />
    <ProgressView
      v-else-if="phase === 'progress'"
      :items="progressItems"
    />
    <PlanReview
      v-else-if="phase === 'review'"
      :data="reviewData"
      @reply="onReply"
    />
    <ResultView
      v-else-if="phase === 'done'"
      :result="finalResult"
    />

    <div v-if="phase === 'error'" style="padding:24px;color:var(--error)">
      {{ error }}
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useSSE } from './composables/useSSE.js'
import ChatView     from './components/ChatView.vue'
import ProgressView from './components/ProgressView.vue'
import PlanReview   from './components/PlanReview.vue'
import ResultView   from './components/ResultView.vue'

const {
  phase, messages, progressItems, reviewData, finalResult, error,
  startChat, sendReply,
} = useSSE()

const waiting = computed(() =>
  phase.value === 'chat' &&
  messages.value.length > 0 &&
  messages.value[messages.value.length - 1]?.role === 'user'
)

function onSend(text) {
  if (phase.value === 'idle') {
    startChat(text)
  } else {
    sendReply(text)
  }
}

function onReply(text) {
  sendReply(text)
}

function stepClass(n) {
  const map = { idle: 0, chat: 1, progress: 2, review: 3, done: 4, error: 0 }
  const current = map[phase.value] ?? 0
  if (n < current) return 'done'
  if (n === current) return 'active'
  return ''
}
</script>
```

- [ ] **Step 3: Verify the frontend builds without errors**

```bash
cd frontend
npm run build
```

Expected: build completes with no errors. Check for any unresolved import warnings.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/ResultView.vue frontend/src/App.vue
git commit -m "feat(frontend): add ResultView, wire App.vue with phase state machine"
```

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Task |
|-----------------|------|
| collect_intent ReAct node | Task 3 |
| lookup_airports tool | Task 2 |
| parse_input remove interrupt | Task 4 |
| human_review after plan_itinerary | Task 5 + 6 |
| API: `message: str` | Task 6 |
| SSE not WebSocket | Task 7 |
| Dark theme | Task 8 |
| Hero chat UI (首屏大输入框) | Task 9 |
| Progress view | Task 10 |
| Plan review (full plans shown) | Task 11 |
| Result view | Task 12 |
| App.vue phase machine | Task 12 |

**Placeholder scan:** No TBD/TODO found. All code blocks are complete.

**Type consistency:**
- `useSSE.js` exports: `phase, messages, progressItems, reviewData, finalResult, error, startChat, sendReply` — all consumed correctly in `App.vue`
- `ChatView` emits `send`, `App.vue` handles `@send="onSend"` ✓
- `PlanReview` emits `reply`, `App.vue` handles `@reply="onReply"` ✓
- `reviewData` in `useSSE.js` matches `PlanReview`'s `data.message` and `data.plans` ✓
- `human_review.py` interrupt payload has `type: "review_plan"`, `message`, `plans` — matches `useSSE.js` handler ✓
- `collect_intent.py` interrupt payload has `type: "collect_intent"`, `message` — matches `useSSE.js` handler ✓
