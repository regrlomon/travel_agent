# 智能出行助手 — 前端 UX 重设计 & 图架构调整

**日期：** 2026-05-23  
**状态：** 已确认  
**基于：** `2026-05-22-travel-agent-refactor-design.md`

---

## 1. 背景与问题

原设计存在三个根本性问题：

1. **前端用表单收集参数**：`destination/origin/duration_days` 三个输入框，违背"AI 对话助手"的定位，用户体验僵硬
2. **WebSocket 端点未实现**：设计文档规划了 `api/websocket.py`，但实际 `api/main.py` 只实现了 SSE，前后端对不上
3. **`parse_input` 职责混乱**：既做对话确认（interrupt），又做技术解析，且让用户回答他们不具备判断力的问题（机场代码选哪个）

---

## 2. 核心设计原则

> **用户只需要知道：去哪里、从哪出发、玩几天。其余全是 AI 的工作。**

- 最小化用户决策次数：全程只打断用户两次（收集意图 + 审核行程）
- AI 主动推荐，不把技术细节甩给用户
- 前端通信层统一为 SSE（不引入 WebSocket）

---

## 3. 新 LangGraph 图结构

```
collect_intent          ← 新增，ReAct Agent，多轮对话
       ↓
parse_input             ← 保留，去掉 interrupt，纯静默转换
       ↓
discover_pois ‖ scrape_flights    ← 不变，并行执行
       ↓
plan_itinerary          ← 不变，自主生成 2-3 个完整方案
       ↓
human_review            ← 移到此处（原在 scrape_flights 之后）
       ↓
compose_output          ← 不变
```

### 3.1 节点职责对比

| 节点 | 原职责 | 新职责 |
|------|--------|--------|
| `collect_intent` | 不存在 | ReAct 对话收集意图，输出结构化字段 |
| `parse_input` | 解析 + interrupt 确认 | 纯技术转换，无 interrupt |
| `human_review` | 展示原始航班/景点列表 | 展示完整行程方案，收集用户偏好 |

---

## 4. collect_intent 节点设计

### 职责
多轮对话收集用户旅行意图，直到获得三个必要字段：`destination`、`origin`、`duration_days`。

### ReAct 工具

```python
tools = [
    lookup_airports(city: str) -> list[str],
    # 本地字典 + AMap 兜底，毫秒级响应
    # 每次涉及城市都调用，保证机场代码准确
    # 例: "苏州" → ["PVG","SHA","NKG"], "成都" → ["CTU","TFU"]

    suggest_destinations(style: str, region: str) -> list[str],
    # 查询 XHS/Tavily 近期热门目的地，返回 3-5 个
    # 仅在用户目的地模糊时触发（"西南"、"好玩的地方"等）
]
```

### 触发逻辑
- 用户说"川西"（明确）→ 不调 `suggest_destinations`，直接追问出发地/天数
- 用户说"西南想看自然风光"（模糊）→ 调 `suggest_destinations`，给出推荐后再收集

### 对话风格（B 风格）
- 用户一句话带多个信息时，AI 一次性识别并确认，不重复问
- AI 主动提供建议和背景信息，不做机械问答
- 示例：
  ```
  用户: 想去川西7天，苏州出发，喜欢自然风光
  AI:   川西很适合～苏州没有直飞，帮你搜上海浦东/虹桥出发。
        出发时间有偏好吗？没有的话我帮你找最近两周最便宜的航班。
  ```

### 输出（写入 TravelPlanState）
```python
{
    "destination":    str,           # 必须
    "origin":         str,           # 必须
    "duration_days":  int,           # 必须
    "origin_airports": list[str],    # lookup_airports 的结果
    "interests":      list[str],     # 可选，聊到了就收
    "depart_date":    str | None,    # 可选，None = 找最便宜日期
    "travelers":      int,           # 可选，默认 1
}
```

---

## 5. parse_input 节点调整

**去掉 `interrupt()`**，变为纯静默节点：

