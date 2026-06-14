# SANDBOX V2 STEP 12 REPORT — PostgreSQL / Redis / MinIO 生产后端迁移适配

**实施日期**: 2026-06-13
**项目**: 黔智脑 Cognitive OS (`D:\dma\day2`)
**步骤**: Sandbox v2 Step 12 — 生产后端迁移适配基础

---

## 一、本次新增文件

| # | 文件 | 用途 |
|---|------|------|
| 1 | `src/open_platform/sandbox_v2/backend_factory.py` | Backend Factory：根据配置创建 store/queue/storage，缺依赖 fail closed |
| 2 | `src/adapters/postgres_sandbox_v2_store.py` | PostgreSQL SandboxV2Store adapter（~500 行，含 row mappers） |
| 3 | `src/adapters/redis_sandbox_v2_queue.py` | Redis SandboxQueue adapter（含 FakeRedisClient 测试用内存客户端） |
| 4 | `src/adapters/object_sandbox_v2_storage.py` | S3/MinIO object storage adapter（含 FakeS3Client 测试用内存客户端） |
| 5 | `docs/sql/sandbox_v2_postgres_schema.sql` | PostgreSQL DDL schema（19 张表，索引，BEGIN/COMMIT） |
| 6 | `docs/sandbox-v2-production-backends.md` | 生产后端迁移指南（配置方法、验证步骤、回滚流程） |
| 7 | `tests/test_open_platform/test_sandbox_v2_backend_factory.py` | Backend Factory 测试（20 项） |
| 8 | `tests/test_open_platform/test_sandbox_v2_postgres_adapter.py` | PostgreSQL adapter 测试（13 项） |
| 9 | `tests/test_open_platform/test_sandbox_v2_redis_queue_adapter.py` | Redis queue adapter 测试（36 项） |
| 10 | `tests/test_open_platform/test_sandbox_v2_object_storage_adapter.py` | Object storage adapter 测试（27 项） |
| 11 | `tests/test_open_platform/test_sandbox_v2_backend_readiness.py` | Backend readiness API 测试（18 项） |

**共新增 11 个文件。**

---

## 二、本次修改文件

| # | 文件 | 变更内容 |
|---|------|----------|
| 1 | `src/open_platform/sandbox_v2/config.py` | +7 个配置字段（postgres_dsn, minio_access_key, minio_secret_key, minio_bucket, s3_region, storage_prefix）；新增 `backend_blockers()` 和 `backend_warnings()` 方法 |
| 2 | `src/api/sandbox_v2.py` | `ReadinessResponse` +16 个 Step 12 backend 字段；`readiness()` 端点动态计算 backend 状态 |
| 3 | `frontend/types/runtime-admin.ts` | `SandboxV2ReadinessResponse` +16 个 Step 12 backend 字段 |
| 4 | `frontend/components/open-platform/SandboxV2Dashboard.tsx` | Overview 增加 "Backend Readiness" 3 卡片网格（Database/Queue/Object Storage） |
| 5 | `.env.sandbox-v2.example` | 补齐 PostgreSQL DSN / MinIO 完整配置 / S3 Region / Storage Prefix |
| 6 | `docs/sandbox-v2-deployment-checklist.md` | 新增"十二、生产后端 (Step 12)" 检查项 |

**共修改 6 个文件。**

---

## 三、新增配置项

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `SANDBOX_V2_POSTGRES_DSN` | (空) | PostgreSQL 连接字符串 |
| `SANDBOX_V2_MINIO_ACCESS_KEY` | (空) | MinIO access key |
| `SANDBOX_V2_MINIO_SECRET_KEY` | (空) | MinIO secret key |
| `SANDBOX_V2_MINIO_BUCKET` | `sandbox-v2-artifacts` | MinIO bucket 名称 |
| `SANDBOX_V2_S3_REGION` | `us-east-1` | S3 区域 |
| `SANDBOX_V2_STORAGE_PREFIX` | (空) | Object key 前缀 |

---

## 四、PostgreSQL Adapter 当前能力

