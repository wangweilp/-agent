# Step 23-E：Sandbox Policy Model + Admin API

## 1. 概述

Step 23-E 实现 Sandbox Policy（沙箱安全策略）的完整领域模型、SQLite 存储、Admin API、Runtime Binding 策略绑定和测试。

**SandboxPolicy 是策略模型，不是容器沙箱。** 真正 sandbox execution 需要 Step 24+ 容器/子进程基础设施。

## 2. SandboxLevel

| Level | is_execution_allowed | 说明 |
|-------|---------------------|------|
| `no_execution` | ❌ | 零代码执行 |
| `simulation_only` | ❌ | 仅仿真，不执行 |
| `restricted` | ✅ (if allowed) | 受限沙箱（预留） |
| `isolated` | ✅ (if allowed) | 隔离沙箱（预留） |

## 3. SandboxPolicy 字段（30+）

关键字段：
- `sandbox_level` — no_execution / simulation_only / restricted / isolated
- `allow_network` / `allowed_domains` — 网络控制
- `allow_filesystem_read/write` / `allowed_paths` — 文件系统控制
- `allow_secrets` / `allowed_secret_names` — 密钥控制
- `max_timeout_ms` / `max_memory_mb` / `max_cpu_percent` — 资源限制
- `audit_enabled` / `kill_switch_enabled` — 审计与 kill switch
- `system_managed` — 不可被普通 admin 删除/修改关键字段

## 4. 默认 Policies（3 个 system policies）

| policy_id | sandbox_level | 说明 |
|-----------|--------------|------|
| `sbxpol_no_execution` | no_execution | 默认回退，零执行 |
| `sbxpol_simulation_only` | simulation_only | 仿真用 policy |
| `sbxpol_restricted_network_off` | restricted | 预留 restricted（禁网）|

全部 `system_managed=True`，`is_execution_allowed() == False`（针对 no_execution/simulation_only）。

## 5. Admin API

**Prefix:** `/admin/sandbox-policies`

| Endpoint | 说明 |
|----------|------|
| `GET /` | List policies（system + tenant） |
| `GET /{id}` | Policy 详情 |
| `POST /` | Create tenant policy |
| `PATCH /{id}` | Update policy |
| `POST /{id}/test` | 静态规则评估（不执行代码） |
| `POST /{id}/enable` | Enable |
| `POST /{id}/disable` | Disable |
| `POST /bindings/{id}/assign` | 绑定 policy 到 runtime binding |

权限：admin/owner/super_admin（JWT only，API Key 禁止）。

## 6. Binding Assignment

- `POST /admin/sandbox-policies/bindings/{binding_id}/assign {"sandbox_policy_id": "..."}`
- 不 enable binding — assignment ≠ execution
- 绑定后 runtime_store.set_binding_sandbox_policy()
- 权限：admin 只能操作 own tenant；super_admin 跨 tenant

## 7. Policy Test（静态评估）

`POST /{id}/test` 只做静态规则评估：sandbox_level / network / domains / filesystem / secrets / timeout / memory / data_access_scope。不执行代码、不联网、不读文件。

## 8. Non-Execution Guarantees

- ❌ SandboxPolicy 是策略模型，不执行代码
- ❌ test endpoint 只做静态规则评估
- ❌ assignment 不 enable binding
- ❌ 不调用 AgentRuntime / AgentRegistry
- ❌ 不联网 / 不读文件 / 不读 secrets
- ✅ 真正 sandbox execution → Step 24+

## 9. 测试

- Sandbox Policy 专项：67 tests
- Open Platform 全量：460 passed（393 + 67）
- 后端全量回归：1107 passed（1040 + 67）

## 10. 新增/修改文件

| 文件 | 操作 |
|------|------|
| `src/open_platform/sandbox_policy.py` | 新增 — domain model (~300 行) |
| `src/adapters/sandbox_policy_store.py` | 新增 — SQLite store (~360 行) |
| `src/api/sandbox_policy_router.py` | 新增 — Admin API (~280 行) |
| `src/core/usage.py` | 修改 — 4 new UsageResources |
| `main.py` | 修改 — store + seed + router bootstrap |
| `tests/test_open_platform/test_sandbox_policy.py` | 新增 — 67 tests |
| `docs/ROADMAP.md` | 修改 — 23-E 标记 ✅ |

## 11. Next Step

Step 23-F：Package Validation Pipeline
