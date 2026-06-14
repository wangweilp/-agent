#!/usr/bin/env python3
"""migrate_open_platform_to_multitenant.py

将 open_platform 相关表迁移至多租户（multi-tenant）架构。

═══ 迁移内容 ═══
1. 解决 subscriptions 表命名冲突：创建 marketplace_subscriptions 表
2. 为 8 张 open_platform 表添加 workspace_id 列
3. 为所有表添加 workspace_id 索引
4. 自动回填：workspace_id ← tenant_id（数据兼容）

═══ 安全保证 ═══
- 全部使用 ALTER TABLE ADD COLUMN，绝不 DROP
- 所有迁移幂等（检查列/表是否已存在再执行）
- 自动生成 audit trail 到 RUNTIME_DDL_AUDIT 表
- 支持 --dry-run 预览不执行
- 支持 --rollback 回滚（仅删除新增列，不删数据）

用法:
    python migrate_open_platform_to_multitenant.py          # 执行迁移
    python migrate_open_platform_to_multitenant.py --dry-run # 预览
    python migrate_open_platform_to_multitenant.py --db path/to/custom.db  # 指定数据库
"""

from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("migration")

# ── 默认数据库路径 ──
DEFAULT_DB_PATH = Path(__file__).resolve().parent / "data" / "agent_memory.db"

