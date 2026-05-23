# UX 交互改进设计文档

**日期**：2026-05-23  
**范围**：后台事件补全 + 对话交互优化 + 航班时段偏好  
**涉及文件**：`agent/nodes/collect_intent.py`、`agent/nodes/human_review.py`、`worker/tasks.py`、`agent/state.py`、`frontend/src/composables/useSSE.js`、`frontend/src/App.vue`、`frontend/src/components/ProgressView.vue`、`frontend/src/components/PlanReview.vue`、新增 `frontend/src/components/ConfirmIntent.vue`

---

## 背景

当前交互存在四个问题：
1. AI 无自我介绍，信息收齐后无确认回执，用户体验冷漠
2. 后台任意异常前端无感知，用户只能看到连接断开的通用错误
3. 方案卡只显示日期不显示起飞时刻；未询问出行时段偏好，系统直接自动分配航班
4. 后台节点运行期间不推送进度，前端长时间白屏

---

## 一、事件协议

### 新增/变更的 SSE 事件 type

| type | 触发时机 | data 结构 |
|---|---|---|
| `hitl_request` (collect_intent) | 现有，追问缺失信息 / 首次自我介绍 | `{type, message}` |
| `hitl_request` (confirm_intent) | **新增**，全部信息收齐后展示确认卡 | `{type, summary}` |
| `progress` | **新增**，每个后台节点启动时 | `{type, node, message}` |
| `hitl_request` (review_plan) | 现有，方案生成后 | `{type, message, plans}` |
| `done` | 现有 | `{type, result}` |
| `error` | **新增**，后台 exception | `{type, message}` |

### confirm_intent 完整 SSE 消息结构

`confirm_intent` 复用 `hitl_request` 外层包装，与现有 `collect_intent` / `review_plan` 保持一致：

```json
{
  "type": "hitl_request",
  "interrupt_id": "<uuid>",
  "data": {
    "type": "confirm_intent",
    "summary": {
      "destination": "川西",
      "origin": "苏州",
      "duration_days": 7,
      "depart_date": "2026-07-15",
      "interests": ["自然风光", "徒步"],
      "depart_time_pref": "9点左右出发",
      "return_time_pref": "下午出发，最后一天尽量玩完再走"
    }
  }
}
```

`depart_time_pref` 和 `return_time_pref` 仅在用户表达了偏好时才包含，缺省不传该字段。

### progress 节点 message 映射

| node | message |
|---|---|
| `parse_input` | 正在解析出行需求... |
| `discover_pois` | 正在搜索目的地景点... |
| `scrape_flights` | 正在查询航班价格... |
| `plan_itinerary` | 正在规划行程方案（约 1-2 分钟）... |
| `compose_output` | 正在整理最终行程... |

`collect_intent` 和 `human_review` 属于 HITL 节点，不发 progress，由 hitl_request 自然承接。

---

## 二、后端变更

### 2.1 `agent/state.py`

新增两个可选字段：

```python
depart_time_pref: Optional[str]   # 去程时段偏好，自然语言，如 "9点左右"
return_time_pref: Optional[str]   # 返程时段偏好，自然语言，如 "下午出发"
```

### 2.2 `agent/nodes/collect_intent.py`

**改动点：**

1. **首次自我介绍**：当 `raw_message` 为空时，第一条 interrupt 消息改为带自我介绍的欢迎语，说明小Z助手能做什么：
   > "我是小Z助手，可以帮你搜景点、查机票、排行程。你想去哪儿玩？从哪儿出发，打算玩几天？"

2. **非空但有追问**：`_llm_build_reply` 的 prompt 风格不变（朋友发微信），但首次追问时在问句前追加一句自我介绍（通过 prompt 指令控制，只在 `collected` 为空时加）。

3. **新增时段偏好问题**：必填信息收齐后，新增一次可选 interrupt 询问去程和返程时段：
   > "去程大概想几点出发？返程呢，比如有些人会想最后一天玩到下午再飞。"

   用 LLM 提取 `depart_time_pref` 和 `return_time_pref`（两者均可为空，用户可跳过）。提取 prompt 要求：
   - 识别模糊时间描述（"9点左右" / "不要太晚" / "上午" / "下午随意"）
   - 输出原始自然语言字符串，不做标准化，交给 `scrape_flights` 处理

4. **confirm_intent interrupt**：所有信息（含时段偏好，但时段偏好缺省也允许通过）收齐后，发一次 `confirm_intent` interrupt，payload 为上述 summary 结构。收到用户回复后，用 LLM 判断意图：
   - 若用户确认（"好的" / "确认" / "没问题" 等），继续流程
   - 若用户提到修改（提到任何字段变更），将修改内容合并到 `collected` 中，重新进入追问/确认循环
   - 判断 prompt 返回 `{"action": "confirm" | "modify", "updates": {...}}`

### 2.3 `agent/nodes/scrape_flights.py`

**新增时段评分排序逻辑：**

在 `_scrape_details` 返回航班列表后，增加评分函数 `_rank_by_time_pref`：

- 接受 `flights: list[Flight]` 和 `time_pref: str | None`
- 若 `time_pref` 为 None，原顺序返回
- 否则，调用 LLM（轻量 prompt）将 `time_pref` 解析为目标时间区间（小时范围），然后对每个航班计算距离分，按升序排列
- **不做硬过滤**：无匹配时所有航班依然返回，只是排在后面

去程和返程分别用 `depart_time_pref` 和 `return_time_pref` 调用一次。

`run()` 从 `state` 读取这两个新字段（可选，缺省 None）。

### 2.4 `agent/nodes/human_review.py`

`_format_plans_for_display` 中：

