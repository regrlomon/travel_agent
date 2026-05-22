# 智能出行助手 — 架构改造设计文档

**日期：** 2026-05-22
**状态：** 已确认
**基于：** [2026-05-19-travel-agent-design.md](./2026-05-19-travel-agent-design.md)

---

## 1. 改造目标

在 MVP 基础上进行三项改造：

1. **HTTP 与 Agent 编排解耦**：将 FastAPI 进程与 LangGraph 执行分离，避免 Web 进程重启中断任务
2. **补充前端**：Vue 3 + 分阶段向导 UI，实现实时进度展示
3. **HITL 机制**：在两个关键节点引入人工确认，对话式交互（非表单填写）

---

## 2. 整体架构

```
Vue 3 前端（4 步向导）
    ↕ WebSocket /ws/{job_id}（双向实时）
FastAPI
    ↓ celery.send_task()          ↑ subscribe Redis Pub/Sub
    ↓                             ↑
Redis（broker + Checkpointer + Pub/Sub + cache）
    ↓ dequeue
Celery Worker
    ↓
LangGraph Graph（含 Redis Checkpointer）
    ├── ① parse_input → interrupt #1
    ├── ② discover_pois ‖ ③ scrape_flights（并行）
    ├── ④ human_review → interrupt #2
    ├── ⑤ plan_itinerary
    └── ⑥ compose_output
```

### HITL 通路（两个 interrupt）

```
interrupt() 触发
  → Worker 捕获 GraphInterrupt
  → publish Redis Pub/Sub: job:{job_id}
  → FastAPI WS 订阅者收到
  → 推送给前端（type: "hitl_request"）
  → 前端展示对话界面，用户自然语言回复
  → WS → FastAPI → resume_plan.delay(job_id, user_text)
  → Worker: LLM 解析 user_text → Command(resume=...) → graph 继续
```

---

## 3. LangGraph 图结构变化

### 新图结构

```
parse_input
  ↓ interrupt #1（确认参数）
discover_pois ‖ scrape_flights
  ↓ 汇合
human_review          ← 新增节点
  ↓ interrupt #2（选航班 + 说偏好）
plan_itinerary
  ↓
compose_output
```

### `agent/graph.py` 改动

```python
from langgraph.checkpoint.redis import RedisSaver
from agent.tools_container import build_tools

def build_graph():
    tools = build_tools()                            # 工具注入
    checkpointer = RedisSaver.from_conn_string(      # Redis Checkpointer
        os.getenv("REDIS_URL", "redis://localhost:6379/0")
    )

    g = StateGraph(TravelPlanState)
    g.add_node("parse_input",     parse_input.run)
    g.add_node("discover_pois",   discover_pois.run)
    g.add_node("scrape_flights",  scrape_flights.run)
    g.add_node("human_review",    human_review.run)   # 新增
    g.add_node("plan_itinerary",  plan_itinerary.run)
    g.add_node("compose_output",  compose_output.run)

    g.set_entry_point("parse_input")
    g.add_edge("parse_input",    "discover_pois")
    g.add_edge("parse_input",    "scrape_flights")
    g.add_edge("discover_pois",  "human_review")
    g.add_edge("scrape_flights", "human_review")
    g.add_edge("human_review",   "plan_itinerary")
    g.add_edge("plan_itinerary", "compose_output")
    g.add_edge("compose_output", END)

    graph = g.compile(checkpointer=checkpointer)
    return graph.with_config({"configurable": {"tools": tools}})
```

---

## 4. HITL 节点设计

### HITL #1 — `parse_input` 节点末尾

触发时机：parse_input 完成参数解析后。

```python
from langgraph.types import interrupt

async def run(state: TravelPlanState, config: RunnableConfig) -> dict:
    parsed = await _llm_parse_destination(state["destination"], state["origin"])
    amap_cities = await _resolve_amap_codes(parsed["city_names"], config)

    # 暂停，推给前端确认
    user_reply = interrupt({
        "type": "confirm_params",
        "message": f"已解析：出发 {parsed['origin_airports']}，目的地 {parsed['destination_airports']}，共 {state['duration_days']} 天。有需要修改吗？",
        "parsed": parsed,
    })

    # 用 LLM 解析用户的修改意图（"改成北京出发" → 更新 origin_airports）
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

`_apply_corrections(parsed, user_text, config)` — 单次 LLM 调用，将用户自然语言修改意图映射为 parsed dict 的字段更新。

### HITL #2 — `human_review` 新节点

触发时机：`discover_pois` 和 `scrape_flights` 都完成，汇合后。

职责：
1. 从 state 提取航班摘要和景点摘要
2. `interrupt()` 暂停，推给前端
3. LLM 解析用户回复，提取 `user_flight_choice`、`user_poi_prefs`
4. 写入 state

```python
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
        "user_flight_choice": choice.get("flight_choice"),
        "user_poi_prefs": choice.get("poi_prefs"),
    }
