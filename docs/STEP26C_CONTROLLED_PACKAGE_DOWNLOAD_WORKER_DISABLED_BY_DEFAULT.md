# Step 26-C: Controlled Package Download Worker, Disabled by Default

**Status**: ✅ Complete  **Date**: 2026-06-12

## Scope

**This step is disabled-by-default download worker control-plane only. No real download. No network. No file write. No package materialization. No execution.**

Step 26-C builds the controlled package download worker domain model, SQLite store, and service — all operating as metadata-only. Every policy starts disabled. Every job starts blocked. Every gate returns BLOCKED_DISABLED. Every lease is inactive.

## Deliverables

### 1. Domain Model (`src/open_platform/package_download_worker.py`)

| Class | Description |
|-------|-------------|
| `PackageDownloadWorkerPolicy` | Worker policy: `worker_enabled=False`, `network_enabled=False`, `download_enabled=False`, `file_write_enabled=False`, `extraction_enabled=False`, `package_execution_enabled=False`. All `is_*()` methods return `False`. |
| `PackageDownloadWorkerJob` | Download job: metadata-only record with snapshots. `download_performed=False`, `network_used=False`, `file_written=False`, `package_executed=False`, `worker_started=False`, `job_dispatched=False`. All `is_*_allowed()` methods return `False`. |
| `PackageDownloadWorkerLease` | Lease placeholder: `lease_active=False`, `worker_started=False`, `heartbeat_enabled=False`, `download_allowed=False`. `is_active()` and `is_download_allowed()` always return `False`. |
| `PackageDownloadWorkerGateResult` | Gate evaluation: `worker_start_allowed=False`, `network_allowed=False`, `download_allowed=False`, `file_write_allowed=False`, `execution_allowed=False`, `metadata_only=True`. |
| `PackageDownloadWorkerAuditEvent` | Audit trail for every worker control-plane action. |
| `PackageDownloadWorkerStore` (Protocol) | Store interface with 20 methods — no start_worker/run_worker/download_package/fetch_package/write_file/materialize_package/execute_package/execute_entrypoint/dispatch_job/enqueue_job/heartbeat/delete_job. |

### 2. SQLite Store (`src/adapters/package_download_worker_store.py`)

5 tables:
- `package_download_worker_policies` — policy CRUD
- `package_download_worker_jobs` — job CRUD + status/decision change
- `package_download_worker_leases` — lease reserve/release metadata-only
- `package_download_worker_gate_results` — gate evaluation storage
- `package_download_worker_audit_events` — audit trail

No dangerous methods. Uses `_placeholders(len(values))` — no hand-counted placeholder strings.

### 3. Service (`src/open_platform/package_download_worker_service.py`)

- `create_disabled_worker_policy()` — policy with ALL capability flags = `False`
- `create_download_job_metadata_only()` — metadata-only job, no side effects
- `evaluate_download_worker_gate()` — always returns `BLOCKED_DISABLED`
- `reserve_worker_lease_metadata_only()` — lease placeholder, `lease_active=False`
- `release_worker_lease_metadata_only()` — release lease metadata-only
- `cancel_job()` / `expire_job()` — job lifecycle management

### 4. Usage (`src/core/usage.py`)

7 new `UsageResource` enums added for download worker tracking. All usage metadata marks `download_performed=False`, `network_used=False`, `metadata_only=True`.

## What This Step IS

- ✅ Disabled-by-default package download worker policy
- ✅ Metadata-only download job records with snapshots
- ✅ Gate evaluation that always returns BLOCKED_DISABLED
- ✅ Lease placeholder (inactive, no download allowed)
- ✅ Audit trail for every control-plane action
- ✅ All capability flags default to False

## What This Step IS NOT

- ❌ NOT a real package downloader
- ❌ NOT a package URL fetcher
- ❌ NOT a network client
- ❌ NOT a file writer
- ❌ NOT a package materializer
- ❌ NOT a package executor
- ❌ NOT an entrypoint runner
- ❌ NOT a worker starter
- ❌ NOT a job dispatcher/enqueuer
- ❌ NOT a production sandbox completion
- ❌ NOT a third-party execution enabler

## Hard Gates Status

| Gate | Status |
|------|--------|
| No real download | ✅ `download_performed=False`, `no_download_performed=True` |
| No network access | ✅ `network_used=False`, `no_network_used=True` |
| No file write | ✅ `file_written=False`, `no_file_written=True` |
| No package materialized | ✅ `package_materialized=False` |
| No package execution | ✅ `package_executed=False` |
| No entrypoint execution | ✅ `entrypoint_executed=False` |
| No worker started | ✅ `worker_started=False`, `no_worker_started=True` |
| No job dispatched | ✅ `job_dispatched=False`, `no_dispatch_performed=True` |
| Gate always blocked | ✅ `BLOCKED_DISABLED` |
| Lease always inactive | ✅ `lease_active=False` |
| Execute endpoint blocked | ✅ Still blocked |

## Tests

```
test_package_download_worker.py  111 passed
```

Coverage:
- 29 Domain tests (policy/job/lease/gate defaults, enum safety)
- 38 Store tests (CRUD, audit, JSON/bool roundtrip, no dangerous methods)
- 26 Service tests (policy creation, job creation, gate evaluation, lease management, no dangerous methods)
- 18 Safety tests (static module scans across domain/store/service, integration guards)

## Files Created/Modified

| File | Change |
|------|--------|
| `src/open_platform/package_download_worker.py` | New — domain model (5 dataclasses, 5 enums, protocol, errors) |
| `src/adapters/package_download_worker_store.py` | New — SQLite store (5 tables, 20 methods) |
| `src/open_platform/package_download_worker_service.py` | New — service layer (7 methods) |
| `tests/test_open_platform/test_package_download_worker.py` | New — 111 tests |
| `docs/STEP26C_CONTROLLED_PACKAGE_DOWNLOAD_WORKER_DISABLED_BY_DEFAULT.md` | New — this doc |
| `src/core/usage.py` | Modified — added 7 UsageResource enums |
| `README.md` | Modified — Step 26-C section |
| `docs/ROADMAP.md` | Modified — 26-C ⏸ → ✅ |

## Next Step

**Step 26-D: Read-only Artifact Materialization Spike**

Step 26-D will create a read-only artifact materialization spike — still no download, no network, no execution.

## Security Boundary

- No real package download ✅
- No package URL access ✅
- No repository URL access ✅
- No network ✅
- No file write ✅
- No package materialization ✅
- No package extraction ✅
- No package execution ✅
- No entrypoint execution ✅
- No worker start ✅
- No real queue creation ✅
- No enqueue ✅
- No dispatch ✅
- No subprocess ✅
- No docker ✅
- No AgentRuntime ✅
- No AgentRegistry ✅
- Execute endpoint still blocked ✅
- `job.is_download_allowed()` = False ✅
- `gate.download_allowed` = False ✅
- `lease.is_active()` = False ✅
