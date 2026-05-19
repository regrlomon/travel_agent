# 智能出行助手 Agent — 设计文档

**日期：** 2026-05-19  
**状态：** 已确认

---

## 1. 项目背景与目标

用户计划去某地旅游时，面临三个核心痛点：

1. **景点发现难**：只知道少数著名景点，冷门打卡点、隐秘路线需要大量搜索
2. **行程规划耗时**：景点之间的地理关系、游览顺序需要手动研究
3. **机票比价繁琐**：需要在多个平台逐一搜索，且机票价格直接影响行程安排

本系统是一个纯后端 API 服务，输入目的地和出行基本参数，输出多条综合考虑了机票价格的完整行程方案，供用户自行对比选择后去对应平台购票。

---

## 2. 系统范围（MVP）

**MVP 包含：**
- 景点发现与行程规划（含打卡点推荐）
- 多平台机票比价（携程、去哪儿、飞猪），含去程 + 回程
- 综合机票权重的多方案输出

**Phase 2（暂不实现）：**
- 住宿比价
- 前端界面

---

## 3. 技术选型

| 组件 | 选型 | 说明 |
|------|------|------|
| Agent 框架 | LangGraph (Python) | StateGraph 模式，节点职责清晰，支持并行 |
| LLM 接入层 | LiteLLM | 统一接口，通过配置切换 GPT / Claude / DeepSeek / GLM / Qwen 等，LangGraph 节点不感知具体模型 |
| 默认 LLM | 可配置 | 建议默认 DeepSeek（性价比高）；推理/规划复杂任务可切换更强模型 |
| 景点数据 | 高德地图 POI API | 结构化景点数据，含坐标、分类、评分 |
| 景点间交通 | 高德路径规划 API | 计算相邻景点间实际驾车/步行耗时，防止 transport_note 产生幻觉 |
| 游记内容（开放平台） | Tavily Search API | 搜索马蜂窝/穷游游记（这两个平台对搜索引擎开放） |
| 游记内容（封闭平台） | Playwright | 直接爬取小红书搜索页 + 笔记正文（小红书不对搜索引擎开放） |
| 机票数据 | Playwright | 价格日历粗筛 + 航班详情精筛 |
| 缓存 | Redis | POI/机票/游记分层缓存，进度状态存储 |

---

## 4. API 规范

### 异步任务模式

机票爬取耗时较长（多机场 × 多平台 × 多日期），同步响应必然超时。API 采用**异步任务 + 轮询**模式：

```
POST /plans          → { "job_id": "abc123", "status": "pending" }
GET  /plans/{job_id} → { "status": "running", "progress": "scraping flights 3/9" }
GET  /plans/{job_id} → { "status": "done", "result": { ... } }
```

各节点在执行关键步骤时向 Redis 写入 `job:{job_id}:progress` 字符串，GET 接口从 Redis 读取后透传给调用方。

### 请求参数

