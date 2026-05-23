# LangSmith Observability Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace litellm with langchain-openai and wire LangSmith tracing so every job produces a full trace (nodes + LLM calls) searchable by job_id, with successful jobs auto-added to a dataset.

**Architecture:** Switch all `litellm.acompletion` calls to a shared `ChatOpenAI` factory (`agent/llm.py`). LangGraph's built-in LangSmith integration activates via env vars alone and auto-traces all graph nodes and LLM calls. A new `_auto_add_to_dataset` helper in `worker/tasks.py` writes completed jobs to a LangSmith dataset using the final state returned by `graph.ainvoke`.

**Tech Stack:** `langchain-openai`, `langsmith`, `langchain-core` (already present), LangGraph (already present)

---

## File Map

| File | Action |
|------|--------|
| `agent/llm.py` | **Create** — `get_llm(temperature)` factory returning `ChatOpenAI` |
| `agent/__init__.py` | **Modify** — remove litellm init block, keep `extract_json` only |
| `agent/nodes/collect_intent.py` | **Modify** — swap `litellm.acompletion` → `get_llm().ainvoke` |
| `agent/nodes/parse_input.py` | **Modify** — swap `litellm.acompletion` → `get_llm().ainvoke` |
| `agent/nodes/plan_itinerary.py` | **Modify** — swap `litellm.acompletion` → `get_llm().ainvoke` (two call sites) |
| `worker/tasks.py` | **Modify** — add metadata to `_build_config`, add `_auto_add_to_dataset`, call it from `_handle_result` |
| `requirements.txt` | **Modify** — drop `litellm`, add `langchain-openai`, `langsmith` |
| `.env.example` | **Modify** — add 4 LangSmith vars |
| `llm_config.yaml` | **Delete** |
| `tests/test_nodes/test_collect_intent.py` | **Modify** — update mocks from `litellm.acompletion` to `get_llm` |
| `tests/test_nodes/test_plan_itinerary.py` | **Modify** — update mocks from `litellm.acompletion` to `get_llm` |
| `tests/test_worker.py` | **Modify** — add tests for `_auto_add_to_dataset` and dataset call in `_handle_result` |

> `tests/test_nodes/test_parse_input.py` — **no change needed**: it already mocks `_llm_parse_destination` directly, not `litellm`.

---

## Task 1: Dependencies, config, delete llm_config.yaml

**Files:**
- Modify: `requirements.txt`
- Modify: `.env.example`
- Delete: `llm_config.yaml`

- [ ] **Step 1: Update requirements.txt**

Replace the `litellm` line and add two new dependencies:

```
# requirements.txt — replace litellm line with:
langchain-openai>=0.1.0
langsmith>=0.1.0
```

Full file after change:
```
langgraph>=0.2.0
langchain-core>=0.3.0
langchain-openai>=0.1.0
langsmith>=0.1.0
fastapi>=0.111.0
uvicorn>=0.30.0
redis>=5.0.0
celery[redis]>=5.3.0,<6.0.0
langgraph-checkpoint-redis>=0.4.0,<1.0.0
redisvl>=0.3.0
playwright>=1.44.0
tavily-python>=0.3.0
httpx>=0.27.0
python-dotenv>=1.0.0
pydantic>=2.0.0
requests
loguru
PyExecJS>=1.5.1

pytest>=8.0.0
pytest-asyncio>=0.23.0
pytest-mock>=3.14.0
```

- [ ] **Step 2: Add LangSmith env vars to .env.example**

Append to `.env.example`:
```
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=ls__your_key_here
LANGCHAIN_PROJECT=travel-agent
LANGCHAIN_TAGS=env:dev
```

- [ ] **Step 3: Delete llm_config.yaml**

```bash
git rm llm_config.yaml
```

- [ ] **Step 4: Commit**

```bash
git add requirements.txt .env.example
git commit -m "chore: replace litellm with langchain-openai+langsmith, add LangSmith env config"
```

---

## Task 2: Create agent/llm.py and clean agent/__init__.py

**Files:**
- Create: `agent/llm.py`
- Modify: `agent/__init__.py`
- Test: `tests/test_llm.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_llm.py`:
```python
import pytest


def test_get_llm_respects_temperature(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    monkeypatch.setenv("LLM_MODEL", "deepseek-chat")
    monkeypatch.setenv("LLM_API_BASE", "https://api.deepseek.com/v1")
    from agent.llm import get_llm
    llm = get_llm(temperature=0.7)
    assert llm.temperature == 0.7


def test_get_llm_default_temperature(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    from agent.llm import get_llm
    llm = get_llm()
    assert llm.temperature == 0.2
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_llm.py -v
```