| 能力 | 状态 | 说明 |
|------|------|------|
| SandboxV2Store Protocol 兼容 | ✅ | 实现全部 Job/ExecRecord/Artifact/Package/Network/Kill 接口 |
| 参数化查询防 SQL 注入 | ✅ | 所有 SQL 使用 `%s` 占位符 |
| 缺 psycopg 时 fail closed | ✅ | 返回 `ImportError`，不静默回退 |
| 缺 DSN 时返回 ValueError | ✅ | 明确错误信息 |
| Schema SQL 文件 | ✅ | 19 张表，索引覆盖 org/ws/job/status/created_at |
| 行映射 (row mappers) | ✅ | `_row_to_job`, `_row_to_artifact` 等 8 个 mapper |
| 连接池 | ❌ | 未实现（当前单连接） |
| 自动 migration | ❌ | 需手动 `psql -f schema.sql` |

---

## 五、Redis Queue Adapter 当前能力

| 能力 | 状态 | 说明 |
|------|------|------|
| SandboxQueue Protocol 兼容 | ✅ | enqueue/lease/ack/fail/cancel/dead_letter/heartbeat |
| Lease 防竞争 | ✅ | Sorted Set + SETNX + EXPIRE |
| FakeRedisClient (测试用) | ✅ | 完整内存实现：Sorted Set/Hash/List/String |
| 缺 redis-py 时 fail closed | ✅ | 返回 `ImportError` |
| 缺 REDIS_URL 时返回 ValueError | ✅ | 明确错误信息 |
| 注入 fake client 隔离测试 | ✅ | `_set_client()` + `create_fake_redis_queue()` |
| Redis cluster | ❌ | 未实现 |
| 连接池 | ❌ | 未实现 |

---

## 六、MinIO / S3 Storage Adapter 当前能力

| 能力 | 状态 | 说明 |
|------|------|------|
| S3-compatible object storage | ✅ | put/get/delete/list/exists |
| Key sanitization | ✅ | 防路径穿越、null byte、危险字符 |
| Build safe object keys | ✅ | `build_object_key(prefix, org, ws, category, filename)` |
| FakeS3Client (测试用) | ✅ | 完整内存实现 |
| 缺 boto3 时 fail closed | ✅ | 返回 `ImportError` |
| 缺 credentials 时返回 ValueError | ✅ | 明确错误信息 |
| 注入 fake client 隔离测试 | ✅ | `_set_client()` + `create_fake_s3_storage()` |
| Presign read URL | ❌ | 返回 `"disabled"` |
| Multipart upload | ❌ | 未实现 |
| Server-side encryption | ❌ | 未实现 |

---

## 七、Backend Readiness 输出示例

```json
{
  "database_backend": "sqlite",
  "database_backend_ready": true,
  "postgres_adapter_available": false,
  "postgres_dsn_configured": false,
  "queue_backend": "sqlite",
  "queue_backend_ready": true,
  "redis_queue_adapter_available": false,
  "redis_url_configured": false,
  "object_storage_backend": "local",
  "object_storage_ready": true,
  "minio_adapter_available": false,
  "minio_endpoint_configured": false,
  "local_fallback_enabled": true,
  "production_backend_configured": false,
  "backend_warnings": [
    "Database backend is sqlite — consider PostgreSQL for production",
    "Queue backend is sqlite (single-node) — consider Redis for distributed workers",
    "Object storage backend is local — consider MinIO/S3 for production"
  ],
  "backend_blockers": []
}
```

---

## 八、Runtime Admin Dashboard 新增展示

Dashboard Overview 分区新增 **3 张 Backend Readiness 卡片**：

| 卡片 | 展示内容 |
|------|----------|
| Database | backend 类型 (sqlite/postgres)、ready 状态、postgres adapter 可用性 |
| Queue | backend 类型 (sqlite/redis)、ready 状态、redis adapter 可用性 |
| Object Storage | backend 类型 (local/minio/s3)、ready 状态、minio adapter 可用性 |

安全约束：
- 不显示密钥/DSN/URL
- 不提供修改配置按钮
- 只展示状态 badge