```json
{
  "destination": "川西",
  "origin": "苏州",
  "duration_days": 7,
  "depart_date": "2026-07-01",
  "travelers": 2,
  "transport_mode": "self_drive",
  "difficulty_level": "medium",
  "interests": ["徒步", "摄影"]
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `destination` | string | 是 | 支持模糊描述，如"川西"、"云南" |
| `origin` | string | 是 | 出发城市，支持无机场城市（如"苏州"） |
| `duration_days` | int | 是 | 行程天数 |
| `depart_date` | string | 否 | 不填则搜索 14 天内最低价的 3 个日期 |
| `travelers` | int | 否 | 默认 1 |
| `transport_mode` | string | 否 | `"self_drive"` / `"public_transit"` / `"mixed"`（默认）。结构性参数，影响哪些景点可达及路线规划方式 |
| `difficulty_level` | string | 否 | `"easy"` / `"medium"`（默认） / `"hard"`。结构性参数，过滤超出体力范围的徒步路线 |
| `interests` | list[string] | 否 | 软偏好标签，如 `["旅拍", "自然风光"]`，由 LLM 解读后影响景点排序权重 |

> **偏好维度设计原则：**
> - **结构性维度**（影响"能不能去"）→ 显式枚举参数，在 `discover_pois` 阶段硬过滤
> - **软偏好维度**（影响"优先推什么"）→ 自由标签 `interests`，由 `plan_itinerary` 的 LLM 解读权重

### 响应结构

```json
{
  "itineraries": [
    {
      "option_id": "A",
      "summary": "稻城亚丁机场进、成都出，7天",
      "flights": {
        "pair_id": "550e8400-e29b-41d4-a716-446655440000",
        "outbound": { "platform": "去哪儿", "depart_airport": "上海浦东 PVG", "arrive_airport": "稻城亚丁 DCY", "price": 980, "flight_no": "MU2345", "depart_time": "2026-07-01 08:30" },
        "return_flight": { "platform": "携程", "depart_airport": "成都双流 CTU", "arrive_airport": "上海浦东 PVG", "price": 760, "flight_no": "CA1235", "depart_time": "2026-07-08 14:00" },
        "total_price": 1740
      },
      "days": [
        {
          "day": 1,
          "pois": [
            { "name": "稻城亚丁景区", "coords": { "lat": 28.67, "lng": 100.3 }, "category": "自然景观", "desc": "三神山核心景区", "confidence": "high" }
          ],
          "transport_note": "机场至景区：驾车约 55 分钟（高德路径规划）",
          "estimated_travel_minutes": 55
        }
      ]
    }
  ],
  "flights_comparison": [
    {
      "route": "PVG → DCY",
      "date": "2026-07-01",
      "options": [
        { "pair_id": "uuid-1", "platform": "去哪儿", "outbound": 980, "return": 760, "total": 1740 },
        { "pair_id": "uuid-2", "platform": "携程",   "outbound": 1200, "return": 820, "total": 2020 }
      ]
    }
  ],
  "warnings": [
    "苏州无机场，已搜索上海浦东(PVG)、上海虹桥(SHA)、南京禄口(NKG)出发航班"
  ]
}
```

---

## 5. LangGraph 架构

### 工作流图

```
① parse_input
      |
      ├──────────────────────┐
      ▼                      ▼
② discover_pois        ③ scrape_flights
      |                      |
      └──────────┬───────────┘
                 ▼
         ④ plan_itinerary
                 |
                 ▼
         ⑤ compose_output