Expected: `ModuleNotFoundError: No module named 'agent.llm'`

- [ ] **Step 3: Create agent/llm.py**

```python
import os
from langchain_openai import ChatOpenAI


def get_llm(temperature: float = 0.2) -> ChatOpenAI:
    return ChatOpenAI(
        model=os.getenv("LLM_MODEL", "deepseek-chat"),
        base_url=os.getenv("LLM_API_BASE", "https://api.deepseek.com/v1"),
        api_key=os.getenv("LLM_API_KEY"),
        temperature=temperature,
    )
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_llm.py -v
```

Expected: 2 PASSED

- [ ] **Step 5: Clean agent/__init__.py**

Remove the litellm initialization block. File should contain only `extract_json`:

```python
import re


def extract_json(text: str) -> str:
    """Strip markdown code fences from LLM output before JSON parsing."""
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    return match.group(1) if match else text.strip()
```

- [ ] **Step 6: Run full test suite to verify nothing broke**

```bash
pytest -x -q
```

Expected: all existing tests still pass (litellm is still imported in nodes but not yet changed)

- [ ] **Step 7: Commit**

```bash
git add agent/llm.py agent/__init__.py tests/test_llm.py
git commit -m "feat: add agent/llm.py ChatOpenAI factory, clean agent/__init__.py"
```

---

## Task 3: Migrate collect_intent.py

**Files:**
- Modify: `agent/nodes/collect_intent.py`
- Modify: `tests/test_nodes/test_collect_intent.py`

- [ ] **Step 1: Update the tests first (TDD)**

Replace `tests/test_nodes/test_collect_intent.py`:
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
    mock_msg = MagicMock()
    mock_msg.content = (
        '{"destination": "川西", "origin": "苏州", "duration_days": 7, '
        '"interests": ["自然风光"], "depart_date": null}'
    )
    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value=mock_msg)
    mocker.patch("agent.nodes.collect_intent.get_llm", return_value=mock_llm)

    result = await _llm_extract("川西7天，苏州出发，喜欢自然风光", {})
    assert result["destination"] == "川西"
    assert result["origin"] == "苏州"
    assert result["duration_days"] == 7
    assert "自然风光" in result["interests"]


@pytest.mark.asyncio
async def test_llm_build_reply_asks_missing(mocker):
    mock_msg = MagicMock()
    mock_msg.content = "从哪里出发？大概玩几天？"
    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value=mock_msg)
    mocker.patch("agent.nodes.collect_intent.get_llm", return_value=mock_llm)

    reply = await _llm_build_reply({"destination": "川西"})
    assert isinstance(reply, str)
    assert len(reply) > 5
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_nodes/test_collect_intent.py -v
```

Expected: `test_llm_extract_full_sentence` and `test_llm_build_reply_asks_missing` FAIL (still patching old `litellm.acompletion`)

- [ ] **Step 3: Migrate collect_intent.py**

Replace the full file:
```python
import json
import os
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.types import interrupt
from agent.state import TravelPlanState
from agent.llm import get_llm


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
    llm = get_llm(temperature=0.1)
    msg = await llm.ainvoke([HumanMessage(content=prompt)])
    extracted = json.loads(msg.content)
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
    llm = get_llm(temperature=0.7)
    msg = await llm.ainvoke([HumanMessage(content=prompt)])
    return msg.content.strip()


async def run(state: TravelPlanState, config: RunnableConfig) -> dict:
    tools = config["configurable"]["tools"]
    collected: dict = {}

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

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_nodes/test_collect_intent.py -v
```

Expected: 6 PASSED

- [ ] **Step 5: Commit**

```bash
git add agent/nodes/collect_intent.py tests/test_nodes/test_collect_intent.py
git commit -m "feat: migrate collect_intent to langchain-openai"
```

---

## Task 4: Migrate parse_input.py

**Files:**
- Modify: `agent/nodes/parse_input.py`

> No test changes needed — `tests/test_nodes/test_parse_input.py` already mocks `_llm_parse_destination` directly.

- [ ] **Step 1: Migrate parse_input.py**

Replace the full file:
```python
import json
import logging
from datetime import date, timedelta
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from agent.state import TravelPlanState
from agent import extract_json
from agent.llm import get_llm

