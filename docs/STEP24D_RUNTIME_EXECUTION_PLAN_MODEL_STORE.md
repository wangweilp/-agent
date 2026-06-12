# Step 24-D：Runtime Execution Plan Model + Store

## 1. 本轮目标

实现 Runtime Execution Plan 的领域模型、SQLite Store、Planner Service 和测试。

**只做 plan — 不 dispatch / 不 execute / 不 worker / 不联网。**

## 2. Domain Model

`src/open_platform/runtime_execution_plan.py`

### Enums
- RuntimeExecutionMode: SIMULATION, SANDBOX_RESERVED, DISABLED
- RuntimeExecutionPlanStatus: DRAFT, PLANNED, BLOCKED, REVIEW_REQUIRED, EXPIRED, CANCELLED
- RuntimeDispatchStatus: NOT_DISPATCHABLE, WORKER_UNAVAILABLE, RESERVED_FOR_STEP24E, DISABLED
- RuntimePlanDecision: ALLOW_PLAN, BLOCK_PLAN, REVIEW_REQUIRED, RESERVED_ONLY
- RuntimePlanCheckType: 20 preflight check types (MARKETPLACE_AGENT_EXISTS through NO_NETWORK_IN_PLAN)
- RuntimePlanCheckStatus / RuntimePlanSeverity / RuntimeExecutionRiskLevel
- RuntimeExecutionPlanAuditEventType: 6 types

### RuntimeExecutionPlanCheck
check_id (planchk_<16>), check_type, status, severity, message, metadata

### RuntimeExecutionPlan
plan_id (rtexplan_<16>), marketplace_agent_id, tenant_id, developer_id, submission_id, runtime_binding_id, adapter_id, adapter_type, sandbox_policy_id, artifact_id, verification_id, execution_mode, plan_status, dispatch_status, decision, risk_level, checks list, counts, input_payload_hash, snapshots, safety flags, worker_required/available

- is_dispatchable() **always False** — Step 24-D no worker
- calculate_status() → BLOCKED/REVIEW_REQUIRED/PLANNED
- hash_payload() — SHA256 of sorted JSON

## 3. SQLite Store

`src/adapters/runtime_execution_plan_store.py`

2 tables: runtime_execution_plans (37 columns, 8 indexes) + runtime_execution_plan_audit_events (8 columns, 4 indexes)

9 methods: create_plan, get_plan, list_plans, update_plan, set_plan_status, cancel_plan, expire_plan, count_plans, add_audit_event, list_audit_events

## 4. Planner Service

`src/open_platform/runtime_execution_planner.py`

20 preflight checks across 7 phases:
- Phase 0: Safety (NO_DOWNLOAD/NO_NETWORK/NO_EXECUTION)
- Phase 1: Marketplace (agent exists + developer-only)
- Phase 2: Installation (active + permissions)
- Phase 3: Runtime Binding (exists + enabled + adapter allowed)
- Phase 4: Sandbox Policy (exists + active)
- Phase 5: Artifact (declared + not rejected + quarantine acceptable)
- Phase 6: Verification (exists + checksum + signature metadata)
- Phase 7: Reserved (kill switch + worker — both skipped/warning)

Uses marketplace_store, runtime_store, sandbox_policy_store, artifact_store, verification_store.
Produces snapshots. input_payload_hash only (no raw input).

## 5. Usage

3 new UsageResource: RUNTIME_EXECUTION_PLAN_CREATE, RUNTIME_EXECUTION_PLAN_STATUS_CHANGE, RUNTIME_EXECUTION_PLAN_CANCEL

## 6. Non-Execution Guarantees

- is_dispatchable() always False
- dispatch_status never DISPATCHED/RUNNING/COMPLETED
- no worker/queue/container/subprocess
- no AgentRuntime/AgentRegistry

## 7. Tests

51 tests: domain (17) + store (25) + planner (9) + safety (5)
```bash
# 51 passed
```

## 8. Next Step

Step 24-E：Sandbox Worker Interface + Disabled-by-default Stub
