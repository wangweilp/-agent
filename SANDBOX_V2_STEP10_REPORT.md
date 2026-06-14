# SANDBOX V2 STEP 10 REPORT — 生产化配置、部署与 Hardening 文档

**实施日期**: 2026-06-13
**项目**: 黔智脑 Cognitive OS (`D:\dma\day2`)
**步骤**: Sandbox v2 Step 10 — 生产化配置、部署与 Hardening 文档

---

## 一、本次新增文件

| # | 文件 | 用途 |
|---|------|------|
| 1 | `.env.sandbox-v2.example` | Sandbox v2 环境变量模板（~200 行），默认安全关闭所有危险能力 |
| 2 | `src/open_platform/sandbox_v2/config.py` | 生产化配置读取层：`SandboxV2Settings` 数据类 + `load_sandbox_v2_settings()` |
| 3 | `scripts/check_sandbox_v2_production_readiness.py` | 生产 readiness 检查脚本（JSON + 人类可读输出） |
| 4 | `docker-compose.sandbox-v2.example.yml` | 生产化依赖样例（postgres/redis/minio），仅参考不强制 |
| 5 | `docs/sandbox-v2-production-hardening.md` | 安全加固指南（安全默认值、前置条件、权限建议、红线清单） |
| 6 | `docs/sandbox-v2-operations-runbook.md` | 运维手册（Dashboard/API 操作、故障处理、回滚流程） |
| 7 | `docs/sandbox-v2-incident-response.md` | 事件响应指南（异常 Job/Package/Network/Kill/Red-Team 处理） |
| 8 | `docs/sandbox-v2-deployment-checklist.md` | 部署检查清单（12 大项逐项检查） |
| 9 | `tests/test_open_platform/test_sandbox_v2_config.py` | 配置层测试（68 项） |
| 10 | `tests/test_open_platform/test_sandbox_v2_production_readiness.py` | Production readiness 测试（32 项） |

**共新增 10 个文件。**

---

## 二、本次修改文件

| # | 文件 | 变更内容 |
|---|------|----------|
| 1 | `src/api/sandbox_v2.py` | `ReadinessResponse` +10 个 production 字段；`readiness()` 端点动态计算文件存在性和安全默认值 |
| 2 | `frontend/types/runtime-admin.ts` | `SandboxV2ReadinessResponse` +10 个 Step 10 production 字段 |
| 3 | `frontend/components/open-platform/SandboxV2Dashboard.tsx` | Overview 增加 "Production Readiness" 卡片（第 4 个卡片，grid 从 md:grid-cols-3 改为 md:grid-cols-4） |

**共修改 3 个文件。**

---

## 三、新增配置项列表

### Core
| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `SANDBOX_V2_ENABLED` | `true` | 启用 Sandbox v2 |
| `SANDBOX_V2_MODE` | `simulation` | 运行模式 |
| `SANDBOX_V2_DEFAULT_ACTION` | `deny` | 默认策略动作 |
| `SANDBOX_V2_FAIL_CLOSED` | `true` | Fail-closed 模式 |

### Artifact
| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `SANDBOX_V2_ARTIFACT_ROOT` | `.sandbox_v2_artifacts` | Artifact 存储根目录 |
| `SANDBOX_V2_MAX_ARTIFACT_BYTES` | `1048576` | 单 artifact 最大字节数 |
| `SANDBOX_V2_MAX_JOB_ARTIFACT_BYTES` | `10485760` | 单 job 最大总字节数 |
| `SANDBOX_V2_READ_ONLY_ARTIFACTS` | `true` | Artifact 只读物化 |

### Package
| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `SANDBOX_V2_PACKAGE_QUARANTINE_ROOT` | `.sandbox_v2_package_quarantine` | 隔离区根目录 |
| `SANDBOX_V2_PACKAGE_DOWNLOAD_ENABLED` | **`false`** | 包下载 |
| `SANDBOX_V2_PUBLIC_REGISTRY_ENABLED` | **`false`** | 公共 registry |
| `SANDBOX_V2_PACKAGE_INSTALLATION_ENABLED` | **`false`** | 包安装 |
| `SANDBOX_V2_REQUIRE_PACKAGE_HASH` | `true` | 强制包 hash |
| `SANDBOX_V2_REQUIRE_PACKAGE_SIGNATURE` | `true` | 强制包签名 |
| `SANDBOX_V2_REQUIRE_SBOM` | `true` | 强制 SBOM |

