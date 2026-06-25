# Phase 26 — Analytics Runtime Integration & Production Readiness 实施方案

> 基于 [ANALYTICS_RUNTIME_AUDIT.md](file:///d:/dma/day2/ANALYTICS_RUNTIME_AUDIT.md) 审计结论。
> 本文档仅给出实施方案，**不实现任何代码**。正式实施在 Phase 27。
>
> 原则：不修改后端接口契约、不修改数据库结构、最大化复用现有 `AnalyticsPipeline` / `AnalyticsStore` / `DashboardAlertEvaluator` / `AlertStoreAdapter`。

---

## 总体目标

打通 Analytics Pipeline 的"最后一公里"：

1. Memory Runtime 接入 → `analytics_memory_events` 有数据
2. Chat Runtime 接入 → `analytics_user_activity_daily` / `analytics_token_usage_daily` 有数据
3. 告警评估器被调度 → 告警自动触发
4. 老数据补齐 → Dashboard 展示历史趋势
5. 生产验证 → 确认数据真实流入

完成后，Dashboard V2 从"展示空数据"变为"展示真实运营数据"。

---

## Step 26.1 — Memory Runtime Integration

### 目标

让 Memory 的 CREATE / UPDATE / DELETE / HIT 四类事件全部写入 `analytics_memory_events` 表。

### 修改文件

| 文件 | 修改内容 |
| --- | --- |
| [src/adapters/sqlite_store.py](file:///d:/dma/day2/src/adapters/sqlite_store.py) | `SQLiteStoreAdapter` 新增可选 `analytics_pipeline` 注入；`store()` 后调用 `record_memory_insert`；`delete()` 后调用 `record_memory_delete`；`get_by_id()` 命中时调用 `record_memory_hit` |
| [src/core/retrieval.py](file:///d:/dma/day2/src/core/retrieval.py) | `Retriever` 新增可选 `analytics_pipeline` 注入；`retrieve()` 返回结果后对每条命中记忆调用 `record_memory_hit` |
| [src/core/memory_lifecycle.py](file:///d:/dma/day2/src/core/memory_lifecycle.py) | `MemoryLifecycleManager` 的 archive/merge 操作调用 `record_memory_update` |
| [main.py](file:///d:/dma/day2/main.py) | 在 `SQLiteStoreAdapter` / `Retriever` / `MemoryLifecycleManager` 实例化后注入 `analytics_pipeline` |

### 设计要点

- **可选注入**：`analytics_pipeline` 作为构造函数可选参数（默认 `None`），保持向后兼容，测试中不注入也能工作。
- **fire-and-forget**：所有 analytics 调用用 `asyncio.create_task` 包装（与 [registry.py:310](file:///d:/dma/day2/src/agents/registry.py#L310) 一致），失败仅日志，不影响主业务。
- **tenant_id / workspace_id 传递**：`Memory` 对象当前无 `tenant_id` 字段（[sqlite_store.py](file:///d:/dma/day2/src/adapters/sqlite_store.py) schema 无此列）。P0 方案：从调用上下文（`CognitiveAgent` / 请求）传递；若无法获取则用空字符串（平台全局）。
- **HIT 去重**：`get_by_id()` 每次访问都记一次 HIT 可能产生大量事件。P0 方案：每次调用都记（与 `access_count++` 一致）；P1 可考虑采样。

### 风险

| 风险 | 等级 | 缓解 |
| --- | --- | --- |
| `get_by_id()` 高频调用导致 analytics 写入放大 | 中 | fire-and-forget + `asyncio.to_thread` 不阻塞主路径；P1 可加采样 |
| `Memory` 对象无 tenant_id 字段 | 中 | P0 用空字符串（全局视图）；P1 考虑 schema 演进 |
| 注入失败导致 Memory 功能不可用 | 低 | `analytics_pipeline` 为可选参数，异常仅日志 |

### 测试方案

1. **单元测试**：`SQLiteStoreAdapter.store()` 后验证 `analytics_memory_events` 表有 INSERT 记录；`delete()` 后有 DELETE 记录；`get_by_id()` 后有 HIT 记录。
2. **集成测试**：通过 `Retriever.retrieve()` 触发检索，验证 HIT 事件数量与返回结果数一致。
3. **降级测试**：`analytics_pipeline=None` 时 Memory 功能正常，不抛异常。
4. **并发测试**：多线程并发 `store()` 验证无死锁（`_write_lock` 已存在）。

### 回滚方案

- `analytics_pipeline` 为可选参数，回滚只需在 `main.py` 移除注入语句（设为 `None`），Memory 功能立即恢复无 analytics 状态。
- 无 schema 变更，无需数据库回滚。

---

## Step 26.2 — Chat Runtime Integration

### 目标

让 `/chat` 和 `/chat/stream` 端点在每次对话后写入：
- `analytics_user_activity_daily`（用户日活）
- `analytics_token_usage_daily`（Token 消耗）
- `analytics_agent_runs`（将 `/chat` 视为一种 Agent Run）

### 修改文件

| 文件 | 修改内容 |
| --- | --- |
| [src/api/routes.py](file:///d:/dma/day2/src/api/routes.py) | `create_router` 接受可选 `analytics_pipeline` 参数；`/chat` 端点在 `agent.run()` 后调用 `record_chat_activity` + `record_chat_token_usage`；`/chat/stream` 在 `done` 事件后调用 |
| [src/core/agent.py](file:///d:/dma/day2/src/core/agent.py) | `CognitiveAgent.run()` 返回值增加 token 用量（从 LLM response.usage 提取）；或暴露 `last_token_usage` 属性供 routes 读取 |
| [main.py](file:///d:/dma/day2/main.py) | `create_router(agent)` 改为 `create_router(agent, analytics_pipeline=analytics_pipeline)` |

### 设计要点

- **Token 用量提取**：`CognitiveAgent.run()` 内部 LLM 调用（[agent.py:216](file:///d:/dma/day2/src/core/agent.py#L216)）的 `response.usage` 含 `prompt_tokens` / `completion_tokens`。需在 `run()` 中累计并暴露。P0 方案：在 `CognitiveAgent` 增加 `last_usage` 属性，`run()` 结束时填充。
- **tenant_id / user_id / workspace_id**：`ChatRequest` 当前可能不含这些字段（[routes.py:67](file:///d:/dma/day2/src/api/routes.py#L67)）。P0 方案：从 `require_auth` 的 `TokenPayload` 获取（需将 `/chat` 改为认证端点，或从 header 解析）。若 `/chat` 当前无认证，P0 用空字符串。
- **stream 端点**：在 `done` 事件 yield 后、break 前调用 analytics 记录。
- **失败降级**：analytics 写入失败不影响 `/chat` 返回 reply（与 Agent Registry 一致）。

### 风险

| 风险 | 等级 | 缓解 |
| --- | --- | --- |
| `/chat` 无认证，无法获取 tenant_id/user_id | 中 | P0 用空字符串（全局视图）；P1 加认证中间件 |
| `CognitiveAgent.run()` 未暴露 token 用量 | 中 | 需修改 `agent.py` 提取 `response.usage`，风险可控 |
| stream 端点 analytics 时机不准 | 低 | 在 `done` 事件后记录，此时 token 已全部产生 |
| 注入失败导致 `/chat` 不可用 | 低 | analytics 调用包裹在 try/except，失败仅日志 |

### 测试方案

1. **单元测试**：mock `analytics_pipeline`，调用 `/chat`，验证 `record_chat_activity` 和 `record_chat_token_usage` 被调用且参数正确。
2. **集成测试**：真实 `/chat` 调用后查询 `analytics_user_activity_daily` 和 `analytics_token_usage_daily` 表有新记录。
3. **stream 测试**：`/chat/stream` 完整消费后验证 analytics 记录。
4. **降级测试**：`analytics_pipeline=None` 时 `/chat` 正常返回。
5. **token 准确性测试**：验证 `agent.last_usage` 与 LLM `response.usage` 一致。

### 回滚方案

- `analytics_pipeline` 为 `create_router` 可选参数，回滚只需在 `main.py` 移除传参。
- `CognitiveAgent.last_usage` 为新增属性，不影响现有调用方。
- 无 schema 变更。

---

## Step 26.3 — Background Alert Evaluation

### 目标

让 `DashboardAlertEvaluator.evaluate_all()` 被定期调用，自动触发告警事件写入 `alert_events` 表；并在启动时播种 Dashboard 规则到 `alert_rules` 表。

### 修改文件

| 文件 | 修改内容 |
| --- | --- |
| [main.py](file:///d:/dma/day2/main.py) | 实例化 `DashboardAlertEvaluator(repo, alert_store)`；启动时调用 `seed_dashboard_rules("default")`；启动后台 `asyncio.create_task` 定时循环（每 60s）调用 `evaluate_all("default")` |
| 新增 `src/core/analytics/alert_scheduler.py`（可选） | 封装定时调度逻辑，避免 `main.py` 膨胀 |

### 设计要点

- **调度方式**：P0 用 `asyncio.create_task` + `asyncio.sleep(60)` 循环（与项目现有 `asyncio` 风格一致，不引入 `apscheduler`）。P1 可升级为 APScheduler。
- **租户范围**：P0 仅评估 `"default"` 租户（全局视图）。P1 遍历所有租户。
- **规则播种**：启动时调用 `seed_dashboard_rules("default")`，幂等（重复调用会创建重复规则，需先检查是否已存在 — `AlertStoreAdapter` 无 upsert，P0 用 `list_rules` 检查名称去重）。
- **冷却期**：`AlertStoreAdapter.get_active_rules()` 已实现冷却期逻辑，但 `DashboardAlertEvaluator` 直接构造 `AlertEvent` 写入，未走 `get_active_rules`。P0 方案：保持现状（每次评估都记录事件，可能产生重复告警）；P1 改为走 `get_active_rules` 过滤冷却期。
- **优雅关闭**：`asyncio.create_task` 的任务需在 FastAPI `shutdown` 事件中取消，避免进程退出时报错。

### 风险

| 风险 | 等级 | 缓解 |
| --- | --- | --- |
| 后台任务异常导致进程不稳定 | 中 | 循环内 try/except 包裹，单次评估失败不退出循环 |
| 重复播种规则 | 中 | 启动时先 `list_rules` 检查名称去重 |
| 告警风暴（无冷却期） | 中 | P0 接受；P1 接入 `get_active_rules` 冷却期 |
| `asyncio.create_task` 在某些部署中不持久 | 低 | FastAPI lifespan 事件管理任务生命周期 |
| 评估依赖 analytics 表有数据 | 中 | Step 26.1/26.2 完成后才有真实数据；空表时评估返回 0，不触发告警 |

### 测试方案

1. **单元测试**：mock `AnalyticsRepository` 返回超阈值指标，调用 `evaluate_all()`，验证 `alert_store.record_event` 被调用且 `alert_events` 表有记录。
2. **调度测试**：启动后台任务，等待 60s+，验证 `evaluate_all` 被调用（mock 计数器）。
3. **播种测试**：调用 `seed_dashboard_rules("default")` 两次，验证第二次不产生重复规则。
4. **降级测试**：`AnalyticsRepository` 抛异常时，后台任务不退出。
5. **已有测试**：[test_dashboard_v2_pipeline.py:403-440](file:///d:/dma/day2/tests/test_api/test_dashboard_v2_pipeline.py#L403-L440) 已覆盖 `evaluate_all` / `seed_dashboard_rules`，可直接复用。

### 回滚方案

- 后台任务为 `asyncio.create_task`，回滚只需注释 `main.py` 中的启动语句。
- `seed_dashboard_rules` 写入的规则可通过 `DELETE FROM alert_rules WHERE name LIKE 'agent_%' OR name LIKE 'token_%'` 清理。
- 无 schema 变更。

---

## Step 26.4 — Analytics Backfill Job

### 目标

将历史数据（`usage_events` / `notes` 表中已有的事件）回填到 `analytics_*` 表，使 Dashboard 能展示历史趋势，而非从接入时刻起才有数据。

### 修改文件

| 文件 | 修改内容 |
| --- | --- | 
| 新增 `scripts/backfill_analytics.py` | 独立回填脚本，从 `usage_events` / `notes` 读取历史记录，转换为 analytics 表格式批量写入 |
| 无 `src/` 修改 | 回填脚本作为运维工具，不集成到运行时 |

### 设计要点

- **数据源映射**：
  - `usage_events` (resource='agent_run') → `analytics_agent_runs`（从 `metadata_json` 提取 status/duration_ms/tokens）
  - `usage_events` (resource='memory') → `analytics_memory_events`（INSERT 事件）
  - `usage_events` (resource IN ('llm_call','embedding')) → `analytics_token_usage_daily`（按日聚合）
  - `usage_events` (distinct user_id by date) → `analytics_user_activity_daily`
  - `notes` 表 → `analytics_memory_events`（INSERT 事件，按 `timestamp` 日期）
- **幂等性**：回填前检查目标表是否已有同日数据，避免重复。或使用 `INSERT OR IGNORE` + 去重 ID。
- **批量写入**：避免逐条 `record_*`，用批量 `INSERT` 提升性能。
- **tenant_id 缺失**：历史 `usage_events` / `notes` 可能无 `tenant_id`。P0 用空字符串（全局）；P1 从 `workspace_id` 推导。
- **运行方式**：`python scripts/backfill_analytics.py [--days 90] [--dry-run]`，手动执行一次。

### 风险

| 风险 | 等级 | 缓解 |
| --- | --- | --- |
| 历史数据无 tenant_id | 中 | P0 用空字符串；不影响 Dashboard 全局视图 |
| `metadata_json` 格式不一致 | 中 | 解析失败时跳过该条，记录 warning |
| 回填产生重复数据 | 中 | 幂等检查 + `INSERT OR IGNORE` |
| 大量历史数据导致回填缓慢 | 低 | 批量 INSERT + 分批提交（每 1000 条） |
| 回填后 Dashboard 数据突变 | 低 | 这是预期行为（从 fallback 切换到真实数据） |

### 测试方案

1. **dry-run 测试**：`--dry-run` 模式只输出统计不写入，验证数据映射正确。
2. **幂等测试**：连续运行两次，第二次不产生新记录。
3. **数据完整性测试**：回填后 `analytics_*` 表记录数与 `usage_events` 对应 resource 记录数一致。
4. **Dashboard 验证**：回填后访问 Dashboard V2，验证趋势图有历史数据。
5. **回滚测试**：`DELETE FROM analytics_* WHERE created_at < '<backfill_time>'` 清理回填数据。

### 回滚方案

- 回填数据可通过 `DELETE FROM analytics_agent_runs WHERE id LIKE 'backfill_%'` 清理（回填时用特殊 ID 前缀）。
- 或记录回填时间戳，按时间删除。
- 脚本为独立运维工具，不影响运行时。

---

## Step 26.5 — Production Validation

### 目标

验证 Step 26.1-26.4 完成后，Dashboard V2 展示的是真实 analytics 数据，告警自动触发，老数据已补齐。

### 修改文件

| 文件 | 修改内容 |
| --- | --- |
| 新增 `scripts/validate_analytics.py` | 验证脚本：检查 analytics 表行数、Dashboard API 响应非零、告警事件存在 |
| 无 `src/` 修改 | 仅验证，不改代码 |

### 验证清单

1. **数据流入验证**：
   - 调用 `/chat` 一次 → 查询 `analytics_user_activity_daily` 今日有新记录
   - 调用 `/chat` 一次 → 查询 `analytics_token_usage_daily` 今日有新记录
   - 创建一条 Memory → 查询 `analytics_memory_events` 有 INSERT 记录
   - 检索 Memory → 查询 `analytics_memory_events` 有 HIT 记录
   - 删除 Memory → 查询 `analytics_memory_events` 有 DELETE 记录

2. **Dashboard 真实数据验证**：
   - `GET /dashboard/v2/overview` → DAU > 0、Token Cost > 0、Memory Hit Rate > 0
   - `GET /dashboard/v2/growth?days=30` → dau_series 非空
   - `GET /dashboard/v2/agent-performance?days=7` → call_volume_series 非空
   - `GET /dashboard/v2/memory-health?days=30` → growth_series 非空、type_distribution 非空
   - 验证 Repository 不再走 fallback（可通过日志 `analytics_query_failed` 是否出现判断）

3. **告警验证**：
   - 启动后台告警任务，等待 60s
   - 查询 `alert_rules` 表有 3 条 Dashboard 规则（agent_success_rate_low / agent_p95_latency_high / token_daily_cost_high）
   - 人为构造超阈值指标（如临时调低 `agent_success_rate_low` 阈值到 200%）→ 等待下次评估 → 查询 `alert_events` 表有新事件
   - `GET /alerts/rules` 返回 Dashboard 规则
   - `GET /alerts/events` 返回触发的告警

4. **回填验证**：
   - 运行 `backfill_analytics.py --days 90`
   - 查询 `analytics_*` 表有 90 天历史数据
   - Dashboard Growth Tab 90 天范围展示完整趋势

5. **前端验证**：
   - 访问 `/dashboard-v2` Overview → KPI 卡非零
   - Growth Tab → 趋势图有数据点
   - Memory Health Tab → 类型分布饼图有切片
   - Cost Analytics Tab → Token 趋势非空
   - Alerts Tab → 规则列表有 3 条 Dashboard 规则

### 风险

| 风险 | 等级 | 缓解 |
| --- | --- | --- |
| 验证发现数据仍为空 | 中 | 检查 analytics_pipeline 注入是否生效、fire-and-forget 任务是否被 GC |
| 告警未触发 | 中 | 检查后台任务是否运行、阈值是否合理 |
| 回填后 Dashboard 数据反而变少 | 低 | 可能是 fallback 数据源与 analytics 数据源范围不一致，属预期 |
| 性能下降 | 低 | analytics 写入为 async + to_thread，不阻塞主路径 |

### 测试方案

1. **端到端测试**：`validate_analytics.py` 自动化执行上述验证清单，输出 PASS/FAIL 报告。
2. **回归测试**：运行现有 `pytest`（120 tests）确保无回归。
3. **性能测试**：对比接入前后 `/chat` P95 延迟，确认无显著退化（< 5%）。
4. **监控**：接入后观察 24h，确认 analytics 表持续增长、无异常日志。

### 回滚方案

- 验证脚本为只读，无需回滚。
- 若发现严重问题，按 Step 26.1-26.4 各自的回滚方案逐步回退。
- 最终回退点：在 `main.py` 移除所有 `analytics_pipeline` 注入和后台任务，恢复到 Phase 25 状态（Dashboard 走 fallback）。

---

## 实施顺序与依赖

```
Step 26.1 (Memory)  ──┐
                      ├──→ Step 26.4 (Backfill) ──→ Step 26.5 (Validation)
Step 26.2 (Chat)    ──┤
                      │
Step 26.3 (Alerts)  ──┘
```

- 26.1 / 26.2 / 26.3 可并行开发（互不依赖）。
- 26.4 依赖 26.1/26.2 完成（回填逻辑需与运行时写入逻辑一致）。
- 26.5 依赖 26.1-26.4 全部完成。

## 不在 Phase 26 范围内

- 不新增 API 端点（Dashboard V2 API 契约不变）
- 不修改数据库 schema（analytics 表结构不变）
- 不重构后端（`AnalyticsStore` / `AnalyticsPipeline` / `DashboardAlertEvaluator` 代码不变，仅增加调用点）
- 不进入 Phase 27（正式实施）
