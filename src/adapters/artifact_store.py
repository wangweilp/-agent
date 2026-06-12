"""SQLite Artifact Store — 实现 ArtifactStore 协议。

Artifact Sandbox 安全约束：
- 只做 CRUD 元数据操作
- 不执行代码
- 不联网
- 不写文件系统
- 不创建 container/microVM/runtime
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from src.adapters.config import Settings
from src.adapters.sqlite_connection import create_sqlite_db, execute_with_retry
from src.open_platform.artifact import (
    Artifact,
    ArtifactNotFoundError,
    ArtifactStateError,
    ArtifactStatus,
    ArtifactValidationError,
    is_valid_transition,
    _safe_parse_dt,
)

logger = logging.getLogger(__name__)

_ARTIFACT_SCHEMA = """
CREATE TABLE IF NOT EXISTS artifacts (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    artifact_type TEXT NOT NULL DEFAULT 'code',
    title TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    content TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'draft',
    execution_allowed INTEGER NOT NULL DEFAULT 0,
    runtime_enabled INTEGER NOT NULL DEFAULT 0,
    metadata_only INTEGER NOT NULL DEFAULT 1,
    reviewed_by TEXT,
    reviewed_at TEXT,
    review_comment TEXT,
    published_by TEXT,
    published_at TEXT,
    tags_json TEXT NOT NULL DEFAULT '[]',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_art_workspace ON artifacts(workspace_id);
CREATE INDEX IF NOT EXISTS idx_art_agent ON artifacts(agent_id);
CREATE INDEX IF NOT EXISTS idx_art_type ON artifacts(artifact_type);
CREATE INDEX IF NOT EXISTS idx_art_status ON artifacts(status);
CREATE INDEX IF NOT EXISTS idx_art_workspace_status ON artifacts(workspace_id, status);
"""


class SQLiteArtifactStore:
    """ArtifactStore 的 SQLite 实现。

    安全保证：
    - 所有 artifact 的 execution_allowed 强制为 0
    - 所有 artifact 的 runtime_enabled 强制为 0
    - 所有 artifact 的 metadata_only 强制为 1
    - 不包含任何执行逻辑
    """

    def __init__(self, config: Settings, db_path: str | None = None) -> None:
        path = db_path or config.sqlite_db_path
        self._db = create_sqlite_db(path)
        execute_with_retry(lambda: self._init_schema(), label="artifact_init_schema")

    def _init_schema(self) -> None:
        for stmt in _ARTIFACT_SCHEMA.strip().split(";"):
            s = stmt.strip()
            if s:
                self._db.execute(s)
        try:
            self._db.conn.commit()
        except Exception:
            pass

    def flush(self) -> None:
        """显式提交底层连接事务。"""
        try:
            if hasattr(self._db, "conn") and self._db.conn:
                self._db.conn.commit()
        except Exception:
            pass

    def _exec(self, sql: str, params: list[Any] | None = None) -> Any:
        return self._db.execute(sql, params or [])

    # ── CRUD ──

    def create(self, artifact: Artifact) -> Artifact:
        """创建 artifact。

        强制安全约束：
        - execution_allowed = False
        - runtime_enabled = False
        - metadata_only = True
        """
        # 强制安全约束
        artifact.execution_allowed = False
        artifact.runtime_enabled = False
        artifact.metadata_only = True

        errors = artifact.validate()
        if errors:
            raise ArtifactValidationError(
                f"Artifact 校验失败: {'; '.join(errors)}", errors)

        if artifact.status != ArtifactStatus.DRAFT:
            raise ArtifactStateError(
                f"新创建的 artifact 状态必须为 draft，当前: {artifact.status}")

        self._exec("""INSERT INTO artifacts (
            id, workspace_id, agent_id, artifact_type,
            title, description, content,
            status,
            execution_allowed, runtime_enabled, metadata_only,
            reviewed_by, reviewed_at, review_comment,
            published_by, published_at,
            tags_json, metadata_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", [
            artifact.id,
            artifact.workspace_id,
            artifact.agent_id,
            artifact.artifact_type,
            artifact.title,
            artifact.description,
            artifact.content,
            artifact.status,
            0,  # execution_allowed 永远为 0
            0,  # runtime_enabled 永远为 0
            1,  # metadata_only 永远为 1
            artifact.reviewed_by,
            artifact.reviewed_at.isoformat() if artifact.reviewed_at else None,
            artifact.review_comment,
            artifact.published_by,
            artifact.published_at.isoformat() if artifact.published_at else None,
            json.dumps(artifact.tags, ensure_ascii=False),
            json.dumps(artifact.metadata, ensure_ascii=False),
        ])
        return artifact

    def get(self, artifact_id: str) -> Artifact | None:
        """获取单个 artifact。"""
        row = next(
            self._exec("SELECT * FROM artifacts WHERE id=?", [artifact_id]),
            None,
        )
        return self._row_to_artifact(dict(row)) if row else None

    def list(
        self,
        *,
        workspace_id: str = "",
        agent_id: str = "",
        artifact_type: str = "",
        status: str = "",
        limit: int = 50,
        offset: int = 0,
    ) -> list[Artifact]:
        """列出 artifacts，支持多条件过滤。"""
        sql = "SELECT * FROM artifacts WHERE 1=1"
        params: list[Any] = []

        if workspace_id:
            sql += " AND workspace_id=?"
            params.append(workspace_id)
        if agent_id:
            sql += " AND agent_id=?"
            params.append(agent_id)
        if artifact_type:
            sql += " AND artifact_type=?"
            params.append(artifact_type)
        if status:
            sql += " AND status=?"
            params.append(status)

        sql += " ORDER BY created_at DESC"
        sql += f" LIMIT {int(limit)} OFFSET {int(offset)}"

        return [self._row_to_artifact(dict(r)) for r in self._exec(sql, params)]

    def update(self, artifact: Artifact) -> None:
        """更新 artifact 内容（仅 draft/rejected 可编辑）。"""
        existing = self.get(artifact.id)
        if existing is None:
            raise ArtifactNotFoundError(f"Artifact 不存在: {artifact.id}")

        if not existing.is_editable():
            raise ArtifactStateError(
                f"Artifact 状态 '{existing.status}' 不允许编辑。"
                f"仅 draft/rejected 状态可编辑。")

        # 强制安全约束
        artifact.execution_allowed = False
        artifact.runtime_enabled = False
        artifact.metadata_only = True
        artifact.status = existing.status  # 不允许通过 update 改状态

        errors = artifact.validate()
        if errors:
            raise ArtifactValidationError(
                f"Artifact 校验失败: {'; '.join(errors)}", errors)

        self._exec("""UPDATE artifacts SET
            workspace_id=?, agent_id=?, artifact_type=?,
            title=?, description=?, content=?,
            execution_allowed=0, runtime_enabled=0, metadata_only=1,
            tags_json=?, metadata_json=?,
            updated_at=?
            WHERE id=?""", [
            artifact.workspace_id,
            artifact.agent_id,
            artifact.artifact_type,
            artifact.title,
            artifact.description,
            artifact.content,
            json.dumps(artifact.tags, ensure_ascii=False),
            json.dumps(artifact.metadata, ensure_ascii=False),
            datetime.now(timezone.utc).isoformat(),
            artifact.id,
        ])

    def update_status(
        self,
        artifact_id: str,
        status: str,
        reviewed_by: str | None = None,
        review_comment: str | None = None,
        published_by: str | None = None,
    ) -> None:
        """状态迁移 — 带合法性校验。

        Draft → Review → Approved → Published
                    → Rejected → Draft
        """
        existing = self.get(artifact_id)
        if existing is None:
            raise ArtifactNotFoundError(f"Artifact 不存在: {artifact_id}")

        if not is_valid_transition(existing.status, status):
            raise ArtifactStateError(
                f"状态迁移非法: {existing.status} → {status}")

        now = datetime.now(timezone.utc).isoformat()

        if status == ArtifactStatus.REVIEW:
            # 提交审核
            self._exec(
                "UPDATE artifacts SET status=?, updated_at=? WHERE id=?",
                [status, now, artifact_id])
        elif status == ArtifactStatus.APPROVED:
            self._exec(
                "UPDATE artifacts SET status=?, reviewed_by=?, reviewed_at=?,"
                " review_comment=?, updated_at=? WHERE id=?",
                [status, reviewed_by, now, review_comment, now, artifact_id])
        elif status == ArtifactStatus.REJECTED:
            self._exec(
                "UPDATE artifacts SET status=?, reviewed_by=?, reviewed_at=?,"
                " review_comment=?, updated_at=? WHERE id=?",
                [status, reviewed_by, now, review_comment, now, artifact_id])
        elif status == ArtifactStatus.PUBLISHED:
            self._exec(
                "UPDATE artifacts SET status=?, published_by=?, published_at=?,"
                " updated_at=? WHERE id=?",
                [status, published_by, now, now, artifact_id])
        elif status == ArtifactStatus.DRAFT:
            # 从 rejected 重回 draft
            self._exec(
                "UPDATE artifacts SET status=?, review_comment=NULL,"
                " updated_at=? WHERE id=?",
                [status, now, artifact_id])

    def delete(self, artifact_id: str) -> None:
        """物理删除 artifact（仅 draft 状态）。"""
        existing = self.get(artifact_id)
        if existing is None:
            raise ArtifactNotFoundError(f"Artifact 不存在: {artifact_id}")

        if existing.status not in (ArtifactStatus.DRAFT, ArtifactStatus.REJECTED):
            raise ArtifactStateError(
                f"Artifact 状态 '{existing.status}' 不允许删除。"
                f"仅 draft/rejected 状态可删除。")

        self._exec("DELETE FROM artifacts WHERE id=?", [artifact_id])

    # ── Row → Domain ──

    @staticmethod
    def _row_to_artifact(row: dict) -> Artifact:
        return Artifact(
            id=row["id"],
            workspace_id=row.get("workspace_id", ""),
            agent_id=row.get("agent_id", ""),
            artifact_type=row.get("artifact_type", "code"),
            title=row.get("title", ""),
            description=row.get("description", ""),
            content=row.get("content", ""),
            status=row.get("status", "draft"),
            execution_allowed=False,  # 永远是 False
            runtime_enabled=False,    # 永远是 False
            metadata_only=True,       # 永远是 True
            reviewed_by=row.get("reviewed_by"),
            reviewed_at=_safe_parse_dt(row.get("reviewed_at")),
            review_comment=row.get("review_comment"),
            published_by=row.get("published_by"),
            published_at=_safe_parse_dt(row.get("published_at")),
            tags=json.loads(row.get("tags_json", "[]")),
            metadata=json.loads(row.get("metadata_json", "{}")),
            created_at=_safe_parse_dt(row.get("created_at")),
            updated_at=_safe_parse_dt(row.get("updated_at")),
        )
