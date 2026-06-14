# Sandbox v2 Step 19 Report — Load Testing & SLO 基线

**日期:** 2026-06-14
**状态:** Complete

## 新增文件

| # | 文件 | 说明 |
|---|------|------|
| 1 | `src/open_platform/sandbox_v2/load_testing.py` | SandboxV2LoadTester - local dry-run + staging load test |
| 2 | `src/open_platform/sandbox_v2/slo.py` | SandboxV2SLOService - SLO 定义与评估 |
| 3 | `tests/test_open_platform/test_sandbox_v2_load_testing.py` | Load testing 测试 (18) |
| 4 | `tests/test_open_platform/test_sandbox_v2_slo.py` | SLO 测试 (8) |
| 5 | `tests/test_open_platform/test_sandbox_v2_load_testing_api.py` | API 测试 (11) |
| 6 | `tests/test_open_platform/red_team/test_sandbox_v2_red_team_load_testing.py` | Red-Team 测试 (14) |
| 7 | `tests/test_open_platform/integration_load/test_sandbox_v2_staging_load_test.py` | 集成测试 (6, skip) |
| 8 | `scripts/run_sandbox_v2_load_test_smoke.py` | Load test smoke 脚本 |
| 9 | `docs/sandbox-v2-load-testing-slo.md` | Load testing & SLO 文档 |

## 修改文件 (10 个)

`config.py`, `models.py`, `store.py`, `sqlite_sandbox_v2_store.py`, `service.py`, `sandbox_v2.py`, `.env.sandbox-v2.example`, `sandbox_v2_postgres_schema.sql`, `runtime-admin.ts` (types), `runtime-admin.ts` (services)

## 新增 API

| 方法 | 路径 |
|------|------|
| GET | `/api/runtime/sandbox-v2/load-testing/readiness` |
| POST | `/api/runtime/sandbox-v2/load-testing/configs` |
| GET | `/api/runtime/sandbox-v2/load-testing/configs` |
| POST | `/api/runtime/sandbox-v2/load-testing/configs/{id}/run` |
| GET | `/api/runtime/sandbox-v2/load-testing/results` |
| GET | `/api/runtime/sandbox-v2/load-testing/slo/definitions` |
| GET | `/api/runtime/sandbox-v2/load-testing/slo/evaluations` |
| POST | `/api/runtime/sandbox-v2/load-testing/slo/evaluate/{id}` |
| GET | `/api/runtime/sandbox-v2/load-testing/capacity/latest` |
| GET | `/api/runtime/sandbox-v2/load-testing/report/{id}` |

## Load Testing Readiness

```
load_testing_framework: true | load_testing_enabled: false
staging_load_testing_enabled: false | local_dry_run_enabled: true
load_testing_safe_mode: true
```

## Local Dry-Run 结果

**3/3 targets completed** (readiness, metrics, network_preflight)
- 15 total requests, 0 failures, error_rate=0%
- Report saved to `.sandbox_v2_load_reports/`

## Staging Load Test

**Skipped** (SANDBOX_V2_RUN_STAGING_LOAD_TEST not set)

## SLO Evaluation 结果

- 7 default SLO definitions
- SLO evaluation engine ready
- SLO evaluation passed on dry-run results

## Capacity Plan 摘要

- Profile: small
- Backend: sqlite (single-worker OK)
- Queue: sqlite → recommended Redis at 4+ workers
- Object storage: local → recommended MinIO at medium+

## Runtime Admin 新增分区

**Load Testing & SLO** — Readiness, configs, dry-run control, results table, SLO definitions/evaluations, capacity plan

## Red-Team Load Test Abuse 结果

**14 passed** — 覆盖: external URL blocking, production URL blocking, concurrency limits, secret masking, fail-closed, no network in dry-run

## 集成测试

**6 skipped** — 需要 `SANDBOX_V2_RUN_STAGING_LOAD_TEST=true` + `SANDBOX_V2_LOAD_TESTING_ENABLED=true`

## 测试结果

| 类别 | 结果 |
|------|------|
| Step 19 核心测试 (load_testing + slo + API) | **37 passed** |
| Red-Team Load Testing | **14 passed** |
| 集成测试 | **6 skipped** |

## 当前仍缺什么

| 项目 | 计划 |
|------|------|
| 真实 staging 环境压测 | Step 22 |
| 分布式压测 | Future |
| 长期 soak test | Step 22 |
| 生产 SLO 门禁 | Step 22 |
| 压测平台集成 | Future |

## 下一步建议

1. **Step 20:** 真实 OIDC/SAML 登录闭环
2. **Step 21:** 真实 Prometheus/Grafana/OTel Collector 集成
3. **Step 22:** 长期 Soak Test 与生产 SLO 门禁
