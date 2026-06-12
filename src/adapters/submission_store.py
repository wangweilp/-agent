"""SQLite Submission Store — 实现 SubmissionStore 协议。"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from src.adapters.config import Settings
from src.adapters.sqlite_connection import create_sqlite_db, execute_with_retry
from src.open_platform.submission import (
    AgentManifest,
    AgentReviewRecord,
    AgentSubmission,
    ManifestValidationError,
    ManifestValidationResult,
    SubmissionNotFoundError,
    SubmissionPermissionError,
    SubmissionStateError,
    SubmissionStatus,
)

logger = logging.getLogger(__name__)

_SUBMISSION_SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_submissions (
    submission_id TEXT PRIMARY KEY,
    developer_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    marketplace_agent_id TEXT,
    agent_manifest_json TEXT NOT NULL,
    package_url TEXT,
    source_type TEXT NOT NULL DEFAULT 'manifest',
    status TEXT NOT NULL DEFAULT 'draft',
    review_notes TEXT,
    submitted_at TEXT,
    reviewed_at TEXT,
    reviewed_by TEXT,
    published_at TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_asub_developer_id ON agent_submissions(developer_id);
CREATE INDEX IF NOT EXISTS idx_asub_tenant_id ON agent_submissions(tenant_id);
CREATE INDEX IF NOT EXISTS idx_asub_status ON agent_submissions(status);
CREATE INDEX IF NOT EXISTS idx_asub_mkp_id ON agent_submissions(marketplace_agent_id);

CREATE TABLE IF NOT EXISTS agent_review_records (
    review_id TEXT PRIMARY KEY,
    submission_id TEXT NOT NULL,
    reviewer_id TEXT NOT NULL,
    decision TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    checklist_json TEXT NOT NULL DEFAULT '{}',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_arv_submission_id ON agent_review_records(submission_id);
CREATE INDEX IF NOT EXISTS idx_arv_reviewer_id ON agent_review_records(reviewer_id);
CREATE INDEX IF NOT EXISTS idx_arv_decision ON agent_review_records(decision);
"""


