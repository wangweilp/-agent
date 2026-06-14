# 黔智脑 Cognitive OS — Runtime / Sandbox 安全审查报告

**审查日期**: 2026-06-13
**审查类型**: 只读审查（不修改任何代码）
**审查范围**: Runtime / Sandbox / 安全运行时能力
**审查人**: 自动化安全审查 Agent

---

## ⚠️ 边界声明

> **当前 Runtime/Sandbox 主要完成的是安全治理控制面、模拟运行、元数据校验、默认关闭和审计追踪能力，不等于已经完成生产级第三方代码执行沙箱。生产级执行环境仍需要真实任务队列、Rootless Container 或 MicroVM、网络隔离、文件系统隔离、资源限制、只读工件物化、安全测试和红队验证。**

此边界声明已出现在以下关键位置：
- `src/open_platform/runtime_governance_summary.py:14-18` (`BOUNDARY_STATEMENT`)
- `frontend/app/admin/runtime/page.tsx:49-50` (`boundaryFallback`)

---

## 第一步：项目结构确认

### 关键目录位置

| 组件 | 路径 | 状态 |
|------|------|------|
| 前端目录 | `D:\dma\day2\frontend\` | ✅ Next.js (App Router) |
| 后端目录 | `D:\dma\day2\src\` | ✅ FastAPI |
| 应用入口 | `D:\dma\day2\main.py` | ✅ uvicorn |
| API 层 | `D:\dma\day2\src\api\` | ✅ 存在 |
| 核心域层 | `D:\dma\day2\src\core\` | ✅ 存在 |
| Open Platform 层 | `D:\dma\day2\src\open_platform\` | ✅ 存在 |
| 适配器层 | `D:\dma\day2\src\adapters\` | ✅ 存在 |
| 测试目录 | `D:\dma\day2\tests\` | ✅ 存在 |
| 前端服务层 | `D:\dma\day2\frontend\services\` | ✅ 存在 |

### Runtime / Sandbox / Governance 相关目录和文件

#### 核心域模型 (src/open_platform/)

| 文件 | 功能 | 行数(约) |
|------|------|----------|
| `runtime.py` | Runtime Adapter + Binding 域模型 | 395 |
| `sandbox_policy.py` | Sandbox 安全策略域模型 | 378 |
| `sandbox_worker.py` | Sandbox Worker 域模型 | 316 |
| `sandbox_worker_stub.py` | Disabled Sandbox Worker Stub (唯一实现) | 82 |
| `local_dev_sandbox.py` | 本地开发 Sandbox 原型 | — |
| `local_dev_sandbox_worker.py` | 本地开发 Sandbox Worker | — |
| `simulation_runtime.py` | Simulation Runtime 服务 (9步安全仿真) | 489 |
| `sandbox_execution.py` | Sandbox Execution Record (audit-only) | 209 |
| `runtime_execution_gate.py` | Runtime Execution Gate (API boundary) | 103 |
| `runtime_execution_planner.py` | Runtime Execution Planner | — |
| `runtime_execution_plan.py` | Runtime Execution Plan | — |
| `production_sandbox_gate.py` | Production Sandbox Gate (readiness assessment) | 237 |
| `runtime_kill_switch.py` | Kill Switch + Incident Store (metadata-only) | 197 |
| `rootless_container_gate.py` | Rootless Container Gate (metadata-only) | 741 |
| `artifact_materialization.py` | Artifact Materialization (disabled) | — |
| `artifact_materialization_service.py` | Artifact Materialization Service | — |
| `package_download_worker.py` | Package Download Worker (disabled) | — |
| `package_download_quarantine.py` | Package Download Quarantine | — |
| `package_validation.py` | Package Validation | — |
| `package_verification.py` | Package Verification | — |
| `policy_enforcement.py` | Policy Enforcement | — |
| `policy_enforcement_translator.py` | Policy Enforcement Translator | — |
| `sandbox_enforcement_proof.py` | Sandbox Enforcement Proof | — |
| `sandbox_adapter_feasibility.py` | Sandbox Adapter Feasibility | — |
| `trusted_fixture_isolation.py` | Trusted Fixture Isolation | — |
| `trusted_fixture_execution.py` | Trusted Fixture Execution | — |
| `runtime_safety_service.py` | Runtime Safety Service | — |
| `sandbox_worker_queue.py` | Sandbox Worker Queue (disabled) | — |
| `runtime_governance_summary.py` | Governance Summary Payload (208行) | 289 |
| `runtime_capability.py` | Runtime Capability | — |

#### API 路由

| 文件 | 端点 |
|------|------|
| `src/api/runtime_admin_router.py` | `/admin/runtime/*` |
| `src/api/runtime_execution_router.py` | `/admin/runtime/executions/*` |
| `src/api/sandbox_policy_router.py` | `/admin/sandbox-policies/*` |
| `src/api/policy_enforcement_router.py` | Policy enforcement 端点 |
| `src/api/runtime_capability_router.py` | Runtime capability 端点 |
| `src/api/artifact_router.py` | Artifact 端点 |
| `src/api/audit_router.py` | Audit 端点 |

#### 适配器层

| 文件 | 功能 |
|------|------|
| `src/adapters/runtime_store.py` | Runtime Store 实现 |
| `src/adapters/sandbox_policy_store.py` | Sandbox Policy Store 实现 |
| `src/adapters/sandbox_execution_store.py` | Sandbox Execution Store |
| `src/adapters/sandbox_enforcement_proof_store.py` | Enforcement Proof Store |
| `src/adapters/sandbox_worker_queue_store.py` | Worker Queue Store |
| `src/adapters/production_sandbox_gate_store.py` | Production Gate Store |
| `src/adapters/runtime_safety_store.py` | Runtime Safety Store |
| `src/adapters/rootless_container_gate_store.py` | Rootless Container Gate Store |
| `src/adapters/artifact_store.py` | Artifact Store |
| `src/adapters/artifact_materialization_store.py` | Artifact Materialization Store |
| `src/adapters/artifact_extraction_guard_store.py` | Artifact Extraction Guard Store |
| `src/adapters/package_download_worker_store.py` | Package Download Worker Store |
| `src/adapters/package_download_quarantine_store.py` | Package Download Quarantine Store |
| `src/adapters/package_verification_store.py` | Package Verification Store |
| `src/adapters/task_queue_adapter.py` | Task Queue Adapter (metadata-only) |
| `src/adapters/policy_decision_store.py` | Policy Decision Store |

#### 前端

| 文件 | 功能 |
|------|------|
| `frontend/app/admin/runtime/page.tsx` | Runtime Admin 可视化页面 |
| `frontend/services/runtime-admin.ts` | Runtime Admin API 客户端 |
| `frontend/types/runtime-admin.ts` | Runtime Admin 类型定义 |
| `frontend/components/open-platform/SecurityProfilePanel.tsx` | 安全配置面板 |

#### 测试

| 文件 | 功能 |
|------|------|
| `tests/test_open_platform/test_step23_security_runtime.py` | Step 23 安全测试 |
| `tests/test_open_platform/test_step24_security_escape_guards.py` | Step 24 安全逃逸守卫测试 |
| `tests/test_open_platform/test_step25_red_team_escape_guards.py` | Step 25 红队逃逸守卫测试（163 项） |
| `tests/test_open_platform/test_sandbox_worker_stub.py` | Sandbox Worker Stub 测试 |
| `tests/test_open_platform/test_sandbox_policy.py` | Sandbox Policy 测试 |
| `tests/test_open_platform/test_simulation_runtime.py` | Simulation Runtime 测试 |
| `tests/test_open_platform/test_sandbox_execution_store.py` | Execution Store 测试 |
| `tests/test_open_platform/test_runtime_execution_api_gate.py` | Execution API Gate 测试 |
| `tests/test_open_platform/test_runtime_store.py` | Runtime Store 测试 |
| `tests/test_open_platform/test_runtime_safety_store.py` | Runtime Safety Store 测试 |
| `tests/test_open_platform/test_production_sandbox_gate.py` | Production Sandbox Gate 测试 |
| `tests/test_open_platform/test_rootless_container_gate.py` | Rootless Container Gate 测试 |
| `tests/test_open_platform/test_package_download_quarantine.py` | Package Download Quarantine 测试 |
| `tests/test_open_platform/test_artifact_extraction_guard.py` | Artifact Extraction Guard 测试 |
| `tests/test_open_platform/test_artifact_materialization.py` | Artifact Materialization 测试 |
| `tests/test_open_platform/test_trusted_fixture_execution.py` | Trusted Fixture Execution 测试 |
| `tests/test_open_platform/test_trusted_fixture_isolation.py` | Trusted Fixture Isolation 测试 |
| `tests/test_open_platform/test_sandbox_enforcement_proof.py` | Sandbox Enforcement Proof 测试 |
| `tests/test_open_platform/test_sandbox_worker_queue.py` | Sandbox Worker Queue 测试 |
| `tests/test_open_platform/test_sandbox_adapter_feasibility.py` | Sandbox Adapter Feasibility 测试 |
| `tests/test_open_platform/test_policy_enforcement.py` | Policy Enforcement 测试 |
| `tests/test_open_platform/test_policy_enforcement_translator.py` | Policy Enforcement Translator 测试 |
| `tests/test_open_platform/test_runtime_capability.py` | Runtime Capability 测试 |
| `tests/test_open_platform/test_runtime_governance_summary_api.py` | Governance Summary API 测试 |
| `tests/test_open_platform/test_step25_final_gate.py` | Step 25 Final Gate |

---

## 第二步：Runtime / Sandbox 现有能力审查

### 2.1 Runtime Governance 控制面 ✅ 已完成

**状态**: 完整的 metadata-only 安全治理控制面已实现。

**证据**:

1. **Runtime Adapter 体系** (`src/open_platform/runtime.py`)
   - `RuntimeAdapter` 数据模型定义了 6 种适配器类型 (`manifest_only`, `simulation`, `http_webhook`, `sandboxed_process`, `container`, `builtin_bridge`)
   - MVP 阶段只允许 `manifest_only` 和 `simulation` 两种类型 (`MVP_ALLOWED_RUNTIME_ADAPTER_TYPES`)
   - 非 MVP 类型默认 `disabled`
   - `RuntimeBindingStatus` 支持 `PENDING → ENABLED → DISABLED → SUSPENDED` 状态机
   - `RuntimeEligibilityResult` 提供 eligibility 评估（不做执行）

2. **Sandbox Policy** (`src/open_platform/sandbox_policy.py`)
   - `SandboxPolicy` 定义了完整的安全策略模型
   - `NO_EXECUTION`, `SIMULATION_ONLY`, `RESTRICTED`, `ISOLATED` 四个安全级别
   - `no_execution` 和 `simulation_only` 级别的 `is_execution_allowed()` 始终返回 `False`
   - 策略校验 (`validate()`) 覆盖了 scope、level、network、filesystem、secrets 等规则

3. **Runtime Execution Gate** (`src/open_platform/runtime_execution_gate.py`)
   - `DISABLED / PLAN_ONLY / DRY_RUN_ONLY` 三种模式
   - `is_execution_allowed()` 始终返回 `False`

4. **Governance Summary** (`src/open_platform/runtime_governance_summary.py`)
   - 聚合所有控制面 store 数据为前端友好的 governance 摘要
   - 包含 7 个模块面板: Kill Switch, Incident Store, Package Download Gate, Artifact Materialization Gate, Simulation Execution Record, Red-Team Result, Production Sandbox Gate

5. **前端可视化** (`frontend/app/admin/runtime/page.tsx`)
   - 完整的 Runtime Admin 页面，5 个 Tab (Governance / Adapters / Bindings / Policies / Guide)
   - 显示边界声明警示

**评价**: 控制面设计完整、层次清晰，fail-closed 为默认行为。但所有都是 metadata-only 层的治理，不涉及真实运行时执行。

---

### 2.2 Sandbox Proof / Enforcement Proof ✅ 已完成

**证据**:
- `src/open_platform/sandbox_enforcement_proof.py` — Enforcement Proof 数据模型
- `src/open_platform/sandbox_enforcement_proof_service.py` — Enforcement Proof 服务
- `src/open_platform/policy_enforcement.py` — Policy Enforcement 决策
- `src/open_platform/policy_enforcement_translator.py` — 策略翻译器
- `tests/test_open_platform/test_sandbox_enforcement_proof.py` — 测试覆盖

**评价**: Enforcement proof 作为审计证据链存在，记录 policy 决策过程但不执行强制措施。

---

### 2.3 Simulation Runtime ✅ 已完成

**证据**:
- `src/open_platform/simulation_runtime.py` — 9-step 安全仿真服务
  1. validate_marketplace_agent
  2. validate_developer_publisher
  3. validate_runtime_metadata
  4. validate_installation
  5. validate_permissions
  6. validate_runtime_binding
  7. validate_adapter
  8. validate_scope
  9. generate_simulated_response (deterministic mock)

- `SimulationRuntimeService` 明确注释：
  - "不导入 AgentRuntime / AgentRegistry"
  - "不执行 package_url / entrypoint"
  - "不联网"
  - 返回 deterministic mock simulated_output

**评价**: Simulation 实现了完整的"不执行代码"模拟链路，安全边界明确。

---

### 2.4 Metadata-only Validation ✅ 已完成

**证据**:
- `src/open_platform/manifest_validator.py` — Manifest 校验
- `src/open_platform/package_validation.py` — Package 校验
- `src/open_platform/package_validation_service.py` — Package 校验服务
- `src/open_platform/package_verification.py` — Package 验证
- `src/open_platform/package_verification_service.py` — Package 验证服务
- `src/open_platform/signature_verifier.py` — 签名验证器

**评价**: 校验层面有完整的 manifest validation、package url format check、static rule evaluation，但无实际包下载或执行动作。

---

### 2.5 Default Deny / Fail Closed 策略 ✅ 已完成

**证据**:

在项目中，"default deny" 和 "fail closed" 是贯穿所有模块的核心设计原则：

1. `src/open_platform/sandbox_worker.py:46-47`
   ```python
   class SandboxWorkerDecision(StrEnum):
       FAIL_CLOSED = "fail_closed"
   ```

2. `src/open_platform/sandbox_worker_stub.py:4-7`
   ```python
   """Disabled Sandbox Worker Stub — fail-closed disabled worker。
   Step 24-E: 唯一实现的 worker。永远 blocked。永不执行代码。"""
   ```

3. `src/open_platform/runtime_kill_switch.py:8`
   ```python
   """Runtime Kill Switch + Incident Store — metadata-only safety control plane。
   Step 26-B: NO process/runtime/worker/container/microVM kill。
   is_runtime_kill_active()/is_runtime_stopped() = always False。"""
   ```

4. `src/open_platform/production_sandbox_gate.py:3-4`
   ```python
   """Production Sandbox Implementation Gate — readiness assessment, never enables execution。
   third_party_execution_allowed/package_execution_allowed/runtime_enabled = always False。"""
   ```

5. `src/open_platform/runtime_execution_gate.py:85-87`
   ```python
   def is_execution_allowed(self) -> bool:
       """Step 24-H: always False。no real execution。"""
       return False
   ```

6. `src/open_platform/task_queue_adapter.py:53`
   ```python
   def is_enqueue_allowed(self) -> bool: return False
   def is_dispatch_allowed(self) -> bool: return False
   ```

**评价**: Default-Deny / Fail-Closed 已深度嵌入所有模块，设计一致性极高。这是当前项目最大的安全优势。

---

### 2.6 API Key / Scope 权限 ✅ 已完成

**证据**:
- `src/open_platform/api_auth.py` — API Key 认证
- `src/api/developer_api_auth.py` — Developer API 认证
- `src/open_platform/rbac_service.py` — RBAC 服务
- `src/core/rbac.py` — RBAC 核心域模型
- `src/api/rbac_router.py` — RBAC API 端点
- `simulation_runtime.py:378-399` — API Key scope 检查 (`agent:simulate` / `agent:execute:simulation`)

**评价**: API Key 管理和 Scope 权限控制基本完整。

---

### 2.7 Audit Log 审计日志 ✅ 已完成

**证据**:
- `src/core/audit.py` — AuditLog, AuditSummary, AuditStore Protocol
- `src/core/collaboration.py` — Collaboration 审计
- `src/api/audit_router.py` — Audit API 端点
- `src/adapters/compliance_store.py` — Compliance 存储

**评价**: 审计日志基础设施存在，但审计主要用于 workspace 级别操作，Runtime/Sandbox 级别的执行审计记录需要通过 SandboxExecutionAuditEvent 独立记录。

---

### 2.8 Kill Switch ✅ Metadata-only 已完成

**证据**:
- `src/open_platform/runtime_kill_switch.py` — 完整的 Kill Switch 策略、触发器、Incident 数据模型
- `RuntimeKillSwitchPolicy` — `runtime_kill_implemented: bool = False`, `process_kill_implemented: bool = False`
- `RuntimeKillSwitchTrigger.is_runtime_kill_active() → False`
- `RuntimeIncidentRecord.is_runtime_stopped() → False`
- `src/adapters/runtime_safety_store.py` — Safety Store 实现
- `src/open_platform/runtime_safety_service.py` — Safety Service

**关键限制**: Kill Switch 是 metadata-only — 可以创建策略、触发 metadata 事件、记录 audit event，但不能真正杀掉进程、Worker 或容器。这是有意为之的设计。

---

### 2.9 Incident Store ✅ 已完成

**证据**:
- `RuntimeIncidentRecord` 数据模型 (`runtime_kill_switch.py:126-151`)
- 16 种 incident 类型 (从 `THIRD_PARTY_EXECUTION_ATTEMPT_BLOCKED` 到 `UNKNOWN_SECURITY_EVENT`)
- Incident 状态机: `OPEN → TRIAGED → MITIGATED_METADATA_ONLY → CLOSED_METADATA_ONLY`
- `RuntimeSafetyStore` protocol: create/list/update/triage/close incidents
- 前端 governance summary 中包含 incident 面板

**评价**: Incident Store 和 Kill Switch 一起构成了完整的安全事件生命周期管理（metadata-only）。

---

### 2.10 Package Download Gate ✅ Metadata-only 已完成

**证据**:
- `src/open_platform/package_download_worker.py` — Package Download Worker (disabled)
- `src/open_platform/package_download_quarantine.py` — Package Download Quarantine
- `src/open_platform/package_download_worker_service.py` — Download Worker Service
- `src/adapters/package_download_worker_store.py` — Store
- `src/adapters/package_download_quarantine_store.py` — Quarantine Store

**关键限制**: `is_downloadable()` 始终返回 `False`。所有 download 请求被 blocked。没有真实网络下载或包管理。

---

### 2.11 Artifact Materialization Gate ✅ Metadata-only 已完成

**证据**:
- `src/open_platform/artifact_materialization.py` — Materialization Gate
- `src/open_platform/artifact_materialization_service.py` — Service
- `src/adapters/artifact_materialization_store.py` — Store
- `src/open_platform/artifact_extraction_guard.py` — Extraction Guard
- `src/open_platform/artifact.py` — Artifact 域模型

**关键限制**: `is_extraction_allowed()` 始终 `False`, `is_materialized()` 始终 `False`。只有 logical references，无真实文件系统写入。

---

### 2.12 Red-Team / Escape Test ✅ Control-plane 测试已完成

**证据**:
- `tests/test_open_platform/test_step24_security_escape_guards.py` — Step 24 安全逃逸守卫测试
- `tests/test_open_platform/test_step25_red_team_escape_guards.py` — 163 项红队逃逸守卫测试

**关键限制**: 这些测试验证的是 control-plane 的安全行为（policy 是否正确 deny、worker 是否正确 block），不是真实代码执行环境下的沙箱逃逸。Red-team 测试覆盖的依然是 metadata-only 层的安全断言。

---

### 2.13 Disabled-by-default Worker ✅ 已完成

**证据**:
- `DisabledSandboxWorker` 是唯一实现的 `SandboxWorker` (`sandbox_worker_stub.py`)
- `worker_type = DISABLED_STUB`, `availability = DISABLED`
- `evaluate_request()` 永远返回 `BLOCKED_DISABLED`
- `is_successful_execution()` 始终返回 `False`

---

### 2.14 Production Sandbox Gate ✅ 已完成

**证据**:
- `src/open_platform/production_sandbox_gate.py` — 23 项 readiness requirements
- `build_step26a_default_requirements()` — 自动构建完整需求矩阵
- 明确标记 14 项为 `MISSING`（Kill Switch, Incident Store, Rollback, Observability, Resource Limits, Tenant Isolation, Supply Chain Scan, Signature Verification, Network Enforcement, FileSystem Enforcement, Secrets Broker, Container/Rootless Runtime, Operational Runbook 等）
- 6 项为 `SATISFIED`（Step25 Final Gate, Red-Team Guards, Docs Honesty, Execute Endpoint Blocked, Worker Queue Disabled 等）

---

### 2.15 Sandbox Execution Record ✅ Audit-only 已完成

**证据**:
- `src/open_platform/sandbox_execution.py` — `SandboxExecutionRecord`
- `is_executable()` 始终返回 `False`
- `is_queued()` 始终返回 `False`
- `SandboxExecutionAuditEvent` — 每个状态变更都有审计事件
- NO RUNNING/COMPLETED/SUCCEEDED status

---

### 2.16 前端 Runtime Admin 可视化页面 ✅ 已完成

**证据**:
- `frontend/app/admin/runtime/page.tsx` — 完整的 Runtime Admin 页面
  - 5 个 Tab: Governance / Adapters / Bindings / Policies / Guide
  - Governance 摘要面板，实时显示所有模块状态
  - Adapter 列表、Binding CRUD、Policy 编辑和测试
  - 边界声明警示
- `frontend/services/runtime-admin.ts` — API Client
- `frontend/types/runtime-admin.ts` — 完整的前端类型定义

---

## 第三步：当前缺口判断

### A. 执行隔离层 — ❌ 未完成

**当前没有任何真实隔离执行环境。**

| 能力 | 状态 | 证据 |
|------|------|------|
| Rootless Container | ❌ 未实现 | `rootless_container_gate.py` 明确列出 22 项 capability，其中 11 项 runtime 能力全部 `MISSING` |
| Firecracker/MicroVM | ❌ 未实现 | `SandboxWorkerType.MICROVM_RESERVED` 仅为预留枚举值 |
| gVisor/Kata Containers | ❌ 未实现 | 无任何相关代码或配置 |
| seccomp profile | ❌ 未实现 | `rootless_container_gate.py:662` "No seccomp profile defined" |
| AppArmor/SELinux | ❌ 未实现 | `rootless_container_gate.py:671` "No AppArmor/SELinux profile defined" |
| Linux namespaces | ❌ 未实现 | `rootless_container_gate.py:647` "No user namespace creation code" |
| cgroups | ❌ 未实现 | 无 cgroup CPU/Memory/PID controller 配置 |
| 网络隔离 | ❌ 未实现 | "No network namespace isolation at runtime" |
| 文件系统只读挂载 | ❌ 未实现 | "No read-only mount applied at runtime" |
| CPU/内存/时间限制 | ❌ 未实现 | "No cgroup controller configured" |
| 非 root 用户执行 | ❌ 设计满足但未验证 | "Root privilege blocked by design" — 控制面通过，但无运行时强制 |
| 临时工作目录清理 | ❌ 未实现 | 无相关代码 |

**结论**: 执行隔离层目前完全是 **控制面 metadata/Prototype Gate**，无任何真实容器或 MicroVM 实例。`RootlessContainerGate` 的 22 项 capability assessment 中，运行时相关的 11 项全部为 `MISSING`。

---

### B. 任务队列 — ❌ 未完成

| 能力 | 状态 | 证据 |
|------|------|------|
| Celery/RQ/Dramatiq | ❌ 未接入 | `task_queue_adapter.py:6` "No real queue in Step 27" |
| Redis Queue | ❌ 未接入 | `queue_active=False`, 仅推荐队列定义存在 |
| Worker 进程 | ❌ 未启动 | `DisabledSandboxWorker` 是唯一实现的 worker |
| Job status | ❌ 未接入 | 只有 metadata-only TaskDefinition |
| Retry | ❌ 未接入 | `TaskDefinition.retry_count` 仅为配置字段 |
| Timeout | ❌ 未接入 | `TaskDefinition.timeout_seconds` 仅为配置字段 |
| Cancellation | ❌ 未接入 | 无相关代码 |
| Dead Letter Queue | ❌ 未接入 | `data/dead_letter/` 目录存在但无写入代码 |

**结论**: 任务队列完全是 readiness assessment 状态。`TaskQueueAdapter.assess_readiness()` 返回的是评估报告，不是真实队列。

---

### C. 工件与文件系统安全 — ❌ 未完成

| 能力 | 状态 | 证据 |
|------|------|------|
| Artifact Storage | ⚠️ 域模型存在但无物化 | `artifact.py` + `artifact_store.py` 存在 |
| 只读工件物化 | ❌ 未实现 | `is_materialized()` 始终 `False` |
| 文件大小限制 | ❌ 未实现 | 无相关代码 |
| MIME 类型检查 | ❌ 未实现 | 无相关代码 |
| 路径穿越防护 | ❌ 未实现 | 无相关代码 |
| 解压炸弹防护 | ❌ 未实现 | `artifact_extraction_guard.py` 域模型存在但无运行时 |
| 临时目录隔离 | ❌ 未实现 | 无相关代码 |
| 输出文件审计 | ⚠️ 审计模型存在 | `SandboxExecutionAuditEvent` 可记录 |
| Artifact Hash | ❌ 未实现 | 无相关代码 |
| Artifact Retention Policy | ❌ 未实现 | 无相关代码 |

---

### D. 包下载与依赖安全 — ❌ 未完成

| 能力 | 状态 | 证据 |
|------|------|------|
| Package Quarantine | ⚠️ 域模型存在 | `package_download_quarantine.py` 存在，但 `is_downloadable()=False` |
| Package Allowlist | ⚠️ 域模型存在 | `PackageRegistry` 存在 |
| Package Denylist | ⚠️ 域模型存在 | 同上 |
| Hash Verification | ⚠️ 域模型有但无真实 crypto | `signature_verifier.py` 存在，但生产级 crypto 标记为 MISSING |
| Signature Verification | ❌ 未实现 | Production Gate explicitly marks as MISSING |
| SBOM | ❌ 未实现 | 无相关代码 |
| Vulnerability Scanning | ❌ 未实现 | Production Gate marks "Supply Chain Scan" as MISSING |
| Offline Install | ❌ 未实现 | 无相关代码 |
| Download Disabled by Default | ✅ 已完成 | 所有 download gate 返回 `False` |
| Dependency Provenance | ❌ 未实现 | 无相关代码 |

---

### E. 网络访问控制 — ❌ 未完成

| 能力 | 状态 | 证据 |
|------|------|------|
| 默认禁止外网访问 | ✅ 控制面达成 | `allow_network=False` 默认 |
| 域名 Allowlist | ⚠️ 域模型存在 | `SandboxPolicy.allowed_domains` |
| IP Denylist | ❌ 未实现 | 无相关代码 |
| Metadata Service Block | ❌ 未实现 | 无相关代码 |
| DNS 控制 | ❌ 未实现 | 无相关代码 |
| Egress Proxy | ❌ 未实现 | 无相关代码 |
| 请求审计 | ⚠️ 部分存在 | Usage events 可记录但粒度不够 |
| SSRF 防护 | ❌ 未实现 | 无相关代码 |

**注意**: 控制面的网络控制已经建模（通过 `SandboxPolicy.allow_network=False` 和 allowed_domains），但运行时网络隔离（iptables/nftables/network namespace）完全没有实现。Production Gate 明确标记 "Real Network Enforcement" 为 MISSING。

---

### F. 权限与多租户隔离 — ⚠️ 部分完成

| 能力 | 状态 | 证据 |
|------|------|------|
| Organization Isolation | ✅ 已完成 | `src/core/organization.py`, `src/api/org_router.py` |
| Workspace Isolation | ✅ 已完成 | `src/api/workspace_router.py` |
| RBAC | ✅ 已完成 | `src/core/rbac.py`, `src/api/rbac_router.py` |
| Scope 权限 | ✅ 已完成 | `api_auth.py` + simulation scope check |
| Per-agent Permission | ⚠️ 域模型存在 | `AgentModule.required_permissions` |
| Per-tool Permission | ❌ 未实现 | 无相关代码 |
| Tenant Data Boundary | ⚠️ 控制面存在 | `tenant_id` 贯穿所有模型 |
| Audit Subject/Actor/Org | ⚠️ 部分存在 | AuditLog 有 actor_id 但粒度不够 |

**注意**: 多租户权限在应用层和控制面做得比较完整。但是，运行时级别的 tenant isolation（如 namespace/cgroup per tenant、VM boundary）完全没有实现。

---

### G. 审计与可观测性 — ⚠️ 部分完成

| 能力 | 状态 | 证据 |
|------|------|------|
| Sandbox Execution Record | ✅ 已完成 (audit-only) | `sandbox_execution.py` |
| Audit Log | ✅ 已完成 | `core/audit.py` + `api/audit_router.py` |
| Incident Store | ✅ 已完成 (metadata-only) | `runtime_kill_switch.py` |
| Run Trace | ❌ 未实现 | 无真实执行 trace |
| Input/Output Capture | ❌ 未实现 | 无真实 I/O |
| Policy Decision Log | ⚠️ 部分完成 | `PolicyDecisionStore` 存在 |
| Risk Score | ⚠️ 域模型存在 | `SandboxExecutionRiskLevel` 但无计算逻辑 |
| Metrics | ❌ 未实现 | Production Gate marks "Observability" as MISSING |
| Alerting | ❌ 未实现 | 无相关代码 |
| Dashboard | ✅ 已完成 | `frontend/app/admin/runtime/page.tsx` |

---

### H. 安全测试 — ⚠️ 控制面测试完成，运行时测试未开始

| 能力 | 状态 | 证据 |
|------|------|------|
| Red-Team Escape Test | ✅ 控制面测试 (163 项) | `test_step25_red_team_escape_guards.py` |
| Malicious Package Test | ⚠️ 部分存在 | 通过 policy deny 间接覆盖 |
| Path Traversal Test | ❌ 未实现 | 无文件系统故无法测试 |
| SSRF Test | ❌ 未实现 | 无网络故无法测试 |
| Privilege Escalation Test | ❌ 未实现 | 无执行环境故无法测试 |
| Timeout Test | ❌ 未实现 | 无执行环境故无法测试 |
| Resource Exhaustion Test | ❌ 未实现 | 无执行环境故无法测试 |
| Artifact Abuse Test | ❌ 未实现 | 无物化故无法测试 |
| Network Isolation Test | ❌ 未实现 | 无运行时网络隔离故无法测试 |
| Policy Fail-Closed Test | ✅ 已完成 | 贯穿所有测试 |

**关键区分**: 现有的 163 项 Red-Team Escape Test 测试的是 **控制面是否正确拒绝执行**，而不是 **真实沙箱能否防止逃逸**。两者有本质区别。

---

## 第四步：整体评估总结

### 核心发现

1. **控制面非常成熟**: 项目拥有一个非常精心设计的 metadata-only Runtime/Sandbox 安全治理控制面，包括完整的策略模型、状态机、审计跟踪和前端可视化。

2. **Default-Deny / Fail-Closed 深度实现**: 这是当前架构最大的安全优势 — 所有执行路径的 `is_execution_allowed()` 都硬编码返回 `False`，不存在"不小心打开执行"的可能。

3. **运行时执行能力为零**: 没有真实的容器、MicroVM、namespace 隔离、cgroup 限制、网络隔离、文件系统隔离或任何形式的代码执行能力。

4. **测试覆盖在控制面层很高**: 有 163 项红队逃逸守卫测试，数十个针对各类 store/service/gate 的单元测试。但这些测试全部验证的是"是否正确拒绝"，而非"沙箱是否防逃逸"。

5. **设计方向正确**: 项目采取的"先建控制面、明确边界声明、逐步推进"的策略是正确的，符合从安全治理到安全执行的安全开发生命周期。

### 最严重的 5 个缺口

1. **无执行隔离层** — 无 Rootless Container、MicroVM、seccomp、namespace、cgroup 等任何运行时隔离
2. **无真实任务队列** — 无 Celery/RQ/Redis Queue，只有 metadata-only readiness assessment
3. **无真实 Kill Switch** — 可以记录 metadata event，但不能真正杀掉进程/容器
4. **无网络/文件系统运行时隔离** — 控制面定义了 policy，但运行时无 iptables/mount namespace 等强制
5. **无生产级包管理** — 无真实签名验证、无供应链扫描、无 SBOM、无漏洞扫描