```

`plan_itinerary` 接收 `user_flight_choice` 和 `user_poi_prefs`，注入到 Phase 1 prompt 中影响方案生成。

---

## 5. 工具依赖注入

### `agent/tools_container.py`（新增）

> **前置工作**：现有 `tools/` 下的工具是裸函数（`async def search_pois(...)`）。需要将每个工具文件重构为持有配置（api_key 等）的 client 类，函数成为其方法。这是本次工具注入的基础改动。

```python
from tools.amap import AmapClient
from tools.tavily import TavilyClient
from tools.xhs_tool import XhsClient
from tools.flight_tool import FlightClient

def build_tools(overrides: dict | None = None) -> dict:
    defaults = {
        "amap":   AmapClient(api_key=os.getenv("AMAP_API_KEY", "")),
        "tavily": TavilyClient(api_key=os.getenv("TAVILY_API_KEY", "")),
        "xhs":    XhsClient(),
        "flight": FlightClient(),
    }
    return {**defaults, **(overrides or {})}
```

### 节点签名统一

所有节点改为接收 `config: RunnableConfig`：

```python
async def run(state: TravelPlanState, config: RunnableConfig) -> dict:
    tools = config["configurable"]["tools"]
    pois = await tools["amap"].search_pois(state["destination_amap_cities"])
    ...
```

**好处：** 测试时直接传 mock tools，无需 `mocker.patch`；将来升级某节点为 ReAct agent 只需修改该节点，不影响其他节点。

---

## 6. 进程解耦：Celery + Redis

### `worker/celery_app.py`

```python
from celery import Celery
import os

celery_app = Celery(
    "travel_agent",
    broker=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
    backend=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
)
celery_app.conf.task_serializer = "json"
celery_app.conf.result_expires = 7200
```

### `worker/tasks.py`

```python
from langgraph.types import Command
from langgraph.errors import GraphInterrupt
import asyncio, json, redis as _redis

r = _redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))

@celery_app.task(bind=True, max_retries=0)
def run_plan(self, job_id: str, request_data: dict):
    graph = build_graph()
    config = {"configurable": {"thread_id": job_id}}
    initial_state = {**request_data, "errors": [], "warnings": [], "job_id": job_id}

    try:
        result = asyncio.run(graph.ainvoke(initial_state, config=config))
        _publish(job_id, {"type": "done", "result": result})
    except GraphInterrupt as exc:
        _publish(job_id, {"type": "hitl_request", "data": exc.args[0]})
        # task 正常结束；等待 resume_plan 被触发

@celery_app.task(bind=True, max_retries=1)
def resume_plan(self, job_id: str, user_text: str):
    graph = build_graph()
    config = {"configurable": {"thread_id": job_id}}

    try:
        result = asyncio.run(
            graph.ainvoke(Command(resume={"text": user_text}), config=config)
        )
        _publish(job_id, {"type": "done", "result": result})
    except GraphInterrupt as exc:
        # 下一个 interrupt（HITL #2）
        _publish(job_id, {"type": "hitl_request", "data": exc.args[0]})

def _publish(job_id: str, payload: dict):
    r.publish(f"job:{job_id}", json.dumps(payload, ensure_ascii=False))

# 节点内进度上报统一改为 publish（替换原有的 r.set key 写法）：
# r.publish(f"job:{job_id}", json.dumps({"type": "progress", "node": "discover_pois", "message": "...", "pct": 40}))
```

### `api/main.py` 改动

```python
# 替换 asyncio.create_task(_run_plan(...))
from worker.tasks import run_plan

@app.post("/plans", status_code=202)
async def create_plan(req: PlanRequest):
    job_id = str(uuid.uuid4())
    run_plan.delay(job_id, req.model_dump())
    return {"job_id": job_id, "status": "pending"}
```

---

## 7. WebSocket + Redis Pub/Sub 桥接

### `api/websocket.py`（新增）

```python
@app.websocket("/ws/{job_id}")
async def ws_endpoint(websocket: WebSocket, job_id: str):
    await websocket.accept()
    pubsub = async_redis.pubsub()
    await pubsub.subscribe(f"job:{job_id}")

    async def forward():                          # Redis → 前端
        async for msg in pubsub.listen():
            if msg["type"] == "message":
                await websocket.send_text(msg["data"].decode())

    async def receive():                          # 前端 → Celery
        while True:
            data = await websocket.receive_text()
            payload = json.loads(data)
            if payload.get("type") == "hitl_response":
                resume_plan.delay(job_id, payload["text"])

    await asyncio.gather(forward(), receive())
