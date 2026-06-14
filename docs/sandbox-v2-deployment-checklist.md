# Sandbox v2 — Deployment Checklist

**版本**: Step 10  
**最后更新**: 2026-06-13  
**用途**: 生产部署前的逐项验证清单

---

## 部署前检查清单

### 一、环境变量审查

- [ ] `.env.sandbox-v2` 已从 `.env.sandbox-v2.example` 创建并审查
- [ ] `SANDBOX_V2_FAIL_CLOSED=true` — 确认 fail-closed
- [ ] `SANDBOX_V2_DEFAULT_ACTION=deny` — 确认默认 deny
- [ ] `SANDBOX_V2_MODE=simulation` — 确认默认 simulation 模式
- [ ] 所有 `*_ENABLED` 变量已逐项审计（不盲目复制示例值）
- [ ] 所有密钥/密码已从占位符替换为真实值

### 二、网络

- [ ] `SANDBOX_V2_NETWORK_ENABLED=false` — 外网访问默认关闭
- [ ] `SANDBOX_V2_NETWORK_PREFLIGHT_ONLY=true` — 仅做策略检查
- [ ] `SANDBOX_V2_BLOCK_PRIVATE_NETWORKS=true` — 阻止内网访问
- [ ] `SANDBOX_V2_BLOCK_METADATA_SERVICE=true` — 阻止云 metadata
- [ ] `SANDBOX_V2_DENIED_DOMAINS` 包含 localhost、metadata IP
- [ ] `SANDBOX_V2_ALLOWED_DOMAINS` 为空或经安全审查

### 三、包管理

- [ ] `SANDBOX_V2_PACKAGE_DOWNLOAD_ENABLED=false` — 包下载默认关闭
- [ ] `SANDBOX_V2_PUBLIC_REGISTRY_ENABLED=false` — 公共 registry 关闭
- [ ] `SANDBOX_V2_PACKAGE_INSTALLATION_ENABLED=false` — 包安装关闭
- [ ] `SANDBOX_V2_REQUIRE_PACKAGE_HASH=true` — 强制要求 hash
- [ ] `SANDBOX_V2_REQUIRE_PACKAGE_SIGNATURE=true` — 强制要求签名
- [ ] `SANDBOX_V2_REQUIRE_SBOM=true` — 强制要求 SBOM

### 四、容器执行

- [ ] `SANDBOX_V2_CONTAINER_EXECUTION_ENABLED=false` — 默认关闭，或已批准且满足所有前置条件
- [ ] 如果启用容器执行：
  - [ ] Linux 宿主（非 Windows/Mac）
  - [ ] Rootless Docker/Podman 已配置
  - [ ] seccomp profile 已配置
  - [ ] AppArmor/SELinux 已启用
  - [ ] User namespace remap 已启用
  - [ ] 所有允许的镜像已手动 pull 并审计
  - [ ] Red-Team container escape tests 在目标环境通过
- [ ] `SANDBOX_V2_USER_COMMAND_EXECUTION=false` — 永久关闭
- [ ] `SANDBOX_V2_USER_IMAGE_EXECUTION=false` — 永久关闭
- [ ] `SANDBOX_V2_AUTO_PULL_IMAGES=false` — 永久关闭
- [ ] `SANDBOX_V2_ALLOWED_IMAGES` 经安全审查

### 五、Kill Switch

- [ ] `SANDBOX_V2_KILL_SWITCH_ENABLED=true` — 启用统一控制
- [ ] `SANDBOX_V2_ARBITRARY_PID_KILL=false` — 永久关闭
- [ ] `SANDBOX_V2_CONTAINER_KILL_ENABLED=false` — 默认关闭（与容器执行同步）
- [ ] Kill records 可审计（API 返回记录）

### 六、Artifact

- [ ] `SANDBOX_V2_ARTIFACT_ROOT` 路径已配置
- [ ] Artifact root 目录权限正确（推荐 750）
- [ ] `SANDBOX_V2_READ_ONLY_ARTIFACTS=true`
- [ ] `SANDBOX_V2_MAX_ARTIFACT_BYTES` 已合理设置
- [ ] 磁盘空间充足

### 七、Package Quarantine

- [ ] `SANDBOX_V2_PACKAGE_QUARANTINE_ROOT` 路径已配置
- [ ] Quarantine 目录权限正确（推荐 700）
- [ ] 目录不可被 Web 服务器直接 serve
- [ ] 磁盘空间充足

### 八、Queue / Worker

