# UI 全面重设计 + 流式进度页 · 设计文档

**日期**: 2026-05-23  
**范围**: 前端全部视图 + 后端 SSE 流式改造

---

## 一、设计目标

1. 所有页面统一切换为「方案 A · 极光暗色」风格，取代现有 GitHub 开发者配色
2. 规划进度页从静态四步骤改为 Perplexity 风格的实时流式展示
3. 国内行程专用（文案、示例数据均使用国内城市，不做国际入口）

---

## 二、视觉设计系统

### 2.1 色彩 Token（替换 style.css）

| Token | 值 | 用途 |
|-------|----|------|
| `--bg-base` | `#080c14` | 页面底色 |
| `--bg-surface` | `#0d1320` | 卡片背景 |
| `--bg-glass` | `rgba(255,255,255,0.05)` | 毛玻璃卡片 |
| `--border-glass` | `rgba(255,255,255,0.10)` | 毛玻璃边框 |
| `--accent-grad-start` | `#6c3bd5` | 渐变起点（紫） |
| `--accent-grad-end` | `#1a6feb` | 渐变终点（蓝） |
| `--accent-cyan` | `#22d3ee` | 价格/高亮数字 |
| `--text-primary` | `#e6edf3` | 主文字 |
| `--text-secondary` | `#8b949e` | 次要文字 |
| `--text-muted` | `#484f58` | 占位/禁用 |
| `--success` | `#3fb950` | 完成状态 |

Aurora 背景：3 个绝对定位 `div.blob`，`filter: blur(90px)`，固定在 `#080c14` 之上，opacity 0.22，无点击事件。各页面共用同一套 blob，intensity 略有差异（聊天页减弱，进度页增强）。

### 2.2 共用组件

**GlassCard**: `background: var(--bg-glass); backdrop-filter: blur(32px); border: 1px solid var(--border-glass); border-radius: 20px`

**GradientButton**: `background: linear-gradient(135deg, #6c3bd5, #1a6feb); border-radius: 10px`

**GlassInput**: `background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.15); border-radius: 14px`，focus 时 `border-color: rgba(108,59,213,0.7); box-shadow: 0 0 0 3px rgba(108,59,213,0.15)`

---

## 三、TopBar 重设计

**现状**: 4 个 28×4px 色块，无标签。  
**新设计**: 带编号和文字标签的四步进度条。

```
[✓ 告诉我] ─── [● 规划中] ─── [2 选方案] ─── [3 出发]
```

- 已完成步骤：绿色圆点 + 绿色文字，连接线变绿
- 当前步骤：渐变圆点 + 紫色文字 + `box-shadow` 发光
- 待完成步骤：暗色圆点 + `#484f58` 文字

步骤映射（与现有 `stepClass()` 逻辑对应）：

| 步骤 | 覆盖的 phase |
|------|-------------|
| 告诉我 | idle / chat / interests / confirm |
| 规划中 | progress |
| 选方案 | review |
| 出发 | done |

---

## 四、各视图改动

### 4.1 首页 Hero（ChatView，messages 为空时）

- Aurora blob 全强度
- 眼眉标签：`AI 国内旅行规划助手`（含脉冲绿点）
- 主标题：渐变文字 `去你一直想去的地方`，字号 clamp(44px, 7vw, 72px)
- 副标题：`#6b7280`，限宽 420px
- GlassInput（限宽 560px）+ GradientButton
- 底部快捷词 5 个：🏔 西藏 · 🌊 三亚 · 🎭 大理 · 🏞 张家界 · 🌸 成都；点击填入输入框

### 4.2 对话中（ChatView，messages 有内容时）

- Aurora blob 减至 opacity 0.15
- 头像：AI 用渐变圆，用户用半透明圆
- AI 气泡：`bg-glass + border-glass`，左下角 4px
- 用户气泡：渐变背景，右下角 4px
- 打字等待动画：3 个紫色脉冲点

### 4.3 选兴趣（SelectInterests）

- GlassCard 容器居中，内边距 32px
- 标签默认：`bg-glass + border-glass`，hover 微亮
- 标签选中：`background: linear-gradient(135deg, rgba(108,59,213,0.3), rgba(26,111,235,0.3)); border-color: rgba(108,59,213,0.6); color: #c4b5fd; box-shadow: 0 0 12px rgba(108,59,213,0.2)`
- 底部：跳过（ghost 按钮）+ 确认（GradientButton，显示已选数量）

### 4.4 确认出行信息（ConfirmIntent）

- GlassCard 居中，max-width 480px
- 顶部 badge：`✦ 信息确认`（紫色小字）
- 信息行：`bg: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.07); border-radius: 10px`，key 带 emoji 图标
- 时段偏好行：紫色背景 + 紫色边框（区别于普通信息行）
- 底部 GlassInput + GradientButton（`确认，开始规划 →`）

### 4.5 规划中（ProgressView）— 流式改造核心

详见第五章。

### 4.6 选方案（PlanReview）

- 标题行：font-size 20px，font-weight 700
- 卡片网格：`repeat(auto-fit, minmax(240px, 1fr))`，gap 16px
- 卡片默认：`bg-glass + border-glass`，border-radius 18px
- 卡片 hover：`border-color: rgba(108,59,213,0.4)`
- 卡片选中：`border-color: #6c3bd5; background: rgba(108,59,213,0.12); box-shadow: 0 0 0 1px #6c3bd5, 0 8px 32px rgba(108,59,213,0.2)`
- 航班时间区：独立的小 glass 块，去程时间大字（20px bold）
- 价格：`#22d3ee`，15px bold
- 选中 badge：`✓ 已选`（紫色胶囊）

