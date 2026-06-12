# Step 26-D: Read-only Artifact Materialization Spike

**Status**: ✅ Complete  **Date**: 2026-06-12

## Scope

**This step is read-only artifact materialization control-plane spike only. No real materialization. No file write. No directory creation. No mount. No archive read. No extraction. No execution.**

Step 26-D builds the artifact materialization domain model, SQLite store, and service — all metadata/control-plane only. Every policy starts disabled. Every request starts blocked. Every gate returns BLOCKED_DISABLED. Every plan is not materialized. Every reference is logical-only with no filesystem path.

## Deliverables

### 1. Domain Model (`src/open_platform/artifact_materialization.py`)

| Class | Description |
|-------|-------------|
| `ArtifactMaterializationPolicy` | Policy: `materialization_enabled=False`, `file_write_enabled=False`, `mount_enabled=False`, `extraction_enabled=False`, `package_execution_enabled=False`. All `is_*()` methods return `False`. |
| `ArtifactMaterializationRequest` | Request: metadata-only record with snapshots. `materialization_performed=False`, `file_written=False`, `directory_created=False`, `mount_created=False`, `archive_read=False`. All `is_*_allowed()` methods return `False`. |
| `ReadOnlyArtifactMaterializationPlan` | Plan: `materialization_allowed=False`, `mount_allowed=False`, `execution_allowed=False`. `is_materialized()` and `is_mount_active()` always return `False`. |
| `ReadOnlyArtifactReference` | Logical reference: `filesystem_path=None`, `filesystem_ref_active=False`, `file_opened=False`, `file_written=False`, `mount_active=False`. All `is_*()` methods return `False`. |
| `ArtifactMaterializationGateResult` | Gate: all `*_allowed` flags = `False`, `metadata_only=True`. |
| `ArtifactMaterializationAuditEvent` | Audit trail for every control-plane action. |
| `ArtifactMaterializationStore` (Protocol) | Store interface with 22 methods — no materialize/write/mount/extract/open/execute/dispatch/enqueue/start_worker. |

### 2. SQLite Store (`src/adapters/artifact_materialization_store.py`)

6 tables:
- `artifact_materialization_policies`
- `artifact_materialization_requests`
- `artifact_materialization_plans`
- `artifact_materialization_references`
- `artifact_materialization_gate_results`
- `artifact_materialization_audit_events`

No dangerous methods. Uses `_placeholders(len(values))`.

### 3. Service (`src/open_platform/artifact_materialization_service.py`)

- `create_disabled_materialization_policy()` — all capability flags = `False`
- `create_materialization_request_metadata_only()` — snapshots only, no side effects
- `evaluate_materialization_gate()` — always returns `BLOCKED_DISABLED`
- `reserve_materialization_plan_metadata_only()` — plan not materialized
- `reserve_read_only_artifact_reference()` — logical ref, `filesystem_path=None`
- `cancel_request()` / `expire_request()` — lifecycle

### 4. Usage (`src/core/usage.py`)

7 new `UsageResource` enums. Metadata marks `materialization_allowed=False`, `file_write_allowed=False`, `mount_allowed=False`, `metadata_only=True`.

## What This Step IS

- ✅ Read-only artifact materialization control-plane spike
- ✅ Metadata-only materialization request/plan/reference records
- ✅ Gate evaluation that always returns BLOCKED_DISABLED
- ✅ Logical artifact references (no real filesystem paths)
- ✅ Audit trail for every control-plane action

## What This Step IS NOT

- ❌ NOT a real artifact materializer
- ❌ NOT a file writer / directory creator
- ❌ NOT a filesystem mounter
- ❌ NOT an archive reader / extractor
- ❌ NOT a package executor / entrypoint runner
- ❌ NOT a local path file checker (no `Path.exists`, no `os.path`)
- ❌ NOT a production sandbox completion

## Hard Gates Status

| Gate | Status |
|------|--------|
| No real materialization | ✅ `materialization_performed=False` |
| No file write | ✅ `file_written=False`, `no_file_written=True` |
| No directory creation | ✅ `directory_created=False`, `no_directory_created=True` |
| No mount | ✅ `mount_created=False`, `mount_allowed=False` |
| No archive read | ✅ `archive_read=False`, `no_archive_read=True` |
| No extraction | ✅ `archive_extracted=False`, `extraction_allowed=False` |
| No execution | ✅ `package_executed=False`, `execution_allowed=False` |
| No local paths | ✅ `filesystem_path=None`, `is_filesystem_ref_active()=False` |
| Execute endpoint blocked | ✅ Still blocked |

## Tests

```
test_artifact_materialization.py  116 passed
```

Coverage: 35 Domain + 36 Store + 27 Service + 18 Safety

## Files

| File | Change |
|------|--------|
| `src/open_platform/artifact_materialization.py` | New — domain model |
| `src/adapters/artifact_materialization_store.py` | New — SQLite store (6 tables) |
| `src/open_platform/artifact_materialization_service.py` | New — service layer |
| `tests/test_open_platform/test_artifact_materialization.py` | New — 116 tests |
| `docs/STEP26D_READ_ONLY_ARTIFACT_MATERIALIZATION_SPIKE.md` | New — this doc |
| `src/core/usage.py` | Modified — 7 UsageResource enums |
| `README.md` | Modified — Step 26-D section |
| `docs/ROADMAP.md` | Modified — 26-D ⏸ → ✅ |

## Next Step

**Step 26-E: Rootless Container Prototype Gate**

Step 26-E will create a rootless container prototype gate — still no real container, no execution, no third-party code.

## Security Boundary

- No real materialization ✅
- No file write ✅
- No directory creation ✅
- No filesystem mount ✅
- No local path read ✅
- No file open ✅
- No `Path.exists` ✅
- No archive read ✅
- No package extraction ✅
- No package download ✅
- No URL access ✅
- No network ✅
- No execution ✅
- No entrypoint ✅
- No worker start ✅
- No queue ✅
- No enqueue ✅
- No dispatch ✅
- No subprocess ✅
- No docker ✅
- No AgentRuntime ✅
- No AgentRegistry ✅
- Execute endpoint still blocked ✅
- `request.is_materialization_allowed()` = False ✅
- `plan.is_materialized()` = False ✅
- `reference.is_filesystem_ref_active()` = False ✅
- `gate.execution_allowed` = False ✅
