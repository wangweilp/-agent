# SANDBOX V2 STEP 15 REPORT — 生产监控、指标、告警与审计信号聚合

**实施日期**: 2026-06-13
**项目**: 黔智脑 Cognitive OS (`D:\dma\day2`)
**步骤**: Sandbox v2 Step 15 — 生产监控、指标、告警与审计信号聚合

---

## 一、本次新增文件

| # | 文件 | 用途 |
|---|------|------|
| 1 | `src/open_platform/sandbox_v2/metrics.py` | Metrics Collector（聚合 job/queue/network/security 指标，Prometheus JSON 导出） |
| 2 | `src/open_platform/sandbox_v2/health.py` | Health Check Service（12 组件健康检查） |
| 3 | `src/open_platform/sandbox_v2/alerts.py` | Alert Engine（9 条默认告警规则，内部 alert record 管理） |
| 4 | `scripts/check_sandbox_v2_monitoring.py` | 监控检查脚本（metrics + health + alerts） |
| 5 | `docs/sandbox-v2-monitoring-alerting.md` | 监控与告警文档 |
| 6 | `tests/test_open_platform/test_sandbox_v2_metrics.py` | Metrics 测试（9 项） |
| 7 | `tests/test_open_platform/test_sandbox_v2_health.py` | Health 测试（7 项） |
| 8 | `tests/test_open_platform/test_sandbox_v2_alerts.py` | Alerts 测试（12 项） |
| 9 | `tests/test_open_platform/test_sandbox_v2_monitoring_api.py` | Monitoring API 测试（8 项） |
| 10 | `tests/test_open_platform/test_sandbox_v2_prometheus_export.py` | Prometheus Export 测试（8 项） |
| 11 | `tests/test_open_platform/red_team/test_sandbox_v2_red_team_monitoring_alerts.py` | 红队监控告警测试（12 项） |

**共新增 11 个文件。**

---

## 二、本次修改文件

| # | 文件 | 变更 |
|---|------|------|
| 1 | `src/open_platform/sandbox_v2/models.py` | +5 个枚举 (MetricName/MetricType/AlertSeverity/AlertStatus/AlertRuleType) + 6 个模型 (MetricSample/Snapshot/AlertRule/Alert/HealthCheckResult) |
| 2 | `src/open_platform/sandbox_v2/store.py` | +14 个 monitoring store 方法签名 |
| 3 | `src/adapters/sqlite_sandbox_v2_store.py` | +5 张表 (metric_samples/snapshots/alert_rules/alerts/health_results) + 14 个 CRUD 方法 |
| 4 | `src/api/sandbox_v2.py` | +10 Step 15 readiness 字段 + 10 个 monitoring API 端点 |
| 5 | `frontend/types/runtime-admin.ts` | +10 Step 15 TypeScript 字段 |

**共修改 5 个文件。**

---

## 三、新增 API 列表

| 方法 | 路径 | 功能 |
|------|------|------|
| `GET` | `/monitoring/metrics/snapshot` | 最新 metrics snapshot |
| `POST` | `/monitoring/metrics/collect` | 手动采集 metrics |
| `GET` | `/monitoring/metrics/prometheus` | Prometheus text 导出 |
| `GET` | `/monitoring/health` | 运行全部 health checks |
| `GET` | `/monitoring/alerts/rules` | 列出告警规则 |
| `POST` | `/monitoring/alerts/evaluate` | 评估告警规则 |
| `GET` | `/monitoring/alerts` | 列出 alerts |
| `POST` | `/monitoring/alerts/{id}/ack` | 确认告警 |
| `POST` | `/monitoring/alerts/{id}/resolve` | 解决告警 |
| `GET` | `/monitoring/readiness` | 监控 readiness |

---

## 四、新增指标列表

| 指标 | 类型 |
|------|------|
| jobs_created_total, jobs_completed_total, jobs_failed_total, jobs_canceled_total | counter |
| queue_depth, queue_dead_letter_total | gauge/counter |
| worker_heartbeat_age_seconds | gauge |
| network_denied_total, metadata_service_blocked_total | counter |
| cross_tenant_denied_total, access_denied_total | counter |
| kill_requests_total, kill_rejected_total | counter |
| audit_chain_verify_failures_total | counter |
| backend_blockers_total | gauge |
| microvm_unavailable_total, container_unavailable_total | gauge |

---

## 五、默认告警规则

| # | 规则 | 条件 | 级别 |
|---|------|------|------|
| 1 | queue-dead-letter | dead_letter > 0 | **high** |
| 2 | queue-depth-high | queue_depth > 100 | warning |
| 3 | worker-no-heartbeat | heartbeat_age > 300s | **critical** |
| 4 | network-denied-spike | denied > 10 | warning |
| 5 | cross-tenant-denied | count > 0 | **high** |
| 6 | audit-chain-failure | failures > 0 | **critical** |
| 7 | artifact-rejected-spike | rejected > 20 | warning |
| 8 | backend-blocker-exists | blockers > 0 | **high** |
| 9 | red-team-failed | failed > 0 | **critical** |

---

## 六、Health Check 覆盖

| 组件 | 说明 |
|------|------|
| core | Store 访问性 |
| queue | Dead letter 检测 |
| worker | Heartbeat |
| artifact_store | Artifact root |
| package_quarantine | Quarantine root |
| network_policy | Preflight 状态 |
| isolation_provider | Trusted fixture |
| container_provider | Docker/Podman |
| microvm_provider | KVM/Firecracker |
| backend | Backend readiness |
| audit_chain | Hash chain 验证 |
| red_team | Test suite 存在性 |

---

## 七、Prometheus Export 示例

```
# HELP sandbox_v2_queue_depth Sandbox v2 queue_depth
# TYPE sandbox_v2_queue_depth gauge
sandbox_v2_queue_depth 0.0
# HELP sandbox_v2_jobs_created_total Sandbox v2 jobs_created_total
# TYPE sandbox_v2_jobs_created_total counter
sandbox_v2_jobs_created_total 0.0
```

---

## 八、测试结果

| 测试 | 结果 |
|------|------|
| Step 15 新增测试 | **45 passed** (0.93s) |
| 红队监控测试 | **12 passed** (0.63s) |
| 全部 Sandbox v2 | **772 passed** (29.42s) |
| 全部 Red-Team | **159 passed** (3.85s) |
| Monitoring 脚本 | **14 metrics, 11/12 health passed** |
| 前端 `npm run build` | **✓ Compiled successfully** |

---

## 九、当前仍缺

| 能力 | 状态 |
|------|------|
| Prometheus server | ❌ 未接入 |
| Grafana dashboard | ❌ 未接入 |
| Slack/email/webhook 通知 | ❌ external_notifications=false |
| 长期指标保留 | ❌ |
| Tracing (OpenTelemetry) | ❌ |
| 生产级 APM | ❌ |

---

## 十、下一步建议

- **Step 16**：性能压测与容量规划
- **Step 17**：外部 IAM / SSO 集成
- **Step 18**：Grafana / Prometheus / OpenTelemetry 集成
