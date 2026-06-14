# Sandbox v2 Performance & Capacity

## Step 16 目标

Step 16 为 Sandbox v2 建立一个安全、可审计、可关闭的性能基准和容量估算流程。它覆盖 Sandbox v2 控制面路径，包括 job metadata、queue lease、worker run-once、artifact metadata、package metadata、network policy preflight、kill request、security audit、metrics collection 和 alert evaluation。

本步骤不是生产压测结论，不代表已经完成分布式压测、长期 soak test 或真实 PostgreSQL/Redis/MinIO 压测。

## 安全边界

Step 16 只使用 synthetic fixture。

它不会：

- 执行用户代码。
- 访问外网或打开外部 socket。
- 下载包。
- 启动容器。
- 启动 MicroVM。
- 调用第三方压测服务。
- 自动启动 PostgreSQL、Redis 或 MinIO。

所有 benchmark metadata 都带有 `synthetic_fixture_only=true` 和 `test_run_id`。

## Benchmark Profiles

| Profile | 用途 | 默认限制 |
|---|---|---|
| `smoke` | 极小自检 | jobs=3, queue=3, artifacts=2, concurrency=1 |
| `small` | 本地安全基准 | jobs<=25, queue<=25, artifacts<=10 |
| `medium` | 受控环境基准 | 需要显式开关 |
| `large` | 容量专项演练 | 默认拒绝，必须显式开关 |
| `custom` | 专项实验 | 受 env 上限约束 |

## 默认 Disabled

性能测试默认关闭，避免普通 pytest、本地开发或 CI 误触发批量写入：

```bash
SANDBOX_V2_PERF_TESTS_ENABLED=false
SANDBOX_V2_RUN_PERFORMANCE_BENCHMARKS=false
```

API 在未启用时会返回 `disabled/skipped`，不会运行 benchmark。

## 如何运行 Smoke

默认未启用时只输出 skipped：

```bash
python scripts/run_sandbox_v2_performance_smoke.py
```

极小自检：

```bash
python scripts/run_sandbox_v2_performance_smoke.py --force-smoke
```

JSON only：

```bash
python scripts/run_sandbox_v2_performance_smoke.py --force-smoke --json
```

报告会写入：

```text
.sandbox_v2_perf_reports/<benchmark_id>.json
.sandbox_v2_perf_reports/<benchmark_id>.md
```

## API

```text
GET  /api/runtime/sandbox-v2/performance/readiness
POST /api/runtime/sandbox-v2/performance/benchmarks
POST /api/runtime/sandbox-v2/performance/benchmarks/{benchmark_id}/run
GET  /api/runtime/sandbox-v2/performance/benchmarks
GET  /api/runtime/sandbox-v2/performance/results
GET  /api/runtime/sandbox-v2/performance/capacity/latest
GET  /api/runtime/sandbox-v2/performance/report/{benchmark_id}
```

`large` profile、超过上限的 `max_jobs`、超过上限的 `max_concurrency`、外部 URL、用户 command、artifact path、container/MicroVM 输入都会 fail closed。

## Runtime Admin

Runtime Admin Dashboard 新增 `Performance` 分区，展示：

- Performance readiness。
- Benchmark configs。
- Benchmark results。
- Latest capacity estimate。

默认动作按钮 disabled。只有 readiness 允许时，才能创建或运行 smoke benchmark。界面文案明确说明 synthetic fixture only，不执行用户代码、不访问外网、不启动容器或 MicroVM。

## 指标解释

- `p50`: 50% 操作延迟低于该值。
- `p95`: 95% 操作延迟低于该值。
- `p99`: 99% 操作延迟低于该值。
- `ops/s`: 当前 synthetic run 的每秒操作数。
- `capacity estimate`: 根据 synthetic benchmark 推算的控制面容量参考，不是生产 SLO。

## SQLite / Local 适用边界

SQLite/local 适合 smoke/small、本地开发和单节点控制面验证。

它不适合：

- 多 worker 并发队列压测。
- 分布式队列 lease 验证。
- 长期高频写入。
- 生产级容量声明。

## PostgreSQL / Redis / MinIO 建议阈值

- PostgreSQL: 持续 job/result metadata 写入前迁移。
- Redis: 多 worker queue lease 或分布式 worker 前迁移。
- MinIO/S3: artifact metadata 或 artifact 文件规模增长前迁移。

这些迁移建议只用于规划，Step 16 不自动启动或压测这些后端。

## 当前限制

- 未做真实分布式压测。
- 未做长期压测。
- 未做真实 PostgreSQL/Redis/MinIO 压测。
- 未做真实容器/MicroVM 压测。
- 未定义生产 SLO。
- 未接入 OpenTelemetry tracing benchmark。

## 下一步建议

- Step 17: 外部 IAM / SSO 集成。
- Step 18: Prometheus / Grafana / OpenTelemetry 集成。
- Step 19: 真实生产压测与 SLO。