- `depart_date` 字段改为包含完整时刻：`fp.outbound.depart_time.strftime("%Y-%m-%d %H:%M")`
- 新增 `depart_time` 字段（仅时刻）：`fp.outbound.depart_time.strftime("%H:%M")`
- 新增 `return_time` 字段：`fp.return_flight.depart_time.strftime("%H:%M")`

`run()` 中 interrupt message 改为：
> "帮你规划了 {n} 套方案，每套搭配了不同航班供参考，可以告诉我想调整出发时间或行程安排。"

### 2.5 `worker/tasks.py`

**新增 `PROGRESS_MESSAGES` 映射：**

```python
PROGRESS_MESSAGES = {
    "parse_input":    "正在解析出行需求...",
    "discover_pois":  "正在搜索目的地景点...",
    "scrape_flights": "正在查询航班价格...",
    "plan_itinerary": "正在规划行程方案（约 1-2 分钟）...",
    "compose_output": "正在整理最终行程...",
}
```

**新增 `make_node_wrapper(job_id)`：**

```python
def make_node_wrapper(job_id: str):
    def wrapper(fn):
        node_name = fn.__module__.split(".")[-1]
        msg = PROGRESS_MESSAGES.get(node_name)
        @functools.wraps(fn)
        async def wrapped(state, config):
            if msg:
                _emit(job_id, {"type": "progress", "node": node_name, "message": msg})
            return await fn(state, config)
        return wrapped
    return wrapper
```

`run_plan` 和 `resume_plan` 传入 `node_wrapper=make_node_wrapper(job_id)`。

**异常处理补 error 事件：**

```python
except Exception as exc:
    logger.exception("[job=%s] run_plan failed", job_id)
    _emit(job_id, {"type": "error", "message": f"规划失败，请稍后重试（{type(exc).__name__}）"})
    raise
```

`resume_plan` 同理。

---

## 三、前端变更

### 3.1 `frontend/src/composables/useSSE.js`

- 新增 `confirmData = ref(null)`
- `hitl_request` 处理分支新增 `confirm_intent`：
  ```js
  } else if (msg.data.type === 'confirm_intent') {
    phase.value = 'confirm'
    confirmData.value = msg.data.summary
  }
  ```
- 新增 `error` 处理（已有 `phase === 'error'` 状态，补 type 判断）：
  ```js
  } else if (msg.type === 'error') {
    error.value = msg.message
    phase.value = 'error'
    eventSource.close()
  }
  ```
- 导出 `confirmData`

### 3.2 新增 `frontend/src/components/ConfirmIntent.vue`

全屏确认卡组件，接收 `data` prop（summary 对象），emit `reply` 事件。

UI 结构：
- 标题"帮你确认一下出行信息" + 副标题"没问题就点确认，或者告诉我哪里要改"
- 信息行列表：目的地、出发地、天数、出发时间（仅在 depart_date 有值时）
- 时段偏好块（蓝色背景）：
  - 仅当 `data.depart_time_pref` 存在时显示"✓ 去程优先安排 {depart_time_pref} 的航班"
  - 仅当 `data.return_time_pref` 存在时显示"✓ 返程 {return_time_pref}"
- 底部输入框（用于用户修改）+ "确认，开始规划 →" 按钮 + "修改" 按钮
- "确认"按钮发送固定文字 `"确认"`；输入框有内容时发输入框内容

### 3.3 `frontend/src/App.vue`

- 新增 `confirm` phase 处理：
  ```html
  <ConfirmIntent
    v-else-if="phase === 'confirm'"
    :data="confirmData"
    @reply="onReply"
  />
  ```
- 导入 `ConfirmIntent`、从 `useSSE` 获取 `confirmData`
- `stepClass` 映射新增 `confirm: 1`（与 chat 同阶段，step 1）

### 3.4 `frontend/src/components/ProgressView.vue`

当前只有静态 ✓ 列表，改为三态时间线：

- **completed**（已有 progress 推过且不是最后一条）：紫色实心圆 + ✓，灰色连接线
- **active**（最后一条 progress）：spinning 圆圈 + 紫色文字 + 节点 message
- **pending**（尚未 progress 的已知节点）：灰色空圆，半透明

已知节点顺序固定为：`parse_input → discover_pois + scrape_flights → plan_itinerary → compose_output`（discover_pois 和 scrape_flights 并行，同一行显示）。

`items` prop 是 `useSSE.js` 按到达顺序累积的 progress 事件数组。渲染逻辑：
- `items` 中出现过的节点 → completed（除最后一个）
- `items` 最后一个节点 → active（spinner）
- 尚未出现在 `items` 中的已知节点 → pending（半透明）

### 3.5 `frontend/src/components/PlanReview.vue`

- 展示航班时刻：`plan.depart_time` 和 `plan.return_time`（HH:MM），字号加大突出
- 分开展示去程和返程两行
- 副标题改为："每套方案搭配了不同航班供参考，可告诉我想调整出发时间或行程"

---

## 四、不在本次范围内

- ProgressView 倒计时估算（需要经验值，暂不做）
- PlanReview "换时段"快捷按钮（方案 C，暂不做）
- 机票过滤后的 fallback 提示（实现时直接降级返回全部）

---

## 五、测试要点

1. `raw_message` 为空时，首条 AI 消息包含"小Z助手"自我介绍
2. 信息全部填完后，出现 `confirm_intent` 卡片而非直接进 progress
3. 用户说"去程9点，返程下午"，confirm 卡显示两行蓝色时段提示
4. 用户未表达时段偏好，confirm 卡无时段块
5. 后台任意节点抛异常，前端切到 error phase 展示具体提示
6. Progress 时间线动态展示当前节点 spinner + 已完成打勾
7. 方案卡显示去程 HH:MM + 返程 HH:MM
8. 时段评分排序：用户偏好 9 点，09:15 的航班排在 14:30 前面