```

② 和 ③ 并行执行，④ 等两者都完成后统一接收数据，由 LLM 综合机票与景点信息生成多条方案。

### 节点职责

**① parse_input**
- 使用 LLM 将目的地映射为城市名称列表（如 `["甘孜藏族自治州", "阿坝藏族羌族自治州"]`），再调用**高德行政区查询 API** 将名称转为编码——避免 LLM 直接输出数字编码产生幻觉：
  - `destination_region: str` — 人类可读描述，如"甘孜州+阿坝州"
  - `destination_amap_cities: list[str]` — 由行政区 API 返回的编码，如 `["513300", "513200"]`
- 将出发城市扩展为附近机场列表（"苏州" → `["PVG", "SHA", "NKG"]`）
- 将目的地扩展为候选到达机场列表（"川西" → `["CTU", "TFU", "DCY", "KGT"]`）
- `depart_date` 未填时，写入从今天起 14 天的全部日期到 `depart_dates`（仅作为搜索范围，不在此阶段筛选——价格尚不可知）
- 使用 LLM 根据目的地生成小红书/马蜂窝搜索关键词，写入 `search_keywords`（如 `["川西 攻略", "稻城亚丁 游记", "四姑娘山 徒步攻略"]`）
- 进度写入 Redis：`"parse_input: done"`
- 输出：规范化参数写入 State

**② discover_pois**
- 用 `destination_amap_cities` 调用高德 POI API 拉取景点列表（含坐标）
- **`transport_mode` 过滤**：`public_transit` 模式下，对每个 POI 调用高德路径规划 API（公交模式）检测从最近城市中心出发是否存在 2 小时内可达的公共交通方案；无方案则标记为"仅自驾可达"并过滤掉
- 根据 `difficulty_level` 过滤超出难度的徒步路线
- **小红书**：Playwright 爬取，使用 `search_keywords` 中的关键词搜索，逐篇抓取正文
- **马蜂窝 / 穷游**：Tavily 搜索，同样使用 `search_keywords`
- **LLM 可信度评估（批量）**：将所有文章批量传入单次 LLM 调用，prompt 要求对每篇输出 JSON 格式评分，避免逐篇调用
- LLM 在提炼景点时同时为每个 POI 生成 `tags: list[str]`（从描述中归纳，如 `["旅拍", "自然风光", "徒步"]`），用于 `plan_itinerary` 阶段按 `interests` 权重排序
- **POI 去重**：同名或坐标距离 ≤ 200m 视为同一景点，合并条目，累加 `mention_count`
- **先截断，再计算路径**：按 `confidence` 降序保留 TOP 40 个 POI
- 调用高德路径规划 API，仅计算同一区域内距离 ≤ 50km 的 POI 对，写入 `travel_time_matrix`（key 为 `poi_id`，避免同名景点冲突）
- 进度写入 Redis：`"discover_pois: found {n} POIs"`
- 输出：`pois[]`、`travel_time_matrix` 写入 State

**③ scrape_flights**
- **粗筛（价格日历）**：若 `len(depart_dates) == 1`（用户已指定日期），跳过此步，直接进入精筛；否则爬各平台价格日历页，遍历全部 14 天，取最低价 TOP 3 日期，写入 `selected_dates`
- **精筛（航班详情）**：对 `selected_dates` 中的日期做详细爬取（3 出发 × 4 到达 × 最多 3 日期 = 最多 36 次，可控）
- 同时爬取去程和回程：
  - **去程**：`origin_airports × destination_airports`
  - **回程**：`destination_airports × origin_airports`（所有可能的出境机场 × 回家机场全组合，覆盖"DCY 进 CTU 出"的异地往返场景）
  - 回程日期 = 出发日期 + `duration_days`
- 组合 outbound × return 生成 `flight_pairs: list[FlightPair]`，合法配对规则：
  - `outbound.arrive_airport ∈ destination_airports`（去程落地目的地区域）
  - `return.depart_airport ∈ destination_airports`（回程从目的地区域出发）
  - 每个去程航班只与同区域出发的回程配对，排除跨目的地的无意义组合
  - 每个 (outbound_airport, return_airport) 组合仅保留各平台最低价各 1 条，控制总量（例：60 条去程 × 60 条回程 → 按合法配对过滤后约 15-30 个 FlightPair）
  - 每个 `FlightPair` 的 `pair_id` 使用 UUID
- 进度写入 Redis：`"scrape_flights: {n}/{total} done"`
- 输出：`flight_pairs[]`、`selected_dates` 写入 State（删除 `cheapest_entry_airport`，可由 `flight_pairs` 推导）

**④ plan_itinerary（两阶段规划）**

*第一阶段 — 候选筛选（压缩格式，控制上下文）：*
- 将 `pois[]` 和 `flight_pairs[]` 转为结构化摘要表传入 LLM：
  ```
  POIs:         poi_id | name | category | confidence | region | tags
  FlightPairs:  pair_id | outbound_route | return_route | date | total_price
  ```
- LLM **按方案分组**输出（不同方案独立选 POI，因为入境机场不同路线不同）：
  ```
  方案A: pair_id=uuid-1 (PVG→DCY进/CTU→PVG出), day1=[poi_1,poi_2], day2=[poi_3], ...
  方案B: pair_id=uuid-2 (NKG→CTU进/CTU→NKG出), day1=[poi_5,poi_6], ...
  ```

*第二阶段 — 方案生成（完整数据）：*
- 根据第一阶段各方案的 `pair_id` 和 `poi_id` 列表，从 State 取对应完整对象
- 每个方案独立传入 LLM，生成完整 `ItineraryOption`（含交通耗时、景点描述等）
- `transport_note` 由高德路径规划 API 数据填入，LLM 只负责措辞整理，不生成数字
- 进度写入 Redis：`"plan_itinerary: done"`
- 输出：`itineraries[]` 写入 State

**⑤ compose_output**
- 整合所有 State 字段，生成最终 JSON
- 负责统一生成 `warnings[]`（汇总各节点写入 State 的 warning 条目）
- Partial failure 处理策略：

| 场景 | 处理方式 |
|------|---------|
| `pois[]` 为空（discover 完全失败） | 返回 400，`error: "无法获取目的地景点数据"` |
| 仅 1 个平台爬到机票 | 降级输出，`warnings` 注明"仅携程数据可用，价格对比不完整" |
| 0 个平台爬到机票 | 返回行程方案但无机票数据，`warnings` 注明"机票数据获取失败，请自行查询" |
| `plan_itinerary` 失败 | 返回 500，不降级（核心功能） |
| 部分日期无直飞 | 降级为中转方案，`warnings` 注明 |

---

## 6. State 结构

```python
class TravelPlanState(TypedDict):
    # 由 ① 写入
    destination_region: str                  # 人类可读，如"甘孜州+阿坝州"
    destination_amap_cities: list[str]       # 高德城市编码
    origin_airports: list[str]
    destination_airports: list[str]
    depart_dates: list[date]                 # 搜索范围（全部 14 天）
    search_keywords: list[str]               # LLM 生成的搜索关键词
    duration_days: int
    travelers: int
    transport_mode: str
    difficulty_level: str
    interests: list[str]

    # 由 ② 写入
    pois: list[POI]                                          # 已截断为 TOP 40
    travel_time_matrix: dict[tuple[str, str], int]           # key 为 poi_id，仅同区域 ≤50km 的 POI 对

    # 由 ③ 写入
    flight_pairs: list[FlightPair]                           # pair_id 为 UUID
    selected_dates: list[date]                               # 粗筛后选出的最低价 TOP 3 日期

    # 由 ④ 写入
    itineraries: list[ItineraryOption]

    # 全局
    errors: list[str]
    warnings: list[str]
