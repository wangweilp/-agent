#!/usr/bin/env python
"""Sandbox v2 PostgreSQL Schema Initialization Script.

Step 13 — Produces Backend Integration.

功能:
1. 读取 SANDBOX_V2_POSTGRES_DSN
2. 读取 docs/sql/sandbox_v2_postgres_schema.sql
3. 检查 SANDBOX_V2_RUN_BACKEND_INTEGRATION=true
4. 执行 CREATE TABLE IF NOT EXISTS / CREATE INDEX IF NOT EXISTS
5. 不 drop 用户数据
6. DSN mask
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def _mask_dsn(dsn: str) -> str:
    """Mask DSN 中的密码。"""
    import re
    return re.sub(r":([^@]+)@", ":****@", dsn)


def main() -> int:
    print("=" * 70)
    print("  Sandbox v2 PostgreSQL Schema Initialization")
    print("=" * 70)

    # 检查集成开关
    run_integration = os.environ.get("SANDBOX_V2_RUN_BACKEND_INTEGRATION", "").lower() in ("true", "1", "yes")
    if not run_integration:
        print("  SKIPPED: SANDBOX_V2_RUN_BACKEND_INTEGRATION is not true.")
        print("  Set SANDBOX_V2_RUN_BACKEND_INTEGRATION=true to run schema init.")
        return 0

    # 检查 DSN
    dsn = os.environ.get("SANDBOX_V2_POSTGRES_DSN", "").strip()
    if not dsn:
        print("  [FAIL] SANDBOX_V2_POSTGRES_DSN is not configured.")
        return 1

    print(f"  DSN: {_mask_dsn(dsn)}")

    # 检查 schema 文件
    schema_path = PROJECT_ROOT / "docs" / "sql" / "sandbox_v2_postgres_schema.sql"
    if not schema_path.is_file():
        print(f"  [FAIL] Schema file not found: {schema_path}")
        return 1

    print(f"  Schema: {schema_path}")

    # 检查 psycopg
    try:
        import psycopg2
        pg_mod = psycopg2
    except ImportError:
        try:
            import psycopg
            pg_mod = psycopg
        except ImportError:
            print("  [FAIL] psycopg2/psycopg not installed. pip install psycopg2-binary")
            return 1

    # 连接并执行 schema
    try:
        conn = pg_mod.connect(dsn)
        conn.autocommit = True
        cur = conn.cursor()
        sql = schema_path.read_text(encoding="utf-8")
        cur.execute(sql)
        conn.commit()
        cur.close()
        conn.close()
        print("  [OK] Schema applied successfully.")
        print("=" * 70)
        return 0
    except Exception as e:
        print(f"  [FAIL] Schema init failed: {e}")
        print("=" * 70)
        return 1


if __name__ == "__main__":
    sys.exit(main())
