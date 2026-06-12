# Step 24-I：Security Tests + Escape Guard Tests

## 1. 本轮目标

系统性补强 Step 24 全链路安全测试、逃逸防护测试、导入污染测试、API 门禁测试、非执行保证测试。

**只做安全测试 — 不开发新功能、不新增执行能力。**

## 2. Security Guard Coverage Matrix

| Guard Category | # Tests | Key Checks |
|---|---|---|
| A. Import Guards | 20 modules × 3 checks | No subprocess/docker/requests/AgentRuntime/AgentRegistry imports |
| B. Method Name Guards | 16 | No execute/run/dispatch on workers/plans/gates |
| C. Execute Endpoint Guards | 14 | Always blocked, no stdout/stderr/exit_code, non_exec_guarantees present |
| D. Worker/Registry Guards | 15 | Default disabled only, no container/process/wasm/microVM, dry-run no real exec |
| E. Package Supply-Chain Guards | 13 | No download, checksum only sha256/384/512, signature metadata-only, path outside root blocked |
| F. Policy Enforcement Guards | 12 | no_exec/sim not execution, isolated fail-closed, host_mount/raw_env/direct_db blocked |
| G. Metadata Leakage Guards | 10 | No raw_key/key_hash/secrets/package_url/raw input/stdout/stderr across all to_dict() outputs |
| H. Startup Guards | 10 | main.py no worker/queue/execution claims, no auto local dev enable |
| I. Documentation Guards | 10 | All STEP24*.md docs checked for false claims of completion |

## 3. Non-Execution Invariants

All 168 tests confirm:
- `/runtime/agents/{id}/execute` always blocked
- `is_execution_allowed()` always False
- `is_successful_execution()` always False
- `is_real_execution()` always False
- `is_dispatchable()` always False
- Worker registry defaults to disabled stub only
- Local dev sandbox is dry-run only, disabled by default
- Policy config ≠ execution permission
- Plan created ≠ dispatchable

## 4. Tests

```bash
python -m pytest tests/test_open_platform/test_step24_security_escape_guards.py -v
# 168 passed

python -m pytest tests/test_open_platform/ -q
# 1320 passed

python -m pytest tests/test_security.py tests/test_agents/ tests/test_saas/ tests/test_open_platform/ -q
# 1967 passed
```

## 5. Startup

- runtime_execution_api_registered ✅
- admin_review_api_registered ✅
- No runtime_worker_started / execution_enabled
- No database is locked / Traceback

## 6. Minimal Security Fixes

No production code changes required. Four test assertions adjusted for false positives:
- AgentRuntime/AgentRegistry check: router module uses these in safety messages ("not called"), not as imports
- Subprocess/container check: NON_EXEC strings contain "no_subprocess_used" safety messages
- Doc check: STEP24A doc includes "external code execution completed" only in denial context

## 7. Next Step

Step 24-J：Demo + Documentation
