"""Tenant Store Adapter — SQLite 实现 TenantStore 协议。

管理 tenants / tenant_members / tenant_organizations 三张表。
"""
import json
import logging
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any

from src.adapters.config import Settings
from src.core.tenant import (
    Organization, OrganizationSize,
    Tenant, TenantMember, TenantStatus,
)

logger = logging.getLogger(__name__)

_TENANT_SCHEMA = """
CREATE TABLE IF NOT EXISTS tenants (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT NOT NULL,
    slug TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'trial',
    owner_user_id TEXT NOT NULL DEFAULT '',
    org_size TEXT NOT NULL DEFAULT 'solo',
    industry TEXT NOT NULL DEFAULT '',
    website TEXT NOT NULL DEFAULT '',
    logo_url TEXT NOT NULL DEFAULT '',
    timezone TEXT NOT NULL DEFAULT 'Asia/Shanghai',
    locale TEXT NOT NULL DEFAULT 'zh-CN',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_tnt_slug ON tenants(slug);
CREATE INDEX IF NOT EXISTS idx_tnt_status ON tenants(status);
CREATE INDEX IF NOT EXISTS idx_tnt_owner ON tenants(owner_user_id);

CREATE TABLE IF NOT EXISTS tenant_members (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'member',
    org_id TEXT,
    joined_at TEXT NOT NULL DEFAULT (datetime('now')),
    invited_by TEXT,
    UNIQUE(tenant_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_tm_tenant ON tenant_members(tenant_id);
CREATE INDEX IF NOT EXISTS idx_tm_user ON tenant_members(user_id);

CREATE TABLE IF NOT EXISTS tenant_organizations (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    parent_org_id TEXT,
    description TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_torg_tenant ON tenant_organizations(tenant_id);
"""