```python
async def run(state, config):
    # 使用 state["destination"] 和 state["origin"]（由 collect_intent 写入）
    parsed = await _llm_parse_destination(state["destination"], state["origin"])
    # ... 查高德城市码、生成搜索关键词 ...
    return {
        "destination_region":        parsed["region"],
        "destination_amap_cities":   amap_cities,
        "destination_airports":      parsed["destination_airports"],
        # origin_airports 已由 collect_intent 通过 lookup_airports 写入，此处不覆盖
        "depart_dates":              _expand_dates(state.get("depart_date")),
        "search_keywords":           parsed["search_keywords"],
    }
```

---

## 6. human_review 节点调整

**位置**：移到 `plan_itinerary` 之后。

**展示内容**：完整行程方案（2-3 个选项），每个包含航班 + 每日安排 + 景点，而非原始数据列表。

**interrupt payload**：
```json
{
  "type": "review_plan",
  "message": "帮你规划了 3 个方案，你看看哪个合适，或者有什么想调整的？",
  "plans": [
    {
      "option_id": "A",
      "summary": "成都飞入，稻城亚丁为核心，轻松路线",
      "flight": "PVG→CTU ¥680 / 回程¥720",
      "days": ["Day1: 成都市区", "Day2-4: 稻城亚丁", ...]
    }
  ]
}
```

用户自然语言回复（"选 A"、"我不想爬山"）→ LLM 解析偏好，提取 `user_flight_choice` 和 `user_poi_prefs` → 写入 state → `compose_output` 根据偏好过滤输出。本次不重跑 `plan_itinerary`。

---

## 7. API 变更

### POST /plans（入参简化）
```python
class PlanRequest(BaseModel):
    message: str    # 用户第一句话，可为空字符串触发问候
```

原结构化字段（`destination/origin/duration_days` 等）全部由 `collect_intent` 在图内收集，不再从 API 传入。

### 不变的端点
```
GET  /plans/{job_id}/events    # SSE，不变
POST /plans/{job_id}/reply     # HITL 回复，不变
```

**WebSocket 方案废弃**：`api/websocket.py` 不再实现，前端统一使用 SSE + REST。

---

## 8. 前端重设计

### 8.1 通信层：useSSE.js（替换 useWebSocket.js）

```javascript
export function useSSE() {
  const phase = ref('idle')   // idle | chat | progress | review | done
  const messages = ref([])    // 聊天消息列表
  const plan = ref(null)      // human_review 时的完整方案
  const result = ref(null)    // compose_output 最终结果
  const error = ref(null)
  let jobId = null
  let interruptId = null

  async function startChat(text) {
    const resp = await fetch('/plans', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text }),
    })
    jobId = (await resp.json()).job_id
    phase.value = 'chat'
    _listenSSE()
  }

  function _listenSSE() {
    const es = new EventSource(`/plans/${jobId}/events`)
    es.onmessage = (e) => {
      const msg = JSON.parse(e.data)
      if (msg.type === 'hitl_request') {
        interruptId = msg.interrupt_id
        if (msg.data.type === 'collect_intent') {
          // AI 问话，追加到消息流
          messages.value.push({ role: 'ai', text: msg.data.message })
        } else if (msg.data.type === 'review_plan') {
          plan.value = msg.data
          phase.value = 'review'
        }
      } else if (msg.type === 'progress') {
        phase.value = 'progress'
      } else if (msg.type === 'done') {
        result.value = msg.result
        phase.value = 'done'
        es.close()
      }
    }
    es.onerror = () => { error.value = 'connection error' }
  }

  async function sendReply(text) {
    messages.value.push({ role: 'user', text })
    await fetch(`/plans/${jobId}/reply`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, interrupt_id: interruptId }),
    })
    if (phase.value === 'chat') {
      // 继续聊天，等待下一条 hitl_request 或切换到 progress
    } else if (phase.value === 'review') {
      phase.value = 'progress'
    }
  }

  return { phase, messages, plan, result, error, startChat, sendReply }
}
```

