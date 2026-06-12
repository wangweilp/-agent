# Step 23-D：Simulation Runtime Adapter

## 1. 概述

Step 23-D 实现 Developer Agent 安全仿真运行时，在不执行第三方代码的前提下验证 install → permissions → runtime binding → adapter → scope 完整链路。

## 2. 为什么 Simulation 不是 Execution

- **不执行 package_url** — 包 URL 只做存在性检查（warning），不下不执行
- **不执行 entrypoint** — 不调用任何外部代码入口
- **不联网** — SimulationAdapter 无网络能力
- **不读取真实企业数据** — simulated_output 是确定性 mock
- **不调用 AgentRuntime** — 不进入 PEOR 循环
- **不注册 AgentRegistry** — 不创建 AgentRegistration

## 3. SimulationRunRequest

```python
@dataclass
class SimulationRunRequest:
    marketplace_agent_id: str
    tenant_id: str
    user_id: str | None
    developer_id: str | None
    input_text: str | None
    input_payload: dict
    requested_permissions: list[str]
    api_key_scopes: list[str]
    auth_type: str     # jwt | developer_api_key
    metadata: dict
```

## 4. SimulationRunResult

```python
@dataclass
class SimulationRunResult:
    run_id: str
    status: str          # success | failed | blocked
    blocked_reason: str | None
    simulated_output: dict   # deterministic mock
    steps: list[SimulationStep]  # 9 validation steps
    usage_recorded: bool
    metadata: dict       # 强制: no_remote_code_execution=True, simulation_only=True
```

## 5. Simulation Steps（9步验证链路）

1. validate_marketplace_agent — agent 是否存在
2. validate_developer_publisher — publisher_type 是否为 developer
3. validate_runtime_metadata — package_url/entrypoint 不执行
4. validate_installation — TenantAgentInstallation 存在且 active
5. validate_permissions — required_permissions 已授予
6. validate_runtime_binding — RuntimeBinding 存在且 enabled
7. validate_adapter — adapter_type 必须 simulation + active
8. validate_scope — API Key 必须有 agent:simulate
9. generate_simulated_response — deterministic mock output

## 6. API Endpoint

**POST /developers/marketplace-agents/{marketplace_agent_id}/simulate**

- Auth：JWT 或 API Key (agent:simulate | agent:execute:simulation)
- 验证：Developer 身份、Marketplace Agent 状态、Installation、Permissions、Runtime Binding
- 响应：SimulationRunResult（blocked 返回 200 含 blocked_reason）
- 不修改任何系统状态（只读 + usage event）

## 7. Non-Execution Guarantees

- ❌ 不执行 package_url
- ❌ 不执行 entrypoint
- ❌ 不联网
- ❌ 不读取真实企业数据
- ❌ 不调用 AgentRuntime
- ❌ 不注册 AgentRegistry
- ❌ 不创建 installation
- ❌ 不创建 runtime binding
- ❌ publish 不自动 runtime enable
- ✅ simulated_output 是 deterministic mock

## 8. Usage

- `UsageResource.AGENT_SIMULATION_RUN` — success 和 blocked 均记录
- metadata：run_id, marketplace_agent_id, developer_id, tenant_id, adapter_id, binding_id, simulation_status, blocked_reason, duration_ms, simulation_only=True, no_remote_code_execution=True
- 不包含：raw_key, key_hash, full input_payload, package_url, entrypoint, secrets

## 9. Main.py Bootstrap

- `SQLiteRuntimeStore` 初始化（Step 23-C）+ `seed_builtin_adapters()`（幂等）
- `SimulationRuntimeService` 初始化（注入 marketplace_store, runtime_store, usage_store）
- `create_developer_router` 传入 marketplace_store, runtime_store, simulation_service

## 10. 新增/修改文件

| 文件 | 操作 |
|------|------|
| `src/open_platform/simulation.py` | 新增 — domain model |
| `src/open_platform/simulation_runtime.py` | 新增 — service |
| `src/core/usage.py` | 修改 — AGENT_SIMULATION_RUN |
| `src/api/developer_router.py` | 修改 — simulation endpoint |
| `main.py` | 修改 — runtime + simulation bootstrap |
| `tests/test_open_platform/test_simulation_runtime.py` | 新增 — 38 tests |
| `docs/STEP23D_SIMULATION_RUNTIME.md` | 新增 — 本文档 |

## 11. 测试

- Simulation 专项：38 tests（domain model + service blocked + service success + api endpoint）
- Open Platform 全量：393 passed（355 + 38）
- 后端全量回归：1040 passed（1002 + 38）

## 12. Known Issues

| # | 问题 | 状态 |
|---|------|------|
| 1 | Simulation 不接真实企业数据 | 设计如此 |
| 2 | 无 AgentMetrics 专用存储 | usage events 替代 |
| 3 | Sandbox Policy 未实现 | Step 23-E |

## 13. Next Step

Step 23-E：Sandbox Policy Model + Admin API
