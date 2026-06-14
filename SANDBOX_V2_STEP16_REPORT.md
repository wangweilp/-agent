# Sandbox v2 Step 16 Report: Performance, Capacity, Baseline

Date: 2026-06-13
Project: `D:\dma\day2`

## Result

Step 16 is implemented as a safe benchmark control plane and baseline report workflow.

This step does not claim production load-test completion. It only benchmarks bounded Sandbox v2 control-plane paths with synthetic fixtures. It does not execute user code, open external network connections, start containers, start MicroVMs, run third-party load tests, or auto-start PostgreSQL/Redis/MinIO.

## Implemented Scope

- Safe performance configuration defaults in Sandbox v2 settings.
- Benchmark and capacity data models.
- SQLite persistence for benchmark configs, benchmark results, and capacity estimates.
- PostgreSQL schema additions for the same entities.
- Performance benchmark runner for synthetic control-plane targets.
- Service-layer APIs with fail-closed default behavior.
- Runtime Admin UI section for performance readiness, benchmark configs, results, and latest capacity.
- Smoke benchmark CLI script with default skipped behavior and explicit `--force-smoke`.
- Documentation, operations runbook notes, monitoring notes, and deployment checklist additions.
- Focused unit, API, script, red-team, and broad Sandbox v2 regression checks.

## Safety Defaults

New environment flags default to disabled:

```bash
SANDBOX_V2_PERF_TESTS_ENABLED=false
SANDBOX_V2_RUN_PERFORMANCE_BENCHMARKS=false
SANDBOX_V2_PERF_PROFILE=small
SANDBOX_V2_PERF_MAX_JOBS=100
SANDBOX_V2_PERF_MAX_QUEUE_ITEMS=100
SANDBOX_V2_PERF_MAX_ARTIFACTS=50
SANDBOX_V2_PERF_MAX_CONCURRENCY=4
SANDBOX_V2_PERF_TIMEOUT_SECONDS=60
SANDBOX_V2_PERF_CLEANUP_AFTER_RUN=true
SANDBOX_V2_PERF_OUTPUT_DIR=.sandbox_v2_perf_reports
```

Default API behavior is `disabled/skipped`, so ordinary test runs and local development do not accidentally create benchmark load.

## Benchmark Targets

- `jobs`: synthetic job metadata creation and lookup.
- `queue`: synthetic queue enqueue, lease, complete path.
- `worker`: bounded worker run-once path over synthetic jobs.
- `artifacts`: small safe artifact metadata or artifact-store write when available.
- `packages`: offline package metadata and quarantine records only, no download.
- `network`: policy preflight only, no socket or external request.
- `kill_switch`: sandbox-managed job cancel or kill request only, no process/container kill.
- `security_audit`: bounded audit records.
- `metrics`: metrics snapshot collection.
- `alerts`: bounded synthetic alert evaluation, no external notification.
- `end_to_end`: tiny synthetic path across internal control-plane components.

## Profiles

| Profile | Purpose | Default Limits |
|---|---|---|
| `smoke` | tiny self-check | jobs=3, queue=3, artifacts=2, concurrency=1 |
| `small` | local baseline | jobs<=25, queue<=25, artifacts<=10 |
| `medium` | controlled environment | requires explicit performance benchmark enablement |
| `large` | capacity planning rehearsal | rejected by default, requires explicit approval flags |
| `custom` | bounded experiment | constrained by environment limits |

## New API Endpoints

```text
GET  /api/runtime/sandbox-v2/performance/readiness
POST /api/runtime/sandbox-v2/performance/benchmarks
POST /api/runtime/sandbox-v2/performance/benchmarks/{benchmark_id}/run
GET  /api/runtime/sandbox-v2/performance/benchmarks
GET  /api/runtime/sandbox-v2/performance/results
GET  /api/runtime/sandbox-v2/performance/capacity/latest
GET  /api/runtime/sandbox-v2/performance/report/{benchmark_id}
```

The existing readiness response now also reports performance benchmark readiness, safe profile state, synthetic-fixture-only state, cleanup state, and explicit false flags for external load testing and user-code benchmarking.

## Runtime Admin

