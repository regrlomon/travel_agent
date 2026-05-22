# Travel Agent Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor the travel agent backend with Celery process isolation, Redis Streams-based WebSocket HITL, tool dependency injection, and a Vue 3 4-step frontend.

**Architecture:** Celery Worker runs LangGraph (with Redis Checkpointer); FastAPI holds WebSocket connections and bridges Redis Streams to the browser; two `interrupt()` points in the graph create conversational HITL checkpoints; all tool dependencies injected via `config["configurable"]["tools"]`.

**Tech Stack:** Python 3.11+, LangGraph 0.2+, LangGraph-checkpoint-redis 0.4+, Celery 5.3+, FastAPI, Redis Streams, Vue 3, Vite

---

## File Map

```
# New files
worker/__init__.py
worker/celery_app.py
worker/tasks.py
agent/tools_container.py
agent/nodes/human_review.py
api/websocket.py
frontend/package.json
frontend/vite.config.js
frontend/index.html
frontend/src/App.vue
frontend/src/composables/useWebSocket.js
frontend/src/components/StepConfirm.vue
frontend/src/components/StepProgress.vue
frontend/src/components/StepReview.vue
frontend/src/components/StepResults.vue
docker-compose.yml

# Modified files
requirements.txt
agent/graph.py
agent/state.py
agent/nodes/parse_input.py
agent/nodes/discover_pois.py
agent/nodes/scrape_flights.py
agent/nodes/plan_itinerary.py
agent/nodes/compose_output.py
api/main.py
tools/amap.py
tools/tavily.py
tools/xhs_tool/__init__.py
tools/flight_tool/tool.py
```

---

## Task 1: Update Dependencies

**Files:**
- Modify: `requirements.txt`
- Create: `worker/__init__.py`

- [ ] **Step 1: Update requirements.txt**

```
langgraph>=0.2.0
langchain-core>=0.3.0
litellm>=1.40.0
fastapi>=0.111.0
uvicorn>=0.30.0
redis>=5.0.0
celery[redis]>=5.3.0
langgraph-checkpoint-redis>=0.4.0
redisvl>=0.3.0
playwright>=1.44.0
tavily-python>=0.3.0
httpx>=0.27.0
python-dotenv>=1.0.0
pydantic>=2.0.0

pytest>=8.0.0
pytest-asyncio>=0.23.0
pytest-mock>=3.14.0
```

- [ ] **Step 2: Create worker/__init__.py**

```python
```

- [ ] **Step 3: Install**

```bash
pip install -r requirements.txt
```

Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add requirements.txt worker/__init__.py
git commit -m "chore: add celery, langgraph-checkpoint-redis, redisvl dependencies"
```

---

## Task 2: Refactor Tool Clients

Existing tools are bare async functions. Wrap each into a client class that holds config (api_key). Keep original functions as private helpers to avoid breaking call sites.

**Files:**
- Modify: `tools/amap.py`
- Modify: `tools/tavily.py`
- Modify: `tools/xhs_tool/__init__.py`
- Modify: `tools/flight_tool/tool.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_tools/test_clients.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

def test_amap_client_has_required_methods():
    from tools.amap import AmapClient
    client = AmapClient(api_key="fake")
    assert hasattr(client, "get_district_codes")
    assert hasattr(client, "search_pois")
    assert hasattr(client, "get_driving_time")
    assert hasattr(client, "check_transit_reachable")

def test_tavily_client_has_required_methods():
    from tools.tavily import TavilyClient
    client = TavilyClient(api_key="fake")
    assert hasattr(client, "search_travel_articles")

def test_xhs_client_has_required_methods():
    from tools.xhs_tool import XhsClient
    client = XhsClient()
    assert hasattr(client, "scrape_notes")

def test_flight_client_has_required_methods():
    from tools.flight_tool.tool import FlightClient
    client = FlightClient()
    assert hasattr(client, "search_flights")
    assert hasattr(client, "city_codes")
```

- [ ] **Step 2: Run to confirm fail**

```bash
pytest tests/test_tools/test_clients.py -v
```

Expected: `ImportError` or `AttributeError`.

- [ ] **Step 3: Add AmapClient to tools/amap.py**

Append at the bottom of the existing file (keep all existing functions):

```python
class AmapClient:
    def __init__(self, api_key: str):
        self.api_key = api_key

    async def get_district_codes(self, city_names: list[str]) -> dict[str, str]:
        return await get_district_codes(city_names, api_key=self.api_key)

    async def search_pois(self, city_codes: list[str], keywords: str = "景点") -> list[dict]:
        return await search_pois(city_codes, keywords, api_key=self.api_key)

    async def get_driving_time(self, origin: tuple, dest: tuple) -> "int | None":
        return await get_driving_time(origin, dest, api_key=self.api_key)

    async def check_transit_reachable(self, origin: tuple, dest: tuple, city_code: str, max_minutes: int = 120) -> bool:
        return await check_transit_reachable(origin, dest, city_code, api_key=self.api_key, max_minutes=max_minutes)
```

- [ ] **Step 4: Add TavilyClient to tools/tavily.py**

Append at the bottom:

```python
class TavilyClient:
    def __init__(self, api_key: str):
        self.api_key = api_key

    async def search_travel_articles(self, keywords: list[str]) -> list[dict]:
        return await search_travel_articles(keywords, api_key=self.api_key)
```

- [ ] **Step 5: Add XhsClient to tools/xhs_tool/__init__.py**

```python
from tools.xhs_tool._core import scrape_xhs_notes


class XhsClient:
    async def scrape_notes(self, keywords: list[str], max_notes_per_keyword: int = 10) -> list[dict]:
        return await scrape_xhs_notes(keywords, max_notes_per_keyword=max_notes_per_keyword)
```

- [ ] **Step 6: Add FlightClient to tools/flight_tool/tool.py**

Append at the bottom:

```python
class FlightClient:
    @property
    def city_codes(self) -> dict[str, str]:
        return CITY_CODES

    async def search_flights(self, origin_city: str, dest_city: str, date_str: str) -> dict:
        return await run_async(origin_city, dest_city, date_str)
```

- [ ] **Step 7: Run tests**

```bash
pytest tests/test_tools/test_clients.py -v
```

Expected: 4 PASSED.

- [ ] **Step 8: Commit**

```bash
git add tools/amap.py tools/tavily.py tools/xhs_tool/__init__.py tools/flight_tool/tool.py tests/test_tools/test_clients.py
git commit -m "feat: add client classes to tool modules for dependency injection"
```

---

## Task 3: tools_container.py

**Files:**
- Create: `agent/tools_container.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_tools/test_clients.py  (append)

def test_build_tools_returns_all_keys():
    from agent.tools_container import build_tools
    tools = build_tools(overrides={
        "amap": "mock_amap",
        "tavily": "mock_tavily",
        "xhs": "mock_xhs",
        "flight": "mock_flight",
    })
    assert set(tools.keys()) == {"amap", "tavily", "xhs", "flight"}

