# Step 24-G：Local Development Sandbox Prototype

## 1. 本轮目标

实现 Local Dev Sandbox Prototype — disabled-by-default, dry-run only, fail-closed。

**不 subprocess/container/network/file/secrets/execute。**

## 2. Domain Model

`src/open_platform/local_dev_sandbox.py`

- LocalDevSandboxMode: DISABLED, DRY_RUN_ONLY, TRUSTED_FIXTURE_RESERVED
- LocalDevSandboxConfig: 14 fields, all dangerous capabilities default False (disabled/dry_run_for_tests)
- LocalDevSandboxDryRunResult: 21 fields, is_real_execution()=False, output_preview only deterministic metadata

## 3. Worker

`src/open_platform/local_dev_sandbox_worker.py`

LocalDevSandboxPrototypeWorker implements SandboxWorker Protocol:
- disabled: returns BLOCKED_DISABLED
- dry_run_for_tests: evaluates policy_config_snapshot, fails closed on network/secrets/filesystem/data access
- All checks: DRY_RUN_ONLY_MODE, POLICY_CONFIG_PRESENT/ENFORCEABLE, NETWORK_DENY, SECRETS_DENY, FILESYSTEM_SAFE, DATA_ACCESS_BROKER, 8 safety PASSED, FAIL_CLOSED
- is_successful_execution() always False

## 4. Registry

`src/open_platform/sandbox_worker_registry.py`

- Default: only DisabledSandboxWorker
- `create_default_sandbox_worker_registry(enable_local_dev_dry_run=False)` — optional dry-run worker
- Never default. Never auto-enable.

## 5. SandboxWorkerRequest

New field: `policy_config_snapshot: dict` — populated by from_plan, can be set manually.

## 6. Usage

3 new: LOCAL_DEV_SANDBOX_EVALUATE, LOCAL_DEV_SANDBOX_BLOCKED, LOCAL_DEV_SANDBOX_DRY_RUN

## 7. Tests

81 tests: domain (19) + disabled (13) + dry-run (16) + registry (9) + request (7) + safety (17)

```bash
python -m pytest tests/test_open_platform/test_local_dev_sandbox_prototype.py -v
# 81 passed

python -m pytest tests/test_open_platform/ -q
# 1127 passed

python -m pytest tests/test_security.py tests/test_agents/ tests/test_saas/ tests/test_open_platform/ -q
# 1774 passed
```

## 8. Next Step

Step 24-H：Runtime Execution API Draft + Admin Gate
