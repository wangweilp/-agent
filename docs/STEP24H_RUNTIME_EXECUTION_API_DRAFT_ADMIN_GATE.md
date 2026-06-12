# Step 24-H：Runtime Execution API Draft + Admin Gate

## 1. 本轮目标

实现 Runtime Execution API 草案 + admin-gated plan endpoints + blocked execute endpoint。

**不执行、不dispatch、不worker、不queue。** `/runtime/agents/{id}/execute` 永远 blocked。

## 2. Domain Model

`src/open_platform/runtime_execution_gate.py`

- RuntimeExecutionGateStatus: DISABLED, PLAN_ONLY, DRY_RUN_ONLY, RESERVED_FOR_SANDBOX, BLOCKED
- RuntimeExecutionGateDecision: 8 decisions (all blocked/preview/plan_only)
- RuntimeExecutionApiMode: ADMIN_PLAN_ONLY, ADMIN_PREVIEW_ONLY, USER_EXECUTE_DISABLED, API_KEY_EXECUTE_DISABLED
- RuntimeExecutionGateCheck — 20 check types
- RuntimeExecutionGateResult — is_execution_allowed() always False

## 3. API Router

`src/api/runtime_execution_router.py`

Admin endpoints (JWT admin/owner/super_admin only):
- `POST /admin/runtime/execution-plans` — create plan (no execution)
- `GET /admin/runtime/execution-plans` — list plans
- `GET /admin/runtime/execution-plans/{id}` — plan detail + audit
- `POST /admin/runtime/execution-plans/{id}/cancel` — cancel (no dispatch)
- `POST /admin/runtime/execution-plans/{id}/expire` — expire (no dispatch)
- `POST /admin/runtime/execution-plans/{id}/policy-preview` — policy → config preview
- `POST /admin/runtime/execution-plans/{id}/worker-preview` — worker evaluation preview

Execute draft endpoint (always blocked):
- `POST /runtime/agents/{id}/execute` — returns 200 + blocked payload, is_execution_allowed=False

## 4. Bootstrap

main.py registers:
- `SQLiteRuntimeExecutionPlanStore`
- `RuntimeExecutionPlannerService`
- `SandboxPolicyEnforcementTranslator`
- `create_default_sandbox_worker_registry(enable_local_dev_dry_run=False)`
- `create_runtime_execution_router(...)`

No worker/queue/subprocess/container started.

## 5. Usage

5 new: RUNTIME_EXECUTION_PLAN_API_CREATE, RUNTIME_EXECUTION_PLAN_API_VIEW, RUNTIME_EXECUTION_POLICY_PREVIEW, RUNTIME_EXECUTION_WORKER_PREVIEW, RUNTIME_EXECUTION_DRAFT_BLOCKED

## 6. Tests

25 tests: gate domain (10) + API logic (5) + safety (10)

```bash
# 25 passed
python -m pytest tests/test_open_platform/ -q
# 1152 passed
python -m pytest tests/test_security.py tests/test_agents/ tests/test_saas/ tests/test_open_platform/ -q
# 1799 passed
```

Startup: runtime_plan_store_initialized ✅, runtime_execution_api_registered ✅, no runtime_worker_started, no database locked

## 7. Next Step

Step 24-I：Security Tests + Escape Guard Tests