def test_build_tools_override_replaces_default():
    from agent.tools_container import build_tools
    mock = object()
    tools = build_tools(overrides={"amap": mock})
    assert tools["amap"] is mock
```

- [ ] **Step 2: Run to confirm fail**

```bash
pytest tests/test_tools/test_clients.py::test_build_tools_returns_all_keys -v
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Create agent/tools_container.py**

```python
import os
from tools.amap import AmapClient
from tools.tavily import TavilyClient
from tools.xhs_tool import XhsClient
from tools.flight_tool.tool import FlightClient


def build_tools(overrides: dict | None = None) -> dict:
    defaults = {
        "amap":   AmapClient(api_key=os.getenv("AMAP_API_KEY", "")),
        "tavily": TavilyClient(api_key=os.getenv("TAVILY_API_KEY", "")),
        "xhs":    XhsClient(),
        "flight": FlightClient(),
    }
    return {**defaults, **(overrides or {})}
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_tools/test_clients.py -v
```

Expected: 6 PASSED.

- [ ] **Step 5: Commit**

```bash
git add agent/tools_container.py tests/test_tools/test_clients.py
git commit -m "feat: tools_container build_tools() for dependency injection"
```

---

## Task 4: State — Add HITL Fields

**Files:**
- Modify: `agent/state.py`

- [ ] **Step 1: Add fields to TravelPlanState**

In `agent/state.py`, add two fields at the end of the TypedDict:

```python
    # Written by human_review (HITL #2)
    user_flight_choice: str | None   # pair_id or natural-language description from user
    user_poi_prefs: str | None       # natural-language prefs injected into plan_itinerary prompt
```

- [ ] **Step 2: Verify existing state tests still pass**

```bash
pytest tests/ -v -k "state or model"
```

Expected: all pass.

- [ ] **Step 3: Commit**

```bash
git add agent/state.py
git commit -m "feat: add user_flight_choice and user_poi_prefs to TravelPlanState"
```

---

## Task 5: Refactor agent/graph.py

Replace `build_graph()` (which held the checkpointer at module level) with `build_compiled_graph(checkpointer)` that receives a checkpointer from the caller. Add `human_review` node.

**Files:**
- Modify: `agent/graph.py`
- Modify: `tests/test_graph.py`

- [ ] **Step 1: Update test_graph.py**

```python
# tests/test_graph.py
import pytest
from unittest.mock import AsyncMock, patch
from langgraph.checkpoint.memory import MemorySaver


def test_graph_builds_without_error():
    from agent.graph import build_compiled_graph
    graph = build_compiled_graph(MemorySaver())
    assert graph is not None


def test_graph_has_human_review_node():
    from agent.graph import build_compiled_graph
    graph = build_compiled_graph(MemorySaver())
    assert "human_review" in graph.get_graph().nodes


@pytest.mark.asyncio
async def test_graph_runs_with_mocked_nodes(mocker):
    mocker.patch("agent.nodes.parse_input.run", new_callable=AsyncMock, return_value={
        "destination_region": "甘孜州", "destination_amap_cities": ["513300"],
        "destination_airports": ["CTU"], "origin_airports": ["PVG"],
        "depart_dates": [], "search_keywords": ["川西"],
    })
    mocker.patch("agent.nodes.discover_pois.run", new_callable=AsyncMock, return_value={
        "pois": [], "travel_time_matrix": {}
    })
    mocker.patch("agent.nodes.scrape_flights.run", new_callable=AsyncMock, return_value={
        "flight_pairs": [], "selected_dates": [], "warnings": []
    })
    mocker.patch("agent.nodes.human_review.run", new_callable=AsyncMock, return_value={
        "user_flight_choice": None, "user_poi_prefs": None
    })
    mocker.patch("agent.nodes.plan_itinerary.run", new_callable=AsyncMock, return_value={
        "itineraries": []
    })
    mocker.patch("agent.nodes.compose_output.run", return_value={
        "status": "ok", "itineraries": [], "flights_comparison": [], "warnings": [], "errors": []
    })

    from agent.graph import build_compiled_graph
    from langgraph.checkpoint.memory import MemorySaver
    graph = build_compiled_graph(MemorySaver())
    result = await graph.ainvoke(
        {"destination": "川西", "origin": "苏州", "duration_days": 7,
         "travelers": 2, "transport_mode": "self_drive", "difficulty_level": "medium",
         "interests": ["徒步"], "depart_date": None, "errors": [], "warnings": [], "job_id": "test"},
        config={"configurable": {"thread_id": "test", "tools": {}}},
    )
    assert result is not None
```

- [ ] **Step 2: Run to confirm fail**

```bash
pytest tests/test_graph.py -v
```

Expected: `ImportError` (no `build_compiled_graph`).

- [ ] **Step 3: Rewrite agent/graph.py**

```python
from langgraph.graph import StateGraph, END
from agent.state import TravelPlanState
import agent.nodes.parse_input   as parse_input
import agent.nodes.discover_pois as discover_pois
import agent.nodes.scrape_flights as scrape_flights
import agent.nodes.human_review  as human_review
import agent.nodes.plan_itinerary as plan_itinerary
import agent.nodes.compose_output as compose_output


def build_compiled_graph(checkpointer):
    """Build and compile the LangGraph. checkpointer lifecycle is owned by the caller."""
    g = StateGraph(TravelPlanState)
    g.add_node("parse_input",    parse_input.run)
    g.add_node("discover_pois",  discover_pois.run)
    g.add_node("scrape_flights", scrape_flights.run)
    g.add_node("human_review",   human_review.run)
    g.add_node("plan_itinerary", plan_itinerary.run)
    g.add_node("compose_output", compose_output.run)

    g.set_entry_point("parse_input")
    g.add_edge("parse_input",    "discover_pois")
    g.add_edge("parse_input",    "scrape_flights")
    g.add_edge("discover_pois",  "human_review")
    g.add_edge("scrape_flights", "human_review")
    g.add_edge("human_review",   "plan_itinerary")
    g.add_edge("plan_itinerary", "compose_output")
    g.add_edge("compose_output", END)

    return g.compile(checkpointer=checkpointer)
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_graph.py -v
```

Expected: 3 PASSED.

- [ ] **Step 5: Commit**

```bash
git add agent/graph.py tests/test_graph.py
git commit -m "feat: refactor graph to build_compiled_graph(checkpointer), add human_review node"
```

---

## Task 6: Update parse_input — HITL #1

Add `interrupt()` after parsing, accept `config: RunnableConfig`, use `tools["amap"]`.

**Files:**
- Modify: `agent/nodes/parse_input.py`
- Modify: `tests/test_nodes/test_parse_input.py`

- [ ] **Step 1: Write new failing tests**

