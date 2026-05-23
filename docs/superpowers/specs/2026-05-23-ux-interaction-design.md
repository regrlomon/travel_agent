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
| `hitl_request` (select_interests) | **新增**，必填信息收齐后展示兴趣标签 | `{type, message, tags, preselected}` |
| `hitl_request` (confirm_intent) | **新增**，兴趣选完后展示确认卡 | `{type, summary}` |
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

### select_interests 完整 SSE 消息结构

```json
{
  "type": "hitl_request",
  "interrupt_id": "<uuid>",
  "data": {
    "type": "select_interests",
    "message": "你对哪些感兴趣？选几个帮你优先安排（也可以跳过）",
    "tags": ["自然风光", "徒步", "寺庙朝圣", "高原摄影", "藏族文化", "美食"],
    "preselected": ["徒步"]
  }
}
```

`tags` 由 LLM 根据目的地动态生成（6–10 个），`preselected` 是已从用户文本中提取到的 interests（可为空列表）。

前端将用户选中的标签以顿号拼接成字符串发回（如 `"自然风光、徒步、寺庙朝圣"`），跳过时发空字符串。后端直接按顿号/逗号 split，不再走 LLM 提取。

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

1. **首次自我介绍**：当 `raw_message` 为空时，第一条 interrupt 消息改为带自我介绍的欢迎语：
   > "我是小Z助手，可以帮你搜景点、查机票、排行程。你想去哪儿玩？从哪儿出发，打算玩几天？"

2. **非空但有追问**：`_llm_build_reply` 的 prompt 风格不变（朋友发微信），但首次追问时在问句前追加一句自我介绍（通过 prompt 指令控制，只在 `collected` 为空时加）。

3. **新增 `_llm_generate_tags(destination: str) -> list[str]`**：必填信息收齐后，调用 LLM 根据目的地生成 6–10 个兴趣标签，返回字符串列表。示例 prompt 要求输出 JSON 数组，如 `["自然风光", "徒步", "寺庙朝圣", "高原摄影", "藏族文化", "温泉"]`。

4. **新增 `select_interests` interrupt**：生成标签后发出，payload 见上方结构。`preselected` 填入当前已从文本提取的 `collected.get("interests", [])`。用户回复后直接 split（`"、"` 或 `","`），覆盖 `collected["interests"]`；空字符串则保留已提取的值。

5. **新增时段偏好问题**：interests 处理完后，问去程和返程时段：
   > "去程大概想几点出发？返程呢，比如有些人会想最后一天玩到下午再飞。"

   用 LLM 提取 `depart_time_pref` 和 `return_time_pref`（均可为空，用户可跳过）。

6. **confirm_intent interrupt**：所有信息（含时段偏好，但时段偏好缺省也允许通过）收齐后，发一次 `confirm_intent` interrupt，payload 为上述 summary 结构。收到用户回复后，用 LLM 判断意图：
   - 若用户确认（"好的" / "确认" / "没问题" 等），继续流程
   - 若用户提到修改（提到任何字段变更），将修改内容合并到 `collected` 中，重新进入追问/确认循环
   - 判断 prompt 返回 `{"action": "confirm" | "modify", "updates": {...}}`

### 2.3 `agent/nodes/scrape_flights.py`

**新增时段评分排序逻辑：**

在 `_scrape_details` 返回航班列表后，增加两个函数：

**`_parse_time_pref(pref: str | None) -> tuple[int, int] | None`**

规则映射，将中文时段描述转为 `(after_minute, before_minute)`（从 0 点起的分钟数）：

| 匹配关键词 | 时间窗口 |
|---|---|
| 早上 / 上午 | 06:00–12:00 |
| 下午 | 12:00–18:00 |
| 晚上 / 傍晚 | 17:00–22:00 |
| `N点左右` | N±60 分钟 |
| 不要太早 / 别太早 | after 08:00 |
| 不要太晚 / 别太晚 | before 20:00 |
| 随意 / 不限 / 无所谓 / None | 返回 None（不过滤） |

无法匹配时兜底返回 None。不调用 LLM。

**`_rank_by_time_pref(flights: list[Flight], pref: str | None) -> list[Flight]`**

- 调用 `_parse_time_pref` 得到目标窗口
- 若窗口为 None，原顺序返回
- 否则对每个航班计算起飞时刻与窗口中点的分钟距离，按升序排列
- **不做硬过滤**：无匹配航班时全部返回，只是靠前的更接近偏好时段

去程用 `depart_time_pref`、返程用 `return_time_pref` 分别调用一次。

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

- 新增 `confirmData = ref(null)`、`interestsData = ref(null)`
- `hitl_request` 处理分支新增两个类型：
  ```js
  } else if (msg.data.type === 'select_interests') {
    phase.value = 'interests'
    interestsData.value = msg.data
  } else if (msg.data.type === 'confirm_intent') {
    phase.value = 'confirm'
    confirmData.value = msg.data.summary
  }
  ```
- 新增 `error` 处理：
  ```js
  } else if (msg.type === 'error') {
    error.value = msg.message
    phase.value = 'error'
    eventSource.close()
  }
  ```
- 导出 `confirmData`、`interestsData`

### 3.2 新增 `frontend/src/components/SelectInterests.vue`

多选标签组件，接收 `data` prop（`{message, tags, preselected}`），emit `reply` 事件。

UI 结构：
- 标题来自 `data.message`
- 标签列表：`data.tags` 中的每个标签渲染为可点击 chip，`data.preselected` 中的默认选中
- 用户点击 toggle 选中/取消
- "确认" 按钮：将选中标签以 `"、"` 拼接后 emit reply；若无选中则发空字符串（跳过）

### 3.3 新增 `frontend/src/components/ConfirmIntent.vue`

全屏确认卡组件，接收 `data` prop（summary 对象），emit `reply` 事件。

UI 结构：
- 标题"帮你确认一下出行信息" + 副标题"没问题就点确认，或者告诉我哪里要改"
- 信息行列表：目的地、出发地、天数、出发时间（仅在 depart_date 有值时）、兴趣（若非空）
- 时段偏好块（蓝色背景）：
  - 仅当 `data.depart_time_pref` 存在时显示"✓ 去程优先安排 {depart_time_pref} 的航班"
  - 仅当 `data.return_time_pref` 存在时显示"✓ 返程 {return_time_pref}"
- 底部输入框（用于用户修改）+ "确认，开始规划 →" 按钮
- "确认"按钮发送固定文字 `"确认"`；输入框有内容时发输入框内容

### 3.4 `frontend/src/App.vue`

- 新增 `interests` 和 `confirm` phase 处理：
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
- 导入两个新组件，从 `useSSE` 获取 `interestsData`、`confirmData`
- `stepClass` 映射：`interests: 1`、`confirm: 1`（同 chat，均属 step 1）

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
