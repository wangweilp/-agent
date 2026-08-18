"""SQLite Package Validation Store — 实现 PackageValidationStore 协议。"""

from __future__ import annotations
import json, logging
from datetime import datetime, timezone
from typing import Any
from src.adapters.config import Settings
from src.adapters.sqlite_connection import create_sqlite_db, execute_with_retry
from src.open_platform.package_validation import (
    PackageValidationResult, PackageValidationCheck, _safe_dt,
)

logger = logging.getLogger(__name__)

_PV_SCHEMA = """
CREATE TABLE IF NOT EXISTS package_validation_results (
    validation_id TEXT PRIMARY KEY,
    submission_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    requested_by TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'not_validated',
    source_type TEXT NOT NULL DEFAULT 'none',
    package_url TEXT,
    repository_url TEXT,
    manifest_name TEXT NOT NULL DEFAULT '',
    manifest_version TEXT NOT NULL DEFAULT '',
    checks_json TEXT NOT NULL DEFAULT '[]',
    warnings_json TEXT NOT NULL DEFAULT '[]',
    errors_json TEXT NOT NULL DEFAULT '[]',
    blockers_json TEXT NOT NULL DEFAULT '[]',
    package_metadata_json TEXT NOT NULL DEFAULT '{}',
    review_recommendation TEXT NOT NULL DEFAULT '',
    no_download_performed INTEGER NOT NULL DEFAULT 1,
    no_execution_performed INTEGER NOT NULL DEFAULT 1,
    no_network_performed INTEGER NOT NULL DEFAULT 1,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_pv_submission ON package_validation_results(submission_id);
CREATE INDEX IF NOT EXISTS idx_pv_tenant ON package_validation_results(tenant_id);
CREATE INDEX IF NOT EXISTS idx_pv_status ON package_validation_results(status);
CREATE INDEX IF NOT EXISTS idx_pv_created ON package_validation_results(created_at);
"""


class SQLitePackageValidationStore:
    def __init__(self, config: Settings, db_path: str | None = None):
        path = db_path or config.sqlite_db_path
        self._db = create_sqlite_db(path)
        execute_with_retry(lambda: self._init_schema(), label="package_validation_init_schema")

    def _init_schema(self):
        for stmt in _PV_SCHEMA.strip().split(";"):
            if stmt.strip(): self._db.execute(stmt.strip())
        try:
            self._db.conn.commit()
        except Exception:
            pass

    def flush(self) -> None:
        """显式提交底层连接事务，释放写锁。autocommit 模式下为安全 no-op。"""
        try:
            if hasattr(self._db, "conn") and self._db.conn:
                self._db.conn.commit()
        except Exception:
            pass

    def _exec(self, sql: str, params=None): return self._db.execute(sql, params or [])

    def create_result(self, result: PackageValidationResult) -> PackageValidationResult:
        self._exec("""INSERT INTO package_validation_results (
            validation_id, submission_id, tenant_id, requested_by, status, source_type,
            package_url, repository_url, manifest_name, manifest_version,
            checks_json, warnings_json, errors_json, blockers_json,
            package_metadata_json, review_recommendation,
            no_download_performed, no_execution_performed, no_network_performed,
            metadata_json, created_at, completed_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", [
            result.validation_id, result.submission_id, result.tenant_id, result.requested_by,
            result.status, result.source_type, result.package_url, result.repository_url,
            result.manifest_name, result.manifest_version,
            json.dumps([c.to_dict() for c in result.checks], ensure_ascii=False),
            json.dumps(result.warnings, ensure_ascii=False),
            json.dumps(result.errors, ensure_ascii=False),
            json.dumps(result.blockers, ensure_ascii=False),
            json.dumps(result.package_metadata, ensure_ascii=False),
            result.review_recommendation,
            int(result.no_download_performed), int(result.no_execution_performed), int(result.no_network_performed),
            json.dumps(result.metadata, ensure_ascii=False),
            result.created_at.isoformat() if result.created_at else datetime.now(timezone.utc).isoformat(),
            result.completed_at.isoformat() if result.completed_at else datetime.now(timezone.utc).isoformat(),
        ])
        return result

    def get_result(self, validation_id: str) -> PackageValidationResult | None:
        row = next(self._exec("SELECT * FROM package_validation_results WHERE validation_id=?", [validation_id]), None)
        return self._row_to_result(dict(row)) if row else None

    def get_latest_by_submission(self, submission_id: str) -> PackageValidationResult | None:
        row = next(self._exec(
            # created_at 相同（同一微秒）时按 rowid 递增序取最新，保证确定性
            "SELECT * FROM package_validation_results WHERE submission_id=? ORDER BY created_at DESC, rowid DESC LIMIT 1",
            [submission_id]), None)
        return self._row_to_result(dict(row)) if row else None

    def list_results(self, *, submission_id="", tenant_id="", status="") -> list[PackageValidationResult]:
        sql, p = "SELECT * FROM package_validation_results WHERE 1=1", []
        if submission_id: sql += " AND submission_id=?"; p.append(submission_id)
        if tenant_id: sql += " AND tenant_id=?"; p.append(tenant_id)
        if status: sql += " AND status=?"; p.append(status)
        return [self._row_to_result(dict(r)) for r in self._exec(sql + " ORDER BY created_at DESC", p)]

    def count_results(self, *, submission_id="", tenant_id="", status="") -> int:
        return len(self.list_results(submission_id=submission_id, tenant_id=tenant_id, status=status))

    @staticmethod
    def _row_to_result(row: dict) -> PackageValidationResult:
        from datetime import datetime, timezone
        checks = [PackageValidationCheck.from_dict(c) for c in json.loads(row.get("checks_json", "[]"))]
        return PackageValidationResult(
            validation_id=row["validation_id"], submission_id=row["submission_id"],
            tenant_id=row["tenant_id"], requested_by=row["requested_by"],
            status=row.get("status", "not_validated"), source_type=row.get("source_type", "none"),
            package_url=row.get("package_url"), repository_url=row.get("repository_url"),
            manifest_name=row.get("manifest_name", ""), manifest_version=row.get("manifest_version", ""),
            checks=checks,
            warnings=json.loads(row.get("warnings_json", "[]")),
            errors=json.loads(row.get("errors_json", "[]")),
            blockers=json.loads(row.get("blockers_json", "[]")),
            package_metadata=json.loads(row.get("package_metadata_json", "{}")),
            review_recommendation=row.get("review_recommendation", ""),
            no_download_performed=bool(row.get("no_download_performed", 1)),
            no_execution_performed=bool(row.get("no_execution_performed", 1)),
            no_network_performed=bool(row.get("no_network_performed", 1)),
            created_at=_safe_dt(row.get("created_at")),
            completed_at=_safe_dt(row.get("completed_at"), none_ok=True),
            metadata=json.loads(row.get("metadata_json", "{}")),
        )