- [ ] `SANDBOX_V2_QUEUE_BACKEND` 已配置
- [ ] `SANDBOX_V2_WORKER_ENABLED=true`
- [ ] `SANDBOX_V2_WORKER_MAX_ATTEMPTS` 已合理设置
- [ ] `SANDBOX_V2_WORKER_LEASE_SECONDS` 已合理设置

### 九、测试

- [ ] Red-team 测试在目标环境通过（132 tests, 100%）
  ```bash
  python -m pytest tests/test_open_platform/red_team -q
  ```
- [ ] 全部 sandbox v2 测试通过
  ```bash
  python -m pytest tests/test_open_platform/test_sandbox_v2_*.py -q
  ```
- [ ] Readiness script 通过（无 blockers）
  ```bash
  python scripts/check_sandbox_v2_production_readiness.py
  ```

### 十、Runtime Admin

- [ ] Runtime Admin Dashboard 可访问
- [ ] Overview 显示正确的能力状态
- [ ] Production Readiness 卡片显示正确
- [ ] Kill Switch 可审计（记录可见）
- [ ] Network Audit 记录可见
- [ ] 前端构建成功
  ```bash
  cd frontend && npm run build
  ```

### 十一、生产日志与备份

- [ ] 应用日志已配置（文件/SIEM）
- [ ] Sandbox audit records 定期备份
- [ ] Kill records 定期备份
- [ ] 日志保留期限符合合规要求
- [ ] 监控告警已配置（Dead Letter、Kill 频率、容器执行开启等）

### 十二、生产后端 (Step 12)

- [ ] PostgreSQL DSN 已配置 (`SANDBOX_V2_POSTGRES_DSN`) 或确认使用 SQLite
- [ ] Redis URL 已配置 (`SANDBOX_V2_REDIS_URL`) 或确认使用 SQLite queue
- [ ] MinIO/S3 bucket 已配置 或确认使用 local storage
- [ ] Backend readiness 无 blocker (`python scripts/check_sandbox_v2_production_readiness.py`)
- [ ] PostgreSQL schema 已应用（如使用 PostgreSQL）
- [ ] Backup/retention 策略已确认

### 十三、后端集成测试 (Step 13)

- [ ] `SANDBOX_V2_RUN_BACKEND_INTEGRATION` 已配置（如需集成测试）
- [ ] `python scripts/check_sandbox_v2_backend_integration.py` 通过
- [ ] PostgreSQL schema 已初始化（如使用 PostgreSQL）
- [ ] 集成测试通过或在无服务时正确 skip
  ```bash
  python -m pytest tests/test_open_platform/integration_backend -q
  ```

### 十四、文档 (Step 10)

- [ ] `docs/sandbox-v2-production-hardening.md` 已阅读并理解
- [ ] `docs/sandbox-v2-operations-runbook.md` 已阅读并理解
- [ ] `docs/sandbox-v2-incident-response.md` 已阅读并理解
- [ ] `docs/sandbox-v2-deployment-checklist.md` 已完成（本文件）
- [ ] `.env.sandbox-v2.example` 已审查
- [ ] `docker-compose.sandbox-v2.example.yml` 已审查（如需生产后端迁移）

### 十五、Performance / Capacity (Step 16)

- [ ] Performance tests 默认关闭
  ```bash
  grep SANDBOX_V2_PERF_TESTS_ENABLED .env.sandbox-v2.example
  ```
- [ ] Benchmark 大规模运行默认关闭
  ```bash
  grep SANDBOX_V2_RUN_PERFORMANCE_BENCHMARKS .env.sandbox-v2.example
  ```
- [ ] Smoke 脚本默认 skipped，不创建大数据
  ```bash
  python scripts/run_sandbox_v2_performance_smoke.py
  ```
- [ ] 如需极小自检，只运行 synthetic fixture
  ```bash
  python scripts/run_sandbox_v2_performance_smoke.py --force-smoke
  ```
- [ ] Runtime Admin `Performance` 分区可见
- [ ] Readiness 显示 `synthetic_fixture_only=true`
- [ ] Readiness 显示 `external_load_testing=false`
- [ ] Readiness 显示 `user_code_benchmarking=false`
- [ ] Capacity estimate 仅作为基准参考，不作为生产 SLO

---

## 签名确认

| 角色 | 姓名 | 日期 | 签名 |
|------|------|------|------|
| 部署执行人 | | | |
| 安全审查人 | | | |
| 运维负责人 | | | |

---

## 部署后验证

部署完成后，执行以下验证：

- [ ] 服务正常启动
- [ ] Runtime Admin API 返回 200
- [ ] Readiness API 返回正确状态
- [ ] 无 unintended container execution
- [ ] 无 unintended network access
- [ ] 无 unintended package download
- [ ] Red-team tests 在部署后环境通过