```python
# tests/test_nodes/test_parse_input.py  (replace existing)
import pytest
from datetime import date
from unittest.mock import AsyncMock, MagicMock
from langchain_core.runnables import RunnableConfig


def _make_config(mock_amap=None):
    amap = mock_amap or MagicMock()
    return RunnableConfig(configurable={"thread_id": "t1", "tools": {"amap": amap}})


def _base_state():
    return {
        "destination": "川西", "origin": "苏州", "duration_days": 7,
        "travelers": 2, "transport_mode": "self_drive",
        "difficulty_level": "medium", "interests": ["徒步"],
        "depart_date": None, "errors": [], "warnings": [], "job_id": "test",
    }


@pytest.mark.asyncio
async def test_parse_input_calls_interrupt(mocker):
    mocker.patch("agent.nodes.parse_input._llm_parse_destination", new_callable=AsyncMock, return_value={
        "region": "甘孜州", "city_names": ["甘孜藏族自治州"],
        "destination_airports": ["CTU"], "origin_airports": ["PVG"],
        "search_keywords": ["川西 攻略"],
    })
    mock_amap = MagicMock()
    mock_amap.get_district_codes = AsyncMock(return_value={"甘孜藏族自治州": "513300"})
    mock_interrupt = mocker.patch("agent.nodes.parse_input.interrupt", return_value={"text": ""})

    from agent.nodes.parse_input import run
    await run(_base_state(), _make_config(mock_amap))
    mock_interrupt.assert_called_once()
    call_data = mock_interrupt.call_args[0][0]
    assert call_data["type"] == "confirm_params"


@pytest.mark.asyncio
async def test_parse_input_applies_corrections_when_user_replies(mocker):
    mocker.patch("agent.nodes.parse_input._llm_parse_destination", new_callable=AsyncMock, return_value={
        "region": "甘孜州", "city_names": ["甘孜藏族自治州"],
        "destination_airports": ["CTU"], "origin_airports": ["PVG"],
        "search_keywords": ["川西"],
    })
    mock_amap = MagicMock()
    mock_amap.get_district_codes = AsyncMock(return_value={"甘孜藏族自治州": "513300"})
    mocker.patch("agent.nodes.parse_input.interrupt", return_value={"text": "改成北京出发"})
    mock_correct = mocker.patch("agent.nodes.parse_input._apply_corrections", new_callable=AsyncMock,
        return_value={
            "region": "甘孜州", "city_names": ["甘孜藏族自治州"],
            "destination_airports": ["CTU"], "origin_airports": ["PEK", "PKX"],
            "search_keywords": ["川西"],
        })

    from agent.nodes.parse_input import run
    result = await run(_base_state(), _make_config(mock_amap))
    mock_correct.assert_called_once()
    assert "PEK" in result["origin_airports"]


@pytest.mark.asyncio
async def test_parse_input_single_date(mocker):
    mocker.patch("agent.nodes.parse_input._llm_parse_destination", new_callable=AsyncMock, return_value={
        "region": "甘孜州", "city_names": ["甘孜藏族自治州"],
        "destination_airports": ["CTU"], "origin_airports": ["PVG"],
        "search_keywords": ["川西"],
    })
    mock_amap = MagicMock()
    mock_amap.get_district_codes = AsyncMock(return_value={"甘孜藏族自治州": "513300"})
    mocker.patch("agent.nodes.parse_input.interrupt", return_value={"text": ""})

    state = {**_base_state(), "depart_date": "2026-07-01"}
    from agent.nodes.parse_input import run
    result = await run(state, _make_config(mock_amap))
    assert result["depart_dates"] == [date(2026, 7, 1)]
```

- [ ] **Step 2: Run to confirm fail**

```bash
pytest tests/test_nodes/test_parse_input.py -v
```

Expected: failures (no `interrupt` import in parse_input yet).

- [ ] **Step 3: Rewrite agent/nodes/parse_input.py**

```python
import json, os
from datetime import date, timedelta
import litellm
from langchain_core.runnables import RunnableConfig
from langgraph.types import interrupt
from agent.state import TravelPlanState


async def _llm_parse_destination(destination: str, origin: str) -> dict:
    prompt = f"""You are a Chinese travel expert. Given destination "{destination}" departing from "{origin}":
Return JSON with:
- region: human-readable string e.g. "甘孜州+阿坝州"
- city_names: list of Chinese admin district names e.g. ["甘孜藏族自治州"]
- destination_airports: IATA codes e.g. ["CTU","DCY"]
- origin_airports: IATA codes near "{origin}" e.g. ["PVG","SHA","NKG"]
- search_keywords: 3-5 Chinese queries e.g. ["川西 攻略"]
Return only valid JSON, no markdown."""
    resp = await litellm.acompletion(
        model=os.getenv("LLM_MODEL", "deepseek/deepseek-chat"),
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
    )
    return json.loads(resp.choices[0].message.content)


async def _apply_corrections(parsed: dict, user_text: str, config: RunnableConfig) -> dict:
    """Single LLM call to apply user's natural-language corrections to parsed params."""
    prompt = f"""Current parsed travel params:
{json.dumps(parsed, ensure_ascii=False)}

User correction: "{user_text}"

Apply the correction and return the updated JSON with the same keys. Only change what the user asked.
Return only valid JSON, no markdown."""
    resp = await litellm.acompletion(
        model=os.getenv("LLM_MODEL", "deepseek/deepseek-chat"),
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
    )
    return json.loads(resp.choices[0].message.content)


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

    user_reply = interrupt({
        "type": "confirm_params",
        "message": (
            f"已解析：出发 {parsed['origin_airports']}，"
            f"目的地 {parsed['destination_airports']}，共 {state['duration_days']} 天。"
            "有需要修改吗？"
        ),
        "parsed": parsed,
    })

    if user_reply.get("text"):
        parsed = await _apply_corrections(parsed, user_reply["text"], config)

    return {
        "destination_region": parsed["region"],
        "destination_amap_cities": amap_cities,
        "destination_airports": parsed["destination_airports"],
        "origin_airports": parsed["origin_airports"],
        "depart_dates": _expand_dates(state.get("depart_date")),
        "search_keywords": parsed["search_keywords"],
    }
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_nodes/test_parse_input.py -v
```

Expected: 3 PASSED.

- [ ] **Step 5: Commit**

```bash
git add agent/nodes/parse_input.py tests/test_nodes/test_parse_input.py
git commit -m "feat: parse_input HITL #1 — interrupt() after parsing, accept config/tools"
```

---

## Task 7: Create human_review Node — HITL #2

