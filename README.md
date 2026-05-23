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

| 层次 | 组件 | 说明 |
|------|------|------|
| AI 框架 | LangGraph · LangSmith | 有向图编排（并行分支 + HITL 中断 + Checkpointer）；trace 自动归档用于持续评估 |
| 后端 API | FastAPI · Uvicorn | 全异步；SSE 端点推送实时进度；`interrupt_id` 幂等防重放 |
| 任务队列 | Celery 5 · Redis Broker | 将 LangGraph 图执行与 HTTP 层解耦，Worker 重启不丢任务 |
| 实时通信 | Redis Streams | SSE 消息持久化，断线重连从上次 offset 继续消费 |
| 前端 | Vue 3 · Vite | 4 步向导 UI，SSE 接收进度事件，流式 token 展示 |

---

## 项目难点

### 1. HITL 状态机与异步图执行的三方协同

LangGraph 图在 Celery Worker 进程中跑，HITL 节点（`collect_intent` / `human_review`）触发时需要：①将图快照持久化到 Redis Checkpointer；②通过 Redis Streams 向 SSE 消费者推送 `hitl_request` 事件；③等待独立 HTTP 请求 `POST /plans/{id}/reply` 携带 `interrupt_id` 触发 resume。三个进程间的状态边界容易出现 race condition，也是调试最耗时的部分。

### 2. 多源 POI 融合与广告过滤

高德官方数据（结构化）、小红书 UGC 游记（非结构化 + 大量广告推广）、Tavily 网络文章格式差异极大。小红书文章通过关键词黑名单（`合作/探店/种草推广…`）过滤广告，再对高德 POI 名称做字符串匹配统计跨平台引用次数，结合 Haversine 地理去重，最终输出带可信度等级（`high/medium/low`）的 POI 列表。字符串匹配会遗漏别名和简称，是当前精度瓶颈。

### 3. LangGraph 并行分支的 fan-out / fan-in

`parse_input` → `discover_pois` 和 `parse_input` → `scrape_flights` 并行执行，两者写入 `TravelPlanState` 的不同字段，再在 `plan_itinerary` 汇聚。LangGraph 并行分支的状态合并依赖 Checkpointer 原子写入，需要保证两条分支的写操作不互相覆盖，本地调试时难以复现并发问题。

### 4. Playwright 实时机票抓取的脆弱性

没有商业机票 API，通过 Playwright 无头浏览器抓取机票平台，面临三重挑战：反爬检测（User-Agent、请求频率）、异步渲染时序（需等待 JS 动态内容加载完成）、目标网站页面结构随时可能改版。任何一处失败都会导致 `scrape_flights` 节点返回空列表，后续规划降级为「无航班」方案。

### 5. 两阶段 LLM 行程生成的 JSON 稳定性

`plan_itinerary` 分两步：Phase 1 让 LLM 输出方案骨架 JSON（景点分配 + 航班选择），Phase 2 基于骨架补全驾车时间与叙述描写。两次调用都要求严格 JSON 输出，但 LLM 频繁夹带 markdown 代码块或遗漏字段。为此叠加了三层兜底：正则抽取 JSON 片段 → `json_repair` 修复 → 结构缺失时 fallback 为空字段。

### 6. O(n) 批量驾车时间矩阵

两两 POI 之间的驾车时间若用高德单点 API 调用为 O(n²) 次请求，40 个 POI 需 1600 次，速度和配额都不可接受。通过高德批量路径 API，对每个目标 POI 合并所有出发地为一次请求，将调用次数降到 O(n)，同时用 Haversine 预过滤距离 >50km 的无效 POI 对，进一步减少约 60% 的无效请求。

### 7. SSE 断线重连与幂等保护

SSE 是单向长连接，网络闪断后前端需从上次位置续读。Redis Streams 天然保留消息偏移量，`GET /plans/{id}/state` 可查询最新快照用于前端状态恢复。同时 HITL 请求携带 `interrupt_id`，服务端做幂等检查，防止断线重连后重复提交同一确认。

---

## 可优化点

### 性能

- **Phase 2 串行 → 并行**：`_phase2_generate` 当前对 2-3 套方案顺序调用 LLM，改为 `asyncio.gather` 并发可将行程生成耗时从约 15s 降至约 5s。

- **LLM Token 压缩**：POI 表以 40 行全字段传入 Phase 1 prompt，token 消耗高。可在进入 Phase 1 前按用户兴趣预筛，只保留前 20-25 条最相关 POI，预计节省 30-40% prompt token。小红书/Tavily 文章也可在字符串匹配之前先做摘要截断。

