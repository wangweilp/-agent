#!/usr/bin/env python
"""Sandbox v2 Backend Integration Preflight Check.

Step 13 — Production Backend Integration.

功能:
1. 读取 SandboxV2Settings
2. 检查 SANDBOX_V2_RUN_BACKEND_INTEGRATION
3. 检查 PostgreSQL/Redis/MinIO 配置和连接
4. 输出 JSON / human summary
5. Mask 敏感信息

安全约束:
- 不执行用户代码
- 不访问外网（仅连接本地后端）
- 不泄露密钥
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def _mask(v: str) -> str:
    """Mask 敏感信息。"""
    if not v:
        return ""
    if v.startswith("postgresql://") or v.startswith("postgres://"):
        return re.sub(r":([^@]+)@", ":****@", v)
    if v.startswith("redis://"):
        return re.sub(r"://[^@]*@", "://****@", v)
    if len(v) > 8:
        return v[:4] + "****"
    return "****"


def _env_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, "").strip().lower() in ("true", "1", "yes")


def run_backend_integration_check() -> dict[str, Any]:
    result: dict[str, Any] = {
        "timestamp": __import__("datetime").datetime.now().isoformat(),
        "run_backend_integration": False,
        "postgres_configured": False, "postgres_ready": False,
        "redis_configured": False, "redis_ready": False,
        "object_storage_configured": False, "object_storage_ready": False,
        "blockers": [], "warnings": [], "next_steps": [],
        "details": {},
    }

    run_integ = _env_bool("SANDBOX_V2_RUN_BACKEND_INTEGRATION")
    result["run_backend_integration"] = run_integ

    if not run_integ:
        result["blockers"].append("SANDBOX_V2_RUN_BACKEND_INTEGRATION is not true")
        result["next_steps"].append("Set SANDBOX_V2_RUN_BACKEND_INTEGRATION=true to enable integration checks")
        return result

    # ── PostgreSQL ──
    db_backend = os.getenv("SANDBOX_V2_DATABASE_BACKEND", "sqlite")
    pg_dsn = os.getenv("SANDBOX_V2_POSTGRES_DSN", "")
    result["postgres_configured"] = bool(db_backend == "postgres" and pg_dsn)
    result["details"]["postgres_backend"] = db_backend
    result["details"]["postgres_dsn_masked"] = _mask(pg_dsn) if pg_dsn else ""

    if db_backend == "postgres" and pg_dsn:
        try:
            from src.adapters.postgres_sandbox_v2_store import PostgresSandboxV2Store
            store = PostgresSandboxV2Store(dsn=pg_dsn, connect=True)
            hc = store.health_check()
            result["postgres_ready"] = hc["ok"]
            result["details"]["postgres_health"] = hc["reason"]
            if hc["ok"]:
                # 检查 schema
                sp = store.get_schema_sql_path()
                result["details"]["schema_path"] = str(sp) if sp else "not found"
            else:
                result["blockers"].append(f"PostgreSQL: {hc['reason']}")
        except Exception as e:
            result["details"]["postgres_error"] = str(e)
            result["blockers"].append(f"PostgreSQL connection failed: {e}")
    elif db_backend == "postgres":
        result["blockers"].append("PostgreSQL selected but DSN is empty")

    # ── Redis ──
    q_backend = os.getenv("SANDBOX_V2_QUEUE_BACKEND", "sqlite")
    redis_url = os.getenv("SANDBOX_V2_REDIS_URL", "")
    result["redis_configured"] = bool(q_backend == "redis" and redis_url)
    result["details"]["queue_backend"] = q_backend
    result["details"]["redis_url_masked"] = _mask(redis_url) if redis_url else ""

    if q_backend == "redis" and redis_url:
        try:
            from src.adapters.redis_sandbox_v2_queue import RedisSandboxV2Queue
            queue = RedisSandboxV2Queue(redis_url=redis_url, connect=True)
            hc = queue.health_check()
            result["redis_ready"] = hc["ok"]
            result["details"]["redis_health"] = hc["reason"]
            if not hc["ok"]:
                result["blockers"].append(f"Redis: {hc['reason']}")
        except Exception as e:
            result["details"]["redis_error"] = str(e)
            result["blockers"].append(f"Redis connection failed: {e}")
    elif q_backend == "redis":
        result["blockers"].append("Redis selected but REDIS_URL is empty")

    # ── MinIO / S3 ──
    os_backend = os.getenv("SANDBOX_V2_OBJECT_STORAGE_BACKEND", "local")
    minio_endpoint = os.getenv("SANDBOX_V2_MINIO_ENDPOINT", "")
    minio_ak = os.getenv("SANDBOX_V2_MINIO_ACCESS_KEY", "") or os.getenv("SANDBOX_V2_S3_ACCESS_KEY", "")
    minio_sk = os.getenv("SANDBOX_V2_MINIO_SECRET_KEY", "") or os.getenv("SANDBOX_V2_S3_SECRET_KEY", "")
    minio_bucket = os.getenv("SANDBOX_V2_MINIO_BUCKET", "") or os.getenv("SANDBOX_V2_S3_BUCKET", "")
    result["object_storage_configured"] = bool(
        os_backend in ("minio", "s3") and minio_ak
    )
    result["details"]["object_storage_backend"] = os_backend
    result["details"]["minio_ak_masked"] = _mask(minio_ak)

    if os_backend in ("minio", "s3") and minio_ak:
        try:
            from src.adapters.object_sandbox_v2_storage import S3SandboxV2Storage
            storage = S3SandboxV2Storage(
                endpoint_url=minio_endpoint, access_key=minio_ak,
                secret_key=minio_sk, bucket=minio_bucket,
                region=os.getenv("SANDBOX_V2_S3_REGION", "us-east-1"),
                connect=True,
            )
            hc = storage.health_check()
            result["object_storage_ready"] = hc["ok"]
            result["details"]["storage_health"] = hc["reason"]
            if not hc["ok"]:
                result["blockers"].append(f"Object storage: {hc['reason']}")
        except Exception as e:
            result["details"]["storage_error"] = str(e)
            result["blockers"].append(f"Object storage connection failed: {e}")
    elif os_backend in ("minio", "s3"):
        missing = []
        if not minio_endpoint and os_backend == "minio":
            missing.append("MINIO_ENDPOINT")
        if not minio_ak:
            missing.append("access key")
        if not minio_bucket:
            missing.append("bucket")
        result["blockers"].append(f"Object storage configured but missing: {', '.join(missing)}")

    # ── Next steps ──
    if not result["blockers"]:
        result["next_steps"] = [
            "Initialize PostgreSQL schema: python scripts/init_sandbox_v2_postgres_schema.py",
            "Run integration tests: python -m pytest tests/test_open_platform/integration_backend -q -v",
        ]
    else:
        result["next_steps"] = [
            "Start docker-compose: docker compose -f docker-compose.sandbox-v2.example.yml up -d",
            "Configure environment variables in .env.sandbox-v2",
            f"Resolve {len(result['blockers'])} blocker(s) before running integration tests",
        ]

    return result


def print_human_summary(result: dict[str, Any]) -> None:
    print("=" * 70)
    print("  Sandbox v2 Backend Integration Preflight")
    print("=" * 70)
    print(f"  Integration enabled: {result['run_backend_integration']}")
    if not result["run_backend_integration"]:
        print("  [SKIP] SANDBOX_V2_RUN_BACKEND_INTEGRATION not true")
        print("=" * 70)
        return

    def ok(v: bool) -> str:
        return "[OK]" if v else "[FAIL]"

    print(f"  {ok(result['postgres_ready'])} PostgreSQL: ready={result['postgres_ready']}")
    if result["postgres_configured"]:
        print(f"       DSN: {result['details'].get('postgres_dsn_masked','')}")
        print(f"       Health: {result['details'].get('postgres_health','')}")

    print(f"  {ok(result['redis_ready'])} Redis: ready={result['redis_ready']}")
    if result["redis_configured"]:
        print(f"       URL: {result['details'].get('redis_url_masked','')}")
        print(f"       Health: {result['details'].get('redis_health','')}")

    print(f"  {ok(result['object_storage_ready'])} Object storage: ready={result['object_storage_ready']}")
    if result["object_storage_configured"]:
        print(f"       Backend: {result['details'].get('object_storage_backend','')}")
        print(f"       Health: {result['details'].get('storage_health','')}")

    blockers = result.get("blockers", [])
    if blockers:
        print(f"\n  [BLOCKERS] ({len(blockers)}):")
        for b in blockers:
            print(f"    - {b}")

    steps = result.get("next_steps", [])
    if steps:
        print(f"\n  Next steps:")
        for s in steps:
            print(f"    - {s}")

    print("=" * 70)


def main() -> int:
    result = run_backend_integration_check()
    if "--json" in sys.argv:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print_human_summary(result)
    return 1 if result.get("blockers") else 0


if __name__ == "__main__":
    sys.exit(main())