**Files:**
- Create: `agent/nodes/human_review.py`
- Create: `tests/test_nodes/test_human_review.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_nodes/test_human_review.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime
from langchain_core.runnables import RunnableConfig
from models import Flight, FlightPair, POI


def _make_config():
    return RunnableConfig(configurable={"thread_id": "t1", "tools": {}})


def _make_state():
    out = Flight("ctrip", "PVG", "DCY", 980, "MU1", datetime(2026, 7, 1))
    ret = Flight("ctrip", "DCY", "PVG", 760, "CA1", datetime(2026, 7, 8))
    pair = FlightPair("uuid-1", out, ret, 1740)
    poi = POI("p1", "稻城亚丁", (28.67, 100.3), "自然", [], "desc", 4.9, [], 3, 2, "high")
    return {
        "flight_pairs": [pair],
        "pois": [poi],
        "errors": [], "warnings": [], "job_id": "test",
    }


@pytest.mark.asyncio
async def test_human_review_calls_interrupt(mocker):
    mock_interrupt = mocker.patch("agent.nodes.human_review.interrupt",
                                  return_value={"text": "选第一个航班"})
    mocker.patch("agent.nodes.human_review._parse_review_reply", new_callable=AsyncMock,
                 return_value={"flight_choice": "uuid-1", "poi_prefs": ""})

    from agent.nodes.human_review import run
    await run(_make_state(), _make_config())
    mock_interrupt.assert_called_once()
    call_data = mock_interrupt.call_args[0][0]
    assert call_data["type"] == "review_flights_pois"
    assert "flights_summary" in call_data
    assert "poi_summary" in call_data


@pytest.mark.asyncio
async def test_human_review_writes_state(mocker):
    mocker.patch("agent.nodes.human_review.interrupt", return_value={"text": "选便宜的"})
    mocker.patch("agent.nodes.human_review._parse_review_reply", new_callable=AsyncMock,
                 return_value={"flight_choice": "uuid-1", "poi_prefs": "不要太累的"})

    from agent.nodes.human_review import run
    result = await run(_make_state(), _make_config())
    assert result["user_flight_choice"] == "uuid-1"
    assert result["user_poi_prefs"] == "不要太累的"


def test_format_flights_returns_list():
    from agent.nodes.human_review import _format_flights
    out = Flight("ctrip", "PVG", "DCY", 980, "MU1", datetime(2026, 7, 1))
    ret = Flight("ctrip", "DCY", "PVG", 760, "CA1", datetime(2026, 7, 8))
    pair = FlightPair("uuid-1", out, ret, 1740)
    result = _format_flights([pair])
    assert len(result) == 1
    assert result[0]["pair_id"] == "uuid-1"
    assert result[0]["total_price"] == 1740
```

- [ ] **Step 2: Run to confirm fail**

```bash
pytest tests/test_nodes/test_human_review.py -v
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Create agent/nodes/human_review.py**

```python
import json, os
import litellm
from langchain_core.runnables import RunnableConfig
from langgraph.types import interrupt
from agent.state import TravelPlanState
from models import FlightPair, POI


def _format_flights(pairs: list[FlightPair]) -> list[dict]:
    return [
        {
            "pair_id": fp.pair_id,
            "outbound": f"{fp.outbound.depart_airport}→{fp.outbound.arrive_airport} {fp.outbound.depart_time.strftime('%Y-%m-%d')} ¥{fp.outbound.price}",
            "return": f"{fp.return_flight.depart_airport}→{fp.return_flight.arrive_airport} ¥{fp.return_flight.price}",
            "total_price": fp.total_price,
            "platform": fp.outbound.platform,
        }
        for fp in pairs
    ]


def _format_pois(pois: list[POI]) -> list[dict]:
    return [
        {"name": p.name, "category": p.category, "confidence": p.confidence, "tags": p.tags}
        for p in pois[:15]
    ]


async def _parse_review_reply(user_text: str, flight_pairs: list[FlightPair], config: RunnableConfig) -> dict:
    """Extract flight_choice and poi_prefs from user's natural language reply."""
    pairs_info = json.dumps(_format_flights(flight_pairs), ensure_ascii=False)
    prompt = f"""User said: "{user_text}"
Available flights: {pairs_info}

Extract:
- flight_choice: the pair_id the user chose (or "" if unclear/confirmed all)
- poi_prefs: any POI preferences mentioned (or "" if none)

Return JSON: {{"flight_choice": "...", "poi_prefs": "..."}}
Return only valid JSON, no markdown."""
    resp = await litellm.acompletion(
        model=os.getenv("LLM_MODEL", "deepseek/deepseek-chat"),
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
    )
    return json.loads(resp.choices[0].message.content)


async def run(state: TravelPlanState, config: RunnableConfig) -> dict:
    flights_summary = _format_flights(state.get("flight_pairs", []))
    poi_summary = _format_pois(state.get("pois", []))

    user_reply = interrupt({
        "type": "review_flights_pois",
        "flights_summary": flights_summary,
        "poi_summary": poi_summary,
        "message": "已找到以上航班和景点，有偏好吗？（或直接说"确认，帮我安排"）",
    })

    choice = await _parse_review_reply(
        user_text=user_reply.get("text", ""),
        flight_pairs=state.get("flight_pairs", []),
        config=config,
    )

    return {
        "user_flight_choice": choice.get("flight_choice") or None,
        "user_poi_prefs": choice.get("poi_prefs") or None,
    }
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_nodes/test_human_review.py -v
```

Expected: 4 PASSED.

- [ ] **Step 5: Commit**

```bash
git add agent/nodes/human_review.py tests/test_nodes/test_human_review.py
git commit -m "feat: human_review node — HITL #2 interrupt for flight/poi selection"
```

---

## Task 8: Update Remaining Nodes — Config + Tools

Add `config: RunnableConfig` parameter to `discover_pois`, `scrape_flights`, `plan_itinerary`, `compose_output`. Replace direct `os.getenv` tool calls with `tools["..."]`.

**Files:**
- Modify: `agent/nodes/discover_pois.py`
- Modify: `agent/nodes/scrape_flights.py`
- Modify: `agent/nodes/plan_itinerary.py`
- Modify: `agent/nodes/compose_output.py`

- [ ] **Step 1: Update discover_pois.py**

Change the `run` signature and internal tool calls:

```python
# agent/nodes/discover_pois.py
# Replace the existing run() function and private helpers that call os.getenv:

async def _fetch_amap_pois(city_codes: list[str], tools: dict) -> list[dict]:
    return await tools["amap"].search_pois(city_codes, "景点")


async def _fetch_article_pois(keywords: list[str], tools: dict) -> list[dict]:
    results = []
    xhs = await tools["xhs"].scrape_notes(keywords)
    results.extend([{"platform": "xiaohongshu", "content": n["content"]} for n in xhs])
    tavily = await tools["tavily"].search_travel_articles(keywords)
    results.extend([{"platform": "mafengwo", "content": a["content"]} for a in tavily])
    return results


async def _build_travel_time_matrix(pois: list, tools: dict) -> dict:
    matrix = {}
    for i, a in enumerate(pois):
        for j, b in enumerate(pois):
            if i >= j:
                continue
            if _haversine_km(a.coords, b.coords) <= MAX_MATRIX_DISTANCE_KM:
                minutes = await tools["amap"].get_driving_time(a.coords, b.coords)
                if minutes is not None:
                    matrix[(a.poi_id, b.poi_id)] = minutes
                    matrix[(b.poi_id, a.poi_id)] = minutes
    return matrix