- **XHS 缓存粒度**：SQLite 缓存当前 TTL 统一为 7 天，对热门城市（如成都、三亚）可延长至 14 天，对实效性强的内容（节假日攻略）可缩短，减少不必要的爬取请求。

### 质量

- **结构化 LLM 输出**：Phase 1/2 依赖 `json_repair` 兜底说明输出不稳定，可切换到 LangChain `with_structured_output` + Pydantic Schema 约束模式，从根本上消除 JSON 解析失败的可能性。

- **POI 实体识别升级**：当前小红书文章中的 POI 提取依赖精确字符串匹配高德名称，遗漏别名（如"都江堰"被写成"都江堰景区"）。可引入 `rapidfuzz` 模糊匹配或 LLM NER，提升跨文章的 POI 召回率。

- **机票抓取多平台降级**：Playwright 单平台抓取，目标站改版即失效。可增加备用抓取源，或集成飞常准 / 航班管家等有开放接口的平台作为降级方案。

### 体验

- **前端流式行程输出**：`compose_output` 当前等行程全部生成后才一次性推送，用户等待感强。可在 `plan_itinerary` Phase 2 阶段就逐方案流式推送，边生成边展示。

- **意图采集对话优化**：`collect_intent` 多轮追问目前提问顺序固定，可根据已知信息动态调整问题顺序（如已知目的地先问出发城市而非天数），减少不必要的对话轮次。

---

## 后续计划

**近期**

- [ ] `_phase2_generate` 并行化，减少行程生成等待时间
- [ ] 切换 `with_structured_output`，从根本上解决 JSON 解析稳定性问题
- [ ] POI 模糊匹配，提升小红书/Tavily 文章中的景点识别率

**中期**

- [ ] 补充 POI 数据源：大众点评（评分）、马蜂窝（攻略）
- [ ] 用户偏好记忆：记录历史选择（航班偏好、景点风格），下次规划自动带入
- [ ] 多城市联程支持：如「上海 → 成都 → 九寨沟」多段行程规划

**长期**

- [ ] 国际目的地支持（当前仅覆盖国内，机场码库和 POI 数据源需替换）
- [ ] 小红书图片多模态理解：识别图片中的景点/美食，不依赖文字匹配
- [ ] 动态价格提醒：规划完成后持续监控机票价格变化，超出阈值时主动通知

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

**与直接调用高德 MCP 的本质区别是什么？**

直接让 LLM 调用高德 MCP 工具可以完成"查附近景点"这类单次查询，但无法胜任"帮我规划一次完整旅行"这类任务。两者的核心差异在于**有没有持久化的多步编排状态**：

| 维度 | 直接调用 MCP 工具 | 本项目（LangGraph 编排） |
|------|------|------|
| **执行模型** | 单次 tool call，LLM 拿到结果继续对话 | 有向图，每个节点独立异步执行，状态跨节点持久化流转 |
| **并行** | 多 tool call 在同一轮对话内仍是串行 | `discover_pois` 与 `scrape_flights` 真正并行，互不阻塞 |
| **HITL 暂停/恢复** | 不支持；一轮对话完成后无法中途等待用户确认 | 任意节点可 `interrupt`，状态写入 Redis，用户回复后从断点 resume |
| **断线容错** | 对话中断即需重来 | Redis Checkpointer 保存快照，页面刷新或网络闪断后自动恢复 |
| **多工具融合** | 多工具结果混在 LLM context 内，融合逻辑隐式且难调试 | 数据在节点层面独立拉取，置信度评分、去重、矩阵计算均为确定性代码，可单独测试 |
| **长耗时任务** | 受 HTTP 超时和 LLM context 长度双重限制 | Celery Worker 解耦，任务跑几十秒不影响 HTTP 层，token 消耗可控 |
| **可观测性** | 只能看 LLM 的 tool call 参数 | LangSmith 追踪每个节点的输入输出，逐步可调试，可归档为评估数据集 |

简言之：**MCP 工具调用适合一问一答的信息检索；LangGraph 编排适合需要多步收集信息、中途等待用户确认、并行聚合多源数据、最终生成结构化方案的复杂工作流。** 本项目中高德 API、小红书爬虫、机票抓取都只是工具节点，真正的价值在于把它们串联成一条可中断、可恢复、可观测的流水线。

---

## License

MIT
