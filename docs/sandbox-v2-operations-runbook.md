# Sandbox v2 — Operations Runbook

**版本**: Step 10  
**最后更新**: 2026-06-13  
**目标受众**: 运维 / SRE / 值班工程师

---

## 一、Runtime Admin Dashboard

### 访问方式

1. 启动后端服务
2. 启动前端开发服务器 (`cd frontend && npm run dev`)
3. 登录后导航至 **Runtime Admin** 页面
4. 选择 **Sandbox V2** tab

### Dashboard 分区

| 分区 | 功能 |
|------|------|
| Overview | 能力总览、安全关闭状态、Production Readiness |
| Jobs & Queue | Jobs/Queue/Worker/Dead Letter 管理 |
| Artifacts | Artifact 列表、内容预览 |
| Packages | Package Requests、Quarantine Records |
| Network | Egress Requests、Audit、Preflight |
| Isolation & Container | Execution Plans、Container Plans |
| Kill Switch | Kill Requests/Records、Active Handles |
| Red-Team | 安全回归测试状态 |

---

## 二、如何查看 Jobs / Queue / Dead Letter

### 通过 Dashboard
- 导航到 **Jobs & Queue** 分区
- 查看 Jobs 表格 (状态、模式、风险等级)
- 查看 Queue 表格 (lease 状态、尝试次数)
- 查看 Dead Letter (已达 max_attempts 的任务)

### 通过 API

```bash
# 列出 jobs
curl http://localhost:8000/api/runtime/sandbox-v2/jobs

# 查看特定 job
curl http://localhost:8000/api/runtime/sandbox-v2/jobs/{job_id}

# 列出队列
curl http://localhost:8000/api/runtime/sandbox-v2/queue

# 列出 dead letter
curl http://localhost:8000/api/runtime/sandbox-v2/dead-letter

# 列出 workers
curl http://localhost:8000/api/runtime/sandbox-v2/workers
```

---

## 三、如何查看 Artifacts

### 通过 Dashboard
- 导航到 **Artifacts** 分区
- 查看 Artifact 列表 (类型、大小、SHA256、只读状态)
- 点击 **View** 查看内容 (截断显示，前 5000 字符)

### 通过 API

```bash
# 列出 artifacts
curl http://localhost:8000/api/runtime/sandbox-v2/artifacts

# 查看 artifact 详情
curl http://localhost:8000/api/runtime/sandbox-v2/artifacts/{artifact_id}

# 查看 artifact 内容
curl http://localhost:8000/api/runtime/sandbox-v2/artifacts/{artifact_id}/content
```

---

## 四、如何查看 Package Quarantine

### 通过 Dashboard
- 导航到 **Packages** 分区
- 查看 Package Requests (包名、版本、来源类型、状态)
- 查看 Quarantine Records (SHA256、签名状态、SBOM、漏洞扫描)

### 通过 API

```bash
# 列出 package requests
curl http://localhost:8000/api/runtime/sandbox-v2/packages/requests

# 列出 quarantine records
curl http://localhost:8000/api/runtime/sandbox-v2/packages/quarantine

# 查看 SBOM
curl http://localhost:8000/api/runtime/sandbox-v2/packages/sbom
```

---

## 五、如何查看 Network Audit

### 通过 Dashboard
- 导航到 **Network** 分区
- 查看 Egress Requests (URL、hostname、端口、策略状态)
- 查看 Audit Records (决定、原因、风险等级)
- 使用 Preflight Check 测试 URL 策略

### 通过 API

```bash
# 列出 egress requests
curl http://localhost:8000/api/runtime/sandbox-v2/network/egress-requests

# 列出 audit records
curl http://localhost:8000/api/runtime/sandbox-v2/network/audit-records

# Preflight 检查
curl -X POST http://localhost:8000/api/runtime/sandbox-v2/network/preflight \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com"}'

# Network readiness
curl http://localhost:8000/api/runtime/sandbox-v2/network/readiness
```

---

## 六、如何查看 Kill Records

### 通过 Dashboard
- 导航到 **Kill Switch** 分区
- 查看 Kill Requests (目标类型、目标 ID、状态)
- 查看 Kill Records (执行动作、前后状态、provider 结果)
- 查看 Active Execution Handles (活动执行句柄)

### 通过 API

```bash
# 列出 kill requests
curl http://localhost:8000/api/runtime/sandbox-v2/kill/requests

# 列出 kill records
curl http://localhost:8000/api/runtime/sandbox-v2/kill/records

# 列出 active handles
curl http://localhost:8000/api/runtime/sandbox-v2/kill/active-handles

# Kill readiness
curl http://localhost:8000/api/runtime/sandbox-v2/kill/readiness
```

---

## 七、如何运行 Red-Team 测试

```bash
# 完整 red-team 套件
python -m pytest tests/test_open_platform/red_team -q -v

# 特定领域
python -m pytest tests/test_open_platform/red_team/test_sandbox_v2_red_team_network_ssrf.py -q -v

# 使用 runner 脚本
python scripts/run_sandbox_v2_red_team.py
```

**要求**: 所有 red-team tests 必须 100% 通过。

---

## 八、如何运行 Readiness Script

```bash
# 人类可读输出
python scripts/check_sandbox_v2_production_readiness.py

# JSON 输出
python scripts/check_sandbox_v2_production_readiness.py --json

# 检查 readiness API
curl http://localhost:8000/api/runtime/sandbox-v2/readiness
```

