"""SQLite Package Verification Store — 实现 PackageVerificationStore 协议。

Step 24-C:
- package_verification_runs 表
- checks JSON 存储
- latest run by artifact
- 不物理删除 / 不下载 / 不联网 / 不执行
"""

from __future__ import annotations

import json, logging
from datetime import datetime, timezone
from typing import Any

from src.adapters.config import Settings
from src.adapters.sqlite_connection import create_sqlite_db, execute_with_retry
from src.open_platform.package_verification import (
    PackageVerificationRun, VerificationCheck, _safe_dt,
)

logger = logging.getLogger(__name__)

_PV_SCHEMA = """
CREATE TABLE IF NOT EXISTS package_verification_runs (
    verification_id TEXT PRIMARY KEY,
    artifact_id TEXT NOT NULL,
    submission_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    developer_id TEXT NOT NULL,
    requested_by TEXT,
    run_status TEXT NOT NULL DEFAULT 'pending',
    checksum_algorithm TEXT,
    expected_checksum TEXT,
    actual_checksum TEXT,
    signature_algorithm TEXT,
    signature_value_present INTEGER NOT NULL DEFAULT 0,
    signature_verified INTEGER NOT NULL DEFAULT 0,
    signature_mode TEXT NOT NULL DEFAULT 'metadata_only',
    checks_json TEXT NOT NULL DEFAULT '[]',
    warnings_count INTEGER NOT NULL DEFAULT 0,
    errors_count INTEGER NOT NULL DEFAULT 0,
    blockers_count INTEGER NOT NULL DEFAULT 0,
    no_network_used INTEGER NOT NULL DEFAULT 1,
    no_execution_used INTEGER NOT NULL DEFAULT 1,
    no_download_used INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_pkv_artifact ON package_verification_runs(artifact_id);
CREATE INDEX IF NOT EXISTS idx_pkv_tenant ON package_verification_runs(tenant_id);
CREATE INDEX IF NOT EXISTS idx_pkv_status ON package_verification_runs(run_status);
CREATE INDEX IF NOT EXISTS idx_pkv_created_at ON package_verification_runs(created_at);
CREATE INDEX IF NOT EXISTS idx_pkv_submission ON package_verification_runs(submission_id);
"""