logger = logging.getLogger(__name__)


async def _llm_parse_destination(destination: str, origin: str) -> dict:
    prompt = f"""You are a Chinese travel expert. Given destination "{destination}" departing from "{origin}":
Return JSON with:
- region: human-readable string e.g. "甘孜州+阿坝州"
- city_names: list of Chinese admin district names e.g. ["甘孜藏族自治州"]
- destination_airports: city-level IATA codes e.g. ["CTU","DCY"] — use city codes like CTU (成都), not airport codes like TFU
- origin_airports: city-level IATA codes near "{origin}" e.g. ["BJS","NKG"] — use city codes like BJS (北京), SHA (上海), NOT airport codes like PEK/PKX/PVG/SHA-airport
- search_keywords: 3-5 Chinese queries e.g. ["川西 攻略"]
Return only valid JSON, no markdown."""
    logger.info("[llm_input] _llm_parse_destination chars=%d\n%s", len(prompt), prompt)
    try:
        llm = get_llm(temperature=0.1)
        msg = await llm.ainvoke([HumanMessage(content=prompt)])
    except Exception:
        logger.exception("LLM call failed in _llm_parse_destination, destination=%r origin=%r", destination, origin)
        raise
    try:
        return json.loads(extract_json(msg.content))
    except json.JSONDecodeError:
        logger.error("JSON parse failed in _llm_parse_destination, raw=%r", msg.content)
        raise


def _expand_dates(depart_date: str | None) -> list[date]:
    if depart_date:
        return [date.fromisoformat(depart_date)]
    today = date.today()
    return [today + timedelta(days=i) for i in range(14)]


async def run(state: TravelPlanState, config: RunnableConfig) -> dict:
    tools = config["configurable"]["tools"]
    parsed = await _llm_parse_destination(state["destination"], state["origin"])

    code_map = await tools["amap"].get_district_codes(parsed["city_names"])
    amap_cities = list(code_map.values())

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

- [ ] **Step 2: Run parse_input tests to verify they still pass**

```bash
pytest tests/test_nodes/test_parse_input.py -v
```

Expected: 3 PASSED (tests mock `_llm_parse_destination` directly, unaffected)

- [ ] **Step 3: Commit**

```bash
git add agent/nodes/parse_input.py
git commit -m "feat: migrate parse_input to langchain-openai"
```

---

## Task 5: Migrate plan_itinerary.py

**Files:**
- Modify: `agent/nodes/plan_itinerary.py`
- Modify: `tests/test_nodes/test_plan_itinerary.py`

- [ ] **Step 1: Update the test first (TDD)**

Replace `tests/test_nodes/test_plan_itinerary.py`:
```python
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
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

    async def fake_ainvoke(messages):
        nonlocal call_count
        call_count += 1
        m = MagicMock()
        m.content = phase1_response if call_count == 1 else phase2_response
        return m

    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(side_effect=fake_ainvoke)
    mocker.patch("agent.nodes.plan_itinerary.get_llm", return_value=mock_llm)

    state = {
        "pois": [make_poi("p1", "稻城亚丁"), make_poi("p2", "四姑娘山")],
        "flight_pairs": [make_pair("uuid-1")],
        "travel_time_matrix": {"p1|p2": 30},
        "interests": ["徒步"],
        "duration_days": 7,
        "errors": [], "warnings": [], "job_id": "test",
    }
    result = await run(state)
    assert len(result["itineraries"]) >= 1
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_nodes/test_plan_itinerary.py::test_run_returns_itineraries -v
```

Expected: FAIL — `get_llm` not yet imported in module

- [ ] **Step 3: Migrate plan_itinerary.py**