```

### 消息协议

| 方向 | `type` | 内容 |
|------|--------|------|
| Server → Client | `hitl_request` | `{data: {type, message, parsed / flights_summary / poi_summary}}` |
| Server → Client | `progress` | `{node, message, pct}` |
| Server → Client | `done` | `{result: {...}}` |
| Client → Server | `hitl_response` | `{text: "用户自然语言回复"}` |

---

## 8. State 新增字段

```python
class TravelPlanState(TypedDict, total=False):
    # ... 原有字段不变 ...

    # 由 ④ human_review 写入
    user_flight_choice: str | None   # 用户选择的航班（pair_id 或自然语言描述）
    user_poi_prefs: str | None       # 用户景点偏好（自然语言，传给 plan_itinerary prompt）
```

---

## 9. 前端：Vue 3 分阶段向导

### 目录结构

```
frontend/
├── src/
│   ├── App.vue                   # step 状态机（1→2→3→4）
│   ├── composables/
│   │   └── useWebSocket.js       # WS 连接管理 + 消息分发
│   └── components/
│       ├── StepConfirm.vue       # Step 1：对话确认参数（HITL #1）
│       ├── StepProgress.vue      # Step 2：节点进度时间线
│       ├── StepReview.vue        # Step 3：航班卡片 + 景点列表（HITL #2）
│       └── StepResults.vue       # Step 4：完整行程方案展示
├── index.html
├── vite.config.js
└── package.json
```

### 步骤状态机

```
用户提交请求
  → WS 连接 /ws/{job_id}
  → 显示 Step 1（StepConfirm）
  → 收到 hitl_request(confirm_params) → 已在 Step 1，展示解析结果供确认
  → 用户确认 → 发送 hitl_response → 显示 Step 2（StepProgress）
  → 收到 progress 消息 → 更新 Step 2 时间线
  → 收到 hitl_request(review_flights_pois) → 切换到 Step 3（StepReview）
  → 用户选择 → 发送 hitl_response → 显示 Step 2（继续进度）
  → 收到 done → 切换到 Step 4（StepResults）
```

### `useWebSocket.js` 核心逻辑

```javascript
const step = ref(1)
const hitlData = ref(null)
const progress = ref([])
const result = ref(null)

ws.onmessage = (e) => {
  const msg = JSON.parse(e.data)
  if (msg.type === 'hitl_request') {
    hitlData.value = msg.data
    step.value = msg.data.type === 'confirm_params' ? 1 : 3
  } else if (msg.type === 'progress') {
    progress.value.push(msg)
    step.value = 2
  } else if (msg.type === 'done') {
    result.value = msg.result
    step.value = 4
  }
}

const sendReply = (text) => {
  ws.send(JSON.stringify({ type: 'hitl_response', text }))
  step.value = 2
}
```

---

## 10. 目录结构全貌

```
travel_agent/
├── agent/
│   ├── graph.py                  # 改：Checkpointer + human_review + 工具注入
│   ├── state.py                  # 改：加 user_flight_choice, user_poi_prefs
│   ├── tools_container.py        # 新：build_tools()
│   └── nodes/
│       ├── parse_input.py        # 改：interrupt #1 + _apply_corrections
│       ├── human_review.py       # 新：interrupt #2 + _parse_review_reply
│       ├── discover_pois.py      # 改：接收 config，用 tools["amap/tavily/xhs"]
│       ├── scrape_flights.py     # 改：接收 config，用 tools["flight"]
│       ├── plan_itinerary.py     # 改：接收 config + user_flight_choice/poi_prefs
│       └── compose_output.py     # 改：接收 config
├── worker/
│   ├── __init__.py
│   ├── celery_app.py             # 新：Celery 配置
│   └── tasks.py                  # 新：run_plan, resume_plan
├── api/
│   ├── main.py                   # 改：send_task 替换 create_task
│   ├── websocket.py              # 新：WS endpoint + pub/sub 桥接
│   └── __init__.py
├── frontend/                     # 新：Vue 3 应用
│   ├── src/
│   │   ├── App.vue
│   │   ├── composables/useWebSocket.js
│   │   └── components/
│   │       ├── StepConfirm.vue
│   │       ├── StepProgress.vue
│   │       ├── StepReview.vue
│   │       └── StepResults.vue
│   ├── index.html
│   ├── vite.config.js
│   └── package.json
├── docker-compose.yml            # 新：Redis + FastAPI + Celery worker
└── requirements.txt              # 改：加 celery[redis], langgraph-checkpoint-redis
```

---

## 11. 新增依赖

```
# requirements.txt 新增
celery[redis]>=5.3.0
langgraph-checkpoint-redis>=0.0.1

# frontend/package.json
vue@^3.4.0
vite@^5.0.0
@vitejs/plugin-vue@^5.0.0
```

---

## 12. 不在本次改造范围内

- 住宿比价
- 移动端适配
- 用户账号/登录
- `plan_itinerary` 之后再加 HITL（当前两个 interrupt 已满足需求）
- 多 Celery worker 水平扩容（当前单 worker 足够）
