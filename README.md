# 智能出行助手 · Smart Travel Agent

> 一句话告诉它你想去哪，它替你查航班、扒攻略、排行程。

---

## 概览

智能出行助手是一个基于 **LangGraph** 编排的多节点 AI Agent 系统。用户通过自然语言描述旅行意图，系统自动完成意图采集 → 参数解析 → 并行信息聚合（多平台景点 + 实时机票）→ 方案生成 → 行程输出的全链路自动化，并在关键节点通过 **Human-in-the-Loop (HITL)** 机制让用户确认或调整，最终输出 2-3 套差异化行程方案。

---

## 系统架构

```
Vue 3 前端（4 步向导 UI）
       ↕  SSE / POST
   FastAPI（异步 API 网关）
       ↓  Celery 任务队列
   Celery Worker
       └─ LangGraph Graph（含 Redis Checkpointer）
              collect_intent  ──►  parse_input
                                        │
                              ┌─────────┴─────────┐
                         discover_pois       scrape_flights
                              └─────────┬─────────┘
                                   human_review  ←── HITL #2
                                        │
                                  plan_itinerary
                                        │
                                  compose_output
   Redis（Broker · Checkpointer · Streams · 状态缓存）
```

### 信息流

| 阶段 | 节点 | 说明 |
|------|------|------|
| 意图采集 | `collect_intent` | 对话式补全目的地、出发城市、天数等必填项，支持多轮追问 |
| 参数解析 | `parse_input` | 将自然语言映射到高德城市代码、IATA 机场码、出发日期区间 |
| POI 发现 | `discover_pois` | 并行拉取高德地图景点 + 小红书游记 + Tavily 旅游文章，LLM 批量评分去重，建立驾车时间矩阵 |
| 机票抓取 | `scrape_flights` | Playwright 无头浏览器抓取往返航班，返回按价格排序的航班对 |
| 用户审核 | `human_review` | HITL 暂停：向用户展示航班摘要与景点列表，接收偏好 |
| 行程规划 | `plan_itinerary` | 两阶段 LLM 生成：先骨架分配，再逐方案补全交通时间与详细描述 |
| 结果输出 | `compose_output` | 格式化 Markdown 行程，注入航班信息 |

---

## 核心特性

- **对话式意图采集**：首次输入可以是任意自然语言；缺什么问什么，问完为止
- **多源 POI 融合**：高德官方数据 + 小红书真实游记 + Tavily 旅游攻略三路并行，按可信度评分合并，去除广告内容
- **驾车时间矩阵**：调用高德批量路径 API，O(n) 并发请求覆盖所有 ≤50 km POI 对，精准估算景区间驾车耗时
- **实时航班比价**：基于 Playwright 动态抓取，支持 7 天日历比价，无需第三方机票 API
- **两处 HITL 确认**：参数确认（可纠正城市 / 机场识别偏差）+ 航班景点审核（可选偏好影响最终方案）
- **幂等恢复**：Redis Streams 持久化所有消息，断线重连自动从断点回放；`interrupt_id` 防止 HITL 重复提交
- **LangSmith 追踪**：每次成功出行规划自动归档到 `travel-agent-traces` 数据集，用于持续评估和微调

---

## 技术栈

| 层次 | 组件 |
|------|------|
| AI 骨架 | LangGraph · LangChain Anthropic |
| 大语言模型 | Claude Sonnet 4.6（可通过环境变量切换） |
| 后端 API | FastAPI · Uvicorn |
| 任务队列 | Celery 5 · Redis Broker |
| 状态持久化 | langgraph-checkpoint-redis · Redis Streams |
| 工具层 | 高德地图 API · 小红书爬虫 · Tavily Search · Playwright |
| 可观测性 | LangSmith |
| 前端 | Vue 3 · Vite |

---

## 目录结构

