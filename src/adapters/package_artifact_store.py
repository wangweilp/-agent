"""SQLite Package Artifact Store — 实现 PackageArtifactStore 协议。

Step 24-B:
- 3 张表：package_artifacts, package_quarantine_records, package_artifact_audit_events
- 状态变更自动生成 audit event
- quarantine 状态变更同步 artifact.quarantine_status
- 不下载 / 不执行 / 不联网
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from src.adapters.config import Settings
from src.adapters.sqlite_connection import create_sqlite_db, execute_with_retry
from src.open_platform.package_artifact import (
    ArtifactAuditEventType,
    ArtifactRiskLevel,
    ArtifactStatus,
    QuarantineStatus,
    VerificationStatus,
    PackageArtifact,
    PackageArtifactAlreadyExistsError,
    PackageArtifactAuditEvent,
    PackageArtifactNotFoundError,
    PackageArtifactStateError,
    PackageQuarantineNotFoundError,
    PackageQuarantineRecord,
)

logger = logging.getLogger(__name__)

_PA_SCHEMA = """
CREATE TABLE IF NOT EXISTS package_artifacts (
    artifact_id TEXT PRIMARY KEY,
    submission_id TEXT NOT NULL,
    developer_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    marketplace_agent_id TEXT,
    source_type TEXT NOT NULL DEFAULT 'unknown',
    package_url TEXT,
    repository_url TEXT,
    package_name TEXT,
    package_version TEXT,
    checksum_algorithm TEXT,
    checksum_value TEXT,
    signature_algorithm TEXT,
    signature_value TEXT,
    signing_key_id TEXT,
    declared_size_bytes INTEGER,
    content_type TEXT,
    artifact_status TEXT NOT NULL DEFAULT 'declared',
    verification_status TEXT NOT NULL DEFAULT 'metadata_only',
    risk_level TEXT NOT NULL DEFAULT 'unknown',
    quarantine_status TEXT NOT NULL DEFAULT 'not_quarantined',
    package_metadata_json TEXT NOT NULL DEFAULT '{}',
    validation_id TEXT,
    created_by TEXT,
    updated_by TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_pa_submission
    ON package_artifacts(submission_id);
CREATE INDEX IF NOT EXISTS idx_pa_tenant ON package_artifacts(tenant_id);
CREATE INDEX IF NOT EXISTS idx_pa_developer ON package_artifacts(developer_id);
CREATE INDEX IF NOT EXISTS idx_pa_mkt_agent ON package_artifacts(marketplace_agent_id);
CREATE INDEX IF NOT EXISTS idx_pa_status ON package_artifacts(artifact_status);
CREATE INDEX IF NOT EXISTS idx_pa_verification_status ON package_artifacts(verification_status);
CREATE INDEX IF NOT EXISTS idx_pa_quarantine_status ON package_artifacts(quarantine_status);
CREATE INDEX IF NOT EXISTS idx_pa_created_at ON package_artifacts(created_at);

CREATE TABLE IF NOT EXISTS package_quarantine_records (
    quarantine_id TEXT PRIMARY KEY,
    artifact_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    submission_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'quarantined',
    reason TEXT NOT NULL DEFAULT '',
    risk_level TEXT NOT NULL DEFAULT 'unknown',
    policy_snapshot_json TEXT NOT NULL DEFAULT '{}',
    validation_summary_json TEXT NOT NULL DEFAULT '{}',
    created_by TEXT,
    released_by TEXT,
    rejected_by TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    released_at TEXT,
    rejected_at TEXT,
    expires_at TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_pq_artifact ON package_quarantine_records(artifact_id);
CREATE INDEX IF NOT EXISTS idx_pq_tenant ON package_quarantine_records(tenant_id);
CREATE INDEX IF NOT EXISTS idx_pq_status ON package_quarantine_records(status);
CREATE INDEX IF NOT EXISTS idx_pq_created_at ON package_quarantine_records(created_at);

CREATE TABLE IF NOT EXISTS package_artifact_audit_events (
    event_id TEXT PRIMARY KEY,
    artifact_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    actor_id TEXT,
    message TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_pae_artifact ON package_artifact_audit_events(artifact_id);
CREATE INDEX IF NOT EXISTS idx_pae_tenant ON package_artifact_audit_events(tenant_id);
CREATE INDEX IF NOT EXISTS idx_pae_type ON package_artifact_audit_events(event_type);
CREATE INDEX IF NOT EXISTS idx_pae_created_at ON package_artifact_audit_events(created_at);
"""


class SQLitePackageArtifactStore:
    """SQLite 实现的 PackageArtifactStore。

    遵守 manifest-first / no-download / no-execution 边界。
    """

    def __init__(self, config: Settings, db_path: str | None = None) -> None:
        path = db_path or config.sqlite_db_path
        self._db = create_sqlite_db(path)
        execute_with_retry(lambda: self._init_schema(), label="package_artifact_init_schema")

    def _init_schema(self) -> None:
        for stmt in _PA_SCHEMA.strip().split(";"):
            s = stmt.strip()
            if s:
                self._db.execute(s)
        try:
            self._db.conn.commit()
        except Exception:
            pass

    def flush(self) -> None:
        try:
            if hasattr(self._db, "conn") and self._db.conn:
                self._db.conn.commit()
        except Exception:
            pass

    def _exec(self, sql: str, params: list[Any] | None = None) -> Any:
        return self._db.execute(sql, params or [])

    # ──── Audit helper ────

    def _audit(self, artifact_id: str, tenant_id: str, event_type: str,
               actor_id: str | None = None, message: str = "",
               meta: dict[str, Any] | None = None) -> None:
        event = PackageArtifactAuditEvent(
            artifact_id=artifact_id, tenant_id=tenant_id,
            event_type=event_type, actor_id=actor_id,
            message=message, metadata=meta or {},
        )
        self.add_audit_event(event)

    # ── Artifact CRUD ──

    def create_artifact(self, artifact: PackageArtifact) -> PackageArtifact:
        existing = self.get_artifact_by_submission(artifact.submission_id)
        if existing is not None:
            raise PackageArtifactAlreadyExistsError(
                f"Artifact already exists for submission {artifact.submission_id}")
        self._exec("""INSERT INTO package_artifacts (
            artifact_id, submission_id, developer_id, tenant_id, marketplace_agent_id,
            source_type, package_url, repository_url, package_name, package_version,
            checksum_algorithm, checksum_value, signature_algorithm, signature_value,
            signing_key_id, declared_size_bytes, content_type,
            artifact_status, verification_status, risk_level, quarantine_status,
            package_metadata_json, validation_id,
            created_by, updated_by, created_at, updated_at, metadata_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", [
            artifact.artifact_id, artifact.submission_id, artifact.developer_id,
            artifact.tenant_id, artifact.marketplace_agent_id,
            artifact.source_type, artifact.package_url, artifact.repository_url,
            artifact.package_name, artifact.package_version,
            artifact.checksum_algorithm, artifact.checksum_value,
            artifact.signature_algorithm, artifact.signature_value,
            artifact.signing_key_id, artifact.declared_size_bytes, artifact.content_type,
            artifact.artifact_status, artifact.verification_status,
            artifact.risk_level, artifact.quarantine_status,
            json.dumps(artifact.package_metadata, ensure_ascii=False),
            artifact.validation_id,
            artifact.created_by, artifact.updated_by,
            artifact.created_at.isoformat() if artifact.created_at else datetime.now(timezone.utc).isoformat(),
            artifact.updated_at.isoformat() if artifact.updated_at else datetime.now(timezone.utc).isoformat(),
            json.dumps(artifact.metadata, ensure_ascii=False),
        ])
        self._audit(artifact.artifact_id, artifact.tenant_id,
                    ArtifactAuditEventType.CREATED, artifact.created_by,
                    f"Artifact created for submission {artifact.submission_id}")
        return artifact

    def get_artifact(self, artifact_id: str) -> PackageArtifact | None:
        row = next(self._exec(
            "SELECT * FROM package_artifacts WHERE artifact_id=?", [artifact_id]), None)
        return self._row_to_artifact(dict(row)) if row else None

    def get_artifact_by_submission(self, submission_id: str) -> PackageArtifact | None:
        row = next(self._exec(
            "SELECT * FROM package_artifacts WHERE submission_id=?", [submission_id]), None)
        return self._row_to_artifact(dict(row)) if row else None

    def list_artifacts(
        self, *,
        tenant_id: str = "", developer_id: str = "",
        submission_id: str = "", status: str = "",
        verification_status: str = "", quarantine_status: str = "",
    ) -> list[PackageArtifact]:
        sql = "SELECT * FROM package_artifacts WHERE 1=1"
        params: list[Any] = []
        if tenant_id:
            sql += " AND tenant_id=?"; params.append(tenant_id)
        if developer_id:
            sql += " AND developer_id=?"; params.append(developer_id)
        if submission_id:
            sql += " AND submission_id=?"; params.append(submission_id)
        if status:
            sql += " AND artifact_status=?"; params.append(status)
        if verification_status:
            sql += " AND verification_status=?"; params.append(verification_status)
        if quarantine_status:
            sql += " AND quarantine_status=?"; params.append(quarantine_status)
        sql += " ORDER BY created_at DESC"
        return [self._row_to_artifact(dict(r)) for r in self._exec(sql, params)]

    def update_artifact(self, artifact: PackageArtifact) -> PackageArtifact:
        existing = self.get_artifact(artifact.artifact_id)
        if existing is None:
            raise PackageArtifactNotFoundError(f"Artifact not found: {artifact.artifact_id}")
        artifact.updated_at = datetime.now(timezone.utc)
        self._exec("""UPDATE package_artifacts SET
            marketplace_agent_id=?, package_url=?, repository_url=?,
            package_name=?, package_version=?,
            checksum_algorithm=?, checksum_value=?,
            signature_algorithm=?, signature_value=?, signing_key_id=?,
            declared_size_bytes=?, content_type=?,
            artifact_status=?, verification_status=?, risk_level=?, quarantine_status=?,
            package_metadata_json=?, validation_id=?,
            updated_by=?, updated_at=?, metadata_json=?
            WHERE artifact_id=?""", [
            artifact.marketplace_agent_id, artifact.package_url, artifact.repository_url,
            artifact.package_name, artifact.package_version,
            artifact.checksum_algorithm, artifact.checksum_value,
            artifact.signature_algorithm, artifact.signature_value, artifact.signing_key_id,
            artifact.declared_size_bytes, artifact.content_type,
            artifact.artifact_status, artifact.verification_status,
            artifact.risk_level, artifact.quarantine_status,
            json.dumps(artifact.package_metadata, ensure_ascii=False),
            artifact.validation_id,
            artifact.updated_by,
            artifact.updated_at.isoformat() if artifact.updated_at else datetime.now(timezone.utc).isoformat(),
            json.dumps(artifact.metadata, ensure_ascii=False),
            artifact.artifact_id,
        ])
        return artifact

    def set_artifact_status(
        self, artifact_id: str, status: str,
        actor_id: str | None = None, reason: str | None = None,
    ) -> PackageArtifact:
        artifact = self.get_artifact(artifact_id)
        if artifact is None:
            raise PackageArtifactNotFoundError(f"Artifact not found: {artifact_id}")
        old_status = artifact.artifact_status
        artifact.artifact_status = status
        artifact.updated_at = datetime.now(timezone.utc)
        artifact.updated_by = actor_id
        self.update_artifact(artifact)
        self._audit(artifact_id, artifact.tenant_id,
                    ArtifactAuditEventType.METADATA_UPDATED, actor_id,
                    f"Status changed: {old_status} -> {status}" + (f" (reason: {reason})" if reason else ""),
                    {"old_status": old_status, "new_status": status, "reason": reason})
        return artifact

    def set_verification_status(
        self, artifact_id: str, verification_status: str,
        actor_id: str | None = None, reason: str | None = None,
    ) -> PackageArtifact:
        artifact = self.get_artifact(artifact_id)
        if artifact is None:
            raise PackageArtifactNotFoundError(f"Artifact not found: {artifact_id}")
        old_vs = artifact.verification_status
        artifact.verification_status = verification_status
        artifact.updated_at = datetime.now(timezone.utc)
        artifact.updated_by = actor_id
        self.update_artifact(artifact)
        self._audit(artifact_id, artifact.tenant_id,
                    ArtifactAuditEventType.VERIFICATION_STATUS_CHANGED, actor_id,
                    f"Verification status changed: {old_vs} -> {verification_status}"
                    + (f" (reason: {reason})" if reason else ""),
                    {"old_verification_status": old_vs, "new_verification_status": verification_status, "reason": reason})
        return artifact

    def set_risk_level(
        self, artifact_id: str, risk_level: str,
        actor_id: str | None = None, reason: str | None = None,
    ) -> PackageArtifact:
        artifact = self.get_artifact(artifact_id)
        if artifact is None:
            raise PackageArtifactNotFoundError(f"Artifact not found: {artifact_id}")
        old_rl = artifact.risk_level
        artifact.risk_level = risk_level
        artifact.updated_at = datetime.now(timezone.utc)
        artifact.updated_by = actor_id
        self.update_artifact(artifact)
        self._audit(artifact_id, artifact.tenant_id,
                    ArtifactAuditEventType.RISK_LEVEL_CHANGED, actor_id,
                    f"Risk level changed: {old_rl} -> {risk_level}"
                    + (f" (reason: {reason})" if reason else ""),
                    {"old_risk_level": old_rl, "new_risk_level": risk_level, "reason": reason})
        return artifact

    # ── Quarantine CRUD ──

    def create_quarantine_record(self, record: PackageQuarantineRecord) -> PackageQuarantineRecord:
        self._exec("""INSERT INTO package_quarantine_records (
            quarantine_id, artifact_id, tenant_id, submission_id,
            status, reason, risk_level,
            policy_snapshot_json, validation_summary_json,
            created_by, released_by, rejected_by,
            created_at, updated_at, released_at, rejected_at, expires_at,
            metadata_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", [
            record.quarantine_id, record.artifact_id, record.tenant_id,
            record.submission_id,
            record.status, record.reason, record.risk_level,
            json.dumps(record.policy_snapshot, ensure_ascii=False),
            json.dumps(record.validation_summary, ensure_ascii=False),
            record.created_by, record.released_by, record.rejected_by,
            record.created_at.isoformat() if record.created_at else datetime.now(timezone.utc).isoformat(),
            record.updated_at.isoformat() if record.updated_at else datetime.now(timezone.utc).isoformat(),
            record.released_at.isoformat() if record.released_at else None,
            record.rejected_at.isoformat() if record.rejected_at else None,
            record.expires_at.isoformat() if record.expires_at else None,
            json.dumps(record.metadata, ensure_ascii=False),
        ])
        # 同步 artifact.quarantine_status
        self._sync_artifact_quarantine_status(record.artifact_id, record.status, record.created_by)
        self._audit(record.artifact_id, record.tenant_id,
                    ArtifactAuditEventType.QUARANTINED, record.created_by,
                    f"Quarantine record created: {record.quarantine_id} (status={record.status})")
        return record

    def get_quarantine_record(self, quarantine_id: str) -> PackageQuarantineRecord | None:
        row = next(self._exec(
            "SELECT * FROM package_quarantine_records WHERE quarantine_id=?", [quarantine_id]), None)
        return self._row_to_quarantine(dict(row)) if row else None

    def get_latest_quarantine_for_artifact(self, artifact_id: str) -> PackageQuarantineRecord | None:
        row = next(self._exec(
            "SELECT * FROM package_quarantine_records WHERE artifact_id=? ORDER BY created_at DESC LIMIT 1",
            [artifact_id]), None)
        return self._row_to_quarantine(dict(row)) if row else None

    def list_quarantine_records(
        self, *, tenant_id: str = "", artifact_id: str = "", status: str = "",
    ) -> list[PackageQuarantineRecord]:
        sql = "SELECT * FROM package_quarantine_records WHERE 1=1"
        params: list[Any] = []
        if tenant_id:
            sql += " AND tenant_id=?"; params.append(tenant_id)
        if artifact_id:
            sql += " AND artifact_id=?"; params.append(artifact_id)
        if status:
            sql += " AND status=?"; params.append(status)
        sql += " ORDER BY created_at DESC"
        return [self._row_to_quarantine(dict(r)) for r in self._exec(sql, params)]

    def set_quarantine_status(
        self, quarantine_id: str, status: str,
        actor_id: str | None = None, reason: str | None = None,
    ) -> PackageQuarantineRecord:
        record = self.get_quarantine_record(quarantine_id)
        if record is None:
            raise PackageQuarantineNotFoundError(f"Quarantine record not found: {quarantine_id}")
        old_status = record.status
        record.status = status
        record.updated_at = datetime.now(timezone.utc)
        now = datetime.now(timezone.utc)
        if status == QuarantineStatus.RELEASED:
            record.released_at = now
            record.released_by = actor_id
        elif status == QuarantineStatus.REJECTED:
            record.rejected_at = now
            record.rejected_by = actor_id
        self._exec("""UPDATE package_quarantine_records SET
            status=?, reason=?, risk_level=?,
            released_by=?, rejected_by=?,
            updated_at=?, released_at=?, rejected_at=?
            WHERE quarantine_id=?""", [
            record.status, record.reason or (reason or ""), record.risk_level,
            record.released_by, record.rejected_by,
            record.updated_at.isoformat() if record.updated_at else datetime.now(timezone.utc).isoformat(),
            record.released_at.isoformat() if record.released_at else None,
            record.rejected_at.isoformat() if record.rejected_at else None,
            record.quarantine_id,
        ])
        # 同步 artifact.quarantine_status
        self._sync_artifact_quarantine_status(record.artifact_id, status, actor_id)
        self._audit(record.artifact_id, record.tenant_id,
                    ArtifactAuditEventType.RELEASED if status == QuarantineStatus.RELEASED
                    else ArtifactAuditEventType.REJECTED if status == QuarantineStatus.REJECTED
                    else ArtifactAuditEventType.METADATA_UPDATED,
                    actor_id,
                    f"Quarantine status changed: {old_status} -> {status}"
                    + (f" (reason: {reason})" if reason else ""))
        return record

    def _sync_artifact_quarantine_status(
        self, artifact_id: str, q_status: str, actor_id: str | None = None,
    ) -> None:
        """同步 artifact.quarantine_status 到与 quarantine record 一致的映射。"""
        mapping = {
            QuarantineStatus.QUARANTINED: QuarantineStatus.QUARANTINED,
            QuarantineStatus.REVIEW_REQUIRED: QuarantineStatus.REVIEW_REQUIRED,
            QuarantineStatus.RELEASED: QuarantineStatus.RELEASED,
            QuarantineStatus.REJECTED: QuarantineStatus.REJECTED,
            QuarantineStatus.EXPIRED: QuarantineStatus.EXPIRED,
        }
        new_artifact_qs = mapping.get(q_status, QuarantineStatus.NOT_QUARANTINED)
        self._exec("UPDATE package_artifacts SET quarantine_status=?, updated_at=? WHERE artifact_id=?",
                   [new_artifact_qs, datetime.now(timezone.utc).isoformat(), artifact_id])

    # ── Audit ──

    def add_audit_event(self, event: PackageArtifactAuditEvent) -> PackageArtifactAuditEvent:
        self._exec("""INSERT INTO package_artifact_audit_events (
            event_id, artifact_id, tenant_id, event_type, actor_id, message,
            metadata_json, created_at
        ) VALUES (?,?,?,?,?,?,?,?)""", [
            event.event_id, event.artifact_id, event.tenant_id,
            event.event_type, event.actor_id, event.message,
            json.dumps(event.metadata, ensure_ascii=False),
            event.created_at.isoformat() if event.created_at else datetime.now(timezone.utc).isoformat(),
        ])
        return event

    def list_audit_events(self, artifact_id: str) -> list[PackageArtifactAuditEvent]:
        rows = self._exec(
            "SELECT * FROM package_artifact_audit_events WHERE artifact_id=? ORDER BY created_at ASC",
            [artifact_id])
        return [self._row_to_audit_event(dict(r)) for r in rows]

    # ── Counts ──

    def count_artifacts(
        self, *, tenant_id: str = "", status: str = "", quarantine_status: str = "",
    ) -> int:
        sql = "SELECT COUNT(*) as cnt FROM package_artifacts WHERE 1=1"
        params: list[Any] = []
        if tenant_id:
            sql += " AND tenant_id=?"; params.append(tenant_id)
        if status:
            sql += " AND artifact_status=?"; params.append(status)
        if quarantine_status:
            sql += " AND quarantine_status=?"; params.append(quarantine_status)
        row = next(self._exec(sql, params), None)
        return row["cnt"] if row else 0

    # ── Row converters ──

    @staticmethod
    def _row_to_artifact(row: dict) -> PackageArtifact:
        return PackageArtifact(
            artifact_id=row["artifact_id"],
            submission_id=row["submission_id"],
            developer_id=row["developer_id"],
            tenant_id=row["tenant_id"],
            marketplace_agent_id=row.get("marketplace_agent_id"),
            source_type=row.get("source_type", "unknown"),
            package_url=row.get("package_url"),
            repository_url=row.get("repository_url"),
            package_name=row.get("package_name"),
            package_version=row.get("package_version"),
            checksum_algorithm=row.get("checksum_algorithm"),
            checksum_value=row.get("checksum_value"),
            signature_algorithm=row.get("signature_algorithm"),
            signature_value=row.get("signature_value"),
            signing_key_id=row.get("signing_key_id"),
            declared_size_bytes=row.get("declared_size_bytes"),
            content_type=row.get("content_type"),
            artifact_status=row.get("artifact_status", "declared"),
            verification_status=row.get("verification_status", "metadata_only"),
            risk_level=row.get("risk_level", "unknown"),
            quarantine_status=row.get("quarantine_status", "not_quarantined"),
            package_metadata=json.loads(row.get("package_metadata_json", "{}")),
            validation_id=row.get("validation_id"),
            created_by=row.get("created_by"),
            updated_by=row.get("updated_by"),
            created_at=_safe_dt(row.get("created_at")),
            updated_at=_safe_dt(row.get("updated_at")),
            metadata=json.loads(row.get("metadata_json", "{}")),
        )

    @staticmethod
    def _row_to_quarantine(row: dict) -> PackageQuarantineRecord:
        return PackageQuarantineRecord(
            quarantine_id=row["quarantine_id"],
            artifact_id=row["artifact_id"],
            tenant_id=row["tenant_id"],
            submission_id=row["submission_id"],
            status=row.get("status", "quarantined"),
            reason=row.get("reason", ""),
            risk_level=row.get("risk_level", "unknown"),
            policy_snapshot=json.loads(row.get("policy_snapshot_json", "{}")),
            validation_summary=json.loads(row.get("validation_summary_json", "{}")),
            created_by=row.get("created_by"),
            released_by=row.get("released_by"),
            rejected_by=row.get("rejected_by"),
            created_at=_safe_dt(row.get("created_at")),
            updated_at=_safe_dt(row.get("updated_at")),
            released_at=_safe_dt(row.get("released_at"), none_ok=True),
            rejected_at=_safe_dt(row.get("rejected_at"), none_ok=True),
            expires_at=_safe_dt(row.get("expires_at"), none_ok=True),
            metadata=json.loads(row.get("metadata_json", "{}")),
        )

    @staticmethod
    def _row_to_audit_event(row: dict) -> PackageArtifactAuditEvent:
        return PackageArtifactAuditEvent(
            event_id=row["event_id"],
            artifact_id=row["artifact_id"],
            tenant_id=row["tenant_id"],
            event_type=row.get("event_type", ""),
            actor_id=row.get("actor_id"),
            message=row.get("message", ""),
            metadata=json.loads(row.get("metadata_json", "{}")),
            created_at=_safe_dt(row.get("created_at")),
        )


def _safe_dt(raw: str | None, none_ok: bool = False) -> datetime | None:
    if not raw:
        return None if none_ok else datetime.now(timezone.utc)
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None if none_ok else datetime.now(timezone.utc)
