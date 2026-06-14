# Sandbox v2 Observability Integrations (Step 18)

## 1. Step 18 目标

为 Sandbox v2 增加 Prometheus / Grafana / OpenTelemetry 集成基础：
- Prometheus scrape config & alert rules 生成
- Grafana dashboard JSON spec 生成
- OpenTelemetry adapter skeleton (Disabled / Mock / OTLP)
- Trace span 内部管理
- Telemetry export 记录
- Runtime Admin 展示

**不部署真实服务，不访问外网，不发送外部 telemetry。**

## 2. Prometheus 集成

- `SandboxV2PrometheusConfigBuilder` 生成 scrape config + alert rules
- 导出为 YAML 示例文本
- scrape target 默认 `localhost:8000`
- 不包含 secret/access key
- Alert rules 对应 Step 15 默认 9 条告警规则

## 3. Grafana Dashboard

- `SandboxV2GrafanaDashboardBuilder` 生成 JSON spec
- 4 个 dashboard：Overview / Security / Runtime / Performance
- datasource 占位符 `${DS_PROMETHEUS}`
- 覆盖：jobs created/completed/failed, queue depth, dead letter, worker heartbeat,
  network denied, metadata blocked, cross-tenant denied, kill requests,
  audit chain failures, red-team results, package quarantine, backend blockers
- **不连接 Grafana API, 不包含密钥, 不包含本地绝对路径**

## 4. OpenTelemetry Adapter

- `DisabledOTelExporter` — 默认 disabled
- `MockOTelExporter` — 测试用，记录 export count
- `OTLPHttpExporterSkeleton` — 只做配置校验，不发送 HTTP
- Telemetry attributes 一律 redacted (secret/token/password/DSN/key)

## 5. 为什么默认不发送 telemetry

- `otel_enabled=false`: 未配置 OTel Collector
- `otel_traces_enabled=false`: 未实现全链路插桩
- `otel_metrics_enabled=false`: 避免外部数据泄露
- `otel_logs_enabled=false`: 日志中可能包含敏感信息
- `include_sensitive_attributes=false`: 安全红线

## 6. Telemetry Redaction 原则

- secret, token, key, password, DSN, credential → `[REDACTED]`
- 超过 500 字符的值 → 截断
- 不记录 user input 全文 / prompt / artifact content
- attributes_redacted 独立字段

## 7. 运行脚本

```bash
python scripts/check_sandbox_v2_observability.py
```

## 8. 查看 Prometheus config

```bash
curl http://localhost:8000/api/runtime/sandbox-v2/observability/prometheus/scrape-config
```

## 9. 导入 Grafana JSON

1. 获取 dashboard JSON
2. 在 Grafana UI: Dashboards → Import → Paste JSON
3. 选择 Prometheus datasource

## 10. 如何未来接入 OTel Collector

1. 部署 OTel Collector (本地或远程)
2. 设置 `SANDBOX_V2_OTEL_ENABLED=true`
3. 设置 `SANDBOX_V2_OTEL_EXPORTER=otlp_http`
4. 设置 `SANDBOX_V2_OTEL_ENDPOINT=http://localhost:4318`
5. Step 20+ 实现真实 OTLP HTTP export

## 11. 当前限制

- 未真实连接 Prometheus server
- 未真实连接 Grafana API
- 未真实发送 OTLP
- 未做 tracing 全链路插桩
- 未做长期存储

## 12. 下一步建议

- Step 19: 真实 staging/prod load test 与 SLO
- Step 20: 真实 OIDC/SAML 登录闭环
- Step 21: OpenTelemetry Collector 真实集成