```

---

## 7. 数据模型

```python
@dataclass
class POISource:
    platform: str               # "xiaohongshu" | "mafengwo" | "qyer"
    mention_count: int
    llm_credibility: float      # 0-1，广告特征→低分，有负面反馈→高分
    has_negative_reviews: bool

@dataclass
class POI:
    poi_id: str                 # 用于两阶段规划的引用
    name: str
    coords: tuple[float, float]
    category: str
    tags: list[str]             # LLM 从描述归纳，如 ["旅拍", "自然风光", "徒步"]，用于 interests 权重匹配
    desc: str
    amap_rating: float
    sources: list[POISource]
    mention_count: int
    platform_count: int
    confidence: str             # "high" | "medium" | "low"

@dataclass
class Flight:
    platform: str
    depart_airport: str
    arrive_airport: str
    price: int                  # 元，单程/人
    flight_no: str
    depart_time: datetime

@dataclass
class FlightPair:
    pair_id: str                # UUID，生成时赋值，同路线同日期多平台不碰撞
    outbound: Flight
    return_flight: Flight
    total_price: int            # 去程 + 回程总价/人；实际支付 = total_price × travelers

@dataclass
class DayPlan:
    day: int
    pois: list[POI]
    transport_note: str         # 基于高德路径规划 API 数据，LLM 仅做措辞整理，不生成数字
    estimated_travel_minutes: int

@dataclass
class ItineraryOption:
    option_id: str
    summary: str
    flights: FlightPair
    days: list[DayPlan]
