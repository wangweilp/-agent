# Sandbox v2 Step 18 Report — Prometheus / Grafana / OpenTelemetry 集成基础

**日期:** 2026-06-14
**状态:** Complete

## 新增文件

| # | 文件 | 说明 |
|---|------|------|
| 1 | `src/open_platform/sandbox_v2/observability.py` | Observability Service — 统一集成服务 |
| 2 | `src/open_platform/sandbox_v2/otel_adapter.py` | OTel Adapter — Disabled/Mock/OTLP exporters |
| 3 | `src/open_platform/sandbox_v2/grafana.py` | Grafana Dashboard Builder — 4 dashboards |
| 4 | `src/open_platform/sandbox_v2/prometheus.py` | Prometheus Config Builder — scrape + alert rules |
| 5 | `tests/test_open_platform/test_sandbox_v2_observability.py` | Observability service tests (19) |
| 6 | `tests/test_open_platform/test_sandbox_v2_otel_adapter.py` | OTel adapter tests (15) |
| 7 | `tests/test_open_platform/test_sandbox_v2_grafana.py` | Grafana dashboard tests (9) |
| 8 | `tests/test_open_platform/test_sandbox_v2_prometheus_config.py` | Prometheus config tests (8) |
| 9 | `tests/test_open_platform/test_sandbox_v2_observability_api.py` | Observability API tests (10) |
| 10 | `tests/test_open_platform/red_team/test_sandbox_v2_red_team_observability.py` | Red-Team tests (15) |
| 11 | `tests/test_open_platform/integration_observability/test_sandbox_v2_observability_integration.py` | Integration tests (6, skip) |
| 12 | `scripts/check_sandbox_v2_observability.py` | Observability check script |
| 13 | `docs/sandbox-v2-observability-integrations.md` | Observability 文档 |

## 修改文件

| 文件 | 修改内容 |
|------|----------|
| `src/open_platform/sandbox_v2/config.py` | +14 个 observability 配置项 |
| `src/open_platform/sandbox_v2/models.py` | +4 枚举 + 5 数据模型 |
| `src/open_platform/sandbox_v2/store.py` | +8 个 Store 接口方法 |
| `src/open_platform/sandbox_v2/service.py` | +9 个 observability 聚合方法 |
| `src/api/sandbox_v2.py` | +9 个 API 端点 + readiness 字段 |
| `.env.sandbox-v2.example` | +22 个环境变量模板 |
| `src/adapters/sqlite_sandbox_v2_store.py` | +3 张表 + 8 个方法 + 3 个 row converters |
| `docs/sql/sandbox_v2_postgres_schema.sql` | +3 张表 |
| `frontend/types/runtime-admin.ts` | +5 个 TypeScript 类型 |
| `frontend/services/runtime-admin.ts` | +9 个 API client 方法 |

## 新增 API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/runtime/sandbox-v2/observability/readiness` | Observability readiness |
| GET | `/api/runtime/sandbox-v2/observability/prometheus/scrape-config` | Scrape config |
| GET | `/api/runtime/sandbox-v2/observability/prometheus/alert-rules` | Alert rules |
| GET | `/api/runtime/sandbox-v2/observability/grafana/dashboard` | Dashboard JSON |
| POST | `/api/runtime/sandbox-v2/observability/grafana/dashboard/generate` | Generate dashboard |
| GET | `/api/runtime/sandbox-v2/observability/traces` | List trace spans |
| POST | `/api/runtime/sandbox-v2/observability/traces` | Create trace span |
| POST | `/api/runtime/sandbox-v2/observability/otel/simulate-export` | Simulate OTel export |
| GET | `/api/runtime/sandbox-v2/observability/export-records` | List export records |

## Observability Readiness

```json
{
  "observability_config": true,
  "prometheus_scrape_config": true,
  "prometheus_alert_rules": true,
  "grafana_dashboard_spec": true,
  "otel_adapter": true,
  "otel_real_export": false,
  "external_telemetry_export": false,
  "telemetry_redaction": true,
  "trace_span_store": true,
  "observability_safe_mode": true
}
```

## Prometheus Config 结果

- Scrape config: 1 job (sandbox-v2), target localhost:8000
- Alert rules: 9 rules — SandboxV2AuditChainFailure, SandboxV2DeadLetter, SandboxV2CrossTenantDenied, SandboxV2MetadataServiceBlocked, SandboxV2WorkerNoHeartbeat, SandboxV2BackendBlocker, SandboxV2RedTeamFailed, SandboxV2QueueDepthHigh, SandboxV2NetworkDeniedSpike
- No secrets, no absolute paths

## Grafana Dashboard 结果

- 4 dashboards: Overview (18 panels), Security (9 panels), Runtime (6 panels), Performance (6 panels)
- All datasources use `${DS_PROMETHEUS}` placeholder
- No keys, DSN, absolute paths

## OTel Adapter 结果

- DisabledOTelExporter: all exports return disabled
- MockOTelExporter: records counts locally, no HTTP
- OTLPHttpExporterSkeleton: config validation only, exports return skipped
- Attribute sanitization: secret/token/key/password/DSN/credential → `[REDACTED]`

## Runtime Admin 新增分区

Observability Integrations — 展示 readiness, Prometheus config preview, Grafana dashboard, OTel status, trace spans, export records

## Red-Team Observability 结果

**15 passed** — 覆盖: secret leakage prevention, no external network, content redaction, fail-closed, safe_mode

## 集成测试

**6 skipped** (需要 `SANDBOX_V2_RUN_OBSERVABILITY_INTEGRATION=true`)

## 测试结果

| 类别 | 结果 |
|------|------|
| Step 18 单元测试 (observability + adapter + grafana + prometheus + API) | **61 passed** |
| Red-Team Observability | **15 passed** |
| 集成测试 | **6 skipped** |
| 已有 IAM + Security tests | **33 passed** |

## 当前仍缺什么

| 项目 | 计划 |
|------|------|
| 真实 Prometheus server | Step 21 |
| 真实 Grafana API | Step 21 |
| 真实 OTel Collector / OTLP HTTP export | Step 21 |
| Tracing 全链路插桩 | Step 21 |
| 长期指标保留 | Future |

## 下一步建议

1. **Step 19:** 真实 staging/prod load test 与 SLO
2. **Step 20:** 真实 OIDC/SAML 登录闭环
3. **Step 21:** OpenTelemetry Collector 真实集成