async def run(state: TravelPlanState, config: RunnableConfig) -> dict:
    from langchain_core.runnables import RunnableConfig  # noqa
    tools = config["configurable"]["tools"]
    city_codes = state["destination_amap_cities"]
    keywords = state.get("search_keywords", [])

    raw_amap = await _fetch_amap_pois(city_codes, tools)
    articles = await _fetch_article_pois(keywords, tools)
    scores = await _score_sources_batch(articles)

    # ... rest of existing logic unchanged, but pass tools to _build_travel_time_matrix ...
    pois = _dedup_pois(pois)
    pois.sort(key=lambda p: ({"high": 0, "medium": 1, "low": 2}[p.confidence], -p.amap_rating))
    pois = pois[:MAX_POIS]
    matrix = await _build_travel_time_matrix(pois, tools)
    return {"pois": pois, "travel_time_matrix": matrix}
```

- [ ] **Step 2: Update scrape_flights.py**

Change `run` signature and replace direct `_search_flights` / `CITY_CODES` references:

```python
# agent/nodes/scrape_flights.py
# Replace run() function:

async def _search_for_date(origin_city: str, dest_city: str, d: date, tools: dict) -> list:
    result = await tools["flight"].search_flights(origin_city, dest_city, d.isoformat())
    if result["status"] != "success":
        return []
    return [_raw_to_flight(f, d) for f in result["merged"]]


async def run(state: TravelPlanState, config: RunnableConfig) -> dict:
    from langchain_core.runnables import RunnableConfig  # noqa
    tools = config["configurable"]["tools"]
    city_codes = tools["flight"].city_codes
    airport_to_city = {v: k for k, v in city_codes.items()}

    origin_airports = state["origin_airports"]
    dest_airports = state["destination_airports"]
    depart_dates = state["depart_dates"]
    warnings = list(state.get("warnings", []))

    origin_cities = [c for c in (airport_to_city.get(a) for a in origin_airports) if c]
    dest_cities = [c for c in (airport_to_city.get(a) for a in dest_airports) if c]

    if not origin_cities:
        warnings.append(f"出发机场 {origin_airports} 不在支持列表，跳过机票查询")
        return {"flight_pairs": [], "selected_dates": depart_dates[:1], "warnings": warnings}
    if not dest_cities:
        warnings.append(f"目的地机场 {dest_airports} 不在支持列表，跳过机票查询")
        return {"flight_pairs": [], "selected_dates": depart_dates[:1], "warnings": warnings}

    origin_city = origin_cities[0]
    dest_city = dest_cities[0]
    candidate_dates = depart_dates[:3]

    outbound_results = await asyncio.gather(
        *[_search_for_date(origin_city, dest_city, d, tools) for d in candidate_dates],
        return_exceptions=True,
    )

    best_date = candidate_dates[0]
    best_price = float("inf")
    outbound_by_date = {}

    for d, result in zip(candidate_dates, outbound_results):
        if isinstance(result, Exception):
            warnings.append(f"{d} 去程查询失败: {result}")
            outbound_by_date[d] = []
            continue
        outbound_by_date[d] = result
        if result:
            min_p = min(f.price for f in result)
            if min_p < best_price:
                best_price = min_p
                best_date = d

    selected_dates = [best_date]
    outbound_flights = outbound_by_date.get(best_date, [])
    return_date = best_date + timedelta(days=state["duration_days"])
    return_flights = await _search_for_date(dest_city, origin_city, return_date, tools)

    best = {}
    for out in outbound_flights:
        for ret in return_flights:
            if ret.depart_airport != out.arrive_airport:
                continue
            key = (out.depart_airport, out.arrive_airport)
            total = out.price + ret.price
            existing = best.get(key)
            if existing is None or total < existing.total_price:
                best[key] = FlightPair(str(uuid.uuid4()), out, ret, total)

    flight_pairs = list(best.values())
    if not flight_pairs:
        warnings.append("机票数据获取失败，请自行查询各平台")

    return {"flight_pairs": flight_pairs, "selected_dates": selected_dates, "warnings": warnings}
```

- [ ] **Step 3: Update plan_itinerary.py**

Add `config` param and inject `user_flight_choice` / `user_poi_prefs` into Phase 1 prompt:

```python
# agent/nodes/plan_itinerary.py
# Change run() signature and add user prefs to _phase1_select prompt:

async def _phase1_select(pois, pairs, interests, duration_days,
                          user_flight_choice: str | None,
                          user_poi_prefs: str | None) -> list[dict]:
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