```

---

## 8. 错误处理策略

- 节点失败不中断整体流程，错误写入 `State.errors[]`
- `scrape_flights` 单个平台失败：跳过，继续其他平台，写入 warning
- `discover_pois` 高德 API 失败：降级为纯游记爬取（小红书 + 马蜂窝/穷游）
- `discover_pois` 完全失败：返回 400
- `plan_itinerary` 失败：重试一次，仍失败返回 500
- 详细 partial failure 场景见 §5 `compose_output` 节点

---

## 9. 性能与工程约束

### 缓存策略（Redis）

| 数据 | TTL | Key 构成 |
|------|-----|---------|
| POI 列表 | 24h | `pois:{destination}:{transport_mode}:{difficulty_level}` |
| 价格日历（粗筛） | 30min | `cal:{origin}:{dest}:{date_range}` |
| 航班详情（精筛） | 15min | `flight:{origin}:{dest}:{date}` |
| 小红书笔记正文 | 6h | `xhs:{keyword}:{page}` |
| 任务进度 | 2h | `job:{job_id}:progress` |

### 并发控制（Worker Pool）

- 机票爬取：最多 3 个并发 Playwright 实例
- 小红书爬取：最多 2 个并发实例，随机延迟 1-3s

### 反爬与合规风险

| 风险 | 等级 | 缓解措施 |
|------|------|---------|
| 机票平台反爬 | P2 | 随机 User-Agent、请求间隔、退避重试 |
| 小红书封禁 | P2 | 限速 + 缓存；触发封禁时降级为仅用马蜂窝/穷游 |
| 法律合规 | P2 | 数据仅展示，不存储个人数据；商用前评估各平台 ToS |

### Tavily 用量估算

每次 `discover_pois` 请求约发出 5-10 次 Tavily query（多关键词 × 多平台）。免费额度 1000次/月 约支撑 100-200 次规划请求。超出后升级付费计划（$20/月起），或降级为仅爬小红书 + 高德 POI。

---

## 10. 多源数据可信度策略

三类数据源各有侧重：

| | 高德 POI | 小红书（Playwright）| 马蜂窝/穷游（Tavily）|
|---|---|---|---|
| 坐标/开放时间 | 权威，直接采用 | 不可靠，忽略 | 不可靠，忽略 |
| 冷门新景点覆盖 | 弱 | 强（网红新地） | 中（传统攻略）|
| 评分可信度 | 高（大样本） | 低（易刷）| 中 |
| 景点描述质量 | 弱 | 强（真实体验）| 强（详细攻略）|
| 广告风险 | 无 | 高 | 低 |

**confidence 计算规则：**
- `mention_count ≥ 3` 且 `platform_count ≥ 2` → `"high"`
- 仅高德有，无游记提及 → `"medium"`
- 其余 → `"low"`

**广告识别信号（LLM 打分）：**
- 降分：通篇正面无缺点、出现"感谢XX品牌/合作/探店邀请"
- 加分：有负面反馈（"排队两小时"）、包含实用细节（费用、踩坑）

**`plan_itinerary` prompt 策略：**
`confidence=high` 优先排入行程；`confidence=low` 作为"隐藏宝藏"附在每日末尾供用户选择。

---

## 11. 外部依赖与 API Key 清单

| 服务 | 用途 | 费用 |
|------|------|------|
| LiteLLM | LLM 统一接入（GPT/Claude/DeepSeek/GLM/Qwen） | 开源免费，按底层模型计费 |
| 高德地图 POI API | 景点搜索 | 免费额度充足 |
| 高德行政区查询 API | 城市名称 → 编码转换（防 LLM 幻觉） | 免费额度充足 |
| 高德路径规划 API | 景点间交通耗时（防 transport_note 幻觉） | 免费额度充足 |
| Tavily Search API | 马蜂窝/穷游游记搜索 | 免费 1000次/月，超出 $20/月 |
| Playwright | 机票 + 小红书爬取 | 开源免费 |
| Redis | 缓存 + 任务进度 | 自建或云服务 |

---

## 12. 项目目录结构

```
travel-agent/
├── agent/
│   ├── graph.py              # LangGraph StateGraph 定义
│   ├── state.py              # TravelPlanState 定义
│   └── nodes/
│       ├── parse_input.py
│       ├── discover_pois.py
│       ├── scrape_flights.py
│       ├── plan_itinerary.py
│       └── compose_output.py
├── tools/
│   ├── amap.py               # 高德 POI + 路径规划 API
│   ├── tavily.py             # 马蜂窝/穷游搜索
│   ├── xhs_scraper.py        # 小红书 Playwright 爬虫
│   └── flight_scraper.py     # 机票 Playwright 爬虫（价格日历 + 详情）
├── api/
│   └── main.py               # FastAPI 入口（异步任务 + 轮询）
├── models.py                 # 所有数据类
├── llm_config.yaml           # LiteLLM 模型配置，按需切换
└── docs/
    └── superpowers/specs/
        └── 2026-05-19-travel-agent-design.md
```