### Network
| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `SANDBOX_V2_NETWORK_ENABLED` | **`false`** | 外网访问 |
| `SANDBOX_V2_NETWORK_PREFLIGHT_ONLY` | `true` | 仅 preflight |
| `SANDBOX_V2_BLOCK_PRIVATE_NETWORKS` | `true` | 阻止私有网络 |
| `SANDBOX_V2_BLOCK_METADATA_SERVICE` | `true` | 阻止云 metadata |
| `SANDBOX_V2_ALLOWED_DOMAINS` | (空) | 域名白名单 |
| `SANDBOX_V2_DENIED_DOMAINS` | `localhost,127.0.0.1,169.254.169.254` | 域名黑名单 |

### Container
| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `SANDBOX_V2_CONTAINER_EXECUTION_ENABLED` | **`false`** | 真实容器执行 |
| `SANDBOX_V2_RUN_CONTAINER_INTEGRATION` | **`false`** | 容器集成测试 |
| `SANDBOX_V2_ALLOWED_IMAGES` | `python:3.11-alpine,busybox:latest` | 允许的镜像 |
| `SANDBOX_V2_AUTO_PULL_IMAGES` | **`false`** | 自动 pull 镜像 |
| `SANDBOX_V2_USER_COMMAND_EXECUTION` | **`false`** | 用户命令执行 |
| `SANDBOX_V2_USER_IMAGE_EXECUTION` | **`false`** | 用户镜像执行 |

### Kill Switch
| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `SANDBOX_V2_KILL_SWITCH_ENABLED` | `true` | Kill Switch 统一控制 |
| `SANDBOX_V2_ARBITRARY_PID_KILL` | **`false`** | 任意 PID kill |
| `SANDBOX_V2_CONTAINER_KILL_ENABLED` | **`false`** | 真实容器 kill |

### Queue / Worker
| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `SANDBOX_V2_QUEUE_BACKEND` | `sqlite` | 队列后端 |
| `SANDBOX_V2_WORKER_ENABLED` | `true` | Worker 轮询 |
| `SANDBOX_V2_WORKER_MAX_ATTEMPTS` | `3` | 最大重试次数 |
| `SANDBOX_V2_WORKER_LEASE_SECONDS` | `60` | Lease 超时秒数 |

### Future Production Backends
| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `SANDBOX_V2_DATABASE_BACKEND` | `sqlite` | 数据库后端 |
| `SANDBOX_V2_REDIS_URL` | (空) | Redis URL |
| `SANDBOX_V2_OBJECT_STORAGE_BACKEND` | `local` | 对象存储后端 |
| `SANDBOX_V2_MINIO_ENDPOINT` | (空) | MinIO endpoint |
| `SANDBOX_V2_S3_ACCESS_KEY` | (空) | S3 Access Key |
| `SANDBOX_V2_S3_SECRET_KEY` | (空) | S3 Secret Key |
| `SANDBOX_V2_S3_BUCKET` | `sandbox-v2-artifacts` | S3 Bucket |

---

## 四、新增文档列表

| # | 文档 | 内容要点 |
|---|------|----------|
| 1 | `sandbox-v2-production-hardening.md` | 安全默认值、永久关闭能力、容器前置条件、权限建议、网络策略、Kill Switch 策略、Red-Team 要求、生产红线、检查清单 |
| 2 | `sandbox-v2-operations-runbook.md` | Dashboard 导航、API 操作示例、常见故障处理（6 类）、回滚到 simulation-only 步骤、日志与监控建议 |
| 3 | `sandbox-v2-incident-response.md` | 异常 Job/Package/Network/Kill/Red-Team 处理步骤、日志保留建议（90-365 天）、上报矩阵、紧急回滚流程 |
| 4 | `sandbox-v2-deployment-checklist.md` | 12 大项部署前检查清单（环境变量/网络/包管理/容器/Kill Switch/Artifact/Queue/测试/Runtime Admin/日志/文档）、签名确认表 |

---

## 五、Readiness Script 输出示例

```
======================================================================
  Sandbox v2 Production Readiness Check
======================================================================
  Project root: D:\dma\day2
  OS: Windows 11 (AMD64)

  [[OK] PASS] Safe defaults

  [[OK] PASS] Artifact root: exists at D:\dma\day2\.sandbox_v2_artifacts

  [[OK] PASS] Package quarantine root: exists at D:\dma\day2\.sandbox_v2_package_quarantine

  [[OK] PASS] Network locked down: yes

  [[OK] PASS] Package download locked down: yes

  [[OK] PASS] Container execution: disabled (safe)

  [[WARN]NOTE] Container runtime: Neither Docker nor Podman found in PATH

  [[OK] PASS] Red-team suite: Found 8 red-team test files

  [[OK]] Doc: production_hardening --- present
  [[OK]] Doc: operations_runbook --- present
  [[OK]] Doc: incident_response --- present
  [[OK]] Doc: deployment_checklist --- present

  [[OK]] .env.sandbox-v2.example: present
  [[OK]] docker-compose.sandbox-v2.example.yml: present

  [WARN]WARNINGS (1):
       -Container runtime not available: Neither Docker nor Podman found in PATH

  ->Recommended next steps:
     1. Set up PostgreSQL and migrate database (Step 12)
     2. Set up Redis and migrate queue backend (Step 12)
     3. Set up MinIO/S3 for artifact storage (Step 12)
     4. Complete Linux/WSL2 rootless container verification
     5. Run red-team tests on target deployment environment
     6. Run production readiness script

  [WARN]Overall: READY with 1 warning(s)
======================================================================
EXIT CODE: 0
```