class TenantStoreAdapter:
    """TenantStore 的 SQLite 实现。"""

    def __init__(self, config: Settings, db_path: str | None = None) -> None:
        from sqlite_utils import Database as SqliteDB
        path = db_path or config.sqlite_db_path
        conn = sqlite3.connect(path, check_same_thread=False)
        self._db = SqliteDB(conn)
        self._db.conn.row_factory = sqlite3.Row
        self._write_lock = threading.Lock()
        self._init_schema()

    def _init_schema(self) -> None:
        all_tables = {r["name"] for r in self._db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        for stmt in _TENANT_SCHEMA.strip().split(";"):
            s = stmt.strip()
            if s:
                self._db.execute(s)

    # ── Tenant ──

    def create_tenant(self, tenant: Tenant) -> Tenant:
        with self._write_lock, self._db.conn:
            self._db.execute(
                """INSERT INTO tenants (id, name, email, slug, status,
                   owner_user_id, org_size, industry, website, logo_url,
                   timezone, locale, metadata_json, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (tenant.id, tenant.name, tenant.email, tenant.slug,
                 tenant.status.value, tenant.owner_user_id,
                 tenant.org_size.value, tenant.industry, tenant.website,
                 tenant.logo_url, tenant.timezone, tenant.locale,
                 json.dumps(tenant.metadata, ensure_ascii=False),
                 tenant.created_at.isoformat(), tenant.updated_at.isoformat()),
            )
        logger.info("tenant:created", extra={"tenant_id": tenant.id})
        return tenant

    def get_tenant(self, tenant_id: str) -> Tenant | None:
        row = self._db.execute(
            "SELECT * FROM tenants WHERE id = ?", (tenant_id,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_tenant(dict(row))

    def get_tenant_by_slug(self, slug: str) -> Tenant | None:
        row = self._db.execute(
            "SELECT * FROM tenants WHERE slug = ?", (slug,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_tenant(dict(row))

    def update_tenant(self, tenant: Tenant) -> None:
        tenant.updated_at = datetime.now(timezone.utc)
        with self._write_lock, self._db.conn:
            self._db.execute(
                """UPDATE tenants SET name=?, email=?, slug=?, status=?,
                   owner_user_id=?, org_size=?, industry=?, website=?,
                   logo_url=?, timezone=?, locale=?, metadata_json=?,
                   updated_at=? WHERE id=?""",
                (tenant.name, tenant.email, tenant.slug,
                 tenant.status.value, tenant.owner_user_id,
                 tenant.org_size.value, tenant.industry, tenant.website,
                 tenant.logo_url, tenant.timezone, tenant.locale,
                 json.dumps(tenant.metadata, ensure_ascii=False),
                 tenant.updated_at.isoformat(), tenant.id),
            )

    def delete_tenant(self, tenant_id: str) -> None:
        """软删除：将状态设为 closed。"""
        now = datetime.now(timezone.utc)
        with self._write_lock, self._db.conn:
            self._db.execute(
                "UPDATE tenants SET status = ?, updated_at = ? WHERE id = ?",
                (TenantStatus.CLOSED.value, now.isoformat(), tenant_id),
            )

    def list_tenants(self, status: str | None = None) -> list[Tenant]:
        if status:
            rows = self._db.execute(
                "SELECT * FROM tenants WHERE status = ? ORDER BY created_at DESC",
                (status,),
            ).fetchall()
        else:
            rows = self._db.execute(
                "SELECT * FROM tenants ORDER BY created_at DESC"
            ).fetchall()
        return [self._row_to_tenant(dict(r)) for r in rows]

    # ── Members ──

    def add_member(self, member: TenantMember) -> TenantMember:
        with self._write_lock, self._db.conn:
            self._db.execute(
                """INSERT INTO tenant_members (id, tenant_id, user_id, role,
                   org_id, joined_at, invited_by)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (member.id, member.tenant_id, member.user_id, member.role,
                 member.org_id,
                 member.joined_at.isoformat(),
                 member.invited_by),
            )
        return member

    def remove_member(self, tenant_id: str, user_id: str) -> None:
        with self._write_lock, self._db.conn:
            self._db.execute(
                "DELETE FROM tenant_members WHERE tenant_id = ? AND user_id = ?",
                (tenant_id, user_id),
            )

    def list_members(self, tenant_id: str) -> list[TenantMember]:
        rows = self._db.execute(
            "SELECT * FROM tenant_members WHERE tenant_id = ? ORDER BY joined_at ASC",
            (tenant_id,),
        ).fetchall()
        return [self._row_to_member(dict(r)) for r in rows]

    def get_member(self, tenant_id: str, user_id: str) -> TenantMember | None:
        row = self._db.execute(
            "SELECT * FROM tenant_members WHERE tenant_id = ? AND user_id = ?",
            (tenant_id, user_id),
        ).fetchone()
        if row is None:
            return None
        return self._row_to_member(dict(row))

    # ── Organization ──

    def create_organization(self, org: Organization) -> Organization:
        with self._write_lock, self._db.conn:
            self._db.execute(
                """INSERT INTO tenant_organizations (id, tenant_id, name,
                   parent_org_id, description, metadata_json,
                   created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (org.id, org.tenant_id, org.name,
                 org.parent_org_id, org.description,
                 json.dumps(org.metadata, ensure_ascii=False),
                 org.created_at.isoformat(), org.updated_at.isoformat()),
            )
        return org

    def get_organization(self, org_id: str) -> Organization | None:
        row = self._db.execute(
            "SELECT * FROM tenant_organizations WHERE id = ?", (org_id,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_org(dict(row))

    def list_organizations(self, tenant_id: str) -> list[Organization]:
        rows = self._db.execute(
            "SELECT * FROM tenant_organizations WHERE tenant_id = ? ORDER BY created_at ASC",
            (tenant_id,),
        ).fetchall()
        return [self._row_to_org(dict(r)) for r in rows]

    def update_organization(self, org: Organization) -> None:
        org.updated_at = datetime.now(timezone.utc)
        with self._write_lock, self._db.conn:
            self._db.execute(
                """UPDATE tenant_organizations SET name=?, parent_org_id=?,
                   description=?, metadata_json=?, updated_at=?
                   WHERE id=?""",
                (org.name, org.parent_org_id, org.description,
                 json.dumps(org.metadata, ensure_ascii=False),
                 org.updated_at.isoformat(), org.id),
            )

    def delete_organization(self, org_id: str) -> None:
        with self._write_lock, self._db.conn:
            self._db.execute(
                "DELETE FROM tenant_organizations WHERE id = ?", (org_id,)
            )

    # ── Helpers ──

    def tenant_exists(self, tenant_id: str) -> bool:
        row = self._db.execute(
            "SELECT 1 FROM tenants WHERE id = ?", (tenant_id,)
        ).fetchone()
        return row is not None

    # ── Internal ──

    @staticmethod
    def _row_to_tenant(row: dict) -> Tenant:
        return Tenant(
            id=row["id"],
            name=row["name"],
            email=row["email"],
            slug=row["slug"],
            status=TenantStatus(row["status"]),
            owner_user_id=row.get("owner_user_id", ""),
            org_size=OrganizationSize(row["org_size"]),
            industry=row.get("industry", ""),
            website=row.get("website", ""),
            logo_url=row.get("logo_url", ""),
            timezone=row.get("timezone", "Asia/Shanghai"),
            locale=row.get("locale", "zh-CN"),
            metadata=json.loads(row.get("metadata_json") or "{}"),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    @staticmethod
    def _row_to_member(row: dict) -> TenantMember:
        return TenantMember(
            id=row["id"],
            tenant_id=row["tenant_id"],
            user_id=row["user_id"],
            role=row.get("role", "member"),
            org_id=row.get("org_id"),
            joined_at=datetime.fromisoformat(row["joined_at"]),
            invited_by=row.get("invited_by"),
        )

    @staticmethod
    def _row_to_org(row: dict) -> Organization:
        return Organization(
            id=row["id"],
            tenant_id=row["tenant_id"],
            name=row["name"],
            parent_org_id=row.get("parent_org_id"),
            description=row.get("description", ""),
            metadata=json.loads(row.get("metadata_json") or "{}"),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def close(self) -> None:
        if hasattr(self._db, "conn") and self._db.conn:
            self._db.conn.close()
