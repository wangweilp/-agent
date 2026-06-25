# PHASE_27_REVIEW_REPORT.md

## 审核结论

**FAIL**

存在 1 个 BLOCKER 级别问题：`_record_memory_event` 中的 `asyncio.create_task` 在 `asyncio.to_thread` 线程池上下文中无一效，导致 **Agent 内部路径（检索、工具调用）产生的所有 Memory Analytics 事件静默丢失**。虽然 try/except 兜底避免崩溃，但数据链路实际断开。

---

## BLOCKER

### B1. `asyncio.create_task` 在非异步线程上下文中失败 — Memory Analytics 事件静默丢失

**文件**: [src/adapters/sqlite_store.py](file:///d:/dma/day2/src/adapters/sqlite_store.py#L127-L133)

**问题描述**:

`_record_memory_event()` 方法（line 107-139）使用 `asyncio.create_task()` 触发 analytics 写入。该方法被 `store()`、`delete()`、`get_by_id()`、`update_status()` 调用。在以下运行时路径中，这些方法在非异步线程上下文中执行，`asyncio.get_running_loop()` 抛出 `RuntimeError: no running event loop`：

1. **Agent 内部检索路径** (`/chat` → `asyncio.to_thread(agent.run)` → `_retrieve_memories()` → `retrieval_service.retrieve()` → `get_by_id()` → `_record_memory_event`):
   - `agent.run()` 在 [src/api/routes.py:120](file:///d:/dma/day2/src/api/routes.py#L120) 通过 `asyncio.to_thread` 调用，运行在线程池线程中，该线程无事件循环。
   - **影响**: 每次 `/chat` 请求中 Agent 检索记忆时，`record_memory_hit` 事件全部丢失。

2. **Agent 工具执行路径** (`agent.run()` → `_execute_tool_call()` → `ThreadPoolExecutor` → `_tool_executor.execute()` → `store()`/`get_by_id()` → `_record_memory_event`):
   - `_execute_tool_call()` 在 [src/core/agent.py:716](file:///d:/dma/day2/src/core/agent.py#L716) 使用 `concurrent.futures.ThreadPoolExecutor`，运行在独立线程中。
   - **影响**: `remember` 工具触发 `store()` 的 `record_memory_insert` 事件丢失；`recall` 工具触发 `get_by_id()` 的 `record_memory_hit` 事件丢失。

3. **MemoryWriteWorker 线程路径** (`_fire_and_forget_remember` → `MemoryWriteWorker` → `store()`):
   - Worker 线程执行 `store()`，同样无事件循环。
   - **影响**: 异步入队的 `remember` 操作产生的 INSERT 事件丢失。

**直接 API 路径不受影响**: `GET /memory/{id}`、`PATCH /memory/{id}`、`DELETE /memory/{id}` 等路由直接调用 `store.get_by_id()` / `store.store()` 等，运行在 FastAPI async handler 线程中，`asyncio.create_task` 正常工作。

**数据影响**:
- `analytics_memory_events` 表仅能收到来自直接 API 操作的 Memory 事件，Agent 内部路径（占绝大多数 Memory 操作）的事件全部丢失。
- Memory Hit Rate 指标严重偏低（Agent 检索记忆是主要 HIT 来源）。
- Memory Growth 指标偏低（Agent 通过 `remember` 工具写入是主要 INSERT 来源）。

**验证方法**: 在 `_record_memory_event` 中加 `logger.info` 打印当前线程名和 `asyncio.get_running_loop()` 结果，然后发一次 `/chat` 请求触发 Agent 检索。

**参考**: [registry.py:310-311](file:///d:/dma/day2/src/agents/registry.py#L310-L311) 的 `asyncio.create_task` 模式在 `AgentRegistry.run()` 中工作，因为 `run()` 是从 async handler 直接调用的（非 `to_thread` 包装）。但 `sqlite_store.py` 的方法被 `to_thread` 包装后调用，继承模式不适用。

---

## HIGH

### H1. API 路由中的 UPDATE 操作被记录为 INSERT — 指标失真

**文件**: [src/api/routes.py](file:///d:/dma/day2/src/api/routes.py)

**路由**: `PATCH /memory/{memory_id}` (line 327-351), `POST /memory/{memory_id}/archive` (line 408-428), `POST /memory/merge` (line 368-406)

**问题描述**: 这些路由调用 `store.store(m)` 来更新已有记忆。`store()` 方法使用 `INSERT ... ON CONFLICT(id) DO UPDATE`（UPSERT），但始终触发 `record_memory_insert`（[sqlite_store.py:290-293](file:///d:/dma/day2/src/adapters/sqlite_store.py#L290-L293)）。

**影响**:
- `PATCH /memory/{memory_id}`: 更新 Memory 内容被计为 INSERT → 虚增 net_growth
- `POST /memory/{memory_id}/archive`: 归档被计为 INSERT → 虚增 net_growth
- `POST /memory/merge`: merge 操作中每个 `store()` 调用都计为 INSERT → 严重虚增 net_growth（如合并 2 条记忆 + 保存 primary = 3 次 INSERT）

**指标偏差**: `net_memory_growth = INSERT_count - DELETE_count` 会显著偏高。

### H2. `tenant_id` 数据质量问题 — `TokenPayload.workspace_id` 被当作 `tenant_id` 使用

**文件**: [src/api/routes.py:124-125](file:///d:/dma/day2/src/api/routes.py#L124-L125), [src/api/routes.py:164-165](file:///d:/dma/day2/src/api/routes.py#L164-L165)

```python
tenant_id=payload.workspace_id if payload else "",
workspace_id=payload.workspace_id if payload else "",
```

**问题描述**: `TokenPayload`（[src/core/auth.py:86-92](file:///d:/dma/day2/src/core/auth.py#L86-L92)）只有 `user_id`、`workspace_id`、`role`、`email` 字段，**没有 `tenant_id`**。实现将 `workspace_id` 同时填入 `tenant_id` 和 `workspace_id` 参数。

**影响**: 在单租户场景下影响有限（workspace_id 作为 tenant_id 代理），但在多租户场景下，`analytics_*` 表中的 `tenant_id` 列实际存储的是 `workspace_id`，导致：
- 租户级 analytics 查询返回错误结果
- `tenant_id` 与 `workspace_id` 的语义混淆，未来难以修正

**PHASE_26 计划预期**: 计划明确说 "P0 用空字符串（全局视图）"（[PHASE_26_IMPLEMENTATION_PLAN.md:88](file:///d:/dma/day2/PHASE_26_IMPLEMENTATION_PLAN.md#L88)）。当前实现使用 `workspace_id` 作为 `tenant_id` 偏离了计划。

### H3. `agent.last_usage` 仅捕获最后轮次 LLM 调用的 token usage — 多轮 Tool Calling 时 token 数据丢失

**文件**: [src/core/agent.py:254](file:///d:/dma/day2/src/core/agent.py#L254)

**问题描述**: `run()` 方法在 tool calling 循环中，每轮 LLM 调用后都调用 `self._capture_usage(response)`（line 254），但 `_capture_usage` 直接**覆盖** `self._last_usage`（[agent.py:205-208](file:///d:/dma/day2/src/core/agent.py#L205-L208)），而非累加。routes 层在 `agent.run()` 返回后读取 `agent.last_usage`，仅获取最后一轮 LLM 调用的 token 数。

**影响**: 当 Agent 需要多轮 tool calling 时（如先 recall 再回复），中间轮次的 LLM token 用量全部丢失。`analytics_token_usage_daily` 指标偏低。

**示例**: Agent 调用 `recall` 工具（LLM 轮次 1: 500 tokens），然后生成最终回复（LLM 轮次 2: 800 tokens）。routes 层仅记录 800 tokens，丢失 500 tokens。

---

## MEDIUM

### M1. `delete()` 和 `update_status("deleted")` 不传 `memory_type` — DELETE 事件缺失 memory_type 信息

**文件**: [src/adapters/sqlite_store.py:312](file:///d:/dma/day2/src/adapters/sqlite_store.py#L312), [src/adapters/sqlite_store.py:387](file:///d:/dma/day2/src/adapters/sqlite_store.py#L387)

```python
self._record_memory_event("record_memory_delete")  # 未传 memory_type
```

**影响**: `analytics_memory_events` 表中 DELETE 事件的 `memory_type` 列为空字符串。按类型统计 Memory 操作时，DELETE 事件无法归入具体类型。

**对比**: `store()` 和 `get_by_id()` 正确传递了 `memory_type=memory.memory_type`。

### M2. `_record_chat_analytics` 中两个 `asyncio.create_task` 共享一个 try/except — 部分失败风险

**文件**: [src/api/routes.py:83-108](file:///d:/dma/day2/src/api/routes.py#L83-L108)

**问题描述**: `record_chat_activity` 和 `record_chat_token_usage` 的 `asyncio.create_task` 调用在同一个 try/except 块中。如果 `record_chat_activity` 的 `create_task` 抛出异常（如 RuntimeError），`record_chat_token_usage` 不会被调度。

**实际影响**: 当前两个 `create_task` 调用在 async handler 的同一线程中执行，不太可能一个成功一个失败。但代码结构不够健壮。

### M3. `Retriever.retrieve()` 路径未记录 `record_memory_hit` — 检索分析覆盖不完整

**文件**: [src/core/retrieval.py](file:///d:/dma/day2/src/core/retrieval.py)（未修改）

**问题描述**: PHASE_26_IMPLEMENTATION_PLAN.md Step 26.1 明确要求 `Retriever` 在 `retrieve()` 返回后对每条命中记忆调用 `record_memory_hit`。当前实现仅在 `SQLiteStoreAdapter.get_by_id()` 单条查询时记录 HIT，但 `Retriever.retrieve()` 路径（Agent 内部使用的主要检索方式）未记录。

**与 B1 的关系**: 即使修复了 B1 的线程问题，`Retriever.retrieve()` 路径仍然缺少 HIT 记录。不过由于 B1 的存在，`get_by_id()` 的 HIT 记录在 Agent 路径中也已失效，实际影响暂时被 B1 掩盖。

**注意**: 该问题是计划偏差（计划要求但未实施），不是代码 bug。

### M4. `/chat` 异常处理中重复 `logger.exception`

**文件**: [src/api/routes.py:131-132](file:///d:/dma/day2/src/api/routes.py#L131-L132)

```python
logger.exception("chat endpoint error")
logger.exception("chat_endpoint_error")
```

**问题描述**: 同一 except 块中有两行 `logger.exception` 调用，会产生两条重复的异常日志（含完整 traceback）。这是代码冗余，不影响功能。

---

## LOW

### L1. `store()` 方法对 UPSERT 操作一律记录 INSERT — 已知限制

**文件**: [src/adapters/sqlite_store.py:290-293](file:///d:/dma/day2/src/adapters/sqlite_store.py#L290-L293)

**问题描述**: `store()` 使用 `INSERT ... ON CONFLICT(id) DO UPDATE`（UPSERT），但始终调用 `record_memory_insert`。当操作为实际 UPDATE 时，事件类型不准确。

**已知状态**: 已在 [PHASE_27_IMPLEMENTATION_REPORT.md:336](file:///d:/dma/day2/PHASE_27_IMPLEMENTATION_REPORT.md#L336) 中记录为已知限制。`net_growth = INSERT - DELETE` 近似方案。

### L2. `_record_memory_event` 失败时 `logger.warning` 不带 `extra` 中的 `tenant_id`/`workspace_id`

**文件**: [src/adapters/sqlite_store.py:135-139](file:///d:/dma/day2/src/adapters/sqlite_store.py#L135-L139)

**问题描述**: 日志仅记录 `method_name`，不包含 `tenant_id`/`workspace_id` 上下文，排查问题时难以定位。

### L3. `analytics_token_usage_daily` 唯一约束为 `(tenant_id, workspace_id, event_date)` — 同一 workspace 每日仅一条记录

**文件**: [src/core/analytics/analytics_store.py:88](file:///d:/dma/day2/src/core/analytics/analytics_store.py#L88)

```sql
CREATE UNIQUE INDEX IF NOT EXISTS idx_atud_unique ON analytics_token_usage_daily(tenant_id, workspace_id, event_date);
```

**问题描述**: 使用 `ON CONFLICT ... DO UPDATE SET prompt_tokens = prompt_tokens + excluded.prompt_tokens` 进行累加。这是正确的设计，但需要注意：如果 `tenant_id` 为 `workspace_id`（H2 问题），不同 workspace 的 token 不会被错误合并（因为 `workspace_id` 也参与唯一约束）。当前唯一约束设计合理，但 H2 修复后需确保 `tenant_id` 唯一性逻辑正确。

---

## 与实施计划一致性检查

### Step 27.1 — Memory Runtime Integration

| 计划要求 | 实施状态 | 评估 |
| --- | --- | --- |
| `SQLiteStoreAdapter` 新增可选 `analytics_pipeline` 注入 | ✅ 已实施 | 一致 |
| `store()` 后调用 `record_memory_insert` | ✅ 已实施 | 一致 |
| `delete()` 后调用 `record_memory_delete` | ✅ 已实施 | 一致 |
| `get_by_id()` 命中时调用 `record_memory_hit` | ✅ 已实施 | 一致 |
| `Retriever` 新增 `analytics_pipeline` 注入 + `retrieve()` 调用 `record_memory_hit` | ❌ 未实施 | **偏差** — 计划要求但未实施（M3） |
| `MemoryLifecycleManager` 的 archive/merge 调用 `record_memory_update` | ❌ 未实施 | **偏差** — 计划要求但未实施 |
| `asyncio.create_task` 包装（fire-and-forget） | ⚠️ 部分失效 | **BLOCKER** — 在 `to_thread` 上下文中无一效（B1） |
| `main.py` 注入 `analytics_pipeline` 到 `memory_store` | ✅ 已实施 | 一致 |

### Step 27.2 — Chat Runtime Integration

| 计划要求 | 实施状态 | 评估 |
| --- | --- | --- |
| `create_router` 接受可选 `analytics_pipeline` 参数 | ✅ 已实施 | 一致 |
| `/chat` 端点调用 `record_chat_activity` + `record_chat_token_usage` | ✅ 已实施 | 一致 |
| `/chat/stream` 在 `done` 事件后调用 analytics | ✅ 已实施 | 一致 |
| `CognitiveAgent` 暴露 `last_usage` 属性 | ✅ 已实施 | 一致 |
| `tenant_id`/`user_id` 从 `TokenPayload` 获取 | ⚠️ 部分实施 | **偏差** — `tenant_id` 使用 `workspace_id` 替代（H2） |
| `main.py` 传入 `analytics_pipeline` 到 `create_router` | ✅ 已实施 | 一致 |
| Token 用量从 `response.usage` 提取 | ⚠️ 部分实施 | **偏差** — 仅捕获最后轮次，多轮丢失（H3） |

### Step 27.3 — Background Alert Evaluation

| 计划要求 | 实施状态 | 评估 |
| --- | --- | --- |
| `DashboardAlertEvaluator` 实例化 | ✅ 已实施 | 一致 |
| 启动时幂等播种 `seed_dashboard_rules("default")` | ✅ 已实施 | 一致 |
| `asyncio.create_task` 定时循环（每 60s）调用 `evaluate_all("default")` | ✅ 已实施 | 一致 |
| `asyncio.to_thread` 包装同步 `evaluate_all` | ✅ 已实施 | 一致 |
| 循环内 try/except 兜底 | ✅ 已实施 | 一致 |
| FastAPI `lifespan` 管理任务生命周期 | ✅ 已实施 | 一致 |
| 仅评估 `"default"` 租户 | ✅ 已实施 | 一致 |

---

## 是否允许进入 Phase 28

**NO**

**阻止原因**: BLOCKER B1（`asyncio.create_task` 在非异步线程上下文失效）导致 **Agent 内部路径的所有 Memory Analytics 事件静默丢失**。这是运行时数据链路的实质性断裂，而非理论问题。

**修复建议方向**（不实施，仅供参考）:
- 将 `_record_memory_event` 中的 `asyncio.create_task` 替换为 `asyncio.get_running_loop().call_soon_threadsafe()` 或使用 `asyncio.run_coroutine_threadsafe()`
- 或将 analytics 记录从 `sqlite_store.py` 的同步方法中移出，改为在 routes 层（async context）中调用

**进入 Phase 28 的前提条件**:
1. B1 必须修复并验证（发 `/chat` 请求 → 查询 `analytics_memory_events` 有 INSERT 和 HIT 记录）
2. H1、H2、H3 建议修复（至少 H1 和 H3）
3. M1、M3 建议修复