```
travel_agent/
├── agent/
│   ├── graph.py              # LangGraph 图构建工厂
│   ├── state.py              # TravelPlanState 类型定义
│   ├── llm.py                # LLM 客户端工厂（Claude）
│   ├── tools_container.py    # 工具依赖注入容器
│   └── nodes/
│       ├── collect_intent.py # 对话式意图采集 + HITL
│       ├── parse_input.py    # 目的地/机场/日期解析
│       ├── discover_pois.py  # 多源 POI 发现与融合
│       ├── scrape_flights.py # Playwright 机票抓取
│       ├── human_review.py   # HITL #2 航班/景点确认
│       ├── plan_itinerary.py # 两阶段行程规划
│       └── compose_output.py # 结果格式化输出
├── api/
│   └── main.py               # FastAPI 路由（SSE · HITL 回复 · 状态查询）
├── worker/
│   ├── celery_app.py         # Celery 应用配置
│   └── tasks.py              # run_plan · resume_plan · LangSmith 归档
├── tools/
│   ├── amap.py               # 高德地图客户端
│   ├── airports.py           # 城市 → IATA 机场码映射
│   ├── tavily.py             # Tavily 旅游文章搜索
│   ├── flight_tool/          # Playwright 机票抓取工具
│   └── xhs_tool/             # 小红书笔记爬虫
├── frontend/                 # Vue 3 分步向导前端
│   └── src/
│       ├── App.vue
│       ├── composables/useWebSocket.js
│       └── components/
│           ├── StepConfirm.vue   # Step 1: 意图确认
│           ├── StepProgress.vue  # Step 2: 实时进度
│           ├── StepReview.vue    # Step 3: 航班/景点审核
│           └── StepResults.vue   # Step 4: 行程展示
├── tests/
└── requirements.txt
```

---

## 快速开始

### 前置依赖

- Python 3.11+
- Redis 7+
- Node.js 20+（前端）
- Playwright 浏览器（`playwright install chromium`）

### 环境变量

复制 `.env.example` 并填入以下变量：

```env
# LLM
LLM_MODEL=claude-sonnet-4-6
LLM_API_KEY=your_anthropic_api_key
LLM_API_BASE=                     # 留空使用官方端点

# 工具 API
AMAP_API_KEY=your_amap_key
TAVILY_API_KEY=your_tavily_key
XHS_COOKIE=your_xiaohongshu_cookie

# 基础设施
REDIS_URL=redis://localhost:6379/0

# 可观测性（可选）
LANGCHAIN_API_KEY=your_langsmith_key
LANGCHAIN_TRACING_V2=true
LANGCHAIN_TAGS=env:dev
```

### 启动服务

```bash
# 1. 安装 Python 依赖
pip install -r requirements.txt
playwright install chromium

# 2. 启动 Redis（Docker 方式）
docker run -d -p 6379:6379 redis:7

# 3. 启动 Celery Worker
celery -A worker.celery_app worker --loglevel=info

# 4. 启动 FastAPI
uvicorn api.main:app --reload --port 8000

# 5. 启动前端（可选）
cd frontend && npm install && npm run dev
```

### 调用示例

```bash
# 创建规划任务
curl -X POST http://localhost:8000/plans \
  -H "Content-Type: application/json" \
  -d '{"message": "想去川西玩一周，从苏州出发"}'

# → {"job_id": "abc-123", "status": "pending"}

# 监听实时事件（SSE）
curl -N http://localhost:8000/plans/abc-123/events

# 响应 HITL 请求
curl -X POST http://localhost:8000/plans/abc-123/reply \
  -H "Content-Type: application/json" \
  -d '{"text": "确认，帮我安排", "interrupt_id": "从事件流中获取"}'
```

---

## API 说明

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/plans` | 创建规划任务，返回 `job_id` |
| `GET` | `/plans/{job_id}/events` | SSE 事件流（进度 · HITL · 完成） |
| `POST` | `/plans/{job_id}/reply` | 提交 HITL 用户回复 |
| `GET` | `/plans/{job_id}/state` | 查询最新状态（断线重连用） |

### SSE 事件类型

```jsonc
// 进度更新
{"type": "progress", "node": "discover_pois", "message": "正在聚合景点数据...", "pct": 40}

// HITL 暂停，等待用户输入
{"type": "hitl_request", "interrupt_id": "uuid", "data": {"type": "confirm_params", "message": "..."}}

// 规划完成
{"type": "done", "result": {"itineraries": [...], "warnings": []}}
```

---

## 运行测试

```bash
pytest tests/ -v
```

---

## 设计决策

**为什么用 Celery 而非直接在 FastAPI 中运行 LangGraph？**
LangGraph 图执行时间可达数十秒，Web 进程重启会中断任务。Celery 将执行与 HTTP 层解耦，Redis Checkpointer 保证中断后可从断点续跑。

**为什么用 Redis Streams 而非 WebSocket Pub/Sub？**
Streams 天然持久化，消费者断线后从上次 offset 继续消费，无需额外备份逻辑。前端刷新或网络闪断后调用 `GET /state` 即可恢复到正确步骤。

**多源 POI 融合的可信度怎么算？**
LLM 对每篇文章评估广告可信度（0-1）+ 是否含负面评价，结合引用次数和平台数量综合打分：3+ 次引用且跨 2+ 平台 → `high`；仅高德官方数据 → `medium`；单平台单次 → `low`。

---

## License

MIT