Runtime Admin Dashboard now includes a `Performance` section.

It shows:

- Performance readiness badges.
- Latest benchmark configs.
- Latest benchmark results.
- Latest capacity estimate.
- Create/run smoke actions guarded by readiness and confirmation.

The UI text explicitly marks the workflow as synthetic fixture only, with no user code, no external network, no container, and no MicroVM.

## Capacity Estimate

One verification forced smoke run produced:

```text
benchmark_id: sbxbench_ab20246916e0414c
profile: smoke
targets: jobs, queue, metrics, alerts
total_operations: 12
max p50/p95/p99 ms: 9.39 / 11.681 / 11.681
combined ops/s: 6532.019
estimated jobs/min: 180000
estimated queue items/min: 180000
estimated artifact metadata/min: 0
estimated network preflight/min: 0
```

This estimate is a local synthetic control-plane reference only. It is not a production SLO, distributed load result, or real backend capacity claim.

Generated artifacts:

```text
.sandbox_v2_perf_reports/sbxbench_ab20246916e0414c.json
.sandbox_v2_perf_reports/sbxbench_ab20246916e0414c.md
```

## Verification

Passed:

```bash
python -m py_compile src\open_platform\sandbox_v2\config.py src\open_platform\sandbox_v2\models.py src\open_platform\sandbox_v2\performance.py src\open_platform\sandbox_v2\service.py src\api\sandbox_v2.py src\adapters\sqlite_sandbox_v2_store.py scripts\run_sandbox_v2_performance_smoke.py
python -m pytest tests/test_open_platform/test_sandbox_v2_performance.py tests/test_open_platform/test_sandbox_v2_performance_api.py tests/test_open_platform/test_sandbox_v2_capacity_estimation.py tests/test_open_platform/test_sandbox_v2_performance_script.py -q
python -m pytest tests/test_open_platform/red_team/test_sandbox_v2_red_team_performance_abuse.py -q
python -m pytest tests/test_open_platform/red_team -q
python -m pytest tests/test_open_platform -q -k sandbox_v2
npm run build
```

Observed results:

- Step 16 focused tests: `29 passed`.
- Step 16 red-team abuse tests: `12 passed`.
- Re-run of combined Step 16 tests: `41 passed`.
- Full red-team directory: `171 passed`.
- Broad Sandbox v2 regression selection: `976 passed, 41 skipped, 3566 deselected`.
- Frontend build: compiled successfully and generated routes. Remaining lint warnings are pre-existing warnings in unrelated frontend files.

Smoke script behavior:

```bash
python scripts\run_sandbox_v2_performance_smoke.py --json
```

Returned `status=skipped` because `SANDBOX_V2_PERF_TESTS_ENABLED=false`.

```bash
python scripts\run_sandbox_v2_performance_smoke.py --force-smoke --json
```

Returned `status=completed` for the tiny synthetic smoke profile and generated JSON/Markdown reports.

## Environment Preflight Notes

Production readiness script:

- Overall: ready with 1 warning.
- Warning: Docker/Podman not found in PATH.

MicroVM preflight:

- Not ready on this Windows host.
- Blockers include non-Linux platform, no `/dev/kvm`, missing Firecracker binary, missing kernel/rootfs, and MicroVM env flags disabled.

Backend integration preflight:

- Skipped because `SANDBOX_V2_RUN_BACKEND_INTEGRATION` is not true.

Monitoring check:

- Metrics collected: 18.
- Health checks: 10/12 passed.
- Alerts open: 0, critical: 0.
- Blocker: not all health checks are passing in the current local setup.

## Current Gaps

- No real PostgreSQL/Redis/MinIO load test was run.
- No distributed worker load test was run.
- No long soak test was run.
- No real container or MicroVM performance test was run.
- No external load-testing service was used.
- No production SLO was defined.
- No OpenTelemetry tracing benchmark was added.

## Recommended Next Steps

1. Step 17: external IAM/SSO integration and auth-bound benchmark access control.
2. Step 18: Prometheus/Grafana/OpenTelemetry integration for production-grade observability.
3. Step 19: real staging/prod load test plan with PostgreSQL, Redis, MinIO, distributed workers, soak tests, and SLOs.