For EACH plan, assign a different FlightPair and select appropriate POIs per day.
If user specified a preferred flight, prioritise that pair_id.
Return a JSON array:
[{{"plan_id": "A", "pair_id": "<uuid>", "days": [{{"day": 1, "poi_ids": ["<id>"]}}]}}]
Return only valid JSON, no markdown."""

    resp = await litellm.acompletion(
        model=os.getenv("LLM_MODEL", "deepseek/deepseek-chat"),
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
    )
    return json.loads(resp.choices[0].message.content)


async def run(state: TravelPlanState, config: RunnableConfig) -> dict:
    from langchain_core.runnables import RunnableConfig  # noqa
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

    return {"itineraries": itineraries}
```

- [ ] **Step 4: Update compose_output.py**

Add `config` param (not used yet, but keeps signature consistent):

```python
# agent/nodes/compose_output.py
# Change: def run(state) -> def run(state, config=None)

def run(state: TravelPlanState, config=None) -> dict:
    # existing body unchanged
```

- [ ] **Step 5: Run existing node tests**

```bash
pytest tests/test_nodes/ -v
```

Expected: all pass (existing tests use mocks so tool injection doesn't break them).

- [ ] **Step 6: Commit**

```bash
git add agent/nodes/discover_pois.py agent/nodes/scrape_flights.py agent/nodes/plan_itinerary.py agent/nodes/compose_output.py
git commit -m "feat: update all nodes to accept config param and use injected tools"
```

---

## Task 9: Celery Worker

**Files:**
- Create: `worker/celery_app.py`
- Create: `worker/tasks.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_worker.py
import pytest
import json
from unittest.mock import MagicMock, patch, call
from datetime import datetime
from models import Flight, FlightPair


def _make_done_result():
    return {"status": "ok", "itineraries": [], "warnings": []}


def _make_interrupt_result():
    class _InterruptVal:
        value = {"type": "confirm_params", "message": "已解析...", "parsed": {}}
    return {"__interrupt__": [_InterruptVal()]}


def test_handle_result_emits_done(mocker):
    mock_xadd = mocker.patch("worker.tasks.r")
    from worker.tasks import _handle_result
    _handle_result("job1", _make_done_result())
    mock_xadd.xadd.assert_called_once()
    call_args = mock_xadd.xadd.call_args
    data = json.loads(call_args[0][1]["data"])
    assert data["type"] == "done"


def test_handle_result_emits_hitl_request(mocker):
    mock_r = mocker.patch("worker.tasks.r")
    from worker.tasks import _handle_result
    _handle_result("job1", _make_interrupt_result())
    mock_r.xadd.assert_called_once()
    call_args = mock_r.xadd.call_args
    data = json.loads(call_args[0][1]["data"])
    assert data["type"] == "hitl_request"
    assert "interrupt_id" in data


def test_resume_plan_idempotent(mocker):
    mock_r = mocker.patch("worker.tasks.r")
    mock_r.set.return_value = None   # lock already held → returns None (falsy)
    from worker.tasks import resume_plan
    resume_plan("job1", "user reply", "iid-1")
    mock_r.xadd.assert_not_called()
```

- [ ] **Step 2: Run to confirm fail**

```bash
pytest tests/test_worker.py -v
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Create worker/celery_app.py**

```python
import os
from celery import Celery

celery_app = Celery(
    "travel_agent",
    broker=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
    backend=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
)
celery_app.conf.task_serializer = "json"
celery_app.conf.result_expires = 7200
```

- [ ] **Step 4: Create worker/tasks.py**

```python
import asyncio, json, os, uuid
import redis as _redis
from langgraph.types import Command
from langgraph.checkpoint.redis import RedisSaver

from agent.graph import build_compiled_graph
from agent.tools_container import build_tools
from worker.celery_app import celery_app

r = _redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
STREAM_KEY = "job:{job_id}:stream"


def _build_config(job_id: str) -> dict:
    return {"configurable": {"thread_id": job_id, "tools": build_tools()}}


def _emit(job_id: str, payload: dict):
    key = STREAM_KEY.format(job_id=job_id)
    r.xadd(key, {"data": json.dumps(payload, ensure_ascii=False)})
    r.expire(key, 7200)


def _handle_result(job_id: str, result: dict):
    interrupts = result.get("__interrupt__")
    if interrupts:
        interrupt_id = str(uuid.uuid4())
        _emit(job_id, {
            "type": "hitl_request",
            "interrupt_id": interrupt_id,
            "data": interrupts[0].value,
        })
    else:
        _emit(job_id, {"type": "done", "result": result})


@celery_app.task(bind=True, max_retries=0)
def run_plan(self, job_id: str, request_data: dict):
    initial_state = {**request_data, "errors": [], "warnings": [], "job_id": job_id}
    with RedisSaver.from_conn_string(os.getenv("REDIS_URL", "redis://localhost:6379/0")) as checkpointer:
        checkpointer.setup()
        graph = build_compiled_graph(checkpointer)
        result = asyncio.run(graph.ainvoke(initial_state, config=_build_config(job_id)))
    _handle_result(job_id, result)


@celery_app.task(bind=True, max_retries=1)
def resume_plan(self, job_id: str, user_text: str, interrupt_id: str):
    lock_key = f"job:{job_id}:resume:{interrupt_id}"
    if not r.set(lock_key, "1", nx=True, ex=300):
        return
    with RedisSaver.from_conn_string(os.getenv("REDIS_URL", "redis://localhost:6379/0")) as checkpointer:
        checkpointer.setup()
        graph = build_compiled_graph(checkpointer)
        result = asyncio.run(
            graph.ainvoke(Command(resume={"text": user_text}), config=_build_config(job_id))
        )
    _handle_result(job_id, result)
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/test_worker.py -v
```

Expected: 3 PASSED.

- [ ] **Step 6: Commit**

```bash
git add worker/celery_app.py worker/tasks.py tests/test_worker.py
git commit -m "feat: Celery worker — run_plan, resume_plan, Redis Streams _emit"
```

---

## Task 10: Update FastAPI — api/main.py + api/websocket.py

**Files:**
- Modify: `api/main.py`
- Create: `api/websocket.py`
- Modify: `tests/test_api.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_api.py  (replace existing)
import pytest, json
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient


@pytest.fixture
def client(mock_redis):
    with patch("worker.tasks.r", mock_redis), \
         patch("api.main._redis", mock_redis):
        from api.main import app
        return TestClient(app)


def test_post_plans_queues_celery_task(client, mock_redis):
    with patch("api.main.run_plan") as mock_task:
        mock_task.delay = MagicMock()
        resp = client.post("/plans", json={
            "destination": "川西", "origin": "苏州", "duration_days": 7
        })
    assert resp.status_code == 202
    assert "job_id" in resp.json()
    mock_task.delay.assert_called_once()


def test_get_state_returns_last_stream_entry(client, mock_redis):
    payload = {"type": "hitl_request", "interrupt_id": "iid-1", "data": {}}
    mock_redis.xrevrange.return_value = [
        (b"1234-0", {b"data": json.dumps(payload).encode()})
    ]
    resp = client.get("/plans/test-job/state")
    assert resp.status_code == 200
    assert resp.json()["type"] == "hitl_request"


def test_get_state_404_when_no_stream(client, mock_redis):
    mock_redis.xrevrange.return_value = []
    resp = client.get("/plans/missing-job/state")
    assert resp.status_code == 404
```

- [ ] **Step 2: Run to confirm fail**

```bash
pytest tests/test_api.py -v
```

Expected: failures.

- [ ] **Step 3: Rewrite api/main.py**

```python
import json, os, uuid
from typing import Optional
import redis
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from worker.tasks import run_plan, STREAM_KEY

app = FastAPI(title="Smart Travel Agent API")
_redis = redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))


class PlanRequest(BaseModel):
    destination: str
    origin: str
    duration_days: int
    travelers: int = 1
    transport_mode: str = "mixed"
    difficulty_level: str = "medium"
    interests: list[str] = []
    depart_date: Optional[str] = None


@app.post("/plans", status_code=202)
async def create_plan(req: PlanRequest):
    job_id = str(uuid.uuid4())
    run_plan.delay(job_id, req.model_dump())
    return {"job_id": job_id, "status": "pending"}


@app.get("/plans/{job_id}/state")
async def get_plan_state(job_id: str):
    key = STREAM_KEY.format(job_id=job_id)
    entries = _redis.xrevrange(key, count=1)
    if entries:
        _, fields = entries[0]
        return json.loads(fields[b"data"])
    raise HTTPException(status_code=404, detail="No stream data for this job")
```

- [ ] **Step 4: Create api/websocket.py**

```python
import asyncio, json, os
import redis.asyncio as aioredis
from fastapi import WebSocket, WebSocketDisconnect
from worker.tasks import resume_plan, STREAM_KEY

async_r = aioredis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))


async def ws_endpoint(websocket: WebSocket, job_id: str):
    await websocket.accept()
    stream_key = STREAM_KEY.format(job_id=job_id)
    last_id = "0"

    async def forward():
        nonlocal last_id
        try:
            while True:
                entries = await async_r.xread({stream_key: last_id}, block=5000, count=10)
                for _, messages in (entries or []):
                    for msg_id, fields in messages:
                        last_id = msg_id
                        await websocket.send_text(fields[b"data"].decode())
        except WebSocketDisconnect:
            pass

    async def receive():
        try:
            while True:
                data = await websocket.receive_text()
                payload = json.loads(data)
                if payload.get("type") == "hitl_response":
                    resume_plan.delay(
                        job_id,
                        payload["text"],
                        payload["interrupt_id"],
                    )
        except WebSocketDisconnect:
            pass

    await asyncio.gather(forward(), receive())
```

- [ ] **Step 5: Register WebSocket route in api/main.py**

Add to the bottom of `api/main.py`:

```python
from api.websocket import ws_endpoint
app.add_api_websocket_route("/ws/{job_id}", ws_endpoint)
```

- [ ] **Step 6: Run tests**

```bash
pytest tests/test_api.py -v
```

Expected: 3 PASSED.

- [ ] **Step 7: Commit**

```bash
git add api/main.py api/websocket.py tests/test_api.py
git commit -m "feat: FastAPI uses Celery.delay, add /state endpoint, WebSocket Streams bridge"
```

---

## Task 11: Vue 3 Frontend Scaffold

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/vite.config.js`
- Create: `frontend/index.html`

- [ ] **Step 1: Create frontend/package.json**

```json
{
  "name": "travel-agent-frontend",
  "version": "0.1.0",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "vue": "^3.4.0"
  },
  "devDependencies": {
    "@vitejs/plugin-vue": "^5.0.0",
    "vite": "^5.0.0"
  }
}
```

- [ ] **Step 2: Create frontend/vite.config.js**

```javascript
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    proxy: {
      '/plans': 'http://localhost:8000',
      '/ws': { target: 'ws://localhost:8000', ws: true },
    },
  },
})
```

- [ ] **Step 3: Create frontend/index.html**

```html
<!DOCTYPE html>
<html lang="zh">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>智能出行助手</title>
</head>
<body>
  <div id="app"></div>
  <script type="module" src="/src/main.js"></script>
</body>
</html>
```

- [ ] **Step 4: Create frontend/src/main.js**

```javascript
import { createApp } from 'vue'
import App from './App.vue'

createApp(App).mount('#app')
```

- [ ] **Step 5: Install dependencies**

```bash
cd frontend && npm install
```

Expected: `node_modules/` created, no errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/
git commit -m "feat: Vue 3 frontend scaffold with Vite"
```

---

## Task 12: useWebSocket.js

**Files:**
- Create: `frontend/src/composables/useWebSocket.js`

- [ ] **Step 1: Create frontend/src/composables/useWebSocket.js**

```javascript
import { ref } from 'vue'

export function useWebSocket() {
  const step = ref(0)          // 0=idle, 1=confirm, 2=progress, 3=review, 4=results
  const hitlData = ref(null)   // full hitl_request message (includes interrupt_id)
  const progress = ref([])
  const result = ref(null)
  const error = ref(null)
  let ws = null
  let jobId = null

  function connect(id) {
    jobId = id
    ws = new WebSocket(`/ws/${jobId}`)

    ws.onmessage = (e) => {
      const msg = JSON.parse(e.data)
      if (msg.type === 'hitl_request') {
        hitlData.value = msg
        step.value = msg.data.type === 'confirm_params' ? 1 : 3
      } else if (msg.type === 'progress') {
        progress.value.push(msg)
        if (step.value !== 3) step.value = 2
      } else if (msg.type === 'done') {
        result.value = msg.result
        step.value = 4
      }
    }

    ws.onerror = () => { error.value = 'WebSocket error' }
    ws.onclose = () => {
      // auto-reconnect after 2s (server replays from last_id=0 so no messages lost)
      if (step.value < 4) setTimeout(() => connect(jobId), 2000)
    }
  }

  async function startPlan(requestData) {
    progress.value = []
    result.value = null
    error.value = null
    step.value = 1

    const resp = await fetch('/plans', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(requestData),
    })
    const { job_id } = await resp.json()
    connect(job_id)
    return job_id
  }

  function sendReply(text) {
    if (!ws || !hitlData.value) return
    ws.send(JSON.stringify({
      type: 'hitl_response',
      text,
      interrupt_id: hitlData.value.interrupt_id,
    }))
    step.value = 2
  }

  return { step, hitlData, progress, result, error, startPlan, sendReply }
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/composables/useWebSocket.js
git commit -m "feat: useWebSocket composable — WS connect, message dispatch, sendReply with interrupt_id"
```

---

## Task 13: Step Components + App.vue

**Files:**
- Create: `frontend/src/components/StepConfirm.vue`
- Create: `frontend/src/components/StepProgress.vue`
- Create: `frontend/src/components/StepReview.vue`
- Create: `frontend/src/components/StepResults.vue`
- Create: `frontend/src/App.vue`

- [ ] **Step 1: Create StepConfirm.vue**

```vue
<template>
  <div class="step-confirm">
    <h2>① 确认出行需求</h2>

    <!-- Initial input form (shown before first hitl_request) -->
    <form v-if="!hitlData" @submit.prevent="submit">
      <input v-model="form.destination" placeholder="目的地（如：川西）" required />
      <input v-model="form.origin" placeholder="出发城市（如：苏州）" required />
      <input v-model.number="form.duration_days" type="number" placeholder="天数" min="1" required />
      <button type="submit" :disabled="loading">{{ loading ? '解析中...' : '开始规划' }}</button>
    </form>

    <!-- HITL confirmation chat -->
    <div v-if="hitlData" class="chat">
      <div class="bot-msg">{{ hitlData.data.message }}</div>
      <form @submit.prevent="confirm">
        <input v-model="reply" placeholder="有需要修改的吗？没有请直接回车确认" />
        <button type="submit" :disabled="sent">{{ sent ? '确认中...' : '确认' }}</button>
      </form>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'

const props = defineProps({ hitlData: Object, loading: Boolean })
const emit = defineEmits(['submit', 'reply'])

const form = ref({ destination: '', origin: '', duration_days: 7 })
const reply = ref('')
const sent = ref(false)

function submit() { emit('submit', form.value) }
function confirm() {
  sent.value = true
  emit('reply', reply.value || '确认')
}
</script>
```

- [ ] **Step 2: Create StepProgress.vue**

```vue
<template>
  <div class="step-progress">
    <h2>② 规划进行中...</h2>
    <ul class="timeline">
      <li v-for="(p, i) in progress" :key="i" class="timeline-item">
        <span class="node">{{ p.node }}</span>
        <span class="msg">{{ p.message }}</span>
        <span class="pct" v-if="p.pct">{{ p.pct }}%</span>
      </li>
      <li class="timeline-item active">
        <span class="spinner">⟳</span> 处理中...
      </li>
    </ul>
  </div>
</template>

<script setup>
defineProps({ progress: Array })
</script>
```

- [ ] **Step 3: Create StepReview.vue**

```vue
<template>
  <div class="step-review">
    <h2>③ 确认航班 &amp; 景点</h2>

    <section v-if="flights.length">
      <h3>航班选项</h3>
      <div v-for="f in flights" :key="f.pair_id" class="flight-card">
        <strong>{{ f.outbound }}</strong> / 回程 {{ f.return }}
        <span class="price">合计 ¥{{ f.total_price }}</span>
      </div>
    </section>

    <section v-if="pois.length">
      <h3>推荐景点（TOP {{ pois.length }}）</h3>
      <span v-for="p in pois" :key="p.name" class="poi-tag">{{ p.name }}</span>
    </section>

    <form @submit.prevent="send">
      <input v-model="reply" placeholder="有偏好吗？或直接说"确认，帮我安排"" />
      <button type="submit" :disabled="sent">{{ sent ? '提交中...' : '提交' }}</button>
    </form>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'

const props = defineProps({ hitlData: Object })
const emit = defineEmits(['reply'])
const reply = ref('')
const sent = ref(false)

const flights = computed(() => props.hitlData?.data?.flights_summary || [])
const pois = computed(() => props.hitlData?.data?.poi_summary || [])

function send() {
  sent.value = true
  emit('reply', reply.value || '确认，帮我安排')
}
</script>
```

- [ ] **Step 4: Create StepResults.vue**

```vue
<template>
  <div class="step-results">
    <h2>④ 行程方案</h2>

    <div v-if="result.warnings?.length" class="warnings">
      <p v-for="w in result.warnings" :key="w">⚠ {{ w }}</p>
    </div>

    <div v-for="itin in result.itineraries" :key="itin.option_id" class="itinerary-card">
      <h3>方案 {{ itin.option_id }}：{{ itin.summary }}</h3>
      <p class="flight-info">
        {{ itin.flights.outbound.depart_airport }} → {{ itin.flights.outbound.arrive_airport }}
        ¥{{ itin.flights.total_price }}/人
      </p>
      <div v-for="day in itin.days" :key="day.day" class="day-plan">
        <strong>Day {{ day.day }}</strong>
        <span v-for="poi in day.pois" :key="poi.poi_id" class="poi-name">{{ poi.name }}</span>
        <span class="transport">{{ day.transport_note }}</span>
      </div>
    </div>

    <p v-if="!result.itineraries?.length" class="empty">暂无行程方案，请检查警告信息。</p>
  </div>
</template>

<script setup>
defineProps({ result: Object })
</script>
```

- [ ] **Step 5: Create App.vue**

```vue
<template>
  <div id="app">
    <header>
      <h1>✈ 智能出行助手</h1>
      <nav class="stepper">
        <span :class="{ active: step === 1 }">① 确认需求</span>
        <span :class="{ active: step === 2 }">② 规划中</span>
        <span :class="{ active: step === 3 }">③ 确认选择</span>
        <span :class="{ active: step === 4 }">④ 查看行程</span>
      </nav>
    </header>

    <main>
      <StepConfirm
        v-if="step <= 1"
        :hitlData="step === 1 ? hitlData : null"
        :loading="step === 1 && !hitlData"
        @submit="onSubmit"
        @reply="onReply"
      />
      <StepProgress v-if="step === 2" :progress="progress" />
      <StepReview   v-if="step === 3" :hitlData="hitlData" @reply="onReply" />
      <StepResults  v-if="step === 4" :result="result" />

      <p v-if="error" class="error">{{ error }}</p>
    </main>
  </div>
</template>

<script setup>
import { useWebSocket } from './composables/useWebSocket.js'
import StepConfirm  from './components/StepConfirm.vue'
import StepProgress from './components/StepProgress.vue'
import StepReview   from './components/StepReview.vue'
import StepResults  from './components/StepResults.vue'

const { step, hitlData, progress, result, error, startPlan, sendReply } = useWebSocket()

function onSubmit(formData) { startPlan(formData) }
function onReply(text)      { sendReply(text) }
</script>
```

- [ ] **Step 6: Verify frontend builds**

```bash
cd frontend && npm run build
```

Expected: `dist/` created, no errors.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/
git commit -m "feat: Vue 3 4-step stepper — StepConfirm, StepProgress, StepReview, StepResults, App.vue"
```

---

## Task 14: docker-compose.yml

**Files:**
- Create: `docker-compose.yml`

- [ ] **Step 1: Create docker-compose.yml**

```yaml
version: "3.9"

services:
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 5

  api:
    build: .
    command: uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
    ports:
      - "8000:8000"
    env_file: .env
    depends_on:
      redis:
        condition: service_healthy
    volumes:
      - .:/app

  worker:
    build: .
    command: celery -A worker.celery_app worker --loglevel=info --concurrency=2
    env_file: .env
    depends_on:
      redis:
        condition: service_healthy
    volumes:
      - .:/app
```

- [ ] **Step 2: Create Dockerfile if missing**

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && playwright install chromium --with-deps
COPY . .
```

- [ ] **Step 3: Commit**

```bash
git add docker-compose.yml Dockerfile
git commit -m "feat: docker-compose — Redis + FastAPI + Celery worker"
```

---

## Task 15: Full Test Suite + Smoke Test

- [ ] **Step 1: Run all Python tests**

```bash
pytest tests/ -v --tb=short
```

Expected: all pass.

- [ ] **Step 2: Smoke test (requires Redis running)**

```bash
docker compose up redis -d
uvicorn api.main:app --reload &
celery -A worker.celery_app worker --loglevel=info &
cd frontend && npm run dev &
```

Open browser at `http://localhost:5173`. Fill in destination "川西", origin "苏州", 7 days. Click "开始规划". Verify:
- Step 1 shows parsed params from LLM
- After confirming, Step 2 shows progress updates
- After discover/scrape complete, Step 3 shows flights and POIs
- After selecting, Step 2 resumes then Step 4 shows itineraries

- [ ] **Step 3: Final commit**

```bash
git add -A
git commit -m "feat: complete travel agent refactor — Celery, HITL x2, Redis Streams, Vue 3 frontend"
```

---

## Self-Review

**Spec coverage:**

| Spec requirement | Task |
|---|---|
| HTTP/Agent process decoupling via Celery | Task 9, 10 |
| Redis Streams (not Pub/Sub) for IPC | Task 9, 10 |
| WebSocket /ws/{job_id} endpoint | Task 10 |
| Two interrupt() HITL points | Tasks 6, 7 |
| interrupt() result in `__interrupt__` field (not exception) | Task 9 |
| tool injection via config["configurable"]["tools"] | Tasks 2, 3, 5, 8 |
| Tool client classes (AmapClient etc.) | Task 2 |
| RedisSaver as context manager | Task 9 |
| resume_plan idempotent via Redis NX lock | Task 9 |
| interrupt_id threaded through WS protocol | Tasks 10, 12 |
| Disconnect reconnect via xread last_id=0 | Task 12 |
| /plans/{job_id}/state reconnect endpoint | Task 10 |
| Vue 3 4-step stepper | Tasks 11–13 |
| docker-compose | Task 14 |
| user_flight_choice + user_poi_prefs in state | Task 4 |
| plan_itinerary uses user prefs in prompt | Task 8 |