class SQLiteSubmissionStore:
    def __init__(self, config: Settings, db_path: str | None = None) -> None:
        path = db_path or config.sqlite_db_path
        self._db = create_sqlite_db(path)
        execute_with_retry(lambda: self._init_schema(), label="submission_init_schema")

    def _init_schema(self) -> None:
        for stmt in _SUBMISSION_SCHEMA.strip().split(";"):
            s = stmt.strip()
            if s:
                self._db.execute(s)
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

    def _exec(self, sql: str, params: list[Any] | None = None) -> Any:
        return self._db.execute(sql, params or [])

    # ── Submission ──

    def create_submission(self, submission: AgentSubmission) -> AgentSubmission:
        manifest_json = json.dumps(
            submission.agent_manifest.to_dict() if submission.agent_manifest else {},
            ensure_ascii=False,
        )
        self._exec("""INSERT INTO agent_submissions (
            submission_id, developer_id, tenant_id, marketplace_agent_id,
            agent_manifest_json, package_url, source_type, status,
            review_notes, submitted_at, reviewed_at, reviewed_by, published_at, metadata_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", [
            submission.submission_id, submission.developer_id, submission.tenant_id,
            submission.marketplace_agent_id,
            manifest_json, submission.package_url, submission.source_type,
            submission.status, submission.review_notes,
            submission.submitted_at.isoformat() if submission.submitted_at else None,
            submission.reviewed_at.isoformat() if submission.reviewed_at else None,
            submission.reviewed_by,
            submission.published_at.isoformat() if submission.published_at else None,
            json.dumps(submission.metadata, ensure_ascii=False),
        ])
        return submission

    def get_submission(self, submission_id: str) -> AgentSubmission | None:
        row = next(self._exec("SELECT * FROM agent_submissions WHERE submission_id=?", [submission_id]), None)
        return self._sub(dict(row)) if row else None

    def list_submissions(
        self, *, developer_id: str = "", tenant_id: str = "", status: str = "",
    ) -> list[AgentSubmission]:
        sql = "SELECT * FROM agent_submissions WHERE 1=1"
        p: list[Any] = []
        if developer_id:
            sql += " AND developer_id=?"
            p.append(developer_id)
        if tenant_id:
            sql += " AND tenant_id=?"
            p.append(tenant_id)
        if status:
            sql += " AND status=?"
            p.append(status)
        sql += " ORDER BY created_at DESC"
        return [self._sub(dict(r)) for r in self._exec(sql, p)]

    def update_submission(self, submission: AgentSubmission) -> None:
        manifest_json = json.dumps(
            submission.agent_manifest.to_dict() if submission.agent_manifest else {},
            ensure_ascii=False,
        )
        self._exec("""UPDATE agent_submissions SET
            marketplace_agent_id=?, agent_manifest_json=?, package_url=?,
            source_type=?, status=?, review_notes=?, submitted_at=?, reviewed_at=?,
            reviewed_by=?, published_at=?, metadata_json=?, updated_at=?
            WHERE submission_id=?""", [
            submission.marketplace_agent_id, manifest_json,
            submission.package_url, submission.source_type,
            submission.status, submission.review_notes,
            submission.submitted_at.isoformat() if submission.submitted_at else None,
            submission.reviewed_at.isoformat() if submission.reviewed_at else None,
            submission.reviewed_by,
            submission.published_at.isoformat() if submission.published_at else None,
            json.dumps(submission.metadata, ensure_ascii=False),
            datetime.now(timezone.utc).isoformat(), submission.submission_id,
        ])

    def update_submission_manifest(
        self, submission_id: str, developer_id: str, manifest: AgentManifest,
    ) -> None:
        sub = self.get_submission(submission_id)
        if sub is None:
            raise SubmissionNotFoundError(f"提交不存在: {submission_id}")
        if sub.developer_id != developer_id:
            raise SubmissionPermissionError("无权编辑此提交的 manifest")
        if not sub.can_edit():
            raise SubmissionStateError(f"当前状态 {sub.status} 不允许编辑 manifest")
        manifest_json = json.dumps(manifest.to_dict(), ensure_ascii=False)
        self._exec(
            "UPDATE agent_submissions SET agent_manifest_json=?, updated_at=? WHERE submission_id=? AND developer_id=?",
            [manifest_json, datetime.now(timezone.utc).isoformat(), submission_id, developer_id],
        )

    def submit_submission(self, submission_id: str, developer_id: str) -> None:
        sub = self.get_submission(submission_id)
        if sub is None:
            raise SubmissionNotFoundError(f"提交不存在: {submission_id}")
        if sub.developer_id != developer_id:
            raise SubmissionPermissionError("无权提交此 submission")
        if not sub.can_submit():
            raise SubmissionStateError(f"当前状态 {sub.status} 不允许提交")

        # 校验 manifest
        if sub.agent_manifest is None:
            raise ManifestValidationError("Manifest 不能为空")
        result = sub.agent_manifest.validate()
        if not result.valid:
            raise ManifestValidationError(
                f"Manifest 校验失败: {'; '.join(result.errors)}",
                errors=result.errors,
            )

        sub.submit()
        self.update_submission(sub)

    def withdraw_submission(self, submission_id: str, developer_id: str) -> None:
        sub = self.get_submission(submission_id)
        if sub is None:
            raise SubmissionNotFoundError(f"提交不存在: {submission_id}")
        if sub.developer_id != developer_id:
            raise SubmissionPermissionError("无权撤回此提交")
        if not sub.can_withdraw():
            raise SubmissionStateError(f"当前状态 {sub.status} 不允许撤回")
        sub.withdraw()
        self.update_submission(sub)

    def start_review(self, submission_id: str, reviewer_id: str) -> None:
        sub = self.get_submission(submission_id)
        if sub is None:
            raise SubmissionNotFoundError(f"提交不存在: {submission_id}")
        if not sub.can_review():
            raise SubmissionStateError(f"当前状态 {sub.status} 不允许开始审核")
        sub.start_review()
        self.update_submission(sub)

    def approve_submission(
        self, submission_id: str, reviewer_id: str, notes: str, checklist: dict[str, Any],
    ) -> None:
        sub = self.get_submission(submission_id)
        if sub is None:
            raise SubmissionNotFoundError(f"提交不存在: {submission_id}")
        if not sub.can_review():
            raise SubmissionStateError(f"当前状态 {sub.status} 不允许审核")
        sub.approve(reviewer_id, notes)
        self.update_submission(sub)
        self.create_review_record(AgentReviewRecord(
            submission_id=submission_id, reviewer_id=reviewer_id,
            decision="approve", notes=notes, checklist=checklist,
        ))

    def reject_submission(
        self, submission_id: str, reviewer_id: str, notes: str, checklist: dict[str, Any],
    ) -> None:
        sub = self.get_submission(submission_id)
        if sub is None:
            raise SubmissionNotFoundError(f"提交不存在: {submission_id}")
        if not sub.can_review():
            raise SubmissionStateError(f"当前状态 {sub.status} 不允许审核")
        sub.reject(reviewer_id, notes)
        self.update_submission(sub)
        self.create_review_record(AgentReviewRecord(
            submission_id=submission_id, reviewer_id=reviewer_id,
            decision="reject", notes=notes, checklist=checklist,
        ))

    def request_changes(
        self, submission_id: str, reviewer_id: str, notes: str, checklist: dict[str, Any],
    ) -> None:
        sub = self.get_submission(submission_id)
        if sub is None:
            raise SubmissionNotFoundError(f"提交不存在: {submission_id}")
        if not sub.can_review():
            raise SubmissionStateError(f"当前状态 {sub.status} 不允许审核")
        sub.request_changes(reviewer_id, notes)
        self.update_submission(sub)
        self.create_review_record(AgentReviewRecord(
            submission_id=submission_id, reviewer_id=reviewer_id,
            decision="request_changes", notes=notes, checklist=checklist,
        ))

    def publish_submission(self, submission_id: str, marketplace_agent_id: str) -> None:
        sub = self.get_submission(submission_id)
        if sub is None:
            raise SubmissionNotFoundError(f"提交不存在: {submission_id}")
        if not sub.can_publish():
            raise SubmissionStateError(f"当前状态 {sub.status} 不允许发布；需要 approved")
        sub.publish(marketplace_agent_id)
        self.update_submission(sub)

    # ── Review Records ──

    def create_review_record(self, record: AgentReviewRecord) -> AgentReviewRecord:
        self._exec("""INSERT INTO agent_review_records (
            review_id, submission_id, reviewer_id, decision, notes,
            checklist_json, metadata_json, created_at
        ) VALUES (?,?,?,?,?,?,?,?)""", [
            record.review_id, record.submission_id, record.reviewer_id,
            record.decision, record.notes,
            json.dumps(record.checklist, ensure_ascii=False),
            json.dumps(record.metadata, ensure_ascii=False),
            record.created_at.isoformat() if record.created_at else datetime.now(timezone.utc).isoformat(),
        ])
        return record

    def list_review_records(self, submission_id: str) -> list[AgentReviewRecord]:
        rows = self._exec(
            "SELECT * FROM agent_review_records WHERE submission_id=? ORDER BY created_at DESC",
            [submission_id],
        )
        return [self._rev(dict(r)) for r in rows]

    def get_latest_review_record(self, submission_id: str) -> AgentReviewRecord | None:
        records = self.list_review_records(submission_id)
        return records[0] if records else None

    # ── Validation ──

    def validate_submission_manifest(self, submission_id: str) -> ManifestValidationResult:
        sub = self.get_submission(submission_id)
        if sub is None:
            raise SubmissionNotFoundError(f"提交不存在: {submission_id}")
        if sub.agent_manifest is None:
            return ManifestValidationResult(valid=False, errors=["Manifest 不能为空"])
        return sub.agent_manifest.validate()

    # ── Converters ──

    @staticmethod
    def _sub(row: dict) -> AgentSubmission:
        manifest = None
        raw = row.get("agent_manifest_json", "{}")
        if raw:
            try:
                mdict = json.loads(raw)
                manifest = AgentManifest.from_dict(mdict)
            except (json.JSONDecodeError, TypeError):
                pass

        sa = None; ra = None; pa = None
        for field, target in [
            ("submitted_at", "sa"), ("reviewed_at", "ra"), ("published_at", "pa"),
        ]:
            v = row.get(field)
            if v:
                try:
                    dt = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
                except (ValueError, OSError):
                    continue
                if target == "sa": sa = dt
                elif target == "ra": ra = dt
                else: pa = dt

        return AgentSubmission(
            submission_id=row["submission_id"],
            developer_id=row["developer_id"],
            tenant_id=row["tenant_id"],
            marketplace_agent_id=row.get("marketplace_agent_id"),
            agent_manifest=manifest,
            package_url=row.get("package_url"),
            source_type=row.get("source_type", "manifest"),
            status=row.get("status", "draft"),
            review_notes=row.get("review_notes"),
            submitted_at=sa,
            reviewed_at=ra,
            reviewed_by=row.get("reviewed_by"),
            published_at=pa,
            metadata=json.loads(row.get("metadata_json", "{}")),
            created_at=_safe_parse_datetime(row.get("created_at")),
            updated_at=_safe_parse_datetime(row.get("updated_at")),
        )

    @staticmethod
    def _rev(row: dict) -> AgentReviewRecord:
        return AgentReviewRecord(
            review_id=row["review_id"],
            submission_id=row["submission_id"],
            reviewer_id=row["reviewer_id"],
            decision=row["decision"],
            notes=row.get("notes", ""),
            checklist=json.loads(row.get("checklist_json", "{}")),
            metadata=json.loads(row.get("metadata_json", "{}")),
            created_at=_safe_parse_datetime(row.get("created_at")),
        )


def _safe_parse_datetime(raw: str | None) -> datetime:
    if not raw:
        return datetime.now(timezone.utc)
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return datetime.now(timezone.utc)
