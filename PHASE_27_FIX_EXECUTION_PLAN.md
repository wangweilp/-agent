# PHASE_27_FIX_EXECUTION_PLAN

基于 [PHASE_27_REVIEW_REPORT.md](file:///d:/dma/day2/PHASE_27_REVIEW_REPORT.md) 的审核结论制定。

---

## 修复范围

仅修改以下 4 个文件：

| 文件 | B1 | H1 | H2 | H3 | M1 | M2 | M3 | M4 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| [src/adapters/sqlite_store.py](file:///d:/dma/day2/src/adapters/sqlite_store.py) | x | x | | | x | | | |
| [src/core/agent.py](file:///d:/dma/day2/src/core/agent.py) | | | | x | | | | |
| [src/api/routes.py](file:///d:/dma/day2/src/api/routes.py) | | | x | | | x | | x |
| [main.py](file:///d:/dma/day2/main.py) | | | | | | | | |

M3 不在本次修复范围（见下方说明）。

---

## Priority 1 — BLOCKER

### B1: `asyncio.create_task` 在非异步线程上下文中失败

**根因**:

`_record_memory_event()` 使用 `asyncio.create_task()` 调度 async coroutine。该方法在以下三种非异步线程上下文中被调用时，`asyncio.get_running_loop()` 抛出 `RuntimeError: no running event loop`：

| 调用路径 | 线程环境 | 来源 |
| --- | --- | --- |
| `/chat` → `asyncio.to_thread(agent.run)` → `retrieve()` → `get_by_id()` | 线程池线程 | [routes.py:120](file:///d:/dma/day2/src/api/routes.py#L120) |
| `agent.run()` → `_execute_tool_call()` → `ThreadPoolExecutor` → `store()`/`get_by_id()` | 独立线程 | [agent.py:716](file:///d:/dma/day2/src/core/agent.py#L716) |
| `MemoryWriteWorker` 线程 → `store()` | Worker 线程 | MemoryWriteWorker |

try/except 仅捕获异常并记录日志，analytics 数据静默丢失。

**参考对比**: [registry.py:310-311](file:///d:/dma/day2/src/agents/registry.py#L310-L311) 的 `asyncio.create_task` 模式在 `AgentRegistry.run()` 中工作，因为 `run()` 从 async handler 直接调用（非 `to_thread` 包装）。`sqlite_store.py` 的方法被 `to_thread` / `ThreadPoolExecutor` 包装后调用，继承模式不适用。

**修改文件**: [src/adapters/sqlite_store.py](file:///d:/dma/day2/src/adapters/sqlite_store.py)

**修改方式**:

采用 **双路径调度 + 惰性事件循环捕获** 方案：

1. 在 `__init__` 中新增 `self._analytics_loop = None`（懒捕获的事件循环引用）
2. 在 `_record_memory_event()` 中：
   - 先尝试 `asyncio.get_running_loop()` → 成功则走快速路径 `asyncio.create_task()`，同时将 loop 引用存入 `self._analytics_loop`
   - 若 `RuntimeError`（无线程局部事件循环），走线程安全路径：使用 `asyncio.run_coroutine_threadsafe(coro, self._analytics_loop)` 将 coroutine 调度到主事件循环
   - 所有异常用 `logger.warning` 兜底，不抛出

**原理**:
- `asyncio.run_coroutine_threadsafe(coro, loop)` 是标准库提供的线程安全 API，可从任意线程向目标事件循环提交 coroutine
- coroutine 内部调用 `asyncio.to_thread` 执行 SQLite 写入，在事件循环线程中正常调度
- 惰性捕获：首次从 async 上下文调用 `_record_memory_event` 时自动捕获 loop；若首次调用来自 sync 线程，loop 尚未捕获，事件被安全丢弃（后续 async 调用会捕获）

**代码变更概要**:

```
__init__:
  + self._analytics_loop = None

_record_memory_event:
  - asyncio.create_task(...) 直接调用
  + 先 try get_running_loop → create_task（快速路径）
  + 再 RuntimeError → run_coroutine_threadsafe（线程安全路径）
  + 惰性捕获 loop 引用
```

**风险分析**:

| 风险 | 等级 | 缓解 |
| --- | --- | --- |
| 惰性捕获的 loop 在 shutdown 后关闭 | 低 | `is_closed()` 检查 |
| `run_coroutine_threadsafe` 返回的 Future 未 await | 低 | fire-and-forget 设计，无需 await |
| 首次调用来自 sync 线程时 loop 未捕获 | 低 | 后续 async 调用会自动捕获；丢失第一个事件可接受 |
| 与现有 `asyncio.create_task` 调用冲突 | 无 | 两者完全兼容，快速路径优先使用 `create_task` |

**测试方案**:

1. 单元测试：在 `asyncio.to_thread` 中调用 `store()` → 验证 `analytics_memory_events` 有 INSERT 记录
2. 集成测试：发 `/chat` 请求 → 查询 `analytics_memory_events` 有 HIT 和 INSERT 记录
3. 线程安全测试：从 `ThreadPoolExecutor` 中调用 `store()` → 验证 analytics 记录正常
4. 降级测试：loop 未捕获时 → 不崩溃，不抛异常
5. 回归测试：直接 API 调用（`GET /memory/{id}`）→ analytics 记录正常

---

## Priority 2 — HIGH

### H1: `store()` 对 UPDATE 操作记录 INSERT

**根因**:

`store()` 使用 `INSERT ... ON CONFLICT(id) DO UPDATE`（UPSERT），但始终调用 `record_memory_insert`。SQLite 的 `changes()` 在 UPSERT 场景下对 INSERT 和 UPDATE 均返回 1，无法区分。

**影响路径**:

| 路由 | 操作 | 当前记录 | 应记录 |
| --- | --- | --- | --- |
| `PATCH /memory/{id}` | UPDATE | INSERT | UPDATE |
| `POST /memory/{id}/archive` | UPDATE | INSERT | UPDATE |
| `POST /memory/merge` | UPDATE (secondary x N + primary) | INSERT x (N+1) | UPDATE x (N+1) |

**修改文件**: [src/adapters/sqlite_store.py](file:///d:/dma/day2/src/adapters/sqlite_store.py)

**修改方式**:

在 `store()` 方法内部，在写锁内执行 UPSERT 前先查询该 ID 是否存在，据此判断 INSERT vs UPDATE：

```python
def store(self, memory: Memory) -> str:
    archived_at = ...
    with self._write_lock:
        with self._db.conn:
            # 查询是否已存在（在写锁内，原子性保证）
            row = self._db.execute(
                "SELECT 1 FROM notes WHERE id = ?", (memory.id,)
            ).fetchone()
            is_update = row is not None

            # 原有 UPSERT 逻辑不变
            self._db.execute("INSERT INTO notes ... ON CONFLICT(id) DO UPDATE ...", ...)
            ...

    # 根据实际操作类型记录 analytics
    if is_update:
        self._record_memory_event("record_memory_update", memory_type=memory.memory_type)
    else:
        self._record_memory_event("record_memory_insert", memory_type=memory.memory_type)

    return memory.id
```

**设计要点**:
- SELECT 查询在 `with self._write_lock` 内，与 UPSERT 原子
- 主键查询成本极低（索引查找）
- 不修改 `store()` 的方法签名，所有调用方无需改动
- `record_memory_update` 方法在 `AnalyticsPipeline` 中已定义（[analytics_pipeline.py:81-97](file:///d:/dma/day2/src/core/analytics/analytics_pipeline.py#L81-L97)），可直接使用

**风险分析**:

| 风险 | 等级 | 缓解 |
| --- | --- | --- |
| 额外 SELECT 增加延迟 | 低 | 主键索引查询，< 1ms |
| 锁内查询增加持锁时间 | 低 | SELECT 在主键上，微秒级 |
| `record_memory_update` 未测试 | 低 | 与 `record_memory_insert` 同路径，复用现有测试基础设施 |

**测试方案**:

1. 首次 `store()` → `analytics_memory_events` 有 event_type=INSERT 记录
2. 再次 `store()` 同一 ID → `analytics_memory_events` 有 event_type=UPDATE 记录
3. `PATCH /memory/{id}` → event_type=UPDATE
4. `POST /memory/{id}/archive` → event_type=UPDATE
5. `POST /memory/merge` → 每个 `store()` 调用产生 event_type=UPDATE

---

### H2: `tenant_id` 使用 `workspace_id` 替代

**根因**:

`TokenPayload`（[auth.py:86-92](file:///d:/dma/day2/src/core/auth.py#L86-L92)）只有 `user_id`、`workspace_id`、`role`、`email`，**没有 `tenant_id` 字段**。实施时用 `workspace_id` 填入 `tenant_id` 参数。

PHASE_26_IMPLEMENTATION_PLAN.md Step 26.2 明确要求：**"P0 用空字符串（全局视图）"**（[PHASE_26_IMPLEMENTATION_PLAN.md:88](file:///d:/dma/day2/PHASE_26_IMPLEMENTATION_PLAN.md#L88)）。

**修改文件**: [src/api/routes.py](file:///d:/dma/day2/src/api/routes.py)

**修改方式**:

将 `_record_chat_analytics` 调用中的 `tenant_id` 参数从 `payload.workspace_id` 改为空字符串 `""`：

```python
# 修改前（/chat 和 /chat/stream 两处）:
_record_chat_analytics(
    analytics_pipeline=analytics_pipeline,
    tenant_id=payload.workspace_id if payload else "",   # ← 错误
    workspace_id=payload.workspace_id if payload else "",
    ...
)

# 修改后:
_record_chat_analytics(
    analytics_pipeline=analytics_pipeline,
    tenant_id="",                                          # ← 空字符串，全局视图
    workspace_id=payload.workspace_id if payload else "",
    ...
)
```

**设计要点**:
- 与 PHASE_26 计划完全一致
- `workspace_id` 继续从 `payload.workspace_id` 获取（正确）
- `tenant_id` 使用空字符串（全局视图），待 `TokenPayload` 未来增加 `tenant_id` 字段后再回填
- 不影响现有 analytics 查询（所有查询已经支持 tenant_id="" 作为全局视图）

**风险分析**:

| 风险 | 等级 | 缓解 |
| --- | --- | --- |
| 多租户场景下 analytics 无法区分租户 | 低 | P0 阶段无多租户需求；TokenPayload 增加 tenant_id 字段后回填 |
| 与 `analytics_agent_runs` 的 tenant_id 不一致 | 低 | `AgentRegistry` 路径也使用空字符串（registry.py 中 tenant_id 默认为 ""） |

**测试方案**:

1. 发 `/chat` 请求 → 查询 `analytics_user_activity_daily` 中 tenant_id 为空字符串
2. 验证 `analytics_token_usage_daily` 中 tenant_id 为空字符串
3. 验证 Dashboard V2 的全局视图查询正常

---

### H3: `agent.last_usage` 仅覆盖不累加

**根因**:

`_capture_usage()` 直接覆盖 `self._last_usage`（[agent.py:205-208](file:///d:/dma/day2/src/core/agent.py#L205-L208)），而非累加。Agent 的 tool calling 循环中每轮 LLM 调用都覆盖，routes 层仅拿到最后一轮的 token 数。

**修改文件**: [src/core/agent.py](file:///d:/dma/day2/src/core/agent.py)

**修改方式**:

两处修改：

1. **`run()` 方法开头重置** `_last_usage` 为 `None`（约 line 217，`t_start` 之后）：

```python
def run(self, user_input: str) -> str:
    t_start = time.monotonic()
    self._current_trace_id = str(uuid.uuid4())
    self._last_usage = None  # Phase 27.2 fix: 每次 run 重置
    ...
```

2. **`_capture_usage()` 改为累加**（line 192-210）：

```python
def _capture_usage(self, response: Any) -> None:
    try:
        usage = getattr(response, "usage", None)
        if usage is None:
            return
        prompt_tokens = getattr(usage, "prompt_tokens", None) or 0
        completion_tokens = getattr(usage, "completion_tokens", None) or 0

        if self._last_usage is None:
            self._last_usage = {"prompt_tokens": 0, "completion_tokens": 0}

        self._last_usage["prompt_tokens"] += int(prompt_tokens)
        self._last_usage["completion_tokens"] += int(completion_tokens)
    except Exception:
        logger.debug("capture_usage_failed", exc_info=True)
```

**设计要点**:
- 每次 `run()` 调用前重置，避免跨请求污染
- 累加而非覆盖，覆盖所有 tool calling 轮次
- `_best_effort()` 路径（line 752-763）的 LLM 调用不调用 `_capture_usage`，但该路径仅在异常退出时使用，token 损失可接受
- 不影响 `run_stream()` 路径（流式模式不捕获 usage，已知限制）

**风险分析**:

| 风险 | 等级 | 缓解 |
| --- | --- | --- |
| `_best_effort` 路径漏记 token | 低 | 仅异常退出时走此路径，极少发生 |
| 并发请求共享 `_last_usage` | 低 | `CognitiveAgent` 为单例，P0 单请求场景可接受；P1 可加锁 |
| 多轮 tool calling 中某轮 LLM 返回无 usage | 低 | `if usage is None: return`，不累加 0，不影响已有累计 |

**测试方案**:

1. 单轮 LLM 调用（无 tool calling）→ `last_usage` = 该轮 token 数
2. 多轮 LLM 调用（tool calling）→ `last_usage` = 各轮 token 数之和
3. 连续两次 `run()` → 第二次 `last_usage` 不包含第一次的 token（已重置）
4. LLM 返回无 usage → `last_usage` 不崩溃，保持之前的值

---

## Priority 3 — MEDIUM

### M1: `delete()` 和 `update_status("deleted")` 不传 `memory_type`

**根因**: 删除时未查询 memory_type，`_record_memory_event` 的 `memory_type` 参数使用默认值 `""`。

**修改文件**: [src/adapters/sqlite_store.py](file:///d:/dma/day2/src/adapters/sqlite_store.py)

**修改方式**:

1. **`delete()`** (line 297-312)：在删除前查询 `memory_type`：

```python
def delete(self, memory_id: str) -> None:
    # 删除前获取 memory_type
    row = self._db.execute(
        "SELECT memory_type FROM notes WHERE id = ?", (memory_id,)
    ).fetchone()
    memory_type = row["memory_type"] if row else ""

    with self._write_lock:
        with self._db.conn:
            self._db.execute("DELETE FROM memory_entities WHERE memory_id = ?", (memory_id,))
            self._db.execute("DELETE FROM relations WHERE memory_id = ?", (memory_id,))
            self._db.execute("DELETE FROM notes WHERE id = ?", (memory_id,))

    self._record_memory_event("record_memory_delete", memory_type=memory_type)
```

2. **`update_status()`** (line 377-387)：在状态更新后查询 `memory_type`：

```python
def update_status(self, memory_id: str, status: str) -> None:
    with self._write_lock:
        with self._db.conn:
            self._db.execute(
                "UPDATE notes SET status = ? WHERE id = ?", (status, memory_id)
            )

    if status == "deleted":
        row = self._db.execute(
            "SELECT memory_type FROM notes WHERE id = ?", (memory_id,)
        ).fetchone()
        memory_type = row["memory_type"] if row else ""
        self._record_memory_event("record_memory_delete", memory_type=memory_type)
```

**风险**: 低 — 主键查询成本极低，不影响业务逻辑。

**测试方案**: 删除一条 semantic 类型记忆 → 验证 `analytics_memory_events` 中 DELETE 事件的 `memory_type="semantic"`。

---

### M2: `_record_chat_analytics` 中两个 `create_task` 共享 try/except

**根因**: `record_chat_activity` 和 `record_chat_token_usage` 在同一个 try/except 块中，第一个失败会导致第二个不被调度。

**修改文件**: [src/api/routes.py](file:///d:/dma/day2/src/api/routes.py)

**修改方式**: 将两个 `create_task` 调用拆分为独立的 try/except：

```python
def _record_chat_analytics(...):
    if analytics_pipeline is None:
        return

    # 记录用户活动
    try:
        asyncio.create_task(
            analytics_pipeline.record_chat_activity(
                tenant_id=tenant_id or "",
                workspace_id=workspace_id or "",
                user_id=user_id or "",
                messages=1,
                active_minutes=1,
            )
        )
    except Exception:
        logger.warning("chat_activity_record_failed", exc_info=True)

    # 记录 Token 用量
    try:
        prompt_tokens = 0
        completion_tokens = 0
        if usage is not None:
            prompt_tokens = int(usage.get("prompt_tokens", 0) or 0)
            completion_tokens = int(usage.get("completion_tokens", 0) or 0)
        asyncio.create_task(
            analytics_pipeline.record_chat_token_usage(
                tenant_id=tenant_id or "",
                workspace_id=workspace_id or "",
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cost_usd=0.0,
            )
        )
    except Exception:
        logger.warning("chat_token_record_failed", exc_info=True)
```

**风险**: 无 — 纯代码结构优化，不改变行为。

---

### M3: `Retriever.retrieve()` 未记录 `record_memory_hit`

**决策**: **不在本次修复范围**。

**原因**:

1. **修复成本高**: 需要修改 `Retriever` / `MemoryRetrievalService` 的构造函数签名、注入 `analytics_pipeline`、修改所有实例化点（agent.py、main.py、routes.py 共 4+ 处）
2. **与 B1 修复后仍有风险**: `Retriever.retrieve()` 在 `agent.run()` 中通过 `to_thread` 调用，即使修复 B1，也需要确保 `_record_memory_event` 在 `Retriever` 上下文中能正确调度
3. **功能重叠**: `get_by_id()` 的 HIT 记录（修复 B1 后恢复）已覆盖单条记忆访问场景；`Retriever.retrieve()` 的 HIT 记录是批量场景，属于增强而非基础功能
4. **计划偏差**: 原计划要求但未实施，属于功能遗漏而非 bug

**建议**: 在 Phase 28+ 中作为独立任务实施，届时一并处理 `MemoryLifecycleManager` 的 analytics 接入。

---

### M4: `/chat` 异常处理中重复 `logger.exception`

**根因**: 同一 except 块中两行 `logger.exception` 调用，产生两条含完整 traceback 的日志。

**修改文件**: [src/api/routes.py](file:///d:/dma/day2/src/api/routes.py)

**修改方式**: 删除重复行（line 131）：

```python
# 修改前:
except Exception as e:
    logger.exception("chat endpoint error")
    logger.exception("chat_endpoint_error")
    raise HTTPException(status_code=500, detail=MSG_INTERNAL_ERROR)

# 修改后:
except Exception as e:
    logger.exception("chat_endpoint_error")
    raise HTTPException(status_code=500, detail=MSG_INTERNAL_ERROR)
```

**风险**: 无 — 仅删除重复日志。

---

## 修改文件汇总

| 文件 | 修改行数（估计） | 涉及问题 |
| --- | --- | --- |
| [src/adapters/sqlite_store.py](file:///d:/dma/day2/src/adapters/sqlite_store.py) | ~30 行 | B1, H1, M1 |
| [src/core/agent.py](file:///d:/dma/day2/src/core/agent.py) | ~8 行 | H3 |
| [src/api/routes.py](file:///d:/dma/day2/src/api/routes.py) | ~20 行 | H2, M2, M4 |
| [main.py](file:///d:/dma/day2/main.py) | 0 行 | 无需修改 |

---

## 回归测试计划

修复完成后执行：

1. `pytest tests/ -x -q` — 确保 168 个测试全部通过
2. 手动验证：
   - 发 `/chat` 请求 → 查询 `analytics_memory_events` 有 INSERT + HIT 记录
   - 发 `/chat` 请求 → 查询 `analytics_user_activity_daily` 有记录（tenant_id=""）
   - 发 `/chat` 请求 → 查询 `analytics_token_usage_daily` 有记录（token 累加正确）
   - `PATCH /memory/{id}` → `analytics_memory_events` 有 UPDATE 记录
   - `DELETE /memory/{id}` → `analytics_memory_events` 有 DELETE 记录（memory_type 非空）
3. 启动日志验证：无 `memory_analytics_record_failed` 警告
4. OpenAPI schema 验证：无破坏

---

**停止。等待人工确认后实施。**