class SQLitePackageVerificationStore:
    def __init__(self, config: Settings, db_path: str | None = None):
        path = db_path or config.sqlite_db_path
        self._db = create_sqlite_db(path)
        execute_with_retry(lambda: self._init_schema(), label="pkg_verification_init_schema")

    def _init_schema(self):
        for stmt in _PV_SCHEMA.strip().split(";"):
            s = stmt.strip()
            if s: self._db.execute(s)
        try: self._db.conn.commit()
        except Exception: pass

    def flush(self) -> None:
        try:
            if hasattr(self._db, "conn") and self._db.conn:
                self._db.conn.commit()
        except Exception: pass

    def _exec(self, sql: str, params=None): return self._db.execute(sql, params or [])

    # ── CRUD ──

    def create_run(self, run: PackageVerificationRun) -> PackageVerificationRun:
        self._exec("""INSERT INTO package_verification_runs (
            verification_id, artifact_id, submission_id, tenant_id, developer_id,
            requested_by, run_status, checksum_algorithm, expected_checksum, actual_checksum,
            signature_algorithm, signature_value_present, signature_verified, signature_mode,
            checks_json, warnings_count, errors_count, blockers_count,
            no_network_used, no_execution_used, no_download_used,
            created_at, completed_at, metadata_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", [
            run.verification_id, run.artifact_id, run.submission_id, run.tenant_id,
            run.developer_id, run.requested_by, run.run_status,
            run.checksum_algorithm, run.expected_checksum, run.actual_checksum,
            run.signature_algorithm, int(run.signature_value_present), int(run.signature_verified),
            run.signature_mode,
            json.dumps([c.to_dict() for c in run.checks], ensure_ascii=False),
            run.warnings_count, run.errors_count, run.blockers_count,
            int(run.no_network_used), int(run.no_execution_used), int(run.no_download_used),
            run.created_at.isoformat() if run.created_at else datetime.now(timezone.utc).isoformat(),
            run.completed_at.isoformat() if run.completed_at else None,
            json.dumps(run.metadata, ensure_ascii=False),
        ])
        return run

    def get_run(self, verification_id: str) -> PackageVerificationRun | None:
        row = next(self._exec(
            "SELECT * FROM package_verification_runs WHERE verification_id=?", [verification_id]), None)
        return self._row_to_run(dict(row)) if row else None

    def get_latest_run_for_artifact(self, artifact_id: str) -> PackageVerificationRun | None:
        row = next(self._exec(
            # created_at 相同（同一微秒）时按 rowid 取最新，保证确定性
            "SELECT * FROM package_verification_runs WHERE artifact_id=? ORDER BY created_at DESC, rowid DESC LIMIT 1",
            [artifact_id]), None)
        return self._row_to_run(dict(row)) if row else None

    def list_runs(self, *, tenant_id="", artifact_id="", status="") -> list[PackageVerificationRun]:
        sql, p = "SELECT * FROM package_verification_runs WHERE 1=1", []
        if tenant_id: sql += " AND tenant_id=?"; p.append(tenant_id)
        if artifact_id: sql += " AND artifact_id=?"; p.append(artifact_id)
        if status: sql += " AND run_status=?"; p.append(status)
        return [self._row_to_run(dict(r)) for r in self._exec(sql + " ORDER BY created_at DESC", p)]

    def update_run(self, run: PackageVerificationRun) -> PackageVerificationRun:
        self._exec("""UPDATE package_verification_runs SET
            run_status=?, checksum_algorithm=?, expected_checksum=?, actual_checksum=?,
            signature_algorithm=?, signature_value_present=?, signature_verified=?, signature_mode=?,
            checks_json=?, warnings_count=?, errors_count=?, blockers_count=?,
            completed_at=?, metadata_json=?
            WHERE verification_id=?""", [
            run.run_status, run.checksum_algorithm, run.expected_checksum, run.actual_checksum,
            run.signature_algorithm, int(run.signature_value_present), int(run.signature_verified),
            run.signature_mode,
            json.dumps([c.to_dict() for c in run.checks], ensure_ascii=False),
            run.warnings_count, run.errors_count, run.blockers_count,
            run.completed_at.isoformat() if run.completed_at else None,
            json.dumps(run.metadata, ensure_ascii=False),
            run.verification_id,
        ])
        return run

    def count_runs(self, *, tenant_id="", status="") -> int:
        sql, p = "SELECT COUNT(*) as cnt FROM package_verification_runs WHERE 1=1", []
        if tenant_id: sql += " AND tenant_id=?"; p.append(tenant_id)
        if status: sql += " AND run_status=?"; p.append(status)
        row = next(self._exec(sql, p), None)
        return row["cnt"] if row else 0

    @staticmethod
    def _row_to_run(row: dict) -> PackageVerificationRun:
        checks = [VerificationCheck.from_dict(c) for c in json.loads(row.get("checks_json", "[]"))]
        return PackageVerificationRun(
            verification_id=row["verification_id"], artifact_id=row["artifact_id"],
            submission_id=row["submission_id"], tenant_id=row["tenant_id"],
            developer_id=row["developer_id"], requested_by=row.get("requested_by"),
            run_status=row.get("run_status", "pending"),
            checksum_algorithm=row.get("checksum_algorithm"),
            expected_checksum=row.get("expected_checksum"), actual_checksum=row.get("actual_checksum"),
            signature_algorithm=row.get("signature_algorithm"),
            signature_value_present=bool(row.get("signature_value_present", 0)),
            signature_verified=bool(row.get("signature_verified", 0)),
            signature_mode=row.get("signature_mode", "metadata_only"),
            checks=checks, warnings_count=int(row.get("warnings_count", 0)),
            errors_count=int(row.get("errors_count", 0)), blockers_count=int(row.get("blockers_count", 0)),
            no_network_used=bool(row.get("no_network_used", 1)),
            no_execution_used=bool(row.get("no_execution_used", 1)),
            no_download_used=bool(row.get("no_download_used", 1)),
            created_at=_safe_dt(row.get("created_at")), completed_at=_safe_dt(row.get("completed_at"), none_ok=True),
            metadata=json.loads(row.get("metadata_json", "{}")),
        )
