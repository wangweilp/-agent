# Step 25-B：Sandbox Execution Store + Audit Model

## 1. 本轮目标

实现 Sandbox Execution Record + Audit Event domain model, SQLite store, audit-only service, tests. **No execution. No queue. No dispatch.**

## 2. Domain Model

`src/open_platform/sandbox_execution.py`

- SandboxExecutionStatus: 9 states (NO RUNNING/COMPLETED/SUCCEEDED)
- SandboxExecutionDecision: 5 decisions (all blocked/review/reserved/fail-closed)
- SandboxExecutionQueueStatus: 4 states (NO QUEUED/DISPATCHED/RUNNING)
- SandboxExecutionRecord: 44 fields, 6 snapshots, 10 safety bools. `is_executable()` always False. `is_queued()` always False. No execute/dispatch/run method.
- SandboxExecutionAuditEvent: 9 fields, append-only. Metadata excludes secrets/raw_key/package_url.
- SandboxExecutionStore Protocol: 12 methods (no enqueue/dispatch/execute/delete).

## 3. SQLite Store

`src/adapters/sandbox_execution_store.py`

2 tables: sandbox_executions (42 columns, 10 indexes) + sandbox_execution_audit_events (9 columns, 4 indexes). Auto-audit on create/status/decision/queue/cancel/expire. No physical delete.

## 4. Service

`src/open_platform/sandbox_execution_service.py`

`SandboxExecutionRecordService.create_audit_only_execution_from_plan()` — copies plan snapshots, stores input_payload_hash only, sets all safety flags True, queue_status=QUEUE_DISABLED. No queue/dispatch/execute.

## 5. Usage

5 new UsageResource enums. Metadata safe.

## 6. Tests

86 tests: domain (20) + store (34) + service (13) + integration/safety (19).
1436 Open Platform passed.

## 7. Next Step

Step 25-C：Container/MicroVM Adapter Feasibility Spike
