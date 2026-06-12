# Step 26-B: Kill Switch + Runtime Incident Store

**Status**: ✅ Complete  **Date**: 2026-06-12

## Scope

**This step is metadata/control-plane readiness only. No runtime kill implementation.**

Step 26-B builds the safety control plane: kill switch policies, triggers, incident records, and audit events — all operating in the data/metadata layer. No process is killed. No runtime is terminated. No worker, container, or microVM is stopped.

## Deliverables

### 1. Domain Models (`src/open_platform/runtime_kill_switch.py`)

| Class | Description |
|-------|-------------|
| `RuntimeKillSwitchPolicy` | Safety policy: blocks future admission/execution, defines auto-trigger rules. All `*_kill_implemented` = `False`. |
| `RuntimeKillSwitchTrigger` | Trigger record: `TRIGGERED_METADATA_ONLY`. All `no_*` flags = `True`. `is_runtime_kill_active()` always returns `False`. |
| `RuntimeIncidentRecord` | Incident lifecycle: `open` → `triaged` → `closed_metadata_only`. `is_runtime_stopped()` always returns `False`. |
| `RuntimeSafetyAuditEvent` | Audit trail for every safety control-plane action. |
| `RuntimeSafetyStore` (Protocol) | Store interface with 17 methods — no kill/terminate/stop/execute/dispatch/enqueue. |

### 2. SQLite Store (`src/adapters/runtime_safety_store.py`)

4 tables:
- `runtime_kill_switch_policies` — policy CRUD
- `runtime_kill_switch_triggers` — trigger CRUD + release
- `runtime_incidents` — incident CRUD + triage + close metadata-only
- `runtime_safety_audit_events` — audit trail

No kill/terminate/stop/execute/dispatch/enqueue methods exist on the store.

### 3. Service (`src/open_platform/runtime_safety_service.py`)

- `create_default_kill_switch_policy()` — creates metadata-only policy (all kill impl = False)
- `trigger_kill_switch_metadata_only()` — creates trigger with `TRIGGERED_METADATA_ONLY`, no kill
- `release_kill_switch_metadata_only()` — releases trigger metadata-only
- `create_incident()` — creates incident record, auto-sets decision based on severity
- `auto_trigger_for_critical_incident()` — only triggers when policy's `auto_trigger_on_critical_incident` = True
- `triage_incident()` / `close_incident_metadata_only()` — incident lifecycle management

### 4. Usage (`src/core/usage.py`)

7 new `UsageResource` enums added for kill switch + incident tracking.

## What This Step IS

- ✅ Kill switch policy as metadata/control-plane readiness
- ✅ `RuntimeKillSwitchTrigger` is `TRIGGERED_METADATA_ONLY`
- ✅ `is_runtime_kill_active()` returns `False` — always
- ✅ `is_runtime_stopped()` returns `False` — always
- ✅ `is_execution_allowed()` returns `False` — always
- ✅ Incident lifecycle: open → triage → close metadata-only
- ✅ Audit events for every safety action
- ✅ All `runtime_kill_implemented`/`process_kill_implemented`/`worker_kill_implemented` = `False`
- ✅ All `no_process_killed`/`no_runtime_terminated`/`no_worker_stopped` = `True`

## What This Step IS NOT

- ❌ NOT a runtime kill implementation
- ❌ NOT a process termination mechanism
- ❌ NOT a worker/container/microVM stop mechanism
- ❌ NOT a package execution or download system
- ❌ NOT a queue dispatch or enqueue system
- ❌ NOT a production sandbox completion
- ❌ NOT a third-party execution enabler
- ❌ NOT `AgentRuntime` or `AgentRegistry` integration

## Hard Gates Status

| Gate | Status |
|------|--------|
| No process kill | ✅ `process_kill_implemented=False`, `no_process_killed=True` |
| No runtime terminate | ✅ `runtime_kill_implemented=False`, `no_runtime_terminated=True` |
| No worker stop | ✅ `worker_kill_implemented=False`, `no_worker_stopped=True` |
| No container stop | ✅ `container_stop_implemented=False`, `no_container_stopped=True` |
| No microVM stop | ✅ `microvm_stop_implemented=False`, `no_microvm_stopped=True` |
| No execution | ✅ `no_execution_performed=True` |
| No dispatch | ✅ `no_dispatch_performed=True` |
| No enqueue | ✅ `no_queue_modified=True` |
| No AgentRuntime | ✅ Not imported |
| No AgentRegistry | ✅ Not imported |
| Execute endpoint blocked | ✅ `test_gate_blocked` PASSED |
| `is_runtime_kill_active()` = False | ✅ Always returns False |
| `is_runtime_stopped()` = False | ✅ Always returns False |
| Incident close ≠ runtime fixed | ✅ `CLOSED_METADATA_ONLY` status |

## Tests

```
test_runtime_safety_store.py  118 passed
```

Coverage:
- 23 Domain tests (policy, trigger, incident, audit event, enum validation)
- 42 Store tests (CRUD, guard methods, audit, behavior)
- 33 Service tests (policy, trigger, release, incident lifecycle, guard methods, behavior)
- 20 Safety tests (static module scans for dangerous imports)

## Files Changed

| File | Change |
|------|--------|
| `src/open_platform/runtime_kill_switch.py` | New — domain models, enums, protocol |
| `src/adapters/runtime_safety_store.py` | New — SQLite store (4 tables, placeholder fix applied) |
| `src/open_platform/runtime_safety_service.py` | New — safety service layer |
| `tests/test_open_platform/test_runtime_safety_store.py` | New — 118 tests |
| `src/core/usage.py` | Modified — added 7 UsageResource enums |

## Next Step

**Step 26-C: Controlled Package Download Worker, Disabled by Default**

Step 26-C will create a disabled-by-default package download worker — still no execution, no entrypoint invocation, no third-party code.

## Security Boundary

- No kill process ✅
- No terminate runtime ✅
- No stop worker ✅
- No stop container ✅
- No stop microVM ✅
- No execution ✅
- No dispatch ✅
- No enqueue ✅
- No start worker ✅
- No download package ✅
- No extract archive ✅
- No network access ✅
- No filesystem write ✅
- No secret access ✅
- No eval/exec/dynamic import ✅
- No subprocess ✅
- No docker ✅
- No AgentRuntime/AgentRegistry ✅
- Execute endpoint still blocked ✅
