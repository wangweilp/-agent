# Analytics Runtime Audit — Dashboard V2 数据链路真实接入状态

> 基于 `D:\dma\day2` 仓库真实代码审计，非猜测。
> 审计范围：`src/core/analytics/`、`src/core/dashboard_v2_service.py`、`src/api/dashboard_v2_router.py`、`src/agents/registry.py`、`src/core/memory.py`、`src/adapters/sqlite_store.py`、`src/core/retrieval.py`、`src/core/agent.py`、`src/api/routes.py`、`src/adapters/alert_store.py`、`src/core/analytics/dashboard_alert_evaluator.py`、`main.py`、`docs/sql/analytics_pipeline_schema.sql`。

---

## 1. Analytics Pipeline 当前接入状态

### 总览

| Runtime | 已接入 Analytics? | 接入位置 | 风险等级 |
| --- | --- | --- | --- |
| Agent Runtime | **部分** — 仅 `AgentRegistry.run()` 路径 | [registry.py:308-318](file:///d:/dma/day2/src/agents/registry.py#L308-L318) | **高** |
| Memory Runtime | **未接入** | 无 | **高** |
| Chat Runtime | **未接入** | 无 | **高** |
| Alert Runtime | **未接入**（评估器存在但从未被调用） | 无 | **高** |
| Dashboard Runtime | **已接入**（读取 analytics 表，含 fallback） | [analytics_repository.py](file:///d:/dma/day2/src/core/analytics/analytics_repository.py) | 中 |

### 1.1 Agent Runtime

**已接入位置**：
- [main.py:441-445](file:///d:/dma/day2/main.py#L441-L445) — `AnalyticsStore` + `AnalyticsPipeline` 实例化，注入 `agent_registry.set_analytics_pipeline(analytics_pipeline)`。
- [registry.py:307-318](file:///d:/dma/day2/src/agents/registry.py#L307-L318) — `AgentRegistry.run()` 在 Agent 执行后调用 `analytics_pipeline.record_agent_run_full(result, tenant_id, workspace_id, user_id)`，写入 `analytics_agent_runs` + `analytics_user_activity_daily` + `analytics_token_usage_daily`。

**未接入位置（关键缺口）**：
- [routes.py:66-74](file:///d:/dma/day2/src/api/routes.py#L66-L74) — `/chat` 端点直接调用 `agent.run()`（`CognitiveAgent`），**不经过** `AgentRegistry.run()`。
- [routes.py:76-100](file:///d:/dma/day2/src/api/routes.py#L76-L100) — `/chat/stream` 同样直接调用 `agent.run_stream()`。
- 结果：**所有通过 `/chat` 的对话流量完全绕过 Analytics Pipeline**，不写入任何 analytics 表。这是最大的数据缺口。

**数据流向**：
```
AgentRegistry.run() → record_agent_run_full() → AnalyticsStore → analytics_* 表 ✓
/chat → agent.run() → (无 analytics 记录) ✗
```

**风险**：
- Dashboard V2 的 Agent 性能、Token 成本、DAU 指标**只反映通过 AgentRegistry 调用的 Agent**（部门 Agent / Workflow），**不反映主聊天流量**。
- DAU/WAU/MAU 严重偏低（仅 Agent 调用用户被计入，聊天用户未计入）。
- Token 成本严重偏低（仅 Agent 调用的 token 被计入，聊天 LLM 调用未计入）。

### 1.2 Memory Runtime

**已接入位置**：**无**。

**未接入位置**：
- [sqlite_store.py:193-243](file:///d:/dma/day2/src/adapters/sqlite_store.py#L193-L243) — `SQLiteStoreAdapter.store()` 写入 `notes` 表，**不调用** `analytics_pipeline.record_memory_insert()`。
- [sqlite_store.py:245-257](file:///d:/dma/day2/src/adapters/sqlite_store.py#L245-L257) — `delete()` 不调用 `record_memory_delete()`。
- [sqlite_store.py:271-289](file:///d:/dma/day2/src/adapters/sqlite_store.py#L271-L289) — `get_by_id()` 更新 `access_count`（即 HIT），**不调用** `record_memory_hit()`。
- [retrieval.py:39-98](file:///d:/dma/day2/src/core/retrieval.py#L39-L98) — `Retriever.retrieve()` 返回检索结果（即 HIT），不调用 `record_memory_hit()`。
- `MemoryLifecycleManager`（[main.py:237](file:///d:/dma/day2/main.py#L237)）的 archive/merge 操作也不记录 UPDATE 事件。

**数据流向**：
```
SQLiteStoreAdapter.store() → notes 表 ✓
                            → analytics_memory_events ✗ (缺失)
```

**风险**：
- `analytics_memory_events` 表**永远为空**。
- Dashboard V2 的 Memory Hit Rate、Memory Growth、Memory Type Distribution 全部走 fallback（`notes.access_count`），数据不准确。
- Memory 增长趋势反映的是 `notes.timestamp`，而非真实事件流。

### 1.3 Chat Runtime

**已接入位置**：**无**。

**未接入位置**：
- [routes.py:66-74](file:///d:/dma/day2/src/api/routes.py#L66-L74) — `/chat` 不调用 `record_chat_activity()` / `record_chat_token_usage()`。
- [routes.py:76-100](file:///d:/dma/day2/src/api/routes.py#L76-L100) — `/chat/stream` 同样不调用。
- `CognitiveAgent.run()`（[agent.py:182](file:///d:/dma/day2/src/core/agent.py#L182)）内部调用 LLM 但不记录 token 用量到 analytics。

**数据流向**：
```
/chat → agent.run() → LLM → reply → (无 analytics 记录) ✗
```

**风险**：
- `analytics_user_activity_daily` 仅由 Agent 调用填充（通过 `record_agent_run_full`），**聊天用户不计入 DAU**。
- `analytics_token_usage_daily` 严重偏低 — 聊天 LLM 调用的 token（通常占大头）未计入。
- Cost Analytics 页面展示的成本远低于真实成本。
- Gross Margin 指标失真（分子 AI 成本偏低）。

### 1.4 Alert Runtime

**已接入位置**：**评估器代码存在但从未被实例化或调用**。

- [dashboard_alert_evaluator.py](file:///d:/dma/day2/src/core/analytics/dashboard_alert_evaluator.py) — `DashboardAlertEvaluator` 类完整实现 3 条规则（agent_success_rate_low / agent_p95_latency_high / token_daily_cost_high）。
- [main.py](file:///d:/dma/day2/main.py) — **未实例化** `DashboardAlertEvaluator`，**未调用** `evaluate_all()`，**未调用** `seed_dashboard_rules()`。
- 全局搜索 `evaluate_all` / `DashboardAlertEvaluator` 在 `src/` 中仅命中 `dashboard_alert_evaluator.py` 自身；其余命中均在 `tests/`。

**未接入位置**：
- 无后台任务（`apscheduler` / `asyncio.create_task` 循环 / `BackgroundTasks`）定期调用 `evaluate_all()`。
- 无 API 端点手动触发评估。
- `seed_dashboard_rules()` 从未在 `main.py` 启动流程中调用 → Dashboard 告警规则**未写入** `alert_rules` 表 → `/alerts/rules` API 查不到 Dashboard 规则。

**数据流向**：
```
DashboardAlertEvaluator.evaluate_all() → (从未被调用) ✗
                                       → alert_events 表永远无 Dashboard 触发的事件
```

**风险**：
- 告警规则定义存在但**完全失效** — 即使 Agent 成功率跌到 0%，也不会触发任何告警。
- Dashboard V2 前端 Alerts Tab 显示的规则/事件为空（除非手动通过 Alert API 创建）。
- "实时监控中" 的绿点（前端 Phase 26）是**假象**。

### 1.5 Dashboard Runtime

**已接入位置**：
- [main.py:334-336](file:///d:/dma/day2/main.py#L334-L336) — `AnalyticsRepository(usage_store._db)` + `DashboardV2Service` + router 注册。
- [analytics_repository.py](file:///d:/dma/day2/src/core/analytics/analytics_repository.py) — 所有查询方法优先读 `analytics_*` 表，表为空时 fallback 到 `usage_events` / `notes` / `subscriptions`。

**关键问题**：
- Dashboard **确实读取** `analytics_*` 表（非纯 fallback），但因上游（Memory/Chat）未写入，**表实际为空** → 自动降级到 fallback 数据。
- Fallback 数据来源（`usage_events`）由 `UsageStoreAdapter` 记录，但 `/chat` 路径是否写入 `usage_events` 需进一步确认（不在本次审计范围，但 `usage_events` 的 `resource='agent_run'` 过滤暗示聊天流量可能也未记录）。

**风险**：
- Dashboard 展示的是 fallback 数据，**不是 Analytics Pipeline 的真实数据**。
- 用户看到的指标与 Analytics 表设计目标不符，但不会崩溃（降级机制生效）。

---

## 2. Analytics 数据链路图

```
User
 │
 ▼
API  ── src/api/routes.py:66  (/chat)               ── ✗ 未接 analytics
 │                                              │
 │                                              ▼
 │   src/api/agent_router.py (/agents/run)  ── AgentRegistry.run()
 │                                              │  src/agents/registry.py:215
 │                                              ▼
 │                                              record_agent_run_full()
 │                                              │  src/agents/registry.py:308-318
 │                                              ▼
 │                                              AnalyticsPipeline
 │                                              │  src/core/analytics/analytics_pipeline.py:187
 │                                              ▼
 │                                              AnalyticsStore.record_agent_run / record_user_activity / record_token_usage
 │                                              │  src/core/analytics/analytics_store.py:138/200/236
 │                                              ▼
 │                                              analytics_agent_runs / analytics_user_activity_daily / analytics_token_usage_daily
 │                                              │  (SQLite)
 │                                              ▼
 │                                              AnalyticsRepository
 │                                              │  src/core/analytics/analytics_repository.py
 │                                              ▼
 │                                              DashboardV2Service
 │                                              │  src/core/dashboard_v2_service.py
 │                                              ▼
 │                                              dashboard_v2_router → Dashboard UI
 │                                              │  src/api/dashboard_v2_router.py
 │                                              ▼
 │                                              frontend/app/dashboard-v2/page.tsx
 │
 ▼ (Memory 路径 — 完全断开)
Memory.store()  ── src/adapters/sqlite_store.py:193  ── ✗ 未接 analytics
Memory.delete() ── src/adapters/sqlite_store.py:245  ── ✗ 未接 analytics
Memory.get_by_id() ── src/adapters/sqlite_store.py:271 ── ✗ 未接 analytics (HIT)
Retriever.retrieve() ── src/core/retrieval.py:39    ── ✗ 未接 analytics (HIT)
 │
 ▼ (Alert 路径 — 完全断开)
DashboardAlertEvaluator.evaluate_all()  ── src/core/analytics/dashboard_alert_evaluator.py:86
                                         ── ✗ 从未被调用 (无后台任务)
                                         │
                                         ▼ (若被调用)
                                         AlertStoreAdapter.record_event()
                                         │  src/adapters/alert_store.py:166
                                         ▼
                                         alert_events 表 → /alerts API → Dashboard UI Alerts Tab
```

**断点汇总**：
1. `/chat` → Analytics（断开）
2. Memory store/delete/get_by_id → Analytics（断开）
3. Retriever.retrieve → Analytics HIT（断开）
4. DashboardAlertEvaluator → 后台调度（断开）

---

## 3. 应该写 Analytics 的位置检查

### 3.1 Agent — `analytics_agent_runs`

| 调用路径 | 是否写入 analytics_agent_runs | 说明 |
| --- | --- | --- |
| `AgentRegistry.run()` | **是** | [registry.py:308-318](file:///d:/dma/day2/src/agents/registry.py#L308-L318) 调用 `record_agent_run_full` |
| `/chat` → `agent.run()` | **否** | [routes.py:69](file:///d:/dma/day2/src/api/routes.py#L69) 直接调用 `CognitiveAgent.run()`，不经过 Registry |
| `/chat/stream` → `agent.run_stream()` | **否** | [routes.py:84](file:///d:/dma/day2/src/api/routes.py#L84) 同上 |

**结论**：**不是所有 Agent Run 都写入**。仅通过 `AgentRegistry.run()` 的部门 Agent / Workflow 调用被记录，主聊天流量（`/chat`）完全未记录。

### 3.2 Memory — `analytics_memory_events`

| 事件 | 写入位置（应有） | 实际写入 | 说明 |
| --- | --- | --- | --- |
| CREATE | `SQLiteStoreAdapter.store()` | **否** | [sqlite_store.py:193](file:///d:/dma/day2/src/adapters/sqlite_store.py#L193) 未调用 `record_memory_insert` |
| UPDATE | `SQLiteStoreAdapter.store()` (UPSERT) / `MemoryLifecycleManager` | **否** | 无任何位置调用 `record_memory_update` |
| DELETE | `SQLiteStoreAdapter.delete()` | **否** | [sqlite_store.py:245](file:///d:/dma/day2/src/adapters/sqlite_store.py#L245) 未调用 `record_memory_delete` |
| HIT | `SQLiteStoreAdapter.get_by_id()` / `Retriever.retrieve()` | **否** | [sqlite_store.py:271](file:///d:/dma/day2/src/adapters/sqlite_store.py#L271) 和 [retrieval.py:39](file:///d:/dma/day2/src/core/retrieval.py#L39) 未调用 `record_memory_hit` |

**结论**：**CREATE/UPDATE/DELETE/HIT 全部未写入** `analytics_memory_events`。表永远为空，Dashboard Memory 指标全部走 fallback。

### 3.3 Chat — `analytics_user_activity_daily` + `analytics_token_usage_daily`

| 事件 | 写入位置（应有） | 实际写入 | 说明 |
| --- | --- | --- | --- |
| 每次聊天请求 → user_activity | `/chat` 端点 | **否** | [routes.py:66-74](file:///d:/dma/day2/src/api/routes.py#L66-L74) 未调用 `record_chat_activity` |
| 每次聊天请求 → token_usage | `/chat` 端点 / `agent.run()` | **否** | 未调用 `record_chat_token_usage`；`agent.run()` 内部 LLM 调用的 token 未上报 |

**间接写入**：仅当通过 `AgentRegistry.run()` 调用 Agent 时，`record_agent_run_full` 会顺带写入 user_activity + token_usage（[analytics_pipeline.py:187-211](file:///d:/dma/day2/src/core/analytics/analytics_pipeline.py#L187-L211)）。但 `/chat` 不走此路径。

**结论**：**聊天流量完全未写入**两张表。DAU/Token 成本严重偏低。

### 3.4 Dashboard — 是否真正读取 `analytics_*` 表

| 指标 | 读取 analytics 表? | Fallback | 实际数据来源（当前） |
| --- | --- | --- | --- |
| DAU/WAU/MAU | 是（[analytics_repository.py:81-140](file:///d:/dma/day2/src/core/analytics/analytics_repository.py#L81-L140)） | `usage_events` | fallback（表空） |
| D1/D7 留存 | 是 | `usage_events` | fallback（表空） |
| D30 留存 | 是 | 无 fallback（返回 0） | **0**（表空且无 fallback） |
| Agent 成功率 | 是 | `usage_events` metadata_json | fallback（表空） |
| P50/P95/P99 | 是 | `usage_events` metadata_json | fallback（表空） |
| Token 成本 | 是 | `usage_events` cost_cents | fallback（表空） |
| Memory Hit Rate | 是 | `notes.access_count` | fallback（表空） |
| Memory Growth | 是 | `notes.timestamp` | fallback（表空） |
| Memory Type Dist | 是 | `notes.memory_type` | fallback（表空） |
| MRR/ARR/ARPU | 否（直接读 `subscriptions`） | — | `subscriptions` 表（正常） |

**结论**：Dashboard **代码上确实读取** `analytics_*` 表（非纯 fallback），但因上游未写入，**运行时实际全部降级到 fallback 数据**。D30 留存直接返回 0（无 fallback）。

---

## 4. 告警触发点检查

### 4.1 DashboardAlertEvaluator

- **规则定义**：[dashboard_alert_evaluator.py:48-73](file:///d:/dma/day2/src/core/analytics/dashboard_alert_evaluator.py#L48-L73) 定义 3 条规则：
  1. `agent_success_rate_low` — 成功率 < 95% → CRITICAL
  2. `agent_p95_latency_high` — P95 > 2000ms → WARNING
  3. `token_daily_cost_high` — 日成本 > 阈值 → CRITICAL
- **评估方法**：`evaluate_all(tenant_id)` 遍历规则，调用 `AnalyticsRepository` 取当前值，超阈值则构造 `AlertEvent` 并写入 `alert_store.record_event()`。
- **规则播种**：`seed_dashboard_rules(tenant_id)` 将规则写入 `alert_rules` 表供 `/alerts/rules` 查询。

### 4.2 alert_store

- [alert_store.py](file:///d:/dma/day2/src/adapters/alert_store.py) — `AlertStoreAdapter` 完整实现 `create_rule` / `record_event` / `list_rules` / `list_events` / `acknowledge_event` / `get_active_rules`（含冷却期）。
- [main.py:316](file:///d:/dma/day2/main.py#L316) — `alert_store = AlertStoreAdapter(settings)` 已实例化。

### 4.3 alert_rules

- 表结构存在（[alert_store.py:28-64](file:///d:/dma/day2/src/adapters/alert_store.py#L28-L64)）。
- `seed_presets()` 方法存在，为新租户初始化预设规则。
- **但 `DashboardAlertEvaluator.seed_dashboard_rules()` 从未在 `main.py` 调用** → Dashboard 专属规则未入库。

### 4.4 判断：当前规则是否会自动执行？

**不会。**

缺失的机制：
1. **无后台调度器** — `main.py` 中没有 `apscheduler` / `asyncio` 定时任务 / `BackgroundTasks` 定期调用 `evaluate_all()`。
2. **无实例化** — `DashboardAlertEvaluator` 在 `main.py` 中从未被实例化（`alert_store` 已就绪，但未与 `AnalyticsRepository` 组装为 evaluator）。
3. **无规则播种** — `seed_dashboard_rules()` 从未被调用，Dashboard 规则不在 `alert_rules` 表中。
4. **无 API 触发** — 没有 `POST /dashboard/v2/alerts/evaluate` 之类的手动触发端点。

**结论**：告警系统是**完全静态的死代码**。规则定义、评估逻辑、存储适配器全部就绪，但缺少"调度层"将它们串联起来。即使指标越界，也不会产生任何告警事件。

---

## 5. 风险汇总

| 风险 | 等级 | 影响 |
| --- | --- | --- |
| `/chat` 流量未接入 Analytics | **高** | DAU/Token 成本/Agent 指标严重偏低，Dashboard 失真 |
| Memory 事件未接入 Analytics | **高** | Memory Hit Rate/Growth/Type Dist 全部走 fallback，不准确 |
| 告警评估器从未被调用 | **高** | 告警系统完全失效，无任何自动告警能力 |
| Dashboard 规则未播种 | **中** | `/alerts/rules` 查不到 Dashboard 规则 |
| D30 留存无 fallback | **中** | 表空时直接返回 0，误导运营 |
| 前端"实时监控中"绿点 | **低** | UI 暗示监控生效，实际无数据流入 |
| 老数据无法补齐 | **中** | 历史 `/chat` / Memory 事件无法回填到 analytics 表 |

---

## 6. 审计结论

Dashboard V2 的**展示层**（Phase 24-26）已完整：API 契约、Repository、Service、前端 UI 全部就绪。但**数据层**存在严重断层：

1. **Agent Runtime**：仅 Registry 路径接入，`/chat` 主流量未接入。
2. **Memory Runtime**：完全未接入，4 类事件（INSERT/UPDATE/DELETE/HIT）全部缺失。
3. **Chat Runtime**：完全未接入，DAU 与 Token 成本数据缺失。
4. **Alert Runtime**：评估器代码完整但从未被调度，告警系统失效。
5. **Dashboard Runtime**：代码正确读取 analytics 表，但表为空导致全部降级到 fallback。

**核心问题**：Analytics Pipeline 的"最后一公里"未打通 — 写入入口（`AnalyticsPipeline`）已定义但未在 Memory/Chat 路径调用，告警评估器已实现但无调度。Phase 27 需完成这些接入，否则 Dashboard 建立在空数据之上。