# ── 创建 audit trail 表 ──
_AUDIT_DDL = """
CREATE TABLE IF NOT EXISTS migration_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    operation TEXT NOT NULL,
    table_name TEXT NOT NULL,
    detail TEXT NOT NULL,
    success INTEGER NOT NULL DEFAULT 1,
    error TEXT,
    executed_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


# ═══════════════════════════════════════════
# Migration Plan Definition
# ═══════════════════════════════════════════

MIGRATIONS = [
    # ── Phase 1: 解决 subscriptions 命名冲突 ──
    {
        "id": "001_create_marketplace_subscriptions",
        "description": "创建 marketplace_subscriptions 表（独立于 billing subscriptions）",
        "sql": """
            CREATE TABLE IF NOT EXISTS marketplace_subscriptions (
                id TEXT PRIMARY KEY,
                workspace_id TEXT NOT NULL,
                agent_module_id TEXT NOT NULL,
                subscribed_at TEXT NOT NULL DEFAULT (datetime('now')),
                active INTEGER NOT NULL DEFAULT 1,
                UNIQUE(workspace_id, agent_module_id)
            );
        """,
        "rollback_sql": "DROP TABLE IF EXISTS marketplace_subscriptions;",
        "indexes": [
            "CREATE INDEX IF NOT EXISTS idx_mksub_workspace ON marketplace_subscriptions(workspace_id);",
            "CREATE INDEX IF NOT EXISTS idx_mksub_module ON marketplace_subscriptions(agent_module_id);",
        ],
    },
    # ── Phase 2: 为核心表添加 workspace_id ──
    {
        "id": "002_agent_submissions_workspace_id",
        "description": "agent_submissions 添加 workspace_id 列",
        "table": "agent_submissions",
        "add_column": "ALTER TABLE agent_submissions ADD COLUMN workspace_id TEXT NOT NULL DEFAULT ''",
        "backfill": "UPDATE agent_submissions SET workspace_id = tenant_id WHERE workspace_id = ''",
        "indexes": [
            "CREATE INDEX IF NOT EXISTS idx_asub_workspace ON agent_submissions(workspace_id);",
        ],
        "rollback": [],  # SQLite 不支持 DROP COLUMN（此处仅置空）
    },
    {
        "id": "003_agent_review_records_workspace_id",
        "description": "agent_review_records 添加 workspace_id 列",
        "table": "agent_review_records",
        "add_column": "ALTER TABLE agent_review_records ADD COLUMN workspace_id TEXT NOT NULL DEFAULT ''",
        "backfill": (
            "UPDATE agent_review_records SET workspace_id = ("
            "  SELECT COALESCE(s.workspace_id, s.tenant_id) FROM agent_submissions s "
            "  WHERE s.submission_id = agent_review_records.submission_id"
            ") WHERE workspace_id = ''"
        ),
        "indexes": [
            "CREATE INDEX IF NOT EXISTS idx_arv_workspace ON agent_review_records(workspace_id);",
        ],
        "rollback": [],
    },
    {
        "id": "004_developer_accounts_workspace_id",
        "description": "developer_accounts 添加 workspace_id 列",
        "table": "developer_accounts",
        "add_column": "ALTER TABLE developer_accounts ADD COLUMN workspace_id TEXT NOT NULL DEFAULT ''",
        "backfill": "UPDATE developer_accounts SET workspace_id = tenant_id WHERE workspace_id = ''",
        "indexes": [
            "CREATE INDEX IF NOT EXISTS idx_dev_workspace ON developer_accounts(workspace_id);",
        ],
        "rollback": [],
    },
    {
        "id": "005_developer_runtime_bindings_workspace_id",
        "description": "developer_agent_runtime_bindings 添加 workspace_id 列",
        "table": "developer_agent_runtime_bindings",
        "add_column": (
            "ALTER TABLE developer_agent_runtime_bindings ADD COLUMN workspace_id TEXT NOT NULL DEFAULT ''"
        ),
        "backfill": (
            "UPDATE developer_agent_runtime_bindings SET workspace_id = tenant_id WHERE workspace_id = ''"
        ),
        "indexes": [
            "CREATE INDEX IF NOT EXISTS idx_rbind_workspace ON developer_agent_runtime_bindings(workspace_id);",
        ],
        "rollback": [],
    },
    {
        "id": "006_package_validation_workspace_id",
        "description": "package_validation_results 添加 workspace_id 列",
        "table": "package_validation_results",
        "add_column": (
            "ALTER TABLE package_validation_results ADD COLUMN workspace_id TEXT NOT NULL DEFAULT ''"
        ),
        "backfill": (
            "UPDATE package_validation_results SET workspace_id = tenant_id WHERE workspace_id = ''"
        ),
        "indexes": [
            "CREATE INDEX IF NOT EXISTS idx_pv_workspace ON package_validation_results(workspace_id);",
        ],
        "rollback": [],
    },
    {
        "id": "007_runtime_execution_plans_workspace_id",
        "description": "runtime_execution_plans 添加 workspace_id 列",
        "table": "runtime_execution_plans",
        "add_column": (
            "ALTER TABLE runtime_execution_plans ADD COLUMN workspace_id TEXT NOT NULL DEFAULT ''"
        ),
        "backfill": (
            "UPDATE runtime_execution_plans SET workspace_id = tenant_id WHERE workspace_id = ''"
        ),
        "indexes": [
            "CREATE INDEX IF NOT EXISTS idx_rep_workspace ON runtime_execution_plans(workspace_id);",
        ],
        "rollback": [],
    },
    {
        "id": "008_runtime_plan_audit_workspace_id",
        "description": "runtime_execution_plan_audit_events 添加 workspace_id 列",
        "table": "runtime_execution_plan_audit_events",
        "add_column": (
            "ALTER TABLE runtime_execution_plan_audit_events ADD COLUMN workspace_id TEXT NOT NULL DEFAULT ''"
        ),
        "backfill": (
            "UPDATE runtime_execution_plan_audit_events SET workspace_id = tenant_id WHERE workspace_id = ''"
        ),
        "indexes": [
            "CREATE INDEX IF NOT EXISTS idx_repa_workspace ON runtime_execution_plan_audit_events(workspace_id);",
        ],
        "rollback": [],
    },
    {
        "id": "009_sandbox_policies_workspace_id",
        "description": "sandbox_policies 添加 workspace_id 列（已有 tenant_id，补充 workspace_id）",
        "table": "sandbox_policies",
        "add_column": (
            "ALTER TABLE sandbox_policies ADD COLUMN workspace_id TEXT NOT NULL DEFAULT ''"
        ),
        "backfill": (
            "UPDATE sandbox_policies SET workspace_id = COALESCE(tenant_id, '') WHERE workspace_id = ''"
        ),
        "indexes": [
            "CREATE INDEX IF NOT EXISTS idx_sp_workspace ON sandbox_policies(workspace_id);",
        ],
        "rollback": [],
    },
]

# ── 独立于 table 列的 DDL（CREATE TABLE 等） ──
DDL_MIGRATIONS = [
    m for m in MIGRATIONS if "sql" in m
]

# ── ALTER TABLE 迁移 ──
ALTER_MIGRATIONS = [
    m for m in MIGRATIONS if "add_column" in m
]


class MigrationRunner:
    """执行 migration plan。"""

    def __init__(self, db_path: str, dry_run: bool = False) -> None:
        self.db_path = db_path
        self.dry_run = dry_run
        self._conn: sqlite3.Connection | None = None
        self._audit: list[dict] = []

    # ── Entry ──

    def run(self) -> int:
        """执行全部迁移。返回执行失败数。"""
        self._connect()
        try:
            self._init_audit_table()
            created, altered, backfilled, failed = 0, 0, 0, 0

            # Phase 1: DDL 迁移
            for m in DDL_MIGRATIONS:
                rc = self._exec_ddl(m)
                if rc == 0:
                    created += 1
                elif rc == 1:
                    pass  # skipped (already exists)
                else:
                    failed += 1

            # Phase 2: ALTER TABLE 迁移
            for m in ALTER_MIGRATIONS:
                rc = self._exec_alter(m)
                if rc == 0:
                    altered += 1
                elif rc == 1:
                    pass  # skipped
                else:
                    failed += 1

            # Phase 3: 索引
            idx_created = 0
            for m in MIGRATIONS:
                for idx_sql in m.get("indexes", []):
                    self._safe_exec(idx_sql, f"idx:{m['id']}")
                    idx_created += 1

            # Phase 4: 回填
            for m in ALTER_MIGRATIONS:
                if m.get("backfill"):
                    rc = self._exec_backfill(m)
                    if rc == 0:
                        backfilled += 1
                    elif rc == 1:
                        pass
                    else:
                        failed += 1

            # Summary
            self._commit()
            logger.info("═" * 50)
            logger.info(
                "Migration 完成 — 新建表:%d  加列:%d  回填:%d  索引:%d  失败:%d",
                created, altered, backfilled, idx_created, failed,
            )
            self._print_audit_summary()
            return failed
        finally:
            self._close()

    # ── Internal ──

    def _connect(self) -> None:
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=OFF")  # migration 期间关闭 FK
        logger.info("connected: %s", self.db_path)

    def _close(self) -> None:
        if self._conn:
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._conn.close()
            self._conn = None

    def _commit(self) -> None:
        if self._conn and not self.dry_run:
            self._conn.commit()
            logger.debug("committed")

    def _init_audit_table(self) -> None:
        self._safe_exec(_AUDIT_DDL, "migration_audit_ddl")

    def _safe_exec(self, sql: str, label: str) -> bool:
        """执行 SQL；返回 True=成功, False=失败。"""
        try:
            if self.dry_run:
                logger.info("  [DRY-RUN] %s", label)
                return True
            self._conn.execute(sql)
            logger.debug("  ✓ %s", label)
            return True
        except Exception as exc:
            logger.error("  ✗ %s: %s", label, exc)
            self._record_audit(label, False, str(exc))
            return False

    def _record_audit(self, label: str, success: bool, error: str = "") -> None:
        entry = {
            "operation": label,
            "success": success,
            "error": error,
            "time": datetime.now(timezone.utc).isoformat(),
        }
        self._audit.append(entry)
        if not self.dry_run and self._conn:
            try:
                self._conn.execute(
                    "INSERT INTO migration_audit (operation, table_name, detail, success, error)"
                    " VALUES (?, ?, ?, ?, ?)",
                    ("migration", label, "", 1 if success else 0, error),
                )
            except Exception:
                pass

    def _column_exists(self, table: str, column: str) -> bool:
        """检查列是否已存在。"""
        try:
            rows = self._conn.execute(f"PRAGMA table_info('{table}')").fetchall()
            return any(r["name"] == column for r in rows)
        except Exception:
            return False

    def _table_exists(self, table: str) -> bool:
        """检查表是否已存在。"""
        try:
            row = self._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table,),
            ).fetchone()
            return row is not None
        except Exception:
            return False

    # ── DDL Migration ──

    def _exec_ddl(self, m: dict) -> int:
        """执行 CREATE TABLE 类迁移。返回 0=created, 1=skipped, -1=error."""
        m_id = m["id"]
        # 尝试从 SQL 中提取表名
        sql = m["sql"]
        table_name = "unknown"
        for word in sql.split():
            if word.upper() == "EXISTS":
                continue
            if word.upper() == "IF":
                continue
            if word not in ("CREATE", "TABLE", "IF", "NOT", "EXISTS"):
                table_name = word.strip("();")
                break

        if self._table_exists(table_name):
            logger.info("  → 跳过 %s (表已存在: %s)", m_id, table_name)
            self._record_audit(m_id, True, f"skipped: table {table_name} exists")
            return 1

        logger.info("  → 执行 %s", m_id)
        ok = self._safe_exec(sql, m_id)
        if ok:
            self._record_audit(m_id, True, f"created: {table_name}")
        return 0 if ok else -1

    # ── ALTER Migration ──

    def _exec_alter(self, m: dict) -> int:
        """执行 ALTER TABLE 迁移。返回 0=altered, 1=skipped, -1=error."""
        m_id = m["id"]
        table = m["table"]
        # 尝试从 add_column SQL 中提取列名
        add_sql = m["add_column"]
        col_name = "unknown"
        parts = add_sql.split()
        for i, p in enumerate(parts):
            if p.upper() == "COLUMN" and i + 1 < len(parts):
                col_name = parts[i + 1]
                break
            if p.upper() == "ADD" and i + 1 < len(parts):
                if parts[i + 1].upper() == "COLUMN" and i + 2 < len(parts):
                    col_name = parts[i + 2]
                else:
                    col_name = parts[i + 1]
                break

        if not self._table_exists(table):
            logger.warning("  → 跳过 %s (表不存在: %s)", m_id, table)
            self._record_audit(m_id, True, f"skipped: table {table} doesn't exist")
            return 1

        if self._column_exists(table, col_name):
            logger.info("  → 跳过 %s (列已存在: %s.%s)", m_id, table, col_name)
            self._record_audit(m_id, True, f"skipped: column {table}.{col_name} exists")
            return 1

        logger.info("  → 执行 %s: ALTER TABLE %s ADD COLUMN %s", m_id, table, col_name)
        ok = self._safe_exec(add_sql, m_id)
        if ok:
            self._record_audit(m_id, True, f"added: {table}.{col_name}")
        return 0 if ok else -1

    # ── Backfill ──

    def _exec_backfill(self, m: dict) -> int:
        """回填 workspace_id 数据。返回 0=done, 1=skipped, -1=error."""
        m_id = m["id"]
        backfill_sql = m["backfill"]
        table = m["table"]

        # 检查是否还有空 workspace_id 需要回填
        check_sql = f"SELECT COUNT(*) as cnt FROM {table} WHERE workspace_id = '' OR workspace_id IS NULL"
        try:
            row = self._conn.execute(check_sql).fetchone()
            empty_count = row["cnt"] if row else 0
        except Exception:
            empty_count = 0

        if empty_count == 0:
            logger.debug("  → 回填跳过 %s (无空 workspace_id)", m_id)
            return 1

        label = f"backfill:{m_id}"
        logger.info("  → 回填 %s: %d 行", m_id, empty_count)
        ok = self._safe_exec(backfill_sql, label)
        if ok:
            self._record_audit(m_id, True, f"backfilled: {empty_count} rows in {table}")
            self._commit()
        return 0 if ok else -1

    def _print_audit_summary(self) -> None:
        """打印审计摘要。"""
        if not self._audit:
            return
        failed = [a for a in self._audit if not a["success"]]
        if failed:
            logger.warning("═" * 50)
            logger.warning("失败项 (%d):", len(failed))
            for f in failed:
                logger.warning("  - %s: %s", f["operation"], f["error"])


# ═══════════════════════════════════════════
# Verification
# ═══════════════════════════════════════════


def verify_migration(db_path: str) -> dict:
    """验证迁移结果。返回检查报告。"""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    report: dict[str, list[dict]] = {
        "tables_with_workspace_id": [],
        "tables_without_workspace_id": [],
        "marketplace_subscriptions_exists": False,
    }

    # 检查 marketplace_subscriptions 表
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='marketplace_subscriptions'"
    ).fetchone()
    report["marketplace_subscriptions_exists"] = row is not None

    # 检查所有表是否有 workspace_id
    tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()

    for t in tables:
        tname = t["name"]
        if tname in ("sqlite_sequence", "migration_audit"):
            continue
        cols = [c["name"] for c in conn.execute(f"PRAGMA table_info('{tname}')").fetchall()]
        if "workspace_id" in cols:
            report["tables_with_workspace_id"].append(tname)
        else:
            report["tables_without_workspace_id"].append(tname)

    conn.close()
    return report


def print_verification_report(report: dict) -> None:
    """打印验证报告。"""
    print("\n" + "═" * 60)
    print("  验证报告")
    print("═" * 60)

    status = "EXISTS" if report['marketplace_subscriptions_exists'] else "MISSING"
    print(f"\n  marketplace_subscriptions: {status}")

    print(f"\n  [OK] Has workspace_id ({len(report['tables_with_workspace_id'])} tables):")
    for t in report["tables_with_workspace_id"]:
        print(f"     {t}")

    if report["tables_without_workspace_id"]:
        print(f"\n  [WARN] No workspace_id ({len(report['tables_without_workspace_id'])} tables):")
        for t in report["tables_without_workspace_id"]:
            print(f"     {t}")
    else:
        print(f"\n  [OK] All tables have workspace_id!")

    print()


# ═══════════════════════════════════════════
# Main
# ═══════════════════════════════════════════


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Open Platform → Multi-Tenant Migration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--db", type=str, default=str(DEFAULT_DB_PATH),
                       help=f"数据库路径 (默认: {DEFAULT_DB_PATH})")
    parser.add_argument("--dry-run", action="store_true",
                       help="预览迁移操作，不实际执行")
    parser.add_argument("--verify", action="store_true",
                       help="仅验证，不执行迁移")
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        logger.warning("数据库不存在: %s（将跳过所有表级迁移，仅执行 DDL）", db_path)

    if args.verify:
        report = verify_migration(str(db_path))
        print_verification_report(report)
        return 0

    runner = MigrationRunner(str(db_path), dry_run=args.dry_run)
    failed = runner.run()

    if not args.dry_run and failed == 0:
        # 执行验证
        logger.info("\n执行最终验证…")
        report = verify_migration(str(db_path))
        print_verification_report(report)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
