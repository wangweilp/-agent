# Sandbox v2 — Backend Integration Testing

**版本**: Step 13
**最后更新**: 2026-06-13

---

## 一、Step 13 目标

为 PostgreSQL / Redis / MinIO 生产后端增加真实集成测试基础和运维脚本。

---

## 二、默认为什么 skip

所有集成测试默认 skip。只有显式设置 `SANDBOX_V2_RUN_BACKEND_INTEGRATION=true` 且配置完整时才运行。

原因：
1. 本地开发不需要 PostgreSQL/Redis/MinIO
2. 普通 `pytest` 不应依赖外部服务
3. 真实后端连接是显式 opt-in

---

## 三、如何启动 docker-compose

```bash
docker compose -f docker-compose.sandbox-v2.example.yml up -d
docker compose -f docker-compose.sandbox-v2.example.yml ps
```

---

## 四、如何配置环境

```bash
export SANDBOX_V2_RUN_BACKEND_INTEGRATION=true

# PostgreSQL
export SANDBOX_V2_DATABASE_BACKEND=postgres
export SANDBOX_V2_POSTGRES_DSN="postgresql://sandbox_v2:password@localhost:5432/sandbox_v2"

# Redis
export SANDBOX_V2_QUEUE_BACKEND=redis
export SANDBOX_V2_REDIS_URL="redis://:password@localhost:6379/0"

# MinIO
export SANDBOX_V2_OBJECT_STORAGE_BACKEND=minio
export SANDBOX_V2_MINIO_ENDPOINT="http://localhost:9000"
export SANDBOX_V2_MINIO_ACCESS_KEY="minioadmin"
export SANDBOX_V2_MINIO_SECRET_KEY="change-me-minio"
export SANDBOX_V2_MINIO_BUCKET="sandbox-v2-artifacts"
```

---

## 五、如何初始化 PostgreSQL Schema

```bash
export SANDBOX_V2_RUN_BACKEND_INTEGRATION=true
export SANDBOX_V2_POSTGRES_DSN="postgresql://..."

python scripts/init_sandbox_v2_postgres_schema.py
```

---

## 六、如何运行 Preflight

```bash
python scripts/check_sandbox_v2_backend_integration.py

# JSON 输出
python scripts/check_sandbox_v2_backend_integration.py --json
```

---

## 七、如何运行集成测试

```bash
# 先确保环境变量已配置
export SANDBOX_V2_RUN_BACKEND_INTEGRATION=true

# 运行所有集成测试
python -m pytest tests/test_open_platform/integration_backend -q -v

# 单独运行
python -m pytest tests/test_open_platform/integration_backend/test_sandbox_v2_postgres_integration.py -q -v
```

---

## 八、如何清理测试数据

```bash
# 测试会使用唯一 test_run_id 标识数据
# 测试结束后自动清理测试数据
# 手动清理:
python -c "
from src.adapters.postgres_sandbox_v2_store import PostgresSandboxV2Store
store = PostgresSandboxV2Store(dsn='$SANDBOX_V2_POSTGRES_DSN', connect=True)
store._execute(\"DELETE FROM sandbox_v2_jobs WHERE organization_id LIKE 'step13%'\")
"
```

---

## 九、如何回滚到 SQLite/local

```bash
unset SANDBOX_V2_DATABASE_BACKEND
unset SANDBOX_V2_POSTGRES_DSN
unset SANDBOX_V2_QUEUE_BACKEND
unset SANDBOX_V2_REDIS_URL
unset SANDBOX_V2_OBJECT_STORAGE_BACKEND
unset SANDBOX_V2_RUN_BACKEND_INTEGRATION

# 重启服务后使用默认 SQLite/local
python scripts/check_sandbox_v2_production_readiness.py
```

---

## 十、当前限制

| 限制 | 说明 |
|------|------|
| HA | 未实现 |
| 自动 backup | 未实现 |
| Migration framework | 需手动 psql |
| Load test | 未进行 |
| 生产集群验证 | 不代表生产已上线 |
| 真实 Firecracker | 需 Linux 环境 |
