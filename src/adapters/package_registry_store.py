"""SQLite Package Store — 实现 PackageStore 协议。

Package Sandbox 约束：
- 只做 CRUD 元数据操作
- metadata_only 强制为 True
- 不执行代码、不联网、不写文件系统
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from src.adapters.config import Settings
from src.adapters.sqlite_connection import create_sqlite_db, execute_with_retry
from src.open_platform.package_registry import (
    Package,
    PackageNotFoundError,
    PackageStateError,
    PackageStatus,
    PackageValidationError,
    is_valid_transition,
    _safe_parse_dt,
)

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS packages (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    name TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    artifact_ids_json TEXT NOT NULL DEFAULT '[]',
    version TEXT NOT NULL DEFAULT '0.1.0',
    status TEXT NOT NULL DEFAULT 'draft',
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
CREATE INDEX IF NOT EXISTS idx_pkg_workspace ON packages(workspace_id);
CREATE INDEX IF NOT EXISTS idx_pkg_status ON packages(status);
CREATE INDEX IF NOT EXISTS idx_pkg_workspace_status ON packages(workspace_id, status);
"""


class SQLitePackageStore:
    """PackageStore 的 SQLite 实现。metadata_only 永远为 1。"""

    def __init__(self, config: Settings, db_path: str | None = None) -> None:
        path = db_path or config.sqlite_db_path
        self._db = create_sqlite_db(path)
        execute_with_retry(lambda: self._init_schema(), label="pkg_init_schema")

    def _init_schema(self) -> None:
        for stmt in _SCHEMA.strip().split(";"):
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

    # ── CRUD ──

    def create(self, package: Package) -> Package:
        package.metadata_only = True
        errors = package.validate()
        if errors:
            raise PackageValidationError(
                f"Package 校验失败: {'; '.join(errors)}", errors)

        if package.status != PackageStatus.DRAFT:
            raise PackageStateError(
                f"新创建的 package 状态必须为 draft，当前: {package.status}")

        self._exec("""INSERT INTO packages (
            id, workspace_id, name, description,
            artifact_ids_json, version,
            status, metadata_only,
            reviewed_by, reviewed_at, review_comment,
            published_by, published_at,
            tags_json, metadata_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", [
            package.id,
            package.workspace_id,
            package.name,
            package.description,
            json.dumps(package.artifact_ids, ensure_ascii=False),
            package.version,
            package.status,
            1,
            package.reviewed_by,
            package.reviewed_at.isoformat() if package.reviewed_at else None,
            package.review_comment,
            package.published_by,
            package.published_at.isoformat() if package.published_at else None,
            json.dumps(package.tags, ensure_ascii=False),
            json.dumps(package.metadata, ensure_ascii=False),
        ])
        return package

    def get(self, package_id: str) -> Package | None:
        row = next(self._exec(
            "SELECT * FROM packages WHERE id=?", [package_id]), None)
        return self._row_to_package(dict(row)) if row else None

    def list(self, *, workspace_id: str = "", status: str = "",
             limit: int = 50, offset: int = 0) -> list[Package]:
        sql = "SELECT * FROM packages WHERE 1=1"
        params: list[Any] = []
        if workspace_id:
            sql += " AND workspace_id=?"
            params.append(workspace_id)
        if status:
            sql += " AND status=?"
            params.append(status)
        sql += " ORDER BY created_at DESC"
        sql += f" LIMIT {int(limit)} OFFSET {int(offset)}"
        return [self._row_to_package(dict(r)) for r in self._exec(sql, params)]

    def update(self, package: Package) -> None:
        existing = self.get(package.id)
        if existing is None:
            raise PackageNotFoundError(f"Package 不存在: {package.id}")
        if not existing.is_editable():
            raise PackageStateError(
                f"Package 状态 '{existing.status}' 不允许编辑。"
                f"仅 draft/rejected 状态可编辑。")

        package.metadata_only = True
        package.status = existing.status

        errors = package.validate()
        if errors:
            raise PackageValidationError(
                f"Package 校验失败: {'; '.join(errors)}", errors)

        self._exec("""UPDATE packages SET
            workspace_id=?, name=?, description=?,
            artifact_ids_json=?, version=?,
            metadata_only=1,
            tags_json=?, metadata_json=?,
            updated_at=?
            WHERE id=?""", [
            package.workspace_id,
            package.name,
            package.description,
            json.dumps(package.artifact_ids, ensure_ascii=False),
            package.version,
            json.dumps(package.tags, ensure_ascii=False),
            json.dumps(package.metadata, ensure_ascii=False),
            datetime.now(timezone.utc).isoformat(),
            package.id,
        ])

    def update_status(self, package_id: str, status: str,
                      reviewed_by: str | None = None,
                      review_comment: str | None = None,
                      published_by: str | None = None) -> None:
        existing = self.get(package_id)
        if existing is None:
            raise PackageNotFoundError(f"Package 不存在: {package_id}")
        if not is_valid_transition(existing.status, status):
            raise PackageStateError(
                f"状态迁移非法: {existing.status} → {status}")

        now = datetime.now(timezone.utc).isoformat()

        if status in (PackageStatus.APPROVED, PackageStatus.REJECTED):
            self._exec(
                "UPDATE packages SET status=?, reviewed_by=?, reviewed_at=?,"
                " review_comment=?, updated_at=? WHERE id=?",
                [status, reviewed_by, now, review_comment, now, package_id])
        elif status == PackageStatus.PUBLISHED:
            self._exec(
                "UPDATE packages SET status=?, published_by=?, published_at=?,"
                " updated_at=? WHERE id=?",
                [status, published_by, now, now, package_id])
        elif status == PackageStatus.DRAFT:
            self._exec(
                "UPDATE packages SET status=?, review_comment=NULL,"
                " updated_at=? WHERE id=?",
                [status, now, package_id])
        else:
            self._exec(
                "UPDATE packages SET status=?, updated_at=? WHERE id=?",
                [status, now, package_id])

    def delete(self, package_id: str) -> None:
        existing = self.get(package_id)
        if existing is None:
            raise PackageNotFoundError(f"Package 不存在: {package_id}")
        if existing.status not in (PackageStatus.DRAFT, PackageStatus.REJECTED):
            raise PackageStateError(
                f"Package 状态 '{existing.status}' 不允许删除。"
                f"仅 draft/rejected 状态可删除。")
        self._exec("DELETE FROM packages WHERE id=?", [package_id])

    @staticmethod
    def _row_to_package(row: dict) -> Package:
        return Package(
            id=row["id"],
            workspace_id=row.get("workspace_id", ""),
            name=row.get("name", ""),
            description=row.get("description", ""),
            artifact_ids=json.loads(row.get("artifact_ids_json", "[]")),
            version=row.get("version", "0.1.0"),
            status=row.get("status", "draft"),
            metadata_only=True,
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
