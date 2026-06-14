# Fix Report

## Fixed

- Added production backend configuration switches and metadata-only health aggregation for database, cache, object storage, and queue backends.
- Kept SQLite/ChromaDB/local defaults intact for local demo mode.
- Fixed import route drift by standardizing the frontend on `/imports` and keeping `/import` as a FastAPI compatibility alias.
- Added Next.js rewrites for same-origin `/api/rbac`, `/api/runtime`, `/api/sandbox-policies`, `/api/admin`, developer, marketplace, and import paths.
- Added read-only Runtime Governance summary API for Runtime Admin.
- Reworked Runtime Admin UI to show Kill Switch, Incident Store, Package Download Worker Gate, Artifact Materialization Gate, Simulation Execution Record, Red-Team Result, and Production Sandbox Gate.
- Added explicit Runtime/Sandbox boundary documentation and production readiness documentation.
- Added API smoke script and route inventory.

## Not Fully Fixed

- PostgreSQL, Redis, S3/MinIO, and real task queues are adapter/readiness skeletons only.
- Production third-party code execution sandbox is not implemented.
- Rootless Container, MicroVM, and runtime isolation enforcement remain future work.

## Files Touched

- `src/adapters/config.py`
- `src/adapters/production_backends.py`
- `src/api/admin_router.py`
- `src/api/import_router.py`
- `src/api/runtime_admin_router.py`
- `src/open_platform/runtime_governance_summary.py`
- `main.py`
- `frontend/next.config.js`
- `frontend/services/api.ts`
- `frontend/services/runtime-admin.ts`
- `frontend/types/runtime-admin.ts`
- `frontend/app/admin/runtime/page.tsx`
- `scripts/check_api_routes.py`
- `docs/production-readiness.md`
- `docs/runtime-governance-boundary.md`
- `docker-compose.production.example.yml`
- `API_ROUTE_INVENTORY.md`

## How To Start

Backend:

```bash
python main.py
```

Frontend:

```bash
cd frontend
npm run dev
```

## How To Test

```bash
pytest tests/test_open_platform/test_production_backend_readiness.py tests/test_open_platform/test_runtime_governance_summary_api.py tests/test_api/test_import_route_alias.py
python scripts/check_api_routes.py --base-url http://127.0.0.1:8000
cd frontend
npm run typecheck
npm run lint
npm run build
```

## Runtime/Sandbox Boundary

当前 Runtime/Sandbox 主要完成的是安全治理控制面、模拟运行、元数据校验、默认关闭和审计追踪能力，不等于已经完成生产级第三方代码执行沙箱。生产级执行环境需要后续接入 PostgreSQL/Redis/对象存储、真实任务队列、Rootless Container/MicroVM、只读工件物化和安全隔离验证。

## Follow-Up Production Work

- Add Alembic migrations and staging PostgreSQL migration tests.
- Add Redis client integration and cache invalidation tests.
- Add S3/MinIO signed object access and lifecycle policies.
- Add Celery/RQ queue workers with dead-letter and idempotency controls.
- Implement Rootless Container/MicroVM as separate disabled-by-default spikes.

## Verification

Passed:

- `python -m compileall src\adapters\production_backends.py src\open_platform\runtime_governance_summary.py src\api\runtime_admin_router.py src\api\import_router.py src\api\admin_router.py`
- `python -m pytest tests\test_open_platform\test_runtime_store.py tests\test_open_platform\test_production_sandbox_gate.py tests\test_open_platform\test_package_download_worker.py tests\test_open_platform\test_artifact_materialization.py tests\test_open_platform\test_sandbox_execution_store.py` -> 439 passed.
- `python -m pytest tests\test_open_platform\test_runtime_governance_summary_api.py tests\test_open_platform\test_production_backend_readiness.py tests\test_api\test_import_route_alias.py tests\test_open_platform\test_step23_security_runtime.py::TestFrontendSecurityUX::test_runtime_admin_no_misleading_execution` -> 6 passed.
- `python scripts\check_api_routes.py --base-url http://127.0.0.1:8000` -> all checked FastAPI routes connected. `/developers/me` returned a resource-level `404 Developer account not found`, not route drift.
- Next.js same-origin proxy smoke check on `http://127.0.0.1:3000` -> `/api/rbac/users`, `/api/admin/config`, `/api/admin/production-backends`, `/api/imports`, `/api/import`, `/api/runtime/adapters`, `/api/runtime/governance/summary`, and `/api/sandbox-policies` returned 200.
- `cd frontend && npm run typecheck` -> passed.