---

## 九、测试结果

### Step 12 新增测试
```
104 passed in 0.67s
```

### 全部 Sandbox v2 测试
```
615 passed, 2 skipped in 29.87s
```

### Red-Team 测试
```
132 passed in 3.05s
```

### Readiness Script
```
EXIT CODE 0 — READY with 1 warning (no Docker/Podman on Windows)
```

### 前端构建
```
✓ Compiled successfully in 4.0s
0 TypeScript errors
```

**零回归。所有现有测试继续通过。**

---

## 十、当前限制（诚实声明）

| 限制 | 状态 | 原因 |
|------|------|------|
| 默认仍是 SQLite/local | ✅ | 本地开发模式不改变 |
| 未进行真实 PostgreSQL 集成压测 | ⚠️ | Windows 环境无 PostgreSQL |
| 未进行真实 Redis 集成压测 | ⚠️ | Windows 环境无 Redis |
| 未进行真实 MinIO 集成压测 | ⚠️ | Windows 环境无 MinIO |
| 无自动 migration | ❌ | 需独立迁移脚本 |
| 无 HA / 主从 / 集群 | ❌ | 需额外基础设施 |
| 无自动 backup | ❌ | 需独立备份策略 |
| 无连接池 | ❌ | 未实现 |
| Object storage presign URL | ❌ | 返回 "disabled" |
| 真实容器执行 | ❌ | 未启用 |

以上限制不影响当前本地开发模式（SQLite/local 正常运行）。

---

## 十一、下一步建议

### 建议 Step 11：MicroVM / Firecracker PoC

如果优先安全隔离深度：
- Firecracker MicroVM 原型
- seccomp / cgroup v2 运行时强制

### 或 Step 13：真实 PostgreSQL / Redis / MinIO 集成测试

如果优先生产后端验证：
- Linux 环境准备
- PostgreSQL 真实连接与压测
- Redis 真实连接与压测
- MinIO 真实上传/下载测试
- 数据 migration 工具

### 或 Step 14：权限、多租户和审计强化

如果优先安全治理：
- RBAC 权限集成
- 多租户数据隔离
- 审计日志增强

---

## 十二、命令速查

```bash
# Step 12 新增测试
python -m pytest tests/test_open_platform/test_sandbox_v2_backend_factory.py tests/test_open_platform/test_sandbox_v2_postgres_adapter.py tests/test_open_platform/test_sandbox_v2_redis_queue_adapter.py tests/test_open_platform/test_sandbox_v2_object_storage_adapter.py tests/test_open_platform/test_sandbox_v2_backend_readiness.py -q

# 全部 Sandbox v2 测试
python -m pytest tests/test_open_platform/ -q --ignore=tests/test_open_platform/red_team -k "sandbox_v2"

# Red-Team 测试
python -m pytest tests/test_open_platform/red_team -q

# Readiness 检查
python scripts/check_sandbox_v2_production_readiness.py

# PostgreSQL Schema 应用（如使用 PostgreSQL）
psql "$SANDBOX_V2_POSTGRES_DSN" -f docs/sql/sandbox_v2_postgres_schema.sql

# 生产后端启动（参考）
docker compose -f docker-compose.sandbox-v2.example.yml up -d

# 前端构建
cd frontend && npm run build
```

---

## 十三、执行原则确认

- [OK] 未强制替换 SQLite
- [OK] 未删除 sqlite_sandbox_v2_store.py
- [OK] 未删除 sqlite_sandbox_v2_queue.py
- [OK] 未破坏本地测试（615 passed）
- [OK] 未要求用户安装 PostgreSQL/Redis/MinIO 才能启动
- [OK] 测试不依赖真实外部服务（全部使用 fake/in-memory）
- [OK] 未标记生产后端为完整生产上线
- [OK] 未执行用户代码
- [OK] 未启用真实容器执行
- [OK] 未访问外网
- [OK] 未自动安装大型依赖（psycopg/redis/boto3 均为 optional extras）
- [OK] 缺依赖时 fail closed，不静默回退