### 8.2 组件结构

```
frontend/src/
├── composables/
│   └── useSSE.js              ← 替换 useWebSocket.js
├── components/
│   ├── ChatView.vue           ← 替换 StepConfirm.vue（首屏 + 聊天流）
│   ├── ProgressView.vue       ← 替换 StepProgress.vue（深色主题）
│   ├── PlanReview.vue         ← 替换 StepReview.vue + StepResults.vue
│   └── ResultView.vue         ← 最终行程展示（可选，PlanReview 确认后展开）
└── App.vue                    ← phase 状态机驱动视图切换
```

### 8.3 ChatView.vue 布局

**首屏（messages 为空）：**
```
┌─────────────────────────────────────────┐
│  ✈ TRAVEL AI              ①②③④ 步骤条  │  ← 细顶栏，深黑
├─────────────────────────────────────────┤
│                                         │
│         你想去哪里？                     │  ← 大标题居中
│    告诉我你的想法，我来帮你搞定一切       │  ← 副标题
│                                         │
│  ┌─────────────────────────────── →┐   │  ← 大圆角输入框
│  │  随便说，比如"想去西藏看星空，7月..."│   │
│  └──────────────────────────────────┘  │
└─────────────────────────────────────────┘
```

**对话中（messages 非空）：**
```
┌─────────────────────────────────────────┐
│  ✈ TRAVEL AI              ① 步骤条      │
├─────────────────────────────────────────┤
│  [AI气泡] 想去哪玩？...                  │
│                    [用户气泡] 川西7天... │
│  [AI气泡] 川西很适合～苏州出发...        │
│                    [用户气泡] 没有特定.. │
│  [AI气泡] 好，帮你扫最近两周低价票～     │
│  ⟳ 规划中...                            │
├─────────────────────────────────────────┤
│  ┌──────────────────────────── →┐       │  ← 底部输入框
│  │  继续输入...                  │       │
│  └───────────────────────────────┘      │
└─────────────────────────────────────────┘
```

### 8.4 视觉规范

```css
:root {
  --bg-base:       #0d1117;   /* 页面底色 */
  --bg-surface:    #161b22;   /* 顶栏、卡片 */
  --bg-elevated:   #1c2128;   /* AI 气泡、输入框 */
  --border:        #30363d;
  --text-primary:  #e6edf3;
  --text-secondary:#8b949e;
  --accent:        #1f6feb;   /* 用户气泡、主按钮 */
  --accent-hover:  #388bfd;
  --success:       #3fb950;   /* 进度完成 */
  --warning:       #d29922;
}
```

无 UI 框架，纯手写 CSS。

---

## 9. 交互流程总览

```
用户打开页面
  → 看到首屏大输入框
  → 输入第一句话（"想去川西"）
  → POST /plans { message: "想去川西" }
  → SSE 连接建立

collect_intent 运行
  → hitl_request(collect_intent): "川西很适合！从哪里出发？大概玩几天？"
  → 前端: AI 气泡出现，用户输入框等待
  → 用户回复: "苏州，7天"
  → POST /reply
  → collect_intent 收集完毕，图继续

parse_input（静默）
discover_pois ‖ scrape_flights（静默，progress 事件推送）
  → 前端: 切换到 ProgressView，显示进度

plan_itinerary（静默，生成 2-3 个完整方案）

human_review
  → hitl_request(review_plan): 展示 3 个完整行程方案
  → 前端: 切换到 PlanReview，用户浏览方案
  → 用户: "选 A，第三天改轻松点"
  → POST /reply

compose_output
  → done 事件
  → 前端: 展示最终行程
```

---

## 10. 不在本次范围

- `plan_itinerary` 根据 human_review 反馈重跑的实现（当前单次生成）
- 移动端适配
- 行程导出（PDF/图片）
- 用户账号/历史记录