Replace the full file:
```python
import json
import logging
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from agent.state import TravelPlanState
from agent import extract_json
from agent.llm import get_llm
from models import POI, FlightPair, DayPlan, ItineraryOption

logger = logging.getLogger(__name__)


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


async def _phase1_select(pois: list[POI], pairs: list[FlightPair], interests: list[str], duration_days: int,
                          user_flight_choice=None, user_poi_prefs=None) -> list[dict]:
    poi_table = _build_poi_table(pois)
    flight_table = _build_flight_table(pairs)

    user_context = ""
    if user_flight_choice:
        user_context += f"\nUser preferred flight: {user_flight_choice}"
    if user_poi_prefs:
        user_context += f"\nUser POI preferences: {user_poi_prefs}"

    prompt = f"""You are a travel planner. Given the POI list and flight options below, create 2-3 travel plans.

Interests: {', '.join(interests)}
Trip duration: {duration_days} days{user_context}

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

    try:
        llm = get_llm(temperature=0.3)
        msg = await llm.ainvoke([HumanMessage(content=prompt)])
    except Exception:
        logger.exception("LLM call failed in _phase1_select, pois=%d pairs=%d", len(pois), len(pairs))
        raise
    try:
        return json.loads(extract_json(msg.content))
    except json.JSONDecodeError:
        logger.error("JSON parse failed in _phase1_select, raw=%r", msg.content)
        raise


async def _phase2_generate(
    plan_skeleton: dict,
    poi_map: dict[str, POI],
    pair_map: dict[str, FlightPair],
    travel_time_matrix: dict[str, int],
) -> ItineraryOption:
    fp = pair_map[plan_skeleton["pair_id"]]
    selected_pois = {pid: poi_map[pid] for day in plan_skeleton["days"] for pid in day["poi_ids"] if pid in poi_map}

    poi_details = "\n".join(
        f"- {p.name} ({p.category}): {p.desc or 'no description'} | tags: {','.join(p.tags)}"
        for p in selected_pois.values()
    )
    time_notes = "\n".join(
        f"  {poi_map[a].name if a in poi_map else a} → {poi_map[b].name if b in poi_map else b}: {m} min drive"
        for key, m in travel_time_matrix.items()
        for a, b in [key.split("|", 1)]
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

    try:
        llm = get_llm(temperature=0.2)
        msg = await llm.ainvoke([HumanMessage(content=prompt)])
    except Exception:
        logger.exception("LLM call failed in _phase2_generate, plan_id=%r", plan_skeleton.get("plan_id"))
        raise
    try:
        raw = json.loads(msg.content)
    except json.JSONDecodeError:
        logger.error("JSON parse failed in _phase2_generate, raw=%r", msg.content)
        raise

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


async def run(state: TravelPlanState, config: RunnableConfig = None) -> dict:
    logger.info("[plan_itinerary] start, pois=%d pairs=%d", len(state.get("pois", [])), len(state.get("flight_pairs", [])))
    pois = state["pois"]
    pairs = state["flight_pairs"]
    matrix = state.get("travel_time_matrix", {})
    interests = state.get("interests", [])
    duration_days = state["duration_days"]
    user_flight_choice = state.get("user_flight_choice")
    user_poi_prefs = state.get("user_poi_prefs")

    poi_map = {p.poi_id: p for p in pois}
    pair_map = {fp.pair_id: fp for fp in pairs}

    plan_skeletons = await _phase1_select(
        pois, pairs, interests, duration_days, user_flight_choice, user_poi_prefs
    )

    itineraries = []
    for skeleton in plan_skeletons:
        if skeleton.get("pair_id") not in pair_map:
            continue
        option = await _phase2_generate(skeleton, poi_map, pair_map, matrix)
        itineraries.append(option)

    logger.info("[plan_itinerary] done, itineraries=%d", len(itineraries))
    return {"itineraries": itineraries}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_nodes/test_plan_itinerary.py -v
```

Expected: 4 PASSED

- [ ] **Step 5: Commit**

```bash
git add agent/nodes/plan_itinerary.py tests/test_nodes/test_plan_itinerary.py
git commit -m "feat: migrate plan_itinerary to langchain-openai"
```

---

## Task 6: Update worker/tasks.py — metadata + dataset

**Files:**
- Modify: `worker/tasks.py`
- Modify: `tests/test_worker.py`

- [ ] **Step 1: Write the new tests first (TDD)**

