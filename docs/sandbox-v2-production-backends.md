# Sandbox v2 — Production Backend Migration Guide

**版本**: Step 12  
**最后更新**: 2026-06-13  
**目标受众**: 后端开发 / SRE / DevOps

---

## 一、当前默认后端（无需任何额外配置即可运行）

| 职责 | 当前后端 | 说明 |
|------|----------|------|
| 数据库 (Store) | SQLite | `src/adapters/sqlite_sandbox_v2_store.py` |
| 任务队列 (Queue) | SQLite | `src/adapters/sqlite_sandbox_v2_queue.py` |
| Artifact 存储 | Local filesystem | `src/open_platform/sandbox_v2/artifacts.py` |
| Package Quarantine | Local filesystem | `src/open_platform/sandbox_v2/packages.py` |

**这些默认后端不会改变。** Step 12 只添加新 adapter，不替换现有实现。

---

## 二、生产建议后端

| 职责 | 生产后端 | Adapter 文件 |
|------|----------|-------------|
| 数据库 | PostgreSQL 16 | `src/adapters/postgres_sandbox_v2_store.py` |
| 任务队列 | Redis 7 | `src/adapters/redis_sandbox_v2_queue.py` |
| Artifact 存储 | MinIO / S3 | `src/adapters/object_sandbox_v2_storage.py` |
| Package Quarantine | MinIO / S3 | `src/adapters/object_sandbox_v2_storage.py` |

---

## 三、如何配置 PostgreSQL

### 3.1 启动 PostgreSQL

```bash
# 使用提供的 docker compose
docker compose -f docker-compose.sandbox-v2.example.yml up -d postgres
```

### 3.2 配置环境变量

```bash
export SANDBOX_V2_DATABASE_BACKEND=postgres
export SANDBOX_V2_POSTGRES_DSN="postgresql://sandbox_v2:password@localhost:5432/sandbox_v2"
```

### 3.3 初始化 Schema

```bash
# Schema 文件位置
docs/sql/sandbox_v2_postgres_schema.sql

# 应用 schema
psql "$SANDBOX_V2_POSTGRES_DSN" -f docs/sql/sandbox_v2_postgres_schema.sql
```

### 3.4 安装依赖

```bash
pip install psycopg2-binary
```

### 3.5 验证

```bash
python scripts/check_sandbox_v2_production_readiness.py
# 应显示: database_backend=postgres, database_backend_ready=true
```

---

## 四、如何配置 Redis Queue

### 4.1 启动 Redis

```bash
docker compose -f docker-compose.sandbox-v2.example.yml up -d redis
```

### 4.2 配置环境变量

```bash
export SANDBOX_V2_QUEUE_BACKEND=redis
export SANDBOX_V2_REDIS_URL="redis://:password@localhost:6379/0"
```

### 4.3 安装依赖

```bash
pip install redis
```

### 4.4 验证

```bash
python scripts/check_sandbox_v2_production_readiness.py
# 应显示: queue_backend=redis, queue_backend_ready=true
```

---

## 五、如何配置 MinIO

### 5.1 启动 MinIO

```bash
docker compose -f docker-compose.sandbox-v2.example.yml up -d minio
```

### 5.2 创建 Bucket

```bash
# 访问 MinIO Console: http://localhost:9001
# 或使用 mc 命令:
mc alias set local http://localhost:9000 minioadmin change-me-minio
mc mb local/sandbox-v2-artifacts
```

### 5.3 配置环境变量

```bash
export SANDBOX_V2_OBJECT_STORAGE_BACKEND=minio
export SANDBOX_V2_MINIO_ENDPOINT="http://localhost:9000"
export SANDBOX_V2_MINIO_ACCESS_KEY="minioadmin"
export SANDBOX_V2_MINIO_SECRET_KEY="change-me-minio"
export SANDBOX_V2_MINIO_BUCKET="sandbox-v2-artifacts"
```

### 5.4 安装依赖

```bash
pip install boto3
```

### 5.5 验证

