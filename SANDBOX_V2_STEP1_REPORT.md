# SANDBOX V2 STEP 1 REPORT — Core Contract 实施报告

**实施日期**: 2026-06-13
**项目**: 黔智脑 Cognitive OS (`D:\dma\day2`)
**步骤**: Sandbox v2 Step 1 — 核心模型、策略引擎、Store、Service、API、类型和测试

---

## 一、本次新增文件

| # | 文件 | 用途 |
|---|------|------|
| 1 | `src/open_platform/sandbox_v2/__init__.py` | 模块初始化与边界声明 |
| 2 | `src/open_platform/sandbox_v2/models.py` | 核心数据模型（8 个模型 + 5 个枚举） |
| 3 | `src/open_platform/sandbox_v2/policy_engine.py` | 策略引擎（默认 deny / fail closed） |
| 4 | `src/open_platform/sandbox_v2/store.py` | Store Protocol 接口定义 |
| 5 | `src/open_platform/sandbox_v2/service.py` | 服务层（submit_job, run_simulation, cancel_job 等） |
| 6 | `src/adapters/sqlite_sandbox_v2_store.py` | SQLite Store 默认实现 |
| 7 | `src/api/sandbox_v2.py` | FastAPI 路由（6 个端点） |
| 8 | `tests/test_open_platform/test_sandbox_v2_models.py` | 数据模型测试 |
| 9 | `tests/test_open_platform/test_sandbox_v2_policy_engine.py` | 策略引擎测试 |
| 10 | `tests/test_open_platform/test_sandbox_v2_service.py` | 服务层测试 |
| 11 | `tests/test_open_platform/test_sandbox_v2_api.py` | API 集成测试 |

**共新增 11 个文件。**

---

## 二、本次修改文件

| # | 文件 | 变更内容 |
|---|------|----------|
| 1 | `main.py` | 新增 Sandbox v2 Store/Service/Router 初始化与注册（约 15 行） |
| 2 | `frontend/services/runtime-admin.ts` | 新增 6 个 Sandbox v2 API client 方法 + 类型导入 |
| 3 | `frontend/types/runtime-admin.ts` | 新增 10 个 Sandbox v2 TypeScript 接口 |

**共修改 3 个文件。**

---

## 三、Sandbox v2 当前完成能力

### 3.1 数据模型 ✅

| 模型 | 状态 | 说明 |
|------|------|------|
| `SandboxJob` | ✅ | 完整的 job 数据模型，含状态机判断方法 |
| `SandboxV2ExecutionRecord` | ✅ | 完整的执行记录，`no_real_execution=True` 默认 |
| `SandboxPolicyV2` | ✅ | 默认 deny-all 安全策略 |
| `SandboxV2PolicyDecision` | ✅ | 策略决策结果，含 fail_closed 标记 |
| `SandboxResourceLimits` | ✅ | 资源限制模型 |
| `SandboxNetworkPolicy` | ✅ | 网络策略（默认 deny） |
| `SandboxFilesystemPolicy` | ✅ | 文件系统策略（默认 deny write） |
| `SandboxArtifactPolicy` | ✅ | Artifact 策略（默认 deny materialization） |
| `SandboxPackagePolicy` | ✅ | 包管理策略（默认 deny download） |

### 3.2 策略引擎 ✅

- 默认 deny
- fail closed（任何异常 → deny）
- 高风险动作（execute_code, shell_exec 等）默认拒绝
- 未识别动作默认拒绝
- 包下载 / 文件写入 / 外网访问 / artifact materialization 默认拒绝
- 只允许 `metadata_only` / `simulation` / `disabled` 模式
- 策略字段缺失 → fail closed
- `future_container` / `future_microvm` 模式被阻止

### 3.3 Store 接口 ✅

- `SandboxV2Store` Protocol 定义
- `SQLiteSandboxV2Store` 默认实现
- 遵循现有 store 模式（`create_sqlite_db` + `execute_with_retry`）
- 接口便于后续替换为 PostgreSQL

### 3.4 Service 层 ✅

- `submit_job` — 含策略评估
- `evaluate_policy` — 策略评估包装
- `create_execution_record` — 生成审计记录
- `run_simulation` — 模拟执行（不运行代码）
- `cancel_job` — 只更新状态，不杀进程
- `get_job_status` / `list_execution_records` / `list_jobs`

### 3.5 API 路由 ✅