Replace `tests/test_worker.py`:
```python
import pytest
import json
from unittest.mock import MagicMock, patch
from datetime import datetime
from models import Flight, FlightPair


def _make_done_result():
    return {
        "status": "ok",
        "destination": "川西", "origin": "苏州",
        "duration_days": 7, "interests": ["徒步"],
        "itineraries": [], "warnings": [], "errors": [],
    }


def _make_done_result_with_errors():
    return {
        "status": "error",
        "destination": "川西", "origin": "苏州",
        "duration_days": 7, "interests": [],
        "itineraries": [], "warnings": [], "errors": ["LLM failed"],
    }


def _make_interrupt_result():
    class _InterruptVal:
        value = {"type": "confirm_params", "message": "已解析...", "parsed": {}}
    return {"__interrupt__": [_InterruptVal()]}


def test_handle_result_emits_done(mocker):
    mock_r = MagicMock()
    mocker.patch("worker.tasks.r", mock_r)
    mocker.patch("worker.tasks._auto_add_to_dataset")
    from worker.tasks import _handle_result
    _handle_result("job1", _make_done_result())
    mock_r.xadd.assert_called_once()
    data = json.loads(mock_r.xadd.call_args[0][1]["data"])
    assert data["type"] == "done"


def test_handle_result_emits_hitl_request(mocker):
    mock_r = MagicMock()
    mocker.patch("worker.tasks.r", mock_r)
    from worker.tasks import _handle_result
    _handle_result("job1", _make_interrupt_result())
    mock_r.xadd.assert_called_once()
    data = json.loads(mock_r.xadd.call_args[0][1]["data"])
    assert data["type"] == "hitl_request"
    assert "interrupt_id" in data


def test_handle_result_adds_to_dataset_on_success(mocker):
    mock_r = MagicMock()
    mocker.patch("worker.tasks.r", mock_r)
    mock_add = mocker.patch("worker.tasks._auto_add_to_dataset")
    from worker.tasks import _handle_result
    result = _make_done_result()
    _handle_result("job1", result)
    mock_add.assert_called_once_with("job1", result)


def test_handle_result_skips_dataset_on_error(mocker):
    mock_r = MagicMock()
    mocker.patch("worker.tasks.r", mock_r)
    mock_add = mocker.patch("worker.tasks._auto_add_to_dataset")
    from worker.tasks import _handle_result
    _handle_result("job1", _make_done_result_with_errors())
    mock_add.assert_not_called()


def test_auto_add_to_dataset_creates_example(mocker):
    mock_dataset = MagicMock()
    mock_dataset.id = "ds-123"
    mock_client = MagicMock()
    mock_client.read_dataset.return_value = mock_dataset
    mocker.patch("worker.tasks._ls_client", mock_client)

    from worker.tasks import _auto_add_to_dataset
    _auto_add_to_dataset("job1", {
        "destination": "川西", "origin": "苏州",
        "duration_days": 7, "interests": ["徒步"],
        "itineraries": [], "warnings": [], "errors": [],
    })
    mock_client.create_example.assert_called_once()
    call_kwargs = mock_client.create_example.call_args[1]
    assert call_kwargs["inputs"]["destination"] == "川西"
    assert call_kwargs["metadata"]["job_id"] == "job1"
    assert call_kwargs["dataset_id"] == "ds-123"


def test_auto_add_to_dataset_creates_dataset_if_missing(mocker):
    mock_new_dataset = MagicMock()
    mock_new_dataset.id = "ds-new"
    mock_client = MagicMock()
    mock_client.read_dataset.side_effect = Exception("not found")
    mock_client.create_dataset.return_value = mock_new_dataset
    mocker.patch("worker.tasks._ls_client", mock_client)

    from worker.tasks import _auto_add_to_dataset
    _auto_add_to_dataset("job1", {"destination": "川西"})
    mock_client.create_dataset.assert_called_once()
    mock_client.create_example.assert_called_once()


def test_auto_add_to_dataset_swallows_exception(mocker):
    mock_client = MagicMock()
    mock_client.read_dataset.side_effect = Exception("network error")
    mock_client.create_dataset.side_effect = Exception("network error")
    mocker.patch("worker.tasks._ls_client", mock_client)

    from worker.tasks import _auto_add_to_dataset
    _auto_add_to_dataset("job1", {"destination": "川西"})  # must not raise


def test_resume_plan_idempotent(mocker):
    mock_r = MagicMock()
    mock_r.set.return_value = None
    mocker.patch("worker.tasks.r", mock_r)
    from worker.tasks import resume_plan
    resume_plan("job1", "user reply", "iid-1")
    mock_r.xadd.assert_not_called()
```

- [ ] **Step 2: Run tests to verify new ones fail**

```bash
pytest tests/test_worker.py -v
```

Expected: `test_handle_result_adds_to_dataset_on_success`, `test_auto_add_to_dataset_*` FAIL

- [ ] **Step 3: Update worker/tasks.py**

