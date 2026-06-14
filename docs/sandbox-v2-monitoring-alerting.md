# Sandbox v2 — Monitoring & Alerting

**版本**: Step 15

---

## 一、Step 15 目标

建立 Sandbox v2 内部监控、指标采集、健康检查、告警评估和 Prometheus 导出基础。

---

## 二、Metrics 列表

| 指标 | 类型 | 说明 |
|------|------|------|
| jobs_created_total | counter | 创建的 job 数 |
| jobs_failed_total | counter | 失败的 job 数 |
| queue_depth | gauge | 队列深度 |
| queue_dead_letter_total | counter | dead letter 数 |
| worker_heartbeat_age_seconds | gauge | Worker 心跳年龄 |
| network_denied_total | counter | 网络被拒数 |
| cross_tenant_denied_total | counter | 跨租户被拒数 |
| audit_chain_verify_failures_total | counter | 审计链验证失败 |
| kill_requests_total | counter | Kill 请求数 |
| backend_blockers_total | gauge | 后端阻塞项 |
| microvm_unavailable_total | gauge | MicroVM 不可用 |
| benchmark_results_total | counter | Benchmark result 数 |
| benchmark_failures_total | counter | Benchmark failure 数 |
| capacity_jobs_per_minute | gauge | 最新 synthetic capacity jobs/min |

---

## 三、Health Check 覆盖

| 组件 | 检查内容 |
|------|----------|
| core | Store 访问性 |
| queue | Dead letter 检测 |
| network_policy | Preflight-only 状态 |
| container_provider | 运行时可用性 |
| microvm_provider | KVM/Firecracker 可用性 |
| backend | Backend readiness |
| audit_chain | Hash chain 完整性 |
| red_team | Red-team 测试文件存在性 |

---

## 四、告警规则

| 规则 | 条件 | 级别 |
|------|------|------|
| queue-dead-letter | dead_letter > 0 | high |
| queue-depth-high | queue_depth > 100 | warning |
| worker-no-heartbeat | heartbeat_age > 300s | critical |
| network-denied-spike | denied > 10 | warning |
| cross-tenant-denied | count > 0 | high |
| audit-chain-failure | failures > 0 | critical |
| artifact-rejected-spike | rejected > 20 | warning |
| backend-blocker-exists | blockers > 0 | high |
| red-team-failed | failed > 0 | critical |

---

## 五、Prometheus Text Export

```bash
curl http://localhost:8000/api/runtime/sandbox-v2/monitoring/metrics/prometheus
```

---

## 六、脚本

```bash
python scripts/check_sandbox_v2_monitoring.py
python scripts/check_sandbox_v2_monitoring.py --json
```

---

## 七、当前限制

- 未接入 Prometheus server
- 未接入 Grafana
- 未发送外部通知 (email/Slack/webhook)
- 未做长期指标保留
- 未做 tracing

---

## 八、Performance / Capacity (Step 16)

Step 16 的 benchmark result 和 capacity estimate 可被 metrics collector 读取：

```bash
curl http://localhost:8000/api/runtime/sandbox-v2/performance/readiness
curl http://localhost:8000/api/runtime/sandbox-v2/performance/results
curl http://localhost:8000/api/runtime/sandbox-v2/performance/capacity/latest
curl http://localhost:8000/api/runtime/sandbox-v2/monitoring/metrics/prometheus
```

注意：

- `benchmark_failures_total` 表示 synthetic benchmark failure，不等同于生产事故。
- `capacity_jobs_per_minute` 是 synthetic capacity estimate，不是生产 SLO。
- Alert engine 不发送外部通知，仍保持 `external_notifications=false`。
- 大规模 benchmark 默认关闭，避免普通测试或本地开发误触发压测。