```bash
python scripts/check_sandbox_v2_production_readiness.py
# 应显示: object_storage_backend=minio, object_storage_ready=true
```

---

## 六、如何运行 docker-compose.sandbox-v2.example.yml

```bash
# 启动所有生产后端
docker compose -f docker-compose.sandbox-v2.example.yml up -d

# 检查健康状态
docker compose -f docker-compose.sandbox-v2.example.yml ps

# 停止
docker compose -f docker-compose.sandbox-v2.example.yml down

# 停止并删除数据卷
docker compose -f docker-compose.sandbox-v2.example.yml down -v
```

**注意**: docker compose 文件仅为参考样例，不强制使用。
所有服务都可独立启动，不要求同时运行。

---

## 七、如何验证 Readiness

### API 端点

```bash
curl http://localhost:8000/api/runtime/sandbox-v2/readiness | jq '.'
```

返回示例:
```json
{
  "database_backend": "sqlite",
  "database_backend_ready": true,
  "postgres_adapter_available": false,
  "queue_backend": "sqlite",
  "queue_backend_ready": true,
  "redis_queue_adapter_available": false,
  "object_storage_backend": "local",
  "object_storage_ready": true,
  "minio_adapter_available": false,
  "local_fallback_enabled": true,
  "production_backend_configured": false,
  "backend_warnings": [...],
  "backend_blockers": []
}
```

### Readiness Script

```bash
python scripts/check_sandbox_v2_production_readiness.py
```

### Runtime Admin Dashboard

导航到 **Runtime Admin > Sandbox V2 > Overview**，查看 "Backend Readiness" 分区。

---

## 八、Backend Blocker 规则

系统遵循 **fail-closed** 原则：

| 配置 | 条件 | 结果 |
|------|------|------|
| `database_backend=postgres` | POSTGRES_DSN 为空 | **BLOCKER** |
| `database_backend=postgres` | psycopg2 未安装 | **BLOCKER** |
| `queue_backend=redis` | REDIS_URL 为空 | **BLOCKER** |
| `queue_backend=redis` | redis-py 未安装 | **BLOCKER** |
| `object_storage_backend=minio` | MINIO_ENDPOINT 为空 | **BLOCKER** |
| `object_storage_backend=minio/s3` | access key/secret key/bucket 任一为空 | **BLOCKER** |
| `object_storage_backend=minio/s3` | boto3 未安装 | **BLOCKER** |
| 默认 sqlite/local | — | 无 blocker |

**显式选择生产后端但缺配置 → blocker（不会静默回退）**

---

## 九、如何回滚到 SQLite/Local

```bash
# 恢复默认后端
export SANDBOX_V2_DATABASE_BACKEND=sqlite
export SANDBOX_V2_QUEUE_BACKEND=sqlite
export SANDBOX_V2_OBJECT_STORAGE_BACKEND=local

# 重启服务

# 验证
python scripts/check_sandbox_v2_production_readiness.py
```

注意：**数据不会自动迁移。** 回滚到 SQLite 后，PostgreSQL 中的数据不可用。
如需数据迁移，需单独的迁移脚本（本步骤未实现自动 migration）。

---

## 十、当前限制（诚实声明）

| 限制 | 状态 | 说明 |
|------|------|------|
| 默认仍是 SQLite/local | ✅ 有意为之 | 不破坏本地开发模式 |
| 未进行真实 PostgreSQL 集成压测 | ⚠️ | 需 Step 13 |
| 未进行真实 Redis 集成压测 | ⚠️ | 需 Step 13 |
| 未进行真实 MinIO 集成压测 | ⚠️ | 需 Step 13 |
| 无自动数据 migration | ❌ | 需独立迁移脚本 |
| 无 HA / 主从 / 集群 | ❌ | 需额外基础设施 |
| 无自动 backup | ❌ | 需独立备份策略 |
| 无连接池 | ❌ | PostgreSQL adapter 未使用连接池 |
| Object storage presign URL | ❌ | 返回 "disabled" |