Replace the full file:
```python
import asyncio, json, logging, os, uuid
import redis as _redis
from langsmith import Client as LangSmithClient

logger = logging.getLogger(__name__)
from langgraph.types import Command
from langgraph.checkpoint.redis.aio import AsyncRedisSaver

from agent.graph import build_compiled_graph
from agent.tools_container import build_tools
from worker.celery_app import celery_app

r = _redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
STREAM_KEY = "job:{job_id}:stream"
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
LANGSMITH_DATASET = "travel-agent-traces"
_ls_client = LangSmithClient()


def _build_config(job_id: str) -> dict:
    return {
        "configurable": {"thread_id": job_id, "tools": build_tools()},
        "metadata": {"job_id": job_id},
        "tags": [os.getenv("LANGCHAIN_TAGS", "env:dev")],
    }


def _emit(job_id: str, payload: dict):
    key = STREAM_KEY.format(job_id=job_id)
    r.xadd(key, {"data": json.dumps(payload, ensure_ascii=False)})
    r.expire(key, 7200)


def _auto_add_to_dataset(job_id: str, result: dict):
    try:
        try:
            dataset = _ls_client.read_dataset(dataset_name=LANGSMITH_DATASET)
        except Exception:
            dataset = _ls_client.create_dataset(LANGSMITH_DATASET)

        _ls_client.create_example(
            inputs={
                "destination":   result.get("destination"),
                "origin":        result.get("origin"),
                "duration_days": result.get("duration_days"),
                "interests":     result.get("interests", []),
            },
            outputs={
                "itineraries_count": len(result.get("itineraries", [])),
                "warnings":          result.get("warnings", []),
                "errors":            result.get("errors", []),
            },
            metadata={"job_id": job_id},
            dataset_id=dataset.id,
        )
    except Exception:
        logger.warning("[job=%s] LangSmith dataset write failed, skipping", job_id)


def _handle_result(job_id: str, result: dict):
    logger.info("[job=%s] LLM result: %s", job_id, json.dumps(result, ensure_ascii=False, default=str))
    interrupts = result.get("__interrupt__")
    if interrupts:
        interrupt_id = str(uuid.uuid4())
        _emit(job_id, {
            "type": "hitl_request",
            "interrupt_id": interrupt_id,
            "data": interrupts[0].value,
        })
    else:
        _emit(job_id, {
            "type": "done",
            "result": {
                "status": result.get("status"),
                "itineraries": result.get("itineraries", []),
                "flights_comparison": result.get("flights_comparison", []),
                "warnings": result.get("warnings", []),
                "errors": result.get("errors", []),
            },
        })
        if not result.get("errors"):
            _auto_add_to_dataset(job_id, result)


@celery_app.task(bind=True, max_retries=0)
def run_plan(self, job_id: str, initial_state: dict):
    async def _run():
        async with AsyncRedisSaver.from_conn_string(REDIS_URL) as checkpointer:
            await checkpointer.asetup()
            graph = build_compiled_graph(checkpointer)
            return await graph.ainvoke(initial_state, config=_build_config(job_id))

    _handle_result(job_id, asyncio.run(_run()))


@celery_app.task(bind=True, max_retries=1)
def resume_plan(self, job_id: str, user_text: str, interrupt_id: str):
    lock_key = f"job:{job_id}:resume:{interrupt_id}"
    if not r.set(lock_key, "1", nx=True, ex=300):
        return

    async def _run():
        async with AsyncRedisSaver.from_conn_string(REDIS_URL) as checkpointer:
            await checkpointer.asetup()
            graph = build_compiled_graph(checkpointer)
            return await graph.ainvoke(
                Command(resume={"text": user_text}), config=_build_config(job_id)
            )

    _handle_result(job_id, asyncio.run(_run()))
```

- [ ] **Step 4: Run tests to verify they all pass**

```bash
pytest tests/test_worker.py -v
```

Expected: 9 PASSED

- [ ] **Step 5: Commit**

```bash
git add worker/tasks.py tests/test_worker.py
git commit -m "feat: add LangSmith job_id metadata and auto dataset collection"
```

---

## Task 7: Final verification

- [ ] **Step 1: Run full test suite**

```bash
pytest -x -q
```

Expected: all tests pass, no failures

- [ ] **Step 2: Verify litellm is fully removed**

```bash
grep -r "litellm" agent/ worker/ --include="*.py"
```

Expected: no output

- [ ] **Step 3: Verify langsmith env vars are in .env.example**

```bash
grep "LANGCHAIN" .env.example
```

Expected: 4 lines — `LANGCHAIN_TRACING_V2`, `LANGCHAIN_API_KEY`, `LANGCHAIN_PROJECT`, `LANGCHAIN_TAGS`

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "chore: LangSmith integration complete — litellm fully removed"
```