---

## 九、常见故障处理

### 9.1 Job 卡在 queued 状态

**症状**: Job 状态长时间为 `queued`，不进入 `processing`。

**处理**:
1. 检查 Worker 状态: `curl .../workers`
2. 手动触发一次 Worker: `curl -X POST .../workers/run-once`
3. 检查 Dead Letter（如果已达 max_attempts）
4. 回收过期 lease: `curl -X POST .../queue/requeue-expired`

### 9.2 Job 进入 dead_letter

**症状**: Job 出现在 dead letter 列表中。

**处理**:
1. 查看 dead letter reason（具体失败原因）
2. 检查 execution records 中的 error_message
3. 如果为 simulation mode，通常是策略拒绝 → 正常行为
4. 如果是真实执行，检查容器/Podman 状态

### 9.3 Artifact 无法创建

**症状**: Artifact 创建返回 400 错误。

**处理**:
1. 检查 artifact policy 是否允许（路径穿越？危险扩展名？）
2. 检查 artifact 大小是否超限
3. 检查 artifact root 目录权限和磁盘空间
4. 检查路径是否在 artifact root 内（路径穿越防护）

### 9.4 Package Request 被拒绝

**症状**: Package request 返回 400 或状态为 `rejected`。

**处理**:
1. 检查 source_type: `external_url` / `public_registry` 默认拒绝
2. 检查是否提供了 SHA256（require_package_hash=true 时必填）
3. 检查是否提供了签名（require_package_signature=true 时必填）
4. 检查是否提供了 SBOM（require_sbom=true 时必填）
5. 检查 package_manager 是否为 `unknown`

### 9.5 Network Egress Request 被拒绝

**症状**: Egress request 状态为 `rejected`。

**处理**:
1. 检查 URL scheme（file/ftp/gopher/dict 被阻止）
2. 检查 hostname（localhost/127.0.0.1/169.254.169.254 被阻止）
3. 检查是否为私有网络地址（10.x/172.16/192.168）
4. 检查端口是否在拒绝列表中
5. 使用 preflight API 测试策略

### 9.6 Kill Switch 无法执行

**症状**: Kill request 返回错误或未生效。

**处理**:
1. 检查 target 是否为 sandbox 管理的对象
2. 检查 target 状态（terminal 状态不可 kill）
3. 检查环境变量 SANDBOX_V2_KILL_SWITCH_ENABLED
4. 检查 arbitrary_pid_kill 是否为 false（不允许 kill 系统 PID）
5. 真实容器 kill 需要 Linux + container_execution_enabled=true

---

## 十、如何回滚到 Simulation-Only

如果出现安全问题或容器执行异常，立即回滚：

```bash
# 1. 关闭容器执行
export SANDBOX_V2_CONTAINER_EXECUTION_ENABLED=false

# 2. 关闭网络
export SANDBOX_V2_NETWORK_ENABLED=false

# 3. 关闭包下载
export SANDBOX_V2_PACKAGE_DOWNLOAD_ENABLED=false

# 4. 确保 fail-closed
export SANDBOX_V2_FAIL_CLOSED=true

# 5. 重启服务

# 6. 验证回滚成功
python scripts/check_sandbox_v2_production_readiness.py
```

安全回滚后，所有 sandbox job 仍可在 `simulation` 模式下继续工作。
外网访问、包下载、容器执行将被立即禁用。

---

## 十一、日志与监控

### 关键日志位置
- Application logs: 标准输出 / 日志文件
- Sandbox v2 audit records: `/api/runtime/sandbox-v2/network/audit-records`
- Kill records: `/api/runtime/sandbox-v2/kill/records`
- Execution records: `/api/runtime/sandbox-v2/execution-records`

### 监控告警建议
1. Dead letter 数量增长 → 告警
2. Kill request 高频 → 告警
3. Container execution 意外开启 → 紧急告警
4. Network egress 大量拒绝 → 需审查
5. Package quarantine 高风险发现 → 告警

---

## 十二、Performance / Capacity (Step 16)

### 12.1 默认状态

性能测试默认关闭：

```bash
SANDBOX_V2_PERF_TESTS_ENABLED=false
SANDBOX_V2_RUN_PERFORMANCE_BENCHMARKS=false
```

未启用时，API 和脚本必须返回 `disabled/skipped`，不得运行 benchmark。

### 12.2 Smoke 自检

```bash
python scripts/run_sandbox_v2_performance_smoke.py
python scripts/run_sandbox_v2_performance_smoke.py --force-smoke
```

`--force-smoke` 只运行极小 synthetic fixture，不执行用户代码、不访问外网、不启动容器或 MicroVM。

### 12.3 运维检查

1. 查看 `/api/runtime/sandbox-v2/performance/readiness`
2. 确认 `synthetic_fixture_only=true`
3. 确认 `external_load_testing=false`
4. 确认 `user_code_benchmarking=false`
5. 确认 `benchmark_cleanup_enabled=true`
6. 查看 latest capacity estimate，不将其当作生产 SLO

### 12.4 故障处理

- `large profile disabled`: 确认是否真的需要生产专项压测；默认不启用。
- `max_jobs exceeds configured maximum`: 降低请求或调整 env 上限并记录审批。
- `benchmark skipped`: 检查 `SANDBOX_V2_PERF_TESTS_ENABLED`。
- `queue target skipped`: 检查 queue backend 是否已配置。
