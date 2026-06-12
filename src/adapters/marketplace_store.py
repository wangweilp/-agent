"""SQLite Marketplace Store — 实现 MarketplaceStore 协议。"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from src.adapters.config import Settings
from src.adapters.sqlite_connection import create_sqlite_db, execute_with_retry
from sqlite_utils import Database as SqliteDB

from src.agents.marketplace import MarketplaceAgent, TenantAgentInstallation

logger = logging.getLogger(__name__)

_MARKETPLACE_SCHEMA = """
CREATE TABLE IF NOT EXISTS marketplace_agents (
    marketplace_agent_id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL, name TEXT NOT NULL,
    display_name TEXT NOT NULL DEFAULT '', description TEXT NOT NULL DEFAULT '',
    long_description TEXT NOT NULL DEFAULT '', category TEXT NOT NULL DEFAULT '',
    department TEXT,
    capabilities_json TEXT NOT NULL DEFAULT '[]',
    required_permissions_json TEXT NOT NULL DEFAULT '[]',
    supported_workflows_json TEXT NOT NULL DEFAULT '[]',
    version TEXT NOT NULL DEFAULT '1.0.0',
    publisher_type TEXT NOT NULL DEFAULT 'builtin',
    publisher_name TEXT NOT NULL DEFAULT 'Cognitive OS', icon TEXT,
    visibility TEXT NOT NULL DEFAULT 'public',
    pricing_model TEXT NOT NULL DEFAULT 'free',
    usage_limits_json TEXT NOT NULL DEFAULT '{}',
    install_count INTEGER NOT NULL DEFAULT 0, rating REAL NOT NULL DEFAULT 0.0,
    status TEXT NOT NULL DEFAULT 'active', metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_mkpa_agent_id ON marketplace_agents(agent_id);
CREATE INDEX IF NOT EXISTS idx_mkpa_category ON marketplace_agents(category);
CREATE INDEX IF NOT EXISTS idx_mkpa_status ON marketplace_agents(status);

CREATE TABLE IF NOT EXISTS tenant_agent_installations (
    installation_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL, workspace_id TEXT NOT NULL DEFAULT '',
    marketplace_agent_id TEXT NOT NULL, agent_id TEXT NOT NULL,
    installed_by TEXT NOT NULL,
    installed_at TEXT NOT NULL DEFAULT (datetime('now')),
    status TEXT NOT NULL DEFAULT 'active', enabled INTEGER NOT NULL DEFAULT 1,
    config_json TEXT NOT NULL DEFAULT '{}',
    permissions_granted_json TEXT NOT NULL DEFAULT '[]',
    usage_limit_override_json TEXT NOT NULL DEFAULT '{}',
    version_pinned TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_inst_unique
    ON tenant_agent_installations(tenant_id, workspace_id, marketplace_agent_id)
    WHERE status != 'uninstalled';
CREATE INDEX IF NOT EXISTS idx_inst_tenant_ws ON tenant_agent_installations(tenant_id, workspace_id);
CREATE INDEX IF NOT EXISTS idx_inst_mkpa ON tenant_agent_installations(marketplace_agent_id);
"""


class SQLiteMarketplaceStore:
    def __init__(self, config: Settings, db_path: str | None = None) -> None:
        path = db_path or config.sqlite_db_path
        self._db = create_sqlite_db(path)
        execute_with_retry(lambda: self._init_schema(), label="marketplace_init_schema")

    def _init_schema(self) -> None:
        for stmt in _MARKETPLACE_SCHEMA.strip().split(";"):
            s = stmt.strip()
            if s: self._db.execute(s)
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

    # ── MarketplaceAgent ──

    def create_agent(self, agent: MarketplaceAgent) -> MarketplaceAgent:
        self._exec("""INSERT OR REPLACE INTO marketplace_agents (
            marketplace_agent_id,agent_id,name,display_name,description,long_description,category,department,
            capabilities_json,required_permissions_json,supported_workflows_json,
            version,publisher_type,publisher_name,icon,visibility,pricing_model,usage_limits_json,
            install_count,rating,status,metadata_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", [
            agent.marketplace_agent_id, agent.agent_id, agent.name, agent.display_name,
            agent.description, agent.long_description, agent.category, agent.department,
            json.dumps(agent.capabilities, ensure_ascii=False),
            json.dumps(agent.required_permissions, ensure_ascii=False),
            json.dumps(agent.supported_workflows, ensure_ascii=False),
            agent.version, agent.publisher_type, agent.publisher_name, agent.icon,
            agent.visibility, agent.pricing_model,
            json.dumps(agent.usage_limits, ensure_ascii=False),
            agent.install_count, agent.rating, agent.status,
            json.dumps(agent.metadata, ensure_ascii=False),
        ])
        return agent

    def get_agent(self, marketplace_agent_id: str) -> MarketplaceAgent | None:
        row = next(self._exec("SELECT * FROM marketplace_agents WHERE marketplace_agent_id=?", [marketplace_agent_id]), None)
        return self._mkpa(dict(row)) if row else None

    def get_agent_by_agent_id(self, agent_id: str) -> MarketplaceAgent | None:
        row = next(self._exec("SELECT * FROM marketplace_agents WHERE agent_id=? LIMIT 1", [agent_id]), None)
        return self._mkpa(dict(row)) if row else None

    def list_agents(self, *, category: str = "", department: str | None = None,
                    status: str = "", visibility: str = "") -> list[MarketplaceAgent]:
        sql = "SELECT * FROM marketplace_agents WHERE 1=1"
        p: list[Any] = []
        if category: sql += " AND category=?"; p.append(category)
        if department is not None:
            if department == "": sql += " AND department IS NULL"
            else: sql += " AND department=?"; p.append(department)
        if status: sql += " AND status=?"; p.append(status)
        if visibility: sql += " AND visibility=?"; p.append(visibility)
        sql += " ORDER BY install_count DESC"
        return [self._mkpa(dict(r)) for r in self._exec(sql, p)]

    def update_agent(self, agent: MarketplaceAgent) -> None:
        self._exec("""UPDATE marketplace_agents SET display_name=?,description=?,long_description=?,
            category=?,department=?,capabilities_json=?,required_permissions_json=?,
            supported_workflows_json=?,version=?,visibility=?,pricing_model=?,
            usage_limits_json=?,status=?,metadata_json=?,install_count=?,rating=?,
            updated_at=? WHERE marketplace_agent_id=?""", [
            agent.display_name, agent.description, agent.long_description,
            agent.category, agent.department,
            json.dumps(agent.capabilities, ensure_ascii=False),
            json.dumps(agent.required_permissions, ensure_ascii=False),
            json.dumps(agent.supported_workflows, ensure_ascii=False),
            agent.version, agent.visibility, agent.pricing_model,
            json.dumps(agent.usage_limits, ensure_ascii=False),
            agent.status, json.dumps(agent.metadata, ensure_ascii=False),
            agent.install_count, agent.rating,
            datetime.now(timezone.utc).isoformat(), agent.marketplace_agent_id,
        ])

    def deactivate_agent(self, marketplace_agent_id: str) -> None:
        self._exec("UPDATE marketplace_agents SET status='disabled',updated_at=? WHERE marketplace_agent_id=?",
                   [datetime.now(timezone.utc).isoformat(), marketplace_agent_id])

    def increment_install_count(self, marketplace_agent_id: str) -> None:
        self._exec("UPDATE marketplace_agents SET install_count=install_count+1,updated_at=? WHERE marketplace_agent_id=?",
                   [datetime.now(timezone.utc).isoformat(), marketplace_agent_id])

    # ── Installation ──

    def install_agent(self, marketplace_agent_id: str, agent_id: str, tenant_id: str,
                      workspace_id: str, installed_by: str, *,
                      config: dict[str, Any] | None = None,
                      permissions_granted: list[str] | None = None) -> TenantAgentInstallation:
        existing = self.get_installation_by_agent(marketplace_agent_id, tenant_id, workspace_id)
        if existing is not None:
            raise DuplicateInstallationError(
                f"Agent {marketplace_agent_id} already installed in t={tenant_id} ws={workspace_id}")
        inst = TenantAgentInstallation(
            tenant_id=tenant_id, workspace_id=workspace_id,
            marketplace_agent_id=marketplace_agent_id, agent_id=agent_id,
            installed_by=installed_by, installed_at=datetime.now(timezone.utc),
            status="active", enabled=True, config=config or {},
            permissions_granted=permissions_granted or [],
        )
        self._exec("""INSERT INTO tenant_agent_installations (
            installation_id,tenant_id,workspace_id,marketplace_agent_id,agent_id,
            installed_by,installed_at,status,enabled,config_json,
            permissions_granted_json,usage_limit_override_json,version_pinned
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""", [
            inst.installation_id, inst.tenant_id, inst.workspace_id,
            inst.marketplace_agent_id, inst.agent_id, inst.installed_by,
            inst.installed_at.isoformat() if inst.installed_at else None,
            inst.status, int(inst.enabled), json.dumps(inst.config, ensure_ascii=False),
            json.dumps(inst.permissions_granted, ensure_ascii=False),
            json.dumps(inst.usage_limit_override, ensure_ascii=False), inst.version_pinned,
        ])
        self.increment_install_count(marketplace_agent_id)
        return inst

    def get_installation(self, installation_id: str) -> TenantAgentInstallation | None:
        row = next(self._exec("SELECT * FROM tenant_agent_installations WHERE installation_id=?", [installation_id]), None)
        return self._inst(dict(row)) if row else None

    def get_installation_by_agent(self, marketplace_agent_id: str, tenant_id: str,
                                  workspace_id: str) -> TenantAgentInstallation | None:
        row = next(self._exec(
            "SELECT * FROM tenant_agent_installations WHERE marketplace_agent_id=? AND tenant_id=? AND workspace_id=? AND status!='uninstalled' ORDER BY installed_at DESC LIMIT 1",
            [marketplace_agent_id, tenant_id, workspace_id]), None)
        return self._inst(dict(row)) if row else None

    def list_installations(self, *, tenant_id: str = "", workspace_id: str = "",
                           marketplace_agent_id: str = "", status: str = "") -> list[TenantAgentInstallation]:
        sql = "SELECT * FROM tenant_agent_installations WHERE status!='uninstalled'"
        p: list[Any] = []
        if tenant_id: sql += " AND tenant_id=?"; p.append(tenant_id)
        if workspace_id: sql += " AND workspace_id=?"; p.append(workspace_id)
        if marketplace_agent_id: sql += " AND marketplace_agent_id=?"; p.append(marketplace_agent_id)
        if status: sql += " AND status=?"; p.append(status)
        sql += " ORDER BY installed_at DESC"
        return [self._inst(dict(r)) for r in self._exec(sql, p)]

    def enable_installation(self, installation_id: str, tenant_id: str, workspace_id: str) -> bool:
        inst = self.get_installation(installation_id)
        if inst is None or inst.tenant_id != tenant_id: return False
        self._exec("UPDATE tenant_agent_installations SET status='active',enabled=1,updated_at=? WHERE installation_id=? AND tenant_id=? AND workspace_id=?",
                   [datetime.now(timezone.utc).isoformat(), installation_id, tenant_id, workspace_id])
        return True

    def disable_installation(self, installation_id: str, tenant_id: str, workspace_id: str) -> bool:
        inst = self.get_installation(installation_id)
        if inst is None or inst.tenant_id != tenant_id: return False
        self._exec("UPDATE tenant_agent_installations SET status='disabled',enabled=0,updated_at=? WHERE installation_id=? AND tenant_id=? AND workspace_id=?",
                   [datetime.now(timezone.utc).isoformat(), installation_id, tenant_id, workspace_id])
        return True

    def update_installation_config(self, installation_id: str, tenant_id: str, workspace_id: str,
                                   config: dict[str, Any]) -> bool:
        inst = self.get_installation(installation_id)
        if inst is None or inst.tenant_id != tenant_id: return False
        merged = {**inst.config, **config}
        self._exec("UPDATE tenant_agent_installations SET config_json=?,updated_at=? WHERE installation_id=? AND tenant_id=? AND workspace_id=?",
                   [json.dumps(merged, ensure_ascii=False), datetime.now(timezone.utc).isoformat(),
                    installation_id, tenant_id, workspace_id])
        return True

    def uninstall_agent(self, installation_id: str, tenant_id: str, workspace_id: str) -> bool:
        inst = self.get_installation(installation_id)
        if inst is None or inst.tenant_id != tenant_id: return False
        self._exec("UPDATE tenant_agent_installations SET status='uninstalled',enabled=0,updated_at=? WHERE installation_id=? AND tenant_id=? AND workspace_id=?",
                   [datetime.now(timezone.utc).isoformat(), installation_id, tenant_id, workspace_id])
        return True

    def is_agent_installed(self, marketplace_agent_id: str, tenant_id: str, workspace_id: str) -> bool:
        return self.get_installation_by_agent(marketplace_agent_id, tenant_id, workspace_id) is not None

    # ── Converters ──

    @staticmethod
    def _mkpa(row: dict) -> MarketplaceAgent:
        return MarketplaceAgent(
            marketplace_agent_id=row["marketplace_agent_id"], agent_id=row["agent_id"],
            name=row["name"], display_name=row.get("display_name", ""),
            description=row.get("description", ""), long_description=row.get("long_description", ""),
            category=row.get("category", ""), department=row.get("department"),
            capabilities=json.loads(row.get("capabilities_json", "[]")),
            required_permissions=json.loads(row.get("required_permissions_json", "[]")),
            supported_workflows=json.loads(row.get("supported_workflows_json", "[]")),
            version=row.get("version", "1.0.0"), publisher_type=row.get("publisher_type", "builtin"),
            publisher_name=row.get("publisher_name", "Cognitive OS"), icon=row.get("icon"),
            visibility=row.get("visibility", "public"), pricing_model=row.get("pricing_model", "free"),
            usage_limits=json.loads(row.get("usage_limits_json", "{}")),
            install_count=row.get("install_count", 0), rating=row.get("rating", 0.0),
            status=row.get("status", "active"), metadata=json.loads(row.get("metadata_json", "{}")),
        )

    @staticmethod
    def _inst(row: dict) -> TenantAgentInstallation:
        ia = None
        if row.get("installed_at"):
            try: ia = datetime.fromisoformat(str(row["installed_at"]).replace("Z", "+00:00"))
            except (ValueError, OSError): pass
        return TenantAgentInstallation(
            installation_id=row["installation_id"], tenant_id=row["tenant_id"],
            workspace_id=row.get("workspace_id", ""),
            marketplace_agent_id=row["marketplace_agent_id"], agent_id=row["agent_id"],
            installed_by=row["installed_by"], installed_at=ia,
            status=row.get("status", "active"), enabled=bool(row.get("enabled", 1)),
            config=json.loads(row.get("config_json", "{}")),
            permissions_granted=json.loads(row.get("permissions_granted_json", "[]")),
            usage_limit_override=json.loads(row.get("usage_limit_override_json", "{}")),
            version_pinned=row.get("version_pinned"),
        )


class DuplicateInstallationError(Exception):
    def __init__(self, message: str, existing_installation: TenantAgentInstallation | None = None):
        super().__init__(message)
        self.existing_installation = existing_installation