### 4.7 最终行程（ResultView）

- 标题渐变文字（同 Hero）
- 行程卡头部：`linear-gradient(135deg, rgba(108,59,213,0.2), rgba(26,111,235,0.15))`
- 价格大字：26px bold，`#22d3ee`
- 航班摘要条：`border-bottom: 1px solid rgba(255,255,255,0.06)`
- 每日 Day badge：紫色背景 + 紫色边框
- POI chip：`bg-glass`，border-radius full

---

## 五、规划中页面流式改造

### 5.1 新 SSE 事件类型

在现有 `progress / hitl_request / done / error` 基础上新增：

```typescript
// 航班找到（scrape_flights 完成后）
{ type: "flight_found", flights: FlightPair[], total_found: number }
// flights 为排序后 top-3，total_found 为实际总数

// 景点找到（discover_pois 完成后）
{ type: "poi_found", pois: string[], total_found: number }
// pois 为评分 top-10 的名称列表，total_found 为实际总数

// LLM 流式文本（plan_itinerary 叙述段）
{ type: "stream_text", token: string }
```

### 5.2 后端改动

**scrape_flights.py**
- `run()` 完成 `_assemble_flight_pairs()` 后，取价格排序 top-3 emit `flight_found`
- emit 通过 config 中注入的 `progress_emit` 函数（已有 `make_node_wrapper` 模式可参考）

**discover_pois.py**
- POI 评分+去重完成后，按 credibility_score 降序取 top-10 名称 emit `poi_found`

**plan_itinerary.py**
- `_phase1_select()` prompt 末尾加指令：先用 2-3 句话概括选择理由（纯文本），再输出 JSON
- 改用 `astream()`，检测到第一个 `{` 字符前的 token 作为 `stream_text` emit；检测到 `{` 后切换缓冲模式，等待完整 JSON 再解析

### 5.3 前端 ProgressView 新布局

```
[状态行] AI 正在规划中…  ●脉冲点

[四步时间线]  ✓ → ✓ → ● spinning → ○
              (已有，样式升级为新设计)

─────────────────────────────────

[流式内容区，按事件顺序出现]

  [航班卡区] 找到 18 个航班，为你筛选最优 3 个
    ┌─────────────────────────────┐
    │ CZ · 07:30 → 12:45  ¥2,380 │  ← 从左滑入
    │ CA · 09:10 → 14:25  ¥2,680 │
    │ MU · 13:50 → 19:05  ¥1,980 │
    └─────────────────────────────┘

  [景点区] 找到 24 个景点，收录评分最高的
    布达拉宫  纳木错  大昭寺  色拉寺  …  ← chip 逐个冒出

  [AI 分析文字区]  ← stream_text token 逐字渲染
    根据你7月广州出发的需求，西藏正值最美夏季…▌
```

动画规格：
- 航班卡：`opacity 0→1, translateX(-12px→0)`，间隔 380ms
- POI chip：`opacity 0→1, scale 0.9→1`，间隔 120ms
- 流式文字：每个 token span `opacity 0→1`，0.15s

### 5.4 useSSE.js 改动

新增 state：
- `streamingFlights: FlightPair[]`
- `streamingPois: string[]`
- `streamText: string`
- `flightsTotalFound: number`
- `poisTotalFound: number`

事件处理：
- `flight_found` → 追加 `streamingFlights`，记录 `flightsTotalFound`
- `poi_found` → 设置 `streamingPois`，记录 `poisTotalFound`
- `stream_text` → 追加 `streamText`

`phase` 保持 `'progress'` 不变，直到 `hitl_request(review_plan)` 到来。

---

## 六、Bug 修复（随本次一起）

### 6.1 时段偏好未生效

**根因**：`scrape_flights._assemble_flight_pairs()` 遍历所有去程×返程组合后**只保留总价最低的一对**，完全覆盖了 `_rank_by_time_pref()` 的排序结果。`plan_itinerary` 最终只收到 1 个 FlightPair（最便宜的），3 个方案都用同一个航班，时段偏好丢失。

**修法**：

1. `_assemble_flight_pairs` 签名改为接收 `depart_time_pref` 和 `return_time_pref`
2. 不再只保留最便宜的一对，而是生成 **最多 3 个 FlightPair**：
   - **偏好优先**：去程选最接近时段偏好的，返程选最接近时段偏好的
   - **价格优先**：去程+返程总价最低的组合
   - **折中**：偏好得分与价格综合排序取第二名
3. 去重（若偏好优先和价格优先碰巧相同则只保留一个）
4. `plan_itinerary._phase1_select` 拿到 2-3 个 FlightPair，LLM 已有逻辑为不同方案分配不同 pair_id，自然生效

### 6.2 费用展示误导用户

**现状**：UI 直接显示 `¥2,380/人`，用户误以为是全程总费用，实际只含机票。

**修法（纯前端）**：
- `PlanReview` 和 `ResultView` 中价格标签改为 **`机票 ¥2,380/人`**
- `ResultView` 行程卡头部价格区下方加一行小字：`住宿·餐饮·地面交通费用另计`

---

## 七、不在此次范围内

- 国际目的地支持
- 住宿/餐饮费用估算（需要独立数据源）
- 多语言
- 移动端响应式（当前维持桌面布局）
- ResultView 的导出/分享功能