Known verification limits:

- Full `python -m pytest` run reached 5361 passed / 3 failed before the final frontend phrase fix. The Runtime Admin frontend failure was fixed and rerun successfully. The remaining reproducible isolated failure is `tests/test_api/test_audit.py::TestUserActivityTimeline::test_user_activity_timeline`, which crosses a UTC day boundary during the test and produces 6 buckets instead of the expected 5 on this machine/time. `tests/test_open_platform/test_package_artifact_store.py::TestDeclarationService::test_service_does_not_network` passed in isolation after the full-suite order-dependent failure.
- `cd frontend && npm run lint` and `npm run build` are still blocked by pre-existing lint errors in unrelated files such as `frontend/app/graph/page.tsx`, `frontend/app/sync/page.tsx`, `frontend/app/timeline/page.tsx`, and upload button components. The new Runtime Admin page passes typecheck and its targeted security UX test.
- In-app Browser screenshot verification could not be completed because the Browser enterprise network policy blocked access to `http://127.0.0.1:3000` and disallowed using alternate browser surfaces as a workaround.

## Account And Memory Hotfix

Fixed after runtime verification on 2026-06-13:

- Added workspace entitlement bootstrap so the local/default workspace always has an active Enterprise subscription for the configured 10-year period.
- Repaired the current SQLite data in `data/agent_memory.db`:
  - `default` tenant now has `plan_tier=enterprise`, `status=active`, `coupon_code=TEN_YEAR_ENTERPRISE`, `current_period_end=2036-06-13T09:18:56.297538+00:00`.
  - Existing workspace tenant `c1815c95-7232-462e-8a91-38d0e0d11b65` is also mapped to the same Enterprise entitlement policy.
- Restored 5 lost memory notes from local evidence:
  - Chroma still contained the 5 vector ids, timestamps, entities, and importance scores.
  - Chroma did not contain original document bodies.
  - The visible note text was recovered from `screenshots/video/03_03_memory.png`.
  - A SQLite backup was created at `data/agent_memory.before-memory-restore.20260613-173427.db` before restoring.
- Added `scripts/recover_notes_from_chroma_metadata.py` as a repeatable recovery script.
- Updated `frontend/app/account/page.tsx` so lowercase API tiers such as `enterprise` map to the Enterprise badge.

Latest verification:

- `python -m py_compile scripts\recover_notes_from_chroma_metadata.py` -> passed.
- `python scripts\recover_notes_from_chroma_metadata.py` -> restored 5 notes, no missing Chroma metadata.
- `GET http://127.0.0.1:8000/subscription` -> `enterprise`, `active`, end date `2036-06-13`, coupon `TEN_YEAR_ENTERPRISE`.
- `GET http://127.0.0.1:8000/memory?limit=10` -> 5 notes, all `embedding_status=vectorized`.
- `GET http://127.0.0.1:3000/account` -> 200.
- `python -m pytest tests\test_api\test_account_entitlements.py tests\test_api\test_import_route_alias.py tests\test_open_platform\test_runtime_governance_summary_api.py tests\test_open_platform\test_production_backend_readiness.py tests\test_open_platform\test_step23_security_runtime.py::TestFrontendSecurityUX::test_runtime_admin_no_misleading_execution` -> 7 passed.
- `python scripts\check_api_routes.py` -> all checked backend routes connected.
- `cd frontend && npm run typecheck` -> passed.
