# Step 23-C：Runtime Adapter Domain Model + Store

## 1. 概述

Step 23-C 实现 Developer Agent Runtime Adapter 的领域模型、Runtime Binding 领域模型、SQLite Store、默认 adapter seed、eligibility 检查和单元测试。

**当前阶段不执行任何代码。本阶段只做状态管理和配置。**

## 2. RuntimeAdapterType

| Type | MVP Allowed | Status | 说明 |
|------|------------|--------|------|
| `manifest_only` | ✅ | active | Step 22 默认状态，纯元数据 |
| `simulation` | ✅ | beta | 不执行代码的仿真适配器 |
| `http_webhook` | ❌ | disabled | HTTP 回调，Step 24+ |
| `sandboxed_process` | ❌ | disabled | 子进程沙箱，Step 24+ |
| `container` | ❌ | disabled | 容器沙箱，Step 24+ |
| `builtin_bridge` | ❌ N/A | 预留 | 内置 Agent 桥接 |

## 3. RuntimeAdapter

```python
@dataclass
class RuntimeAdapter:
    adapter_id: str           # "rtadp_xxx"
    adapter_type: str         # RuntimeAdapterType
    name: str
    description: str
    supports_network: bool
    supports_user_data_read: bool
    supports_user_data_write: bool
    sandbox_required: bool
    max_timeout_ms: int
    max_memory_mb: int
    status: str               # active | beta | disabled | deprecated
    version: str
    config_schema: dict
    metadata: dict
```

## 4. DeveloperAgentRuntimeBinding

```python
@dataclass
class DeveloperAgentRuntimeBinding:
    binding_id: str              # "rtbind_xxx"
    marketplace_agent_id: str     # 关联 MarketplaceAgent
    submission_id: str | None     # 关联 Submission
    developer_id: str
    tenant_id: str
    adapter_id: str
    adapter_type: str
    runtime_status: str           # pending | enabled | disabled | suspended
    sandbox_policy_id: str | None # Step 23-E 接入
    enabled_by: str | None
    disabled_by: str | None
```

## 5. RuntimeEligibilityResult

评估 Developer Agent 是否具备 Runtime 条件。

**Eligibility Codes**：

| Code | 说明 |
|------|------|
| `eligible` | 可运行 |
| `no_binding` | 无 runtime binding |
| `binding_disabled` | binding pending/disabled/suspended |
| `adapter_disabled` | adapter 非 active/beta |
| `adapter_not_allowed` | MVP 不允许的 adapter type |
| `sandbox_policy_required` | sandbox adapter 无 policy |
| `installation_required` | 无 Marketplace installation（预留） |
| `permissions_required` | permissions 不满足（预留） |
| `runtime_not_implemented` | 运行时未实现（预留） |

## 6. Seed Adapters

`seed_builtin_adapters()` 幂等创建 5 个 adapter：

| adapter_id | type | status |
|-----------|------|--------|
| `rtadp_manifest_only` | manifest_only | active |
| `rtadp_simulation` | simulation | beta |
| `rtadp_http_webhook` | http_webhook | disabled |
| `rtadp_sandboxed_process` | sandboxed_process | disabled |
| `rtadp_container` | container | disabled |

## 7. Store Tables

**runtime_adapters**：15 列，UNIQUE adapter_type，含 config_schema_json + metadata_json。

**developer_agent_runtime_bindings**：13 列，UNIQUE (marketplace_agent_id, tenant_id)。

## 8. Binding Rules

1. 一个 marketplace_agent_id + tenant_id 最多一个 runtime binding
2. 不同 tenant 可为同一 mkp 创建不同 binding
3. create 默认 pending，需要 admin enable
4. enable 前检查：adapter 存在 + active + MVP allowed
5. 非 MVP adapter 禁止 enable
6. simulation/manifest_only 不需要 sandbox policy
7. publish 不自动创建 binding

## 9. Non-Execution Guarantees

- ❌ 不执行 package_url
- ❌ 不执行 entrypoint  
- ❌ 不调用 AgentRuntime
- ❌ 不注册 AgentRegistry
- ❌ publish 不自动创建 runtime binding
- ❌ simulation adapter 只是配置，不执行代码
- ✅ 所有操作仅为状态管理和持久化

## 10. 测试

- 新增 `tests/test_open_platform/test_runtime_store.py` — 65 tests
- Open Platform：355 passed（290 + 65）
- 后端全量回归：1002 passed（937 + 65）

## 11. 新增/修改文件

| 文件 | 操作 |
|------|------|
| `src/open_platform/runtime.py` | 新增 — domain model |
| `src/adapters/runtime_store.py` | 新增 — SQLite store |
| `tests/test_open_platform/test_runtime_store.py` | 新增 — 65 tests |
| `docs/STEP23C_RUNTIME_ADAPTER_STORE.md` | 新增 — 本文档 |
| `docs/ROADMAP.md` | 修改 — 23-C 标记 ✅ |

## 12. Next Step

Step 23-D：Simulation Runtime Adapter