6 个端点全部可用。

### 3.6 前端类型 ✅

10 个 TypeScript 接口 + 6 个 API client 方法。

### 3.7 测试 ✅

57 个测试全部通过。

---

## 四、Sandbox v2 仍未完成能力（诚实声明）

| 能力 | 状态 | 计划 |
|------|------|------|
| 真实代码执行隔离（Rootless Container / MicroVM） | ❌ | Step 4+ |
| seccomp / namespace / cgroup 运行时强制 | ❌ | Step 4+ |
| 真实任务队列（Celery / RQ / Redis） | ❌ | Step 2 |
| Worker 生命周期管理 | ❌ | Step 2 |
| 进程级 Kill Switch | ❌ | Step 3 |
| 网络隔离（iptables / network namespace） | ❌ | Step 4+ |
| 文件系统隔离（read-only mount） | ❌ | Step 4+ |
| 包下载与供应链安全（签名验证、SBOM、漏洞扫描） | ❌ | Step 4+ |
| 只读 Artifact 物化 | ❌ | Step 4+ |
| 红队运行时逃逸测试 | ❌ | Step 5+ |

---

## 五、API 路径清单

| 方法 | 路径 | 功能 |
|------|------|------|
| `POST` | `/api/runtime/sandbox-v2/jobs` | 提交 sandbox job |
| `GET` | `/api/runtime/sandbox-v2/jobs/{job_id}` | 查看 job 状态 |
| `GET` | `/api/runtime/sandbox-v2/jobs` | 列出 jobs（支持筛选） |
| `POST` | `/api/runtime/sandbox-v2/jobs/{job_id}/cancel` | 取消 job |
| `GET` | `/api/runtime/sandbox-v2/execution-records` | 列出执行记录 |
| `GET` | `/api/runtime/sandbox-v2/readiness` | 返回当前能力状态 |

---

## 六、测试结果

```
tests/test_open_platform/test_sandbox_v2_models.py .............. 14 passed
tests/test_open_platform/test_sandbox_v2_policy_engine.py ....... 15 passed
tests/test_open_platform/test_sandbox_v2_service.py .............. 11 passed
tests/test_open_platform/test_sandbox_v2_api.py ................. 17 passed

Total: 57 passed in 1.26s
```

测试覆盖：
1. ✅ 默认策略是 deny
2. ✅ 未知动作 fail closed
3. ✅ package download 默认拒绝
4. ✅ network access 默认拒绝
5. ✅ write filesystem 默认拒绝
6. ✅ metadata_only job 可以生成 execution record
7. ✅ simulation job 可以生成 execution record
8. ✅ cancel job 不会假装杀进程
9. ✅ readiness 正确返回未完成项
10. ✅ API 不返回 500

---

## 七、关键设计决策

1. **复用而非重造**: 新模块 `sandbox_v2/` 独立于已有的 `sandbox_policy.py` / `sandbox_execution.py` 等，避免破坏现有控制面。两者共存，v2 是 v1 的工程化升级。

2. **默认 deny + fail closed**: 所有策略默认拒绝，任何异常导致 fail closed。与现有代码库的安全哲学完全一致。

3. **模拟执行明确标注**: 所有 execution record 的 `no_real_execution=True`，readiness API 诚实声明所有隔离能力为 `false`。

4. **接口隔离**: Store 使用 Protocol，便于后续替换 PostgreSQL。

5. **不开真实执行**: `future_container` / `future_microvm` 只作为预留枚举，API 层直接拒绝。

---

## 八、下一步建议

**建议进入 Step 2：真实任务队列与 Worker 框架**

具体任务（参考 SANDBOX_NEXT_STEPS.md Phase 3）：

1. 接入 Redis + Celery/RQ
2. 实现 `SandboxV2Worker` 基类
3. 实现 Worker 健康检查、优雅关闭
4. Job 状态机：`CREATED → QUEUED → RUNNING → COMPLETED/FAILED/CANCELED/TIMEOUT`
5. Retry + Timeout + Dead Letter Queue
6. 所有 Sandbox Worker 仍默认不执行不可信代码

---

## 九、执行原则确认

- ❌ 未实现真实任务队列
- ❌ 未实现 Docker
- ❌ 未实现 MicroVM
- ❌ 未执行第三方代码
- ❌ 未大改前端页面
- ✅ 只做了核心模型、策略引擎、Store、Service、API、类型和测试
