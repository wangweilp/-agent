"""Enterprise Compliance Adapter — SQLite 实现 ComplianceStore 协议。

管理 data_retention_policies / data_requests / compliance_scans 三张表。
"""
import json
import logging
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlite_utils import Database

from src.adapters.config import Settings
from src.core.compliance import (
    ComplianceReport,
    DataRequest,
    DataRequestStatus,
    DataRequestType,
    DataRetentionPolicy,
    RetentionPeriod,
    ArchiveAction,
    detect_sensitive,
    SensitiveMatch,
)

logger = logging.getLogger(__name__)

_COMPLIANCE_SCHEMA = """
CREATE TABLE IF NOT EXISTS data_retention_policies (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    resource_type   TEXT NOT NULL,
    retention_period TEXT NOT NULL DEFAULT '1y',
    archive_action  TEXT NOT NULL DEFAULT 'archive',
    organization_id TEXT NOT NULL DEFAULT '',
    description     TEXT DEFAULT '',
    enabled         INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_drp_org ON data_retention_policies(organization_id);

CREATE TABLE IF NOT EXISTS data_requests (
    id              TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL,
    organization_id TEXT NOT NULL,
    request_type    TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending',
    result_url      TEXT DEFAULT '',
    error_message   TEXT DEFAULT '',
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at    TEXT
);
CREATE INDEX IF NOT EXISTS idx_dr_user ON data_requests(user_id, organization_id);
CREATE INDEX IF NOT EXISTS idx_dr_status ON data_requests(status);

CREATE TABLE IF NOT EXISTS compliance_scans (
    id              TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL,
    memory_id       TEXT NOT NULL,
    entity_type     TEXT NOT NULL DEFAULT '',
    value_masked    TEXT NOT NULL DEFAULT '',
    position        INTEGER NOT NULL DEFAULT 0,
    confidence      REAL NOT NULL DEFAULT 1.0,
    scanned_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_cs_org ON compliance_scans(organization_id);
CREATE INDEX IF NOT EXISTS idx_cs_memory ON compliance_scans(memory_id);
"""


