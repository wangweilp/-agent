# Sandbox v2 Load Testing & SLO Baselines (Step 19)

## 1. Step 19 目标

为 Sandbox v2 建立真实 staging/production load test 方案、SLO/SLA 基线:
- Local dry-run 框架（不访问外网）
- Staging load test（需显式配置）
- SLO 定义与评估
- Capacity planning
- Runtime Admin 展示

**不建议对生产环境运行，不建议未配置 staging base URL 时启用。**

## 2. Local Dry-Run vs Staging

| 模式 | 外网 | 需要设置 | 说明 |
|------|------|----------|------|
| local_dry_run | 否 | 无 | 只调用本地 service，安全可测试 |
| staging | 是 | STAGING_BASE_URL | 对 staging 服务器发送 HTTP |

## 3. 为什么默认 disabled

- `load_testing_enabled=false`: 不启用 load testing
- `run_staging_load_test=false`: 不对任何远程服务器发请求
- `allow_production=false`: 禁止生产 URL
- 默认 profile=smoke: 最大 5 用户、5 rps、30 秒

## 4. 配置

```bash
SANDBOX_V2_LOAD_TESTING_ENABLED=false
SANDBOX_V2_RUN_STAGING_LOAD_TEST=false
SANDBOX_V2_STAGING_BASE_URL=
SANDBOX_V2_STAGING_API_TOKEN=
SANDBOX_V2_LOAD_TEST_PROFILE=smoke
```

## 5. 运行命令

```bash
# 本地 dry-run
python scripts/run_sandbox_v2_load_test_smoke.py --dry-run --json

# Staging load test（需配置 env）
SANDBOX_V2_RUN_STAGING_LOAD_TEST=true \
SANDBOX_V2_LOAD_TESTING_ENABLED=true \
SANDBOX_V2_STAGING_BASE_URL=http://localhost:8000 \
python scripts/run_sandbox_v2_load_test_smoke.py --staging --json
```

## 6. SLO 定义

默认 7 个 SLO：
- readiness-p95 (500ms), metrics-p95 (800ms), health-p95 (1000ms)
- network-preflight-p95 (200ms), security-access-p95 (100ms)
- global-error-rate (< 1%)
- load-test-availability (> 99%)

## 7. Capacity Plan

根据 profile 自动推荐 backend/workers/object_storage/queue_backend。

## 8. 当前限制

- 未做分布式压测
- 未做真实生产压测
- 未做长期 soak test
- 未接真实压测平台

## 9. 下一步

- Step 20: 真实 OIDC/SAML 登录闭环
- Step 21: 真实 Prometheus/Grafana/OTel Collector 集成
- Step 22: 长期 Soak Test 与生产 SLO 门禁
