# Step 24-E：Sandbox Worker Interface + Disabled-by-default Stub

## 1. 本轮目标

实现 Sandbox Worker 的接口抽象、Disabled-by-default Stub、Worker Registry 和 74 个安全测试。

**只做 interface + disabled stub — 不 subprocess/container/execute。**

## 2. Domain Model

`src/open_platform/sandbox_worker.py`

- SandboxWorkerType: DISABLED_STUB + 4 RESERVED types
- SandboxWorkerAvailability: DISABLED (default in Step 24-E)
- SandboxWorkerDecision: 6 values (all BLOCKED/RESERVED/FAIL_CLOSED)
- SandboxWorkerResultStatus: BLOCKED/REJECTED/SKIPPED/RESERVED — 无 RUNNING/COMPLETED/SUCCESS
- SandboxWorker Protocol: get_worker_type(), get_availability(), evaluate_request() — 无 execute/run/dispatch
- SandboxWorkerRequest (sbxreq_<16>): plan_id, input_payload_hash only, 3 snapshots
- SandboxWorkerResult (sbxres_<16>): 10 safety booleans all True, is_successful_execution() always False
- build_worker_request_from_plan() — no dispatch, no mutation

## 3. DisabledSandboxWorker

`src/open_platform/sandbox_worker_stub.py`

- availability=DISABLED, evaluate_request→BLOCKED_DISABLED
- 9 checks: WORKER_DISABLED (BLOCKED) + 7 PASSED + FAIL_CLOSED (PASSED)
- No execute/dispatch/run methods. No file/network/subprocess access.

## 4. SandboxWorkerRegistry

`src/open_platform/sandbox_worker_registry.py`

- Default: only DisabledSandboxWorker. No dynamic import. Not AgentRegistry.

## 5. Usage

3 new: SANDBOX_WORKER_EVALUATE, SANDBOX_WORKER_BLOCKED, SANDBOX_WORKER_FAIL_CLOSED

## 6. Tests

74 tests (domain 19 + stub 22 + registry 8 + plan integration 6 + safety 19)
978 Open Platform / 1625 full regression passed.

## 7. Next Step

Step 24-F：Policy Enforcement Translator