---

## 六、Runtime Admin 新增展示

Dashboard Overview 分区新增第 4 张卡片：**"Production Readiness"**

展示内容：
- 8 个状态 badge（Hardening Docs, Env Template, Readiness Script, Deploy Checklist, Ops Runbook, IR Runbook, Docker Compose, Safe Defaults）
- Production Blockers 列表（红色高亮）
- Warnings 列表（橙色高亮）
- 无 blockers 且无 warnings 时显示 "Production ready"

安全约束：
- 仅展示状态，不提供操作按钮
- 不提供一键启用容器执行
- 不提供一键开放网络
- 不提供一键安装包

---

## 七、测试结果

### Config + Production Readiness 测试
```
100 passed in 0.42s
```

### 全部 Sandbox v2 测试
```
511 passed, 2 skipped in 18.82s
```

### Red-Team 测试
```
132 passed in 2.95s
```

### 前端构建
```
✓ Compiled successfully in 4.0s
0 TypeScript errors
```

**零回归。所有现有测试继续通过。**

---

## 八、Readiness API 新增字段

```
production_hardening_docs: true
env_template_present: true
production_readiness_script: true
deployment_checklist_present: true
operations_runbook_present: true
incident_response_runbook_present: true
docker_compose_example_present: true
safe_defaults_configured: true
production_blockers: []
warnings: []
```

---

## 九、当前仍缺什么

| 能力 | 状态 | 原因 |
|------|------|------|
| 真实 Linux 容器验证 | [WARN] | Windows 环境无 Docker/Podman — 需 Linux/WSL2 |
| MicroVM / Firecracker | [WARN] | 未实现 — 计划 Step 11 |
| Redis/Celery 生产队列 | [WARN] | 当前 SQLite — 计划 Step 12 |
| PostgreSQL 生产迁移 | [WARN] | 当前 SQLite — 计划 Step 12 |
| MinIO / S3 对象存储迁移 | [WARN] | 当前 local — 计划 Step 12 |
| 真实 CVE scanner | [WARN] | 仅 fixture scanner |
| 生产级镜像签名验证 | [WARN] | 接口已定义，未接入真实签名服务 |

以上均标记为 `warnings` 而非 `production_blockers`，因为它们是"建议升级"而非"阻塞安全"。

---

## 十、下一步建议

### 建议 Step 11：MicroVM / Firecracker PoC

如果优先安全隔离深度：
- Firecracker MicroVM 原型
- seccomp / cgroup v2 运行时强制
- 与现有 Container Provider 抽象层集成

### 或 Step 12：PostgreSQL / Redis / MinIO 生产后端迁移

如果优先生产化基础设施：
- PostgreSQL 替代 SQLite（数据持久化 + 并发）
- Redis 替代 SQLite 队列（分布式 Worker）
- MinIO/S3 替代本地文件系统（Artifact 对象存储）
- 使用 `docker-compose.sandbox-v2.example.yml` 作为参考

---

## 十一、命令速查

```bash
# 生产 readiness 检查
python scripts/check_sandbox_v2_production_readiness.py

# JSON 输出
python scripts/check_sandbox_v2_production_readiness.py --json

# 新增测试
python -m pytest tests/test_open_platform/test_sandbox_v2_config.py tests/test_open_platform/test_sandbox_v2_production_readiness.py -q -v

# 全部 Sandbox v2 测试
python -m pytest tests/test_open_platform/ -q --ignore=tests/test_open_platform/red_team -k "sandbox_v2"

# Red-Team 测试
python -m pytest tests/test_open_platform/red_team -q

# 前端构建
cd frontend && npm run build
```

---

## 十二、执行原则确认

- [OK] 未默认启用真实容器执行
- [OK] 未默认允许外网访问
- [OK] 未默认允许包下载
- [OK] 未默认允许用户命令或用户镜像
- [OK] 未删除本地开发模式（SQLite/local 不变）
- [OK] 未强制迁移 PostgreSQL / Redis / MinIO
- [OK] 未引入大规模依赖导致项目无法启动
- [OK] 未修改安全策略为宽松模式
- [OK] 未执行用户代码
- [OK] 未自动 pull 镜像
- [OK] 未实现 MicroVM
- [OK] 未破坏现有测试（511+132 全部通过）
