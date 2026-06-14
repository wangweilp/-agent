# SANDBOX V2 STEP 2 REPORT — 任务队列与 Worker 框架

**实施日期**: 2026-06-13
**项目**: 黔智脑 Cognitive OS (`D:\dma\day2`)
**步骤**: Sandbox v2 Step 2 — 真实任务队列与 Worker 框架

---

## 一、本次新增文件

| # | 文件 | 用途 |
|---|------|------|
| 1 | `src/open_platform/sandbox_v2/queue.py` | SandboxQueue Protocol 接口（lease/dead_letter/retry） |
| 2 | `src/open_platform/sandbox_v2/worker.py` | SandboxV2Worker Runner（policy re-check + simulation） |
| 3 | `src/adapters/sqlite_sandbox_v2_queue.py` | SQLite Queue 实现（租约/重试/死信/worker 心跳） |
| 4 | `tests/test_open_platform/test_sandbox_v2_queue.py` | 队列单元测试（18 项） |
| 5 | `tests/test_open_platform/test_sandbox_v2_worker.py` | Worker 单元测试（10 项） |
| 6 | `tests/test_open_platform/test_sandbox_v2_queue_api.py` | 队列 API 集成测试（14 项） |

**共新增 6 个文件。**

---

## 二、本次修改文件

| # | 文件 | 变更内容 |
|---|------|----------|
| 1 | `src/open_platform/sandbox_v2/models.py` | 新增 3 个数据类 + 2 个枚举（~220 行）：SandboxQueueItem, SandboxWorkerHeartbeat, SandboxWorkerResult; SandboxV2QueueStatus, SandboxV2WorkerStatus |
| 2 | `src/open_platform/sandbox_v2/service.py` | 构造函数接受可选 queue；submit_job 支持 enqueue 参数；新增 7 个队列方法 |
| 3 | `src/api/sandbox_v2.py` | Router factory 接受 worker；新增 5 个端点；更新 readiness schema |
| 4 | `main.py` | 初始化 SQLiteSandboxV2Queue + SandboxV2Worker，注入 service 和 router |
| 5 | `frontend/services/runtime-admin.ts` | 新增 6 个 API client 方法 + 类型导入 |
| 6 | `frontend/types/runtime-admin.ts` | 新增 9 个 TypeScript 接口 |
| 7 | `tests/test_open_platform/test_sandbox_v2_api.py` | 适配 Step 2 readiness 变化（2 测试更新） |
| 8 | `tests/test_open_platform/test_sandbox_v2_worker.py` | N/A（新增） |

**共修改 7 个文件（含新增测试文件中的修复）。**

---

## 三、新增 API 列表

| 方法 | 路径 | 功能 | 新增于 |
|------|------|------|--------|
| `POST` | `/api/runtime/sandbox-v2/jobs` | 提交 job（新增 `enqueue: true` 参数） | Step 2 |
| `GET` | `/api/runtime/sandbox-v2/queue` | 查看任务队列 | Step 2 |
| `POST` | `/api/runtime/sandbox-v2/queue/requeue-expired` | 回收过期 lease | Step 2 |
| `GET` | `/api/runtime/sandbox-v2/workers` | 查看 worker heartbeat | Step 2 |
| `POST` | `/api/runtime/sandbox-v2/workers/run-once` | 手动触发 worker 处理一个任务 | Step 2 |
| `GET` | `/api/runtime/sandbox-v2/dead-letter` | 查看 dead letter 队列 | Step 2 |

Step 1 的 6 个原始端点不变，全部向后兼容。

---

## 四、Queue / Worker 当前能力

### 4.1 队列能力 ✅

| 能力 | 状态 | 说明 |
|------|------|------|
| enqueue | ✅ | 入队创建 queue item，状态=queued |
| lease_next | ✅ | 租约机制，同一 job 不会被多 worker 同时处理 |
| acknowledge | ✅ | 完成任务确认 |
| fail + retry | ✅ | attempts < max_attempts → 重新 queued |
| dead_letter | ✅ | attempts >= max_attempts → 进入死信队列 |
| cancel | ✅ | queued/leased/processing → canceled |
| requeue_expired_leases | ✅ | 回收过期 lease，超 max_attempts 进 dead_letter |
| worker heartbeat | ✅ | 追踪 worker 状态和计数 |
| priority ordering | ✅ | 按 priority ASC, available_at ASC 出队 |

### 4.2 Worker 能力 ✅