class ComplianceStoreAdapter:
    """ComplianceStore 的 SQLite 实现。"""

    def __init__(self, config: Settings, db_path: str | None = None) -> None:
        path = db_path or config.sqlite_db_path
        conn = sqlite3.connect(path, check_same_thread=False)
        self._db = Database(conn)
        self._db.conn.row_factory = sqlite3.Row
        self._write_lock = threading.Lock()
        self._init_schema()

    def _init_schema(self) -> None:
        for stmt in _COMPLIANCE_SCHEMA.strip().split(";"):
            s = stmt.strip()
            if s:
                self._db.execute(s)

    # ── Data Retention Policy ──

    def create_retention_policy(self, policy: DataRetentionPolicy) -> DataRetentionPolicy:
        with self._write_lock, self._db.conn:
            self._db.execute(
                """INSERT INTO data_retention_policies
                   (id, name, resource_type, retention_period, archive_action,
                    organization_id, description, enabled, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (policy.id, policy.name, policy.resource_type,
                 policy.retention_period.value, policy.archive_action.value,
                 policy.organization_id, policy.description,
                 int(policy.enabled), policy.created_at.isoformat(),
                 policy.updated_at.isoformat()),
            )
        return policy

    def get_retention_policy(self, policy_id: str) -> DataRetentionPolicy | None:
        row = self._db.execute(
            "SELECT * FROM data_retention_policies WHERE id = ?", (policy_id,)
        ).fetchone()
        return self._row_to_policy(dict(row)) if row else None

    def list_retention_policies(self, organization_id: str) -> list[DataRetentionPolicy]:
        rows = self._db.execute(
            """SELECT * FROM data_retention_policies
               WHERE organization_id = ? OR organization_id = ''
               ORDER BY resource_type, name""",
            (organization_id,),
        ).fetchall()
        return [self._row_to_policy(dict(r)) for r in rows]

    def update_retention_policy(self, policy: DataRetentionPolicy) -> None:
        policy.updated_at = datetime.now(timezone.utc)
        with self._write_lock, self._db.conn:
            self._db.execute(
                """UPDATE data_retention_policies
                   SET name=?, retention_period=?, archive_action=?, description=?,
                       enabled=?, updated_at=?
                   WHERE id=?""",
                (policy.name, policy.retention_period.value,
                 policy.archive_action.value, policy.description,
                 int(policy.enabled), policy.updated_at.isoformat(), policy.id),
            )

    def delete_retention_policy(self, policy_id: str) -> None:
        with self._write_lock, self._db.conn:
            self._db.execute(
                "DELETE FROM data_retention_policies WHERE id = ?", (policy_id,)
            )

    def enforce_retention(self, organization_id: str) -> dict[str, int]:
        """执行保留策略 — 对过期数据进行归档/删除/匿名化。

        返回每种操作影响的记录数。
        """
        result = {"archived": 0, "deleted": 0, "anonymized": 0}
        policies = self.list_retention_policies(organization_id)

        for policy in policies:
            if not policy.enabled:
                continue
            days = policy.retention_days()
            if days is None:
                continue  # forever = 不处理

            cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

            if policy.resource_type == "audit_log":
                count = self._enforce_audit_log_retention(
                    organization_id, cutoff, policy.archive_action,
                )
            elif policy.resource_type == "memory":
                count = self._enforce_memory_retention(
                    organization_id, cutoff, policy.archive_action,
                )
            elif policy.resource_type == "notification":
                count = self._enforce_notification_retention(
                    organization_id, cutoff, policy.archive_action,
                )
            else:
                count = 0

            if policy.archive_action == ArchiveAction.ARCHIVE:
                result["archived"] += count
            elif policy.archive_action == ArchiveAction.DELETE:
                result["deleted"] += count
            elif policy.archive_action == ArchiveAction.ANONYMIZE:
                result["anonymized"] += count

        return result

    def _enforce_audit_log_retention(self, org_id: str, cutoff: str,
                                     action: ArchiveAction) -> int:
        with self._write_lock, self._db.conn:
            if action == ArchiveAction.DELETE:
                cursor = self._db.execute(
                    "DELETE FROM audit_logs WHERE workspace_id IN "
                    "(SELECT id FROM workspaces WHERE owner_id IN "
                    "(SELECT owner_id FROM organizations WHERE id = ?))"
                    " AND timestamp < ?",
                    (org_id, cutoff),
                )
                return cursor.rowcount if cursor else 0
            # ARCHIVE/ANONYMIZE: audit_logs 不支持，直接删除
            cursor = self._db.execute(
                "DELETE FROM audit_logs WHERE timestamp < ? AND workspace_id IN "
                "(SELECT id FROM workspaces WHERE owner_id IN "
                "(SELECT owner_id FROM organizations WHERE id = ?))",
                (cutoff, org_id),
            )
            return cursor.rowcount if cursor else 0

    def _enforce_memory_retention(self, org_id: str, cutoff: str,
                                  action: ArchiveAction) -> int:
        with self._write_lock, self._db.conn:
            if action == ArchiveAction.ARCHIVE:
                cursor = self._db.execute(
                    "UPDATE notes SET status = 'archived', archived_at = ? "
                    "WHERE timestamp < ? AND status = 'active'",
                    (datetime.now(timezone.utc).isoformat(), cutoff),
                )
                return cursor.rowcount if cursor else 0
            elif action == ArchiveAction.ANONYMIZE:
                cursor = self._db.execute(
                    "UPDATE notes SET content = '[已匿名化]', summary = NULL "
                    "WHERE timestamp < ? AND status = 'active'",
                    (cutoff,),
                )
                return cursor.rowcount if cursor else 0
            else:  # DELETE
                cursor = self._db.execute(
                    "DELETE FROM notes WHERE timestamp < ? AND status = 'active'",
                    (cutoff,),
                )
                return cursor.rowcount if cursor else 0

    def _enforce_notification_retention(self, org_id: str, cutoff: str,
                                        action: ArchiveAction) -> int:
        with self._write_lock, self._db.conn:
            cursor = self._db.execute(
                "DELETE FROM notifications WHERE created_at < ?",
                (cutoff,),
            )
            return cursor.rowcount if cursor else 0

    # ── Data Requests (GDPR) ──

    def create_data_request(self, req: DataRequest) -> DataRequest:
        with self._write_lock, self._db.conn:
            self._db.execute(
                """INSERT INTO data_requests
                   (id, user_id, organization_id, request_type, status, result_url,
                    error_message, created_at, completed_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (req.id, req.user_id, req.organization_id, req.request_type.value,
                 req.status.value, req.result_url, req.error_message,
                 req.created_at.isoformat(),
                 req.completed_at.isoformat() if req.completed_at else None),
            )
        return req

    def get_data_request(self, request_id: str) -> DataRequest | None:
        row = self._db.execute(
            "SELECT * FROM data_requests WHERE id = ?", (request_id,)
        ).fetchone()
        return self._row_to_data_request(dict(row)) if row else None

    def list_data_requests(self, organization_id: str,
                           user_id: str = "",
                           status: str = "") -> list[DataRequest]:
        where = ["organization_id = ?"]
        params: list[Any] = [organization_id]
        if user_id:
            where.append("user_id = ?")
            params.append(user_id)
        if status:
            where.append("status = ?")
            params.append(status)

        sql = f"SELECT * FROM data_requests WHERE {' AND '.join(where)} ORDER BY created_at DESC"
        rows = self._db.execute(sql, params).fetchall()
        return [self._row_to_data_request(dict(r)) for r in rows]

    def update_data_request(self, req: DataRequest) -> None:
        with self._write_lock, self._db.conn:
            self._db.execute(
                """UPDATE data_requests
                   SET status=?, result_url=?, error_message=?, completed_at=?
                   WHERE id=?""",
                (req.status.value, req.result_url, req.error_message,
                 req.completed_at.isoformat() if req.completed_at else None,
                 req.id),
            )

    def export_user_data(self, user_id: str, organization_id: str) -> str:
        """导出用户的所有数据为 JSON，返回文件路径。"""
        # 查询用户的所有记忆
        mem_rows = self._db.execute(
            "SELECT * FROM notes WHERE workspace_id IN "
            "(SELECT id FROM workspaces WHERE owner_id = ?)",
            (user_id,),
        ).fetchall()
        # 查询用户的操作记录
        audit_rows = self._db.execute(
            "SELECT * FROM audit_logs WHERE user_id = ?", (user_id,),
        ).fetchall()
        # 查询用户的导入记录
        # (simplified — just return memories and audit logs)

        export_data = {
            "user_id": user_id,
            "organization_id": organization_id,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "memories": [dict(r) for r in mem_rows],
            "audit_logs": [dict(r) for r in audit_rows],
        }

        # 写入临时文件
        import tempfile, os
        fd, path = tempfile.mkstemp(suffix=".json", prefix=f"data_export_{user_id}_")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2, default=str)
        return path

    def delete_user_data(self, user_id: str, organization_id: str) -> int:
        """删除用户的所有个人数据，返回删除的记录总数。"""
        count = 0
        with self._write_lock, self._db.conn:
            # 删除用户记忆
            c = self._db.execute(
                "DELETE FROM notes WHERE workspace_id IN "
                "(SELECT id FROM workspaces WHERE owner_id = ?)",
                (user_id,),
            )
            count += (c.rowcount if c else 0)

            # 删除审计日志
            c = self._db.execute(
                "DELETE FROM audit_logs WHERE user_id = ?", (user_id,),
            )
            count += (c.rowcount if c else 0)

            # 删除通知
            c = self._db.execute(
                "DELETE FROM notifications WHERE user_id = ?", (user_id,),
            )
            count += (c.rowcount if c else 0)

            # 删除职位
            c = self._db.execute(
                "DELETE FROM positions WHERE user_id = ? AND organization_id = ?",
                (user_id, organization_id),
            )
            count += (c.rowcount if c else 0)

        logger.info("compliance:user_data_deleted", extra={"user_id": user_id, "count": count})
        return count

    # ── Compliance Report ──

    def generate_compliance_report(self, organization_id: str) -> ComplianceReport:
        """生成组织的合规状态报告。"""
        # 总记忆数
        mem_row = self._db.execute(
            "SELECT COUNT(*) as cnt FROM notes WHERE status = 'active'",
        ).fetchone()
        total_memories = mem_row["cnt"] if mem_row else 0

        # 敏感记忆数
        sens_row = self._db.execute(
            "SELECT COUNT(DISTINCT memory_id) as cnt FROM compliance_scans",
        ).fetchone()
        sensitive_memories = sens_row["cnt"] if sens_row else 0

        # 保留策略数
        pol_row = self._db.execute(
            "SELECT COUNT(*) as cnt FROM data_retention_policies WHERE enabled = 1",
        ).fetchone()
        retention_policies = pol_row["cnt"] if pol_row else 0

        # 待处理数据请求
        req_row = self._db.execute(
            "SELECT COUNT(*) as cnt FROM data_requests WHERE status = 'pending'",
        ).fetchone()
        pending_data_requests = req_row["cnt"] if req_row else 0

        # PII 分解
        pii_rows = self._db.execute(
            "SELECT entity_type, COUNT(*) as cnt FROM compliance_scans GROUP BY entity_type",
        ).fetchall()
        pii_breakdown = {r["entity_type"]: r["cnt"] for r in pii_rows}

        return ComplianceReport(
            organization_id=organization_id,
            total_memories=total_memories,
            sensitive_memories=sensitive_memories,
            retention_policies=retention_policies,
            pending_data_requests=pending_data_requests,
            pii_breakdown=pii_breakdown,
        )

    # ── Sensitive Info Scanning ──

    def scan_sensitive_content(self, organization_id: str,
                                entity_types: list[str] | None = None) -> list[dict]:
        """扫描组织内所有记忆中的敏感信息。"""
        # 获取所有活跃记忆
        rows = self._db.execute(
            "SELECT id, content FROM notes WHERE status = 'active'",
        ).fetchall()

        results: list[dict] = []
        with self._write_lock, self._db.conn:
            # 清除旧扫描结果
            self._db.execute(
                "DELETE FROM compliance_scans WHERE organization_id = ?",
                (organization_id,),
            )
            now = datetime.now(timezone.utc).isoformat()
            for row in rows:
                memory_id = row["id"]
                content = row["content"] or ""
                matches = detect_sensitive(content, entity_types)
                if matches:
                    for m in matches:
                        scan_id = str(__import__("uuid").uuid4())
                        self._db.execute(
                            """INSERT INTO compliance_scans
                               (id, organization_id, memory_id, entity_type, value_masked,
                                position, confidence, scanned_at)
                               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                            (scan_id, organization_id, memory_id, m.entity_type,
                             m.value_masked, m.position, m.confidence, now),
                        )
                    results.append({
                        "memory_id": memory_id,
                        "matches": [
                            {"entity_type": m.entity_type, "value_masked": m.value_masked,
                             "position": m.position, "confidence": m.confidence}
                            for m in matches
                        ],
                    })

        logger.info(
            "compliance:scan_complete",
            extra={"org_id": organization_id, "sensitive_memories": len(results)},
        )
        return results

    # ── Internal ──

    @staticmethod
    def _row_to_policy(row: dict) -> DataRetentionPolicy:
        return DataRetentionPolicy(
            id=row["id"],
            name=row["name"],
            resource_type=row["resource_type"],
            retention_period=RetentionPeriod(row["retention_period"]),
            archive_action=ArchiveAction(row["archive_action"]),
            organization_id=row.get("organization_id", ""),
            description=row.get("description", ""),
            enabled=bool(row.get("enabled", 1)),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    @staticmethod
    def _row_to_data_request(row: dict) -> DataRequest:
        return DataRequest(
            id=row["id"],
            user_id=row["user_id"],
            organization_id=row["organization_id"],
            request_type=DataRequestType(row["request_type"]),
            status=DataRequestStatus(row.get("status", "pending")),
            result_url=row.get("result_url", ""),
            error_message=row.get("error_message", ""),
            created_at=datetime.fromisoformat(row["created_at"]),
            completed_at=datetime.fromisoformat(row["completed_at"])
            if row.get("completed_at") else None,
        )

    def close(self) -> None:
        if hasattr(self._db, "conn") and self._db.conn:
            self._db.conn.close()
