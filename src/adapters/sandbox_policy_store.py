"""SQLite Sandbox Policy Store — 实现 SandboxPolicyStore 协议。"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from src.adapters.config import Settings
from src.adapters.sqlite_connection import create_sqlite_db, execute_with_retry
from src.open_platform.sandbox_policy import (
    SandboxLevel,
    SandboxPolicy,
    SandboxPolicyAlreadyExistsError,
    SandboxPolicyDecision,
    SandboxPolicyNotFoundError,
    SandboxPolicyPermissionError,
    SandboxPolicyScope,
    SandboxPolicyStateError,
    SandboxPolicyStatus,
    SandboxPolicyTestRequest,
    SandboxPolicyTestResult,
    SandboxPolicyValidationError,
    _safe_parse_dt,
)

logger = logging.getLogger(__name__)

_SP_SCHEMA = """
CREATE TABLE IF NOT EXISTS sandbox_policies (
    policy_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    scope TEXT NOT NULL DEFAULT 'system',
    tenant_id TEXT,
    sandbox_level TEXT NOT NULL DEFAULT 'no_execution',
    allow_network INTEGER NOT NULL DEFAULT 0,
    allowed_domains_json TEXT NOT NULL DEFAULT '[]',
    allow_filesystem_read INTEGER NOT NULL DEFAULT 0,
    allow_filesystem_write INTEGER NOT NULL DEFAULT 0,
    allowed_paths_json TEXT NOT NULL DEFAULT '[]',
    allow_secrets INTEGER NOT NULL DEFAULT 0,
    allowed_secret_names_json TEXT NOT NULL DEFAULT '[]',
    max_timeout_ms INTEGER NOT NULL DEFAULT 0,
    max_memory_mb INTEGER NOT NULL DEFAULT 0,
    max_cpu_percent INTEGER NOT NULL DEFAULT 0,
    max_output_bytes INTEGER NOT NULL DEFAULT 0,
    max_requests_per_minute INTEGER NOT NULL DEFAULT 0,
    data_access_scope_json TEXT NOT NULL DEFAULT '[]',
    audit_enabled INTEGER NOT NULL DEFAULT 1,
    kill_switch_enabled INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'active',
    system_managed INTEGER NOT NULL DEFAULT 0,
    created_by TEXT,
    updated_by TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_sp_name_tenant ON sandbox_policies(name, tenant_id);
CREATE INDEX IF NOT EXISTS idx_sp_scope ON sandbox_policies(scope);
CREATE INDEX IF NOT EXISTS idx_sp_tenant_id ON sandbox_policies(tenant_id);
CREATE INDEX IF NOT EXISTS idx_sp_status ON sandbox_policies(status);
CREATE INDEX IF NOT EXISTS idx_sp_level ON sandbox_policies(sandbox_level);
"""

_BUILTIN_POLICIES: list[dict[str, Any]] = [
    {
        "policy_id": "sbxpol_no_execution",
        "name": "No Execution Policy",
        "description": "Default fallback policy. No code execution allowed. Applied automatically when no other policy is assigned.",
        "scope": SandboxPolicyScope.SYSTEM,
        "tenant_id": None,
        "sandbox_level": SandboxLevel.NO_EXECUTION,
        "allow_network": False,
        "allowed_domains": [],
        "allow_filesystem_read": False,
        "allow_filesystem_write": False,
        "allowed_paths": [],
        "allow_secrets": False,
        "allowed_secret_names": [],
        "max_timeout_ms": 0,
        "max_memory_mb": 0,
        "max_cpu_percent": 0,
        "max_output_bytes": 0,
        "max_requests_per_minute": 0,
        "data_access_scope": [],
        "audit_enabled": True,
        "kill_switch_enabled": True,
        "status": SandboxPolicyStatus.ACTIVE,
        "system_managed": True,
        "metadata": {"no_remote_code_execution": True, "no_network": True},
    },
    {
        "policy_id": "sbxpol_simulation_only",
        "name": "Simulation Only Policy",
        "description": "Safe simulation policy. No code execution, no network, no data access. Used with simulation adapter.",
        "scope": SandboxPolicyScope.SYSTEM,
        "tenant_id": None,
        "sandbox_level": SandboxLevel.SIMULATION_ONLY,
        "allow_network": False,
        "allowed_domains": [],
        "allow_filesystem_read": False,
        "allow_filesystem_write": False,
        "allowed_paths": [],
        "allow_secrets": False,
        "allowed_secret_names": [],
        "max_timeout_ms": 5_000,
        "max_memory_mb": 64,
        "max_cpu_percent": 10,
        "max_output_bytes": 65_536,
        "max_requests_per_minute": 30,
        "data_access_scope": [],
        "audit_enabled": True,
        "kill_switch_enabled": True,
        "status": SandboxPolicyStatus.ACTIVE,
        "system_managed": True,
        "metadata": {"simulation_only": True, "no_remote_code_execution": True},
    },
    {
        "policy_id": "sbxpol_restricted_network_off",
        "name": "Restricted No Network Policy",
        "description": "Restricted sandbox with network disabled. Reserved for future sandboxed execution capability.",
        "scope": SandboxPolicyScope.SYSTEM,
        "tenant_id": None,
        "sandbox_level": SandboxLevel.RESTRICTED,
        "allow_network": False,
        "allowed_domains": [],
        "allow_filesystem_read": False,
        "allow_filesystem_write": False,
        "allowed_paths": [],
        "allow_secrets": False,
        "allowed_secret_names": [],
        "max_timeout_ms": 10_000,
        "max_memory_mb": 128,
        "max_cpu_percent": 25,
        "max_output_bytes": 131_072,
        "max_requests_per_minute": 60,
        "data_access_scope": [],
        "audit_enabled": True,
        "kill_switch_enabled": True,
        "status": SandboxPolicyStatus.ACTIVE,
        "system_managed": True,
        "metadata": {
            "restricted": True,
            "no_network": True,
            "execution_not_implemented": True,
        },
    },
]


class SQLiteSandboxPolicyStore:
    def __init__(self, config: Settings, db_path: str | None = None) -> None:
        path = db_path or config.sqlite_db_path
        self._db = create_sqlite_db(path)
        execute_with_retry(lambda: self._init_schema(), label="sandbox_policy_init_schema")

    def _init_schema(self) -> None:
        for stmt in _SP_SCHEMA.strip().split(";"):
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

    # ── CRUD ──

    def create_policy(self, policy: SandboxPolicy) -> SandboxPolicy:
        errors = policy.validate()
        if errors:
            raise SandboxPolicyValidationError(
                f"Sandbox Policy 校验失败: {'; '.join(errors)}", errors)

        existing = self.get_policy_by_name(policy.name, policy.tenant_id)
        if existing is not None:
            raise SandboxPolicyAlreadyExistsError(
                f"Policy '{policy.name}' 已存在 (tenant={policy.tenant_id or 'system'})")

        self._exec("""INSERT INTO sandbox_policies (
            policy_id, name, description, scope, tenant_id, sandbox_level,
            allow_network, allowed_domains_json,
            allow_filesystem_read, allow_filesystem_write, allowed_paths_json,
            allow_secrets, allowed_secret_names_json,
            max_timeout_ms, max_memory_mb, max_cpu_percent,
            max_output_bytes, max_requests_per_minute,
            data_access_scope_json,
            audit_enabled, kill_switch_enabled,
            status, system_managed, created_by, updated_by, metadata_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", [
            policy.policy_id,
            policy.name, policy.description, policy.scope, policy.tenant_id,
            policy.sandbox_level,
            int(policy.allow_network),
            json.dumps(policy.allowed_domains, ensure_ascii=False),
            int(policy.allow_filesystem_read),
            int(policy.allow_filesystem_write),
            json.dumps(policy.allowed_paths, ensure_ascii=False),
            int(policy.allow_secrets),
            json.dumps(policy.allowed_secret_names, ensure_ascii=False),
            policy.max_timeout_ms, policy.max_memory_mb, policy.max_cpu_percent,
            policy.max_output_bytes, policy.max_requests_per_minute,
            json.dumps(policy.data_access_scope, ensure_ascii=False),
            int(policy.audit_enabled), int(policy.kill_switch_enabled),
            policy.status, int(policy.system_managed),
            policy.created_by, policy.updated_by,
            json.dumps(policy.metadata, ensure_ascii=False),
        ])
        return policy

    def get_policy(self, policy_id: str) -> SandboxPolicy | None:
        row = next(self._exec("SELECT * FROM sandbox_policies WHERE policy_id=?", [policy_id]), None)
        return self._policy(dict(row)) if row else None

    def get_policy_by_name(self, name: str, tenant_id: str | None = None) -> SandboxPolicy | None:
        if tenant_id is not None:
            row = next(self._exec(
                "SELECT * FROM sandbox_policies WHERE name=? AND tenant_id=?",
                [name, tenant_id]), None)
        else:
            row = next(self._exec(
                "SELECT * FROM sandbox_policies WHERE name=? AND tenant_id IS NULL",
                [name]), None)
        return self._policy(dict(row)) if row else None

    def list_policies(
        self, *, tenant_id: str = "", scope: str = "",
        status: str = "", include_system: bool = True,
    ) -> list[SandboxPolicy]:
        sql = "SELECT * FROM sandbox_policies WHERE 1=1"
        p: list[Any] = []

        if tenant_id and include_system:
            sql += " AND (tenant_id=? OR scope='system')"
            p.append(tenant_id)
        elif tenant_id:
            sql += " AND tenant_id=?"
            p.append(tenant_id)
        elif include_system and not tenant_id:
            sql += " AND (scope='system' OR tenant_id IS NOT NULL)"
        if scope:
            sql += " AND scope=?"
            p.append(scope)
        if status:
            sql += " AND status=?"
            p.append(status)
        sql += " ORDER BY scope, name"
        return [self._policy(dict(r)) for r in self._exec(sql, p)]

    def update_policy(self, policy: SandboxPolicy) -> None:
        existing = self.get_policy(policy.policy_id)
        if existing is None:
            raise SandboxPolicyNotFoundError(f"Policy 不存在: {policy.policy_id}")

        # system_managed: 关键字段不可修改
        if existing.system_managed:
            policy.sandbox_level = existing.sandbox_level
            policy.scope = existing.scope
            policy.tenant_id = existing.tenant_id
            policy.system_managed = True

        errors = policy.validate()
        if errors:
            raise SandboxPolicyValidationError(
                f"Sandbox Policy 校验失败: {'; '.join(errors)}", errors)

        self._exec("""UPDATE sandbox_policies SET
            name=?, description=?, scope=?, tenant_id=?, sandbox_level=?,
            allow_network=?, allowed_domains_json=?,
            allow_filesystem_read=?, allow_filesystem_write=?, allowed_paths_json=?,
            allow_secrets=?, allowed_secret_names_json=?,
            max_timeout_ms=?, max_memory_mb=?, max_cpu_percent=?,
            max_output_bytes=?, max_requests_per_minute=?,
            data_access_scope_json=?,
            audit_enabled=?, kill_switch_enabled=?,
            status=?, system_managed=?, updated_by=?, metadata_json=?,
            updated_at=?
            WHERE policy_id=?""", [
            policy.name, policy.description, policy.scope, policy.tenant_id,
            policy.sandbox_level,
            int(policy.allow_network),
            json.dumps(policy.allowed_domains, ensure_ascii=False),
            int(policy.allow_filesystem_read),
            int(policy.allow_filesystem_write),
            json.dumps(policy.allowed_paths, ensure_ascii=False),
            int(policy.allow_secrets),
            json.dumps(policy.allowed_secret_names, ensure_ascii=False),
            policy.max_timeout_ms, policy.max_memory_mb, policy.max_cpu_percent,
            policy.max_output_bytes, policy.max_requests_per_minute,
            json.dumps(policy.data_access_scope, ensure_ascii=False),
            int(policy.audit_enabled), int(policy.kill_switch_enabled),
            policy.status, int(policy.system_managed),
            policy.updated_by,
            json.dumps(policy.metadata, ensure_ascii=False),
            datetime.now(timezone.utc).isoformat(),
            policy.policy_id,
        ])

    def set_policy_status(self, policy_id: str, status: str,
                          updated_by: str | None = None) -> bool:
        policy = self.get_policy(policy_id)
        if policy is None:
            return False
        policy.status = status
        policy.updated_by = updated_by
        self.update_policy(policy)
        return True

    def delete_policy(self, policy_id: str) -> None:
        policy = self.get_policy(policy_id)
        if policy is None:
            raise SandboxPolicyNotFoundError(f"Policy 不存在: {policy_id}")
        if policy.system_managed:
            raise SandboxPolicyPermissionError(
                f"system_managed policy '{policy.name}' 不允许删除")
        self.set_policy_status(policy_id, SandboxPolicyStatus.DISABLED)

    def seed_builtin_policies(self) -> int:
        created = 0
        updated = 0
        for data in _BUILTIN_POLICIES:
            pid = data["policy_id"]
            existing = self.get_policy(pid)
            policy = SandboxPolicy(
                policy_id=pid,
                name=str(data["name"]),
                description=str(data["description"]),
                scope=str(data["scope"]),
                tenant_id=data.get("tenant_id"),
                sandbox_level=str(data["sandbox_level"]),
                allow_network=bool(data.get("allow_network", False)),
                allowed_domains=list(data.get("allowed_domains", [])),
                allow_filesystem_read=bool(data.get("allow_filesystem_read", False)),
                allow_filesystem_write=bool(data.get("allow_filesystem_write", False)),
                allowed_paths=list(data.get("allowed_paths", [])),
                allow_secrets=bool(data.get("allow_secrets", False)),
                allowed_secret_names=list(data.get("allowed_secret_names", [])),
                max_timeout_ms=int(data.get("max_timeout_ms", 0)),
                max_memory_mb=int(data.get("max_memory_mb", 0)),
                max_cpu_percent=int(data.get("max_cpu_percent", 0)),
                max_output_bytes=int(data.get("max_output_bytes", 0)),
                max_requests_per_minute=int(data.get("max_requests_per_minute", 0)),
                data_access_scope=list(data.get("data_access_scope", [])),
                audit_enabled=bool(data.get("audit_enabled", True)),
                kill_switch_enabled=bool(data.get("kill_switch_enabled", True)),
                status=str(data.get("status", SandboxPolicyStatus.ACTIVE)),
                system_managed=bool(data.get("system_managed", False)),
                metadata=dict(data.get("metadata", {})),
            )
            if existing is None:
                self.create_policy(policy)
                created += 1
            else:
                # 保留手动修改的 status
                policy.status = existing.status
                self.update_policy(policy)
                updated += 1
        logger.info("sandbox_policies_seeded", extra={"created_count": created, "updated_count": updated})
        return created

    # ── Test ──

    def test_policy(
        self, policy_id: str, request: SandboxPolicyTestRequest,
    ) -> SandboxPolicyTestResult:
        """静态规则评估 — 不执行代码、不联网、不读文件。"""
        policy = self.get_policy(policy_id)
        if policy is None:
            raise SandboxPolicyNotFoundError(f"Policy 不存在: {policy_id}")

        result = SandboxPolicyTestResult(policy_id=policy_id)
        result.evaluated_rules.append(f"policy_sandbox_level={policy.sandbox_level}")

        # Rule: sandbox_level check
        if request.sandbox_level != policy.sandbox_level:
            result.violations.append(
                f"sandbox_level mismatch: requested={request.sandbox_level}, policy={policy.sandbox_level}")
            result.evaluated_rules.append("sandbox_level: deny (mismatch)")

        # Rule: network
        if request.requested_network and not policy.allow_network:
            result.violations.append("network request denied: policy does not allow network")
            result.evaluated_rules.append("network: deny")
        else:
            result.evaluated_rules.append("network: allow" if request.requested_network else "network: n/a")

        # Rule: domains
        if request.requested_domains:
            for domain in request.requested_domains:
                if domain not in policy.allowed_domains:
                    result.violations.append(
                        f"domain '{domain}' not in allowed_domains")
                    result.evaluated_rules.append(f"domain {domain}: deny")
                else:
                    result.evaluated_rules.append(f"domain {domain}: allow")

        # Rule: filesystem read
        if request.requested_filesystem_read and not policy.allow_filesystem_read:
            result.violations.append("filesystem_read denied")
            result.evaluated_rules.append("filesystem_read: deny")

        # Rule: filesystem write
        if request.requested_filesystem_write and not policy.allow_filesystem_write:
            result.violations.append("filesystem_write denied")
            result.evaluated_rules.append("filesystem_write: deny")

        # Rule: secrets
        for sn in request.requested_secret_names:
            if sn not in policy.allowed_secret_names:
                result.violations.append(f"secret '{sn}' not in allowed_secret_names")
                result.evaluated_rules.append(f"secret {sn}: deny")

        # Rule: timeout
        if request.requested_timeout_ms > policy.max_timeout_ms:
            result.violations.append(
                f"timeout exceeded: requested={request.requested_timeout_ms}ms > max={policy.max_timeout_ms}ms")
            result.evaluated_rules.append("timeout: deny")

        # Rule: memory
        if request.requested_memory_mb > policy.max_memory_mb:
            result.violations.append(
                f"memory exceeded: requested={request.requested_memory_mb}MB > max={policy.max_memory_mb}MB")
            result.evaluated_rules.append("memory: deny")

        # Rule: data access scope
        for scope_item in request.requested_data_access_scope:
            if scope_item not in policy.data_access_scope:
                result.warnings.append(f"data_access_scope '{scope_item}' not in policy data_access_scope")
                result.evaluated_rules.append(f"data_access {scope_item}: warn")

        # Final decision
        if result.violations:
            result.decision = SandboxPolicyDecision.DENY
            result.allowed = False
        elif result.warnings:
            result.decision = SandboxPolicyDecision.WARN
            result.allowed = True
        else:
            result.decision = SandboxPolicyDecision.ALLOW
            result.allowed = True

        result.metadata["policy_sandbox_level"] = policy.sandbox_level
        result.metadata["policy_status"] = policy.status
        result.metadata["static_evaluation_only"] = True
        result.metadata["no_code_executed"] = True

        return result

    # ── Row → Domain ──

    @staticmethod
    def _policy(row: dict) -> SandboxPolicy:
        return SandboxPolicy(
            policy_id=row["policy_id"],
            name=row["name"],
            description=row.get("description", ""),
            scope=row.get("scope", "system"),
            tenant_id=row.get("tenant_id"),
            sandbox_level=row.get("sandbox_level", "no_execution"),
            allow_network=bool(row.get("allow_network", 0)),
            allowed_domains=json.loads(row.get("allowed_domains_json", "[]")),
            allow_filesystem_read=bool(row.get("allow_filesystem_read", 0)),
            allow_filesystem_write=bool(row.get("allow_filesystem_write", 0)),
            allowed_paths=json.loads(row.get("allowed_paths_json", "[]")),
            allow_secrets=bool(row.get("allow_secrets", 0)),
            allowed_secret_names=json.loads(row.get("allowed_secret_names_json", "[]")),
            max_timeout_ms=int(row.get("max_timeout_ms", 0)),
            max_memory_mb=int(row.get("max_memory_mb", 0)),
            max_cpu_percent=int(row.get("max_cpu_percent", 0)),
            max_output_bytes=int(row.get("max_output_bytes", 0)),
            max_requests_per_minute=int(row.get("max_requests_per_minute", 0)),
            data_access_scope=json.loads(row.get("data_access_scope_json", "[]")),
            audit_enabled=bool(row.get("audit_enabled", 1)),
            kill_switch_enabled=bool(row.get("kill_switch_enabled", 1)),
            status=row.get("status", "active"),
            system_managed=bool(row.get("system_managed", 0)),
            created_by=row.get("created_by"),
            updated_by=row.get("updated_by"),
            metadata=json.loads(row.get("metadata_json", "{}")),
            created_at=_safe_parse_dt(row.get("created_at")),
            updated_at=_safe_parse_dt(row.get("updated_at")),
        )