| 能力 | 状态 | 说明 |
|------|------|------|
| run_once | ✅ | 单次处理一个队列任务 |
| run_loop | ✅ | 轮询循环（支持 max_jobs 和 stop_requested） |
| policy re-check | ✅ | 执行前必须通过 policy_engine，不绕过 |
| mode 校验 | ✅ | 只处理 simulation / metadata_only |
| future 模式拒绝 | ✅ | future_container / future_microvm → fail |
| execution record | ✅ | 每次执行生成 record，no_real_execution=True |
| cancel 处理 | ✅ | 检查队列取消状态，不杀进程 |
| timeout | ✅ | 只作用于 simulation 流程 |

---

## 五、Queue / Worker 当前限制（诚实声明）

| 能力 | 状态 | 原因 |
|------|------|------|
| 分布式 worker | ❌ | SQLite 是单机队列，无 Redis/Celery 跨节点协调 |
| Redis/RabbitMQ 后端 | ❌ | 当前仅 SQLite；Protocol 设计允许后续替换 |
| 真实进程 kill | ❌ | cancel 只标记状态，不杀 OS 进程 |
| Worker 自动扩缩 | ❌ | 需手动启动 worker |
| Worker 健康检查自动恢复 | ❌ | 仅记录 heartbeat，无自动重启 |
| 队列持久化到 PostgreSQL | ❌ | 接口已预留，实现留到后续 |

---

## 六、为什么这一步仍然不等于生产级沙箱

1. **队列是 SQLite 单机** — 不支持分布式 worker，无法水平扩展。
2. **Worker 不执行真实代码** — 所有执行仍然是 simulation/metadata-only。
3. **没有执行隔离** — 无 container/namespace/cgroup/seccomp 运行时强制。
4. **没有网络隔离** — 无 iptables/network namespace。
5. **没有文件系统隔离** — 无 read-only mount/temp dir isolation。
6. **不能真正杀进程** — cancel 只更新数据库状态。

这一步的价值在于：建立了经过策略检查的、带租约和重试的、有死信队列的任务调度框架。真实执行能力将在 Step 3+ 逐步加入。

---

## 七、测试结果

### 新测试
```
tests/test_open_platform/test_sandbox_v2_queue.py  18 passed (队列 lease/retry/dead_letter/heartbeat)
tests/test_open_platform/test_sandbox_v2_worker.py  10 passed (run_once/fail_future/safety/cancel)
tests/test_open_platform/test_sandbox_v2_queue_api.py 14 passed (API 200/readiness/compatibility)
```

### 全部 sandbox v2 测试
```
99 passed in 3.02s
```

### 全部 test_open_platform 测试
```
3665 passed in 78.44s
```

零回归。原有测试全部通过。

---

## 八、测试覆盖清单

1. ✅ enqueue 后 queue item 状态为 queued
2. ✅ lease_next 能租约一个任务
3. ✅ acknowledge 后任务 completed
4. ✅ fail 后未超过 max_attempts 会重新 queued
5. ✅ fail 超过 max_attempts 会进入 dead_letter
6. ✅ cancel queued job 后状态 canceled
7. ✅ expired lease 可以 requeue
8. ✅ worker run_once 可以处理一个 simulation job
9. ✅ worker 不处理 future_container / future_microvm
10. ✅ worker 不导入 subprocess 模块
11. ✅ worker 不导入网络模块
12. ✅ submit job with enqueue=true 后进入队列
13. ✅ run-once API 能处理一个任务
14. ✅ readiness 正确显示 worker_framework=true、execution_isolation=false
15. ✅ 旧的 Step 1 测试仍通过（enqueue=false 行为不变）

---

## 九、下一步建议

**建议进入 Step 3：Artifact 文件系统隔离与只读物化**

参考 SANDBOX_NEXT_STEPS.md Phase 4，具体任务：

1. 只读 Artifact 物化（文件大小限制、MIME 检查、路径穿越防护）
2. SandboxV2FilesystemPolicy 运行时验证
3. Artifact hash 计算（SHA256）
4. 临时目录隔离
5. 解压炸弹防护
6. 不执行、不联网、不写 host 文件系统

---

## 十、命令速查

```bash
# 运行全部 sandbox v2 测试
python -m pytest tests/test_open_platform/test_sandbox_v2_*.py -q -v

# 运行完整 test_open_platform
python -m pytest tests/test_open_platform -q
```
