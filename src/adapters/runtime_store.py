"""SQLite Runtime Store — 实现 RuntimeStore 协议。

提供 RuntimeAdapter + DeveloperAgentRuntimeBinding 持久化。
遵循现有 store 模式（sqlite_utils.Database + row_factory）。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from src.adapters.sqlite_connection import create_sqlite_db, execute_with_retry
from src.adapters.config import Settings
from src.open_platform.runtime import (
    RuntimeAdapter,
    RuntimeAdapterAlreadyExistsError,
    RuntimeAdapterNotAllowedError,
    RuntimeAdapterNotFoundError,
    RuntimeAdapterStatus,
    RuntimeAdapterType,
    RuntimeBindingAlreadyExistsError,
    RuntimeBindingNotFoundError,
    RuntimeBindingStatus,
    RuntimeEligibilityCode,
    RuntimeEligibilityResult,
    RuntimeStateError,
    DeveloperAgentRuntimeBinding,
    is_mvp_allowed_adapter_type,
    _safe_parse_datetime,
)

logger = logging.getLogger(__name__)

_RUNTIME_SCHEMA = """
CREATE TABLE IF NOT EXISTS runtime_adapters (
    adapter_id TEXT PRIMARY KEY,
    adapter_type TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    supports_network INTEGER NOT NULL DEFAULT 0,
    supports_user_data_read INTEGER NOT NULL DEFAULT 0,
    supports_user_data_write INTEGER NOT NULL DEFAULT 0,
    sandbox_required INTEGER NOT NULL DEFAULT 0,
    max_timeout_ms INTEGER NOT NULL DEFAULT 0,
    max_memory_mb INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'active',
    version TEXT NOT NULL DEFAULT '1.0.0',
    config_schema_json TEXT NOT NULL DEFAULT '{}',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_runtime_adapters_type ON runtime_adapters(adapter_type);
CREATE INDEX IF NOT EXISTS idx_runtime_adapters_status ON runtime_adapters(status);

CREATE TABLE IF NOT EXISTS developer_agent_runtime_bindings (
    binding_id TEXT PRIMARY KEY,
    marketplace_agent_id TEXT NOT NULL,
    submission_id TEXT,
    developer_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    adapter_id TEXT NOT NULL,
    adapter_type TEXT NOT NULL,
    runtime_status TEXT NOT NULL DEFAULT 'pending',
    sandbox_policy_id TEXT,
    enabled_by TEXT,
    disabled_by TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_runtime_bindings_mkp_tenant
    ON developer_agent_runtime_bindings(marketplace_agent_id, tenant_id);
CREATE INDEX IF NOT EXISTS idx_runtime_bindings_marketplace_agent
    ON developer_agent_runtime_bindings(marketplace_agent_id);
CREATE INDEX IF NOT EXISTS idx_runtime_bindings_developer_id
    ON developer_agent_runtime_bindings(developer_id);
CREATE INDEX IF NOT EXISTS idx_runtime_bindings_tenant_id
    ON developer_agent_runtime_bindings(tenant_id);
CREATE INDEX IF NOT EXISTS idx_runtime_bindings_status
    ON developer_agent_runtime_bindings(runtime_status);
CREATE INDEX IF NOT EXISTS idx_runtime_bindings_adapter_type
    ON developer_agent_runtime_bindings(adapter_type);
"""

# ═══════════════════════════════════════════
# Built-in Adapter Definitions
# ═══════════════════════════════════════════

_BUILTIN_ADAPTERS: list[dict[str, Any]] = [
    {
        "adapter_id": "rtadp_manifest_only",
        "adapter_type": RuntimeAdapterType.MANIFEST_ONLY,
        "name": "Manifest Only",
        "description": "Metadata-only developer agent. No execution.",
        "supports_network": False,
        "supports_user_data_read": False,
        "supports_user_data_write": False,
        "sandbox_required": False,
        "max_timeout_ms": 0,
        "max_memory_mb": 0,
        "status": RuntimeAdapterStatus.ACTIVE,
        "version": "1.0.0",
        "config_schema": {},
        "metadata": {
            "no_execution": True,
            "default_for_step22": True,
        },
    },
    {
        "adapter_id": "rtadp_simulation",
        "adapter_type": RuntimeAdapterType.SIMULATION,
        "name": "Simulation Runtime",
        "description": "Safe no-code simulation adapter for validating runtime flow.",
        "supports_network": False,
        "supports_user_data_read": False,
        "supports_user_data_write": False,
        "sandbox_required": False,
        "max_timeout_ms": 5_000,
        "max_memory_mb": 64,
        "status": RuntimeAdapterStatus.BETA,
        "version": "0.1.0",
        "config_schema": {},
        "metadata": {
            "no_remote_code_execution": True,
            "no_network": True,
            "simulation_only": True,
        },
    },
    {
        "adapter_id": "rtadp_http_webhook",
        "adapter_type": RuntimeAdapterType.HTTP_WEBHOOK,
        "name": "HTTP Webhook",
        "description": "External HTTP webhook adapter. Requires sandbox policy. (Step 24+)",
        "supports_network": True,
        "supports_user_data_read": False,
        "supports_user_data_write": False,
        "sandbox_required": True,
        "max_timeout_ms": 30_000,
        "max_memory_mb": 128,
        "status": RuntimeAdapterStatus.DISABLED,
        "version": "0.1.0",
        "config_schema": {},
        "metadata": {
            "requires_sandbox_policy": True,
            "future": True,
        },
    },
    {
        "adapter_id": "rtadp_sandboxed_process",
        "adapter_type": RuntimeAdapterType.SANDBOXED_PROCESS,
        "name": "Sandboxed Process",
        "description": "Subprocess-isolated adapter with resource limits. (Step 24+)",
        "supports_network": False,
        "supports_user_data_read": True,
        "supports_user_data_write": True,
        "sandbox_required": True,
        "max_timeout_ms": 30_000,
        "max_memory_mb": 256,
        "status": RuntimeAdapterStatus.DISABLED,
        "version": "0.1.0",
        "config_schema": {},
        "metadata": {
            "requires_sandbox_policy": True,
            "future": True,
        },
    },
    {
        "adapter_id": "rtadp_container",
        "adapter_type": RuntimeAdapterType.CONTAINER,
        "name": "Container Sandbox",
        "description": "Full container isolation (Docker/Podman). (Step 24+)",
        "supports_network": True,
        "supports_user_data_read": True,
        "supports_user_data_write": True,
        "sandbox_required": True,
        "max_timeout_ms": 120_000,
        "max_memory_mb": 512,
        "status": RuntimeAdapterStatus.DISABLED,
        "version": "0.1.0",
        "config_schema": {},
        "metadata": {
            "requires_sandbox_policy": True,
            "future": True,
        },
    },
]


class SQLiteRuntimeStore:
    """SQLite Runtime Adapter + Binding Store。"""

    def __init__(self, config: Settings, db_path: str | None = None) -> None:
        path = db_path or config.sqlite_db_path
        self._db = create_sqlite_db(path)
        execute_with_retry(lambda: self._init_schema(), label="runtime_init_schema")

    def _init_schema(self) -> None:
        for stmt in _RUNTIME_SCHEMA.strip().split(";"):
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

    # ═══════════════════════════════════════════
    # Adapter CRUD
    # ═══════════════════════════════════════════

    def create_adapter(self, adapter: RuntimeAdapter) -> RuntimeAdapter:
        existing = self.get_adapter(adapter.adapter_id)
        if existing is not None:
            raise RuntimeAdapterAlreadyExistsError(
                f"Runtime Adapter 已存在: {adapter.adapter_id}")
        self._exec("""INSERT INTO runtime_adapters (
            adapter_id, adapter_type, name, description,
            supports_network, supports_user_data_read, supports_user_data_write,
            sandbox_required, max_timeout_ms, max_memory_mb,
            status, version, config_schema_json, metadata_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", [
            adapter.adapter_id,
            adapter.adapter_type,
            adapter.name,
            adapter.description,
            int(adapter.supports_network),
            int(adapter.supports_user_data_read),
            int(adapter.supports_user_data_write),
            int(adapter.sandbox_required),
            adapter.max_timeout_ms,
            adapter.max_memory_mb,
            adapter.status,
            adapter.version,
            json.dumps(adapter.config_schema, ensure_ascii=False),
            json.dumps(adapter.metadata, ensure_ascii=False),
        ])
        return adapter

    def get_adapter(self, adapter_id: str) -> RuntimeAdapter | None:
        row = next(self._exec(
            "SELECT * FROM runtime_adapters WHERE adapter_id=?", [adapter_id]), None)
        return self._adapter(dict(row)) if row else None

    def get_adapter_by_type(self, adapter_type: str) -> RuntimeAdapter | None:
        row = next(self._exec(
            "SELECT * FROM runtime_adapters WHERE adapter_type=?", [adapter_type]), None)
        return self._adapter(dict(row)) if row else None

    def list_adapters(
        self, *, status: str = "", mvp_only: bool = False,
    ) -> list[RuntimeAdapter]:
        sql = "SELECT * FROM runtime_adapters WHERE 1=1"
        p: list[Any] = []
        if status:
            sql += " AND status=?"
            p.append(status)
        if mvp_only:
            sql += " AND adapter_type IN (?,?)"
            p.extend([RuntimeAdapterType.MANIFEST_ONLY, RuntimeAdapterType.SIMULATION])
        sql += " ORDER BY adapter_type"
        return [self._adapter(dict(r)) for r in self._exec(sql, p)]

    def update_adapter(self, adapter: RuntimeAdapter) -> None:
        self._exec("""UPDATE runtime_adapters SET
            name=?, description=?, supports_network=?, supports_user_data_read=?,
            supports_user_data_write=?, sandbox_required=?, max_timeout_ms=?,
            max_memory_mb=?, status=?, version=?, config_schema_json=?,
            metadata_json=?, updated_at=?
            WHERE adapter_id=?""", [
            adapter.name, adapter.description,
            int(adapter.supports_network), int(adapter.supports_user_data_read),
            int(adapter.supports_user_data_write), int(adapter.sandbox_required),
            adapter.max_timeout_ms, adapter.max_memory_mb,
            adapter.status, adapter.version,
            json.dumps(adapter.config_schema, ensure_ascii=False),
            json.dumps(adapter.metadata, ensure_ascii=False),
            datetime.now(timezone.utc).isoformat(),
            adapter.adapter_id,
        ])

    def set_adapter_status(self, adapter_id: str, status: str) -> bool:
        adapter = self.get_adapter(adapter_id)
        if adapter is None:
            return False
        self._exec(
            "UPDATE runtime_adapters SET status=?, updated_at=? WHERE adapter_id=?",
            [status, datetime.now(timezone.utc).isoformat(), adapter_id],
        )
        return True

    def seed_builtin_adapters(self) -> int:
        """初始化内置 Runtime Adapters。幂等。返回新增数量。"""
        created = 0
        updated = 0
        for data in _BUILTIN_ADAPTERS:
            adapter_id = data["adapter_id"]
            existing = self.get_adapter(adapter_id)
            adapter = RuntimeAdapter(
                adapter_id=adapter_id,
                adapter_type=str(data["adapter_type"]),
                name=str(data["name"]),
                description=str(data["description"]),
                supports_network=bool(data.get("supports_network", False)),
                supports_user_data_read=bool(data.get("supports_user_data_read", False)),
                supports_user_data_write=bool(data.get("supports_user_data_write", False)),
                sandbox_required=bool(data.get("sandbox_required", False)),
                max_timeout_ms=int(data.get("max_timeout_ms", 0)),
                max_memory_mb=int(data.get("max_memory_mb", 0)),
                status=str(data.get("status", RuntimeAdapterStatus.ACTIVE)),
                version=str(data.get("version", "1.0.0")),
                config_schema=dict(data.get("config_schema", {})),
                metadata=dict(data.get("metadata", {})),
            )
            if existing is None:
                self.create_adapter(adapter)
                created += 1
            else:
                # 更新但保留手动修改的 status（如果手动设为 active 则尊重）
                adapter.status = existing.status
                self.update_adapter(adapter)
                updated += 1

        logger.info("runtime_adapters_seeded", extra={"created_count": created, "updated_count": updated})
        return created

    # ═══════════════════════════════════════════
    # Binding CRUD
    # ═══════════════════════════════════════════

    def create_binding(self, binding: DeveloperAgentRuntimeBinding) -> DeveloperAgentRuntimeBinding:
        # 检查 adapter 存在
        adapter = self.get_adapter(binding.adapter_id)
        if adapter is None:
            raise RuntimeAdapterNotFoundError(
                f"Runtime Adapter 不存在: {binding.adapter_id}")

        # 检查 adapter_type 匹配
        if binding.adapter_type != adapter.adapter_type:
            raise RuntimeAdapterNotAllowedError(
                f"binding adapter_type '{binding.adapter_type}' 与 adapter "
                f"'{adapter.adapter_type}' 不匹配")

        # 检查重复 (marketplace_agent_id + tenant_id)
        existing = self.get_binding_by_marketplace_agent(
            binding.marketplace_agent_id, binding.tenant_id)
        if existing is not None:
            raise RuntimeBindingAlreadyExistsError(
                f"Runtime Binding 已存在: mkp={binding.marketplace_agent_id} "
                f"tenant={binding.tenant_id}")

        self._exec("""INSERT INTO developer_agent_runtime_bindings (
            binding_id, marketplace_agent_id, submission_id,
            developer_id, tenant_id, adapter_id, adapter_type,
            runtime_status, sandbox_policy_id,
            enabled_by, disabled_by, metadata_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""", [
            binding.binding_id,
            binding.marketplace_agent_id,
            binding.submission_id,
            binding.developer_id,
            binding.tenant_id,
            binding.adapter_id,
            binding.adapter_type,
            binding.runtime_status,
            binding.sandbox_policy_id,
            binding.enabled_by,
            binding.disabled_by,
            json.dumps(binding.metadata, ensure_ascii=False),
        ])
        return binding

    def get_binding(self, binding_id: str) -> DeveloperAgentRuntimeBinding | None:
        row = next(self._exec(
            "SELECT * FROM developer_agent_runtime_bindings WHERE binding_id=?",
            [binding_id]), None)
        return self._binding(dict(row)) if row else None

    def get_binding_by_marketplace_agent(
        self, marketplace_agent_id: str, tenant_id: str | None = None,
    ) -> DeveloperAgentRuntimeBinding | None:
        if tenant_id:
            row = next(self._exec(
                """SELECT * FROM developer_agent_runtime_bindings
                   WHERE marketplace_agent_id=? AND tenant_id=?""",
                [marketplace_agent_id, tenant_id]), None)
        else:
            row = next(self._exec(
                """SELECT * FROM developer_agent_runtime_bindings
                   WHERE marketplace_agent_id=?""",
                [marketplace_agent_id]), None)
        return self._binding(dict(row)) if row else None

    def list_bindings(
        self, *, developer_id: str = "", tenant_id: str = "",
        runtime_status: str = "", adapter_type: str = "",
    ) -> list[DeveloperAgentRuntimeBinding]:
        sql = "SELECT * FROM developer_agent_runtime_bindings WHERE 1=1"
        p: list[Any] = []
        if developer_id:
            sql += " AND developer_id=?"
            p.append(developer_id)
        if tenant_id:
            sql += " AND tenant_id=?"
            p.append(tenant_id)
        if runtime_status:
            sql += " AND runtime_status=?"
            p.append(runtime_status)
        if adapter_type:
            sql += " AND adapter_type=?"
            p.append(adapter_type)
        sql += " ORDER BY created_at DESC"
        return [self._binding(dict(r)) for r in self._exec(sql, p)]

    def update_binding(self, binding: DeveloperAgentRuntimeBinding) -> None:
        self._exec("""UPDATE developer_agent_runtime_bindings SET
            submission_id=?, adapter_id=?, adapter_type=?, runtime_status=?,
            sandbox_policy_id=?, enabled_by=?, disabled_by=?,
            metadata_json=?, updated_at=?
            WHERE binding_id=?""", [
            binding.submission_id,
            binding.adapter_id,
            binding.adapter_type,
            binding.runtime_status,
            binding.sandbox_policy_id,
            binding.enabled_by,
            binding.disabled_by,
            json.dumps(binding.metadata, ensure_ascii=False),
            datetime.now(timezone.utc).isoformat(),
            binding.binding_id,
        ])

    def enable_binding(self, binding_id: str, enabled_by: str) -> None:
        binding = self.get_binding(binding_id)
        if binding is None:
            raise RuntimeBindingNotFoundError(f"Runtime Binding 不存在: {binding_id}")

        adapter = self.get_adapter(binding.adapter_id)
        if adapter is None:
            raise RuntimeAdapterNotFoundError(
                f"关联的 Runtime Adapter 不存在: {binding.adapter_id}")

        if not adapter.is_active():
            raise RuntimeStateError(
                f"Adapter '{adapter.adapter_type}' 状态为 {adapter.status}，不可启用 binding")

        if not is_mvp_allowed_adapter_type(binding.adapter_type):
            raise RuntimeAdapterNotAllowedError(
                f"adapter_type '{binding.adapter_type}' 在 MVP 阶段不允许启用。"
                f"允许的类型: manifest_only, simulation")

        if adapter.sandbox_required and not binding.sandbox_policy_id:
            if binding.adapter_type not in (
                RuntimeAdapterType.MANIFEST_ONLY, RuntimeAdapterType.SIMULATION,
            ):
                raise RuntimeStateError(
                    f"adapter '{binding.adapter_type}' 要求 sandbox_policy_id")

        binding.runtime_status = RuntimeBindingStatus.ENABLED
        binding.enabled_by = enabled_by
        binding.disabled_by = None
        binding.updated_at = datetime.now(timezone.utc)
        self.update_binding(binding)

    def disable_binding(self, binding_id: str, disabled_by: str) -> None:
        binding = self.get_binding(binding_id)
        if binding is None:
            raise RuntimeBindingNotFoundError(f"Runtime Binding 不存在: {binding_id}")
        binding.runtime_status = RuntimeBindingStatus.DISABLED
        binding.disabled_by = disabled_by
        binding.updated_at = datetime.now(timezone.utc)
        self.update_binding(binding)

    def suspend_binding(self, binding_id: str, disabled_by: str) -> None:
        binding = self.get_binding(binding_id)
        if binding is None:
            raise RuntimeBindingNotFoundError(f"Runtime Binding 不存在: {binding_id}")
        binding.runtime_status = RuntimeBindingStatus.SUSPENDED
        binding.disabled_by = disabled_by
        binding.updated_at = datetime.now(timezone.utc)
        self.update_binding(binding)

    def set_binding_sandbox_policy(
        self, binding_id: str, sandbox_policy_id: str,
    ) -> None:
        binding = self.get_binding(binding_id)
        if binding is None:
            raise RuntimeBindingNotFoundError(f"Runtime Binding 不存在: {binding_id}")
        binding.sandbox_policy_id = sandbox_policy_id
        binding.updated_at = datetime.now(timezone.utc)
        self.update_binding(binding)

    # ═══════════════════════════════════════════
    # Eligibility
    # ═══════════════════════════════════════════

    def get_runtime_eligibility(
        self, marketplace_agent_id: str, tenant_id: str | None = None,
    ) -> RuntimeEligibilityResult:
        """评估 Developer Agent 的 Runtime eligibility。

        不执行代码，不调用 AgentRuntime，不注册 AgentRegistry。
        """
        binding = self.get_binding_by_marketplace_agent(marketplace_agent_id, tenant_id)

        # No binding
        if binding is None:
            return RuntimeEligibilityResult.not_found(marketplace_agent_id)

        base = RuntimeEligibilityResult(
            marketplace_agent_id=marketplace_agent_id,
            binding_id=binding.binding_id,
            adapter_id=binding.adapter_id,
            adapter_type=binding.adapter_type,
        )

        # Check runtime_status
        if binding.runtime_status == RuntimeBindingStatus.PENDING:
            base.code = RuntimeEligibilityCode.BINDING_DISABLED
            base.message = "Runtime binding is pending (not yet enabled)."
            base.required_action = "Admin must enable this runtime binding."
            return base

        if binding.runtime_status == RuntimeBindingStatus.DISABLED:
            base.code = RuntimeEligibilityCode.BINDING_DISABLED
            base.message = "Runtime binding is disabled."
            base.required_action = "Admin must enable this runtime binding."
            return base

        if binding.runtime_status == RuntimeBindingStatus.SUSPENDED:
            base.code = RuntimeEligibilityCode.BINDING_DISABLED
            base.message = "Runtime binding is suspended."
            base.required_action = "Admin must re-enable this runtime binding."
            return base

        # Check adapter
        adapter = self.get_adapter(binding.adapter_id)
        if adapter is None:
            base.code = RuntimeEligibilityCode.ADAPTER_DISABLED
            base.message = "Runtime adapter not found."
            base.required_action = "Contact system administrator."
            return base

        if not adapter.is_active():
            base.code = RuntimeEligibilityCode.ADAPTER_DISABLED
            base.message = f"Runtime adapter '{adapter.adapter_type}' is {adapter.status}."
            base.required_action = "Admin must activate this adapter."
            return base

        if not is_mvp_allowed_adapter_type(adapter.adapter_type):
            base.code = RuntimeEligibilityCode.ADAPTER_NOT_ALLOWED
            base.message = (
                f"Adapter type '{adapter.adapter_type}' is not allowed in MVP."
                f" Allowed: manifest_only, simulation."
            )
            base.required_action = "Wait for future adapter support (Step 24+)."
            return base

        # Sandbox policy required
        if adapter.sandbox_required and not binding.sandbox_policy_id:
            if adapter.adapter_type not in (
                RuntimeAdapterType.MANIFEST_ONLY, RuntimeAdapterType.SIMULATION,
            ):
                base.code = RuntimeEligibilityCode.SANDBOX_POLICY_REQUIRED
                base.message = (
                    f"Adapter '{adapter.adapter_type}' requires a sandbox policy "
                    f"but none is assigned."
                )
                base.required_action = "Admin must assign a sandbox policy."
                return base

        # Eligible
        base.eligible = True
        base.code = RuntimeEligibilityCode.ELIGIBLE
        base.message = (
            f"Developer agent is eligible for runtime via "
            f"adapter '{adapter.adapter_type}'."
        )
        base.metadata = {
            "adapter_status": adapter.status,
            "adapter_sandbox_required": adapter.sandbox_required,
            "adapter_max_timeout_ms": adapter.max_timeout_ms,
            "binding_status": binding.runtime_status,
            "simulation": adapter.adapter_type == RuntimeAdapterType.SIMULATION,
            "manifest_only": adapter.adapter_type == RuntimeAdapterType.MANIFEST_ONLY,
        }
        return base

    # ═══════════════════════════════════════════
    # Converters
    # ═══════════════════════════════════════════

    @staticmethod
    def _adapter(row: dict) -> RuntimeAdapter:
        return RuntimeAdapter(
            adapter_id=row["adapter_id"],
            adapter_type=row["adapter_type"],
            name=row.get("name", ""),
            description=row.get("description", ""),
            supports_network=bool(row.get("supports_network", 0)),
            supports_user_data_read=bool(row.get("supports_user_data_read", 0)),
            supports_user_data_write=bool(row.get("supports_user_data_write", 0)),
            sandbox_required=bool(row.get("sandbox_required", 0)),
            max_timeout_ms=int(row.get("max_timeout_ms", 0)),
            max_memory_mb=int(row.get("max_memory_mb", 0)),
            status=row.get("status", "active"),
            version=row.get("version", "1.0.0"),
            config_schema=json.loads(row.get("config_schema_json", "{}")),
            metadata=json.loads(row.get("metadata_json", "{}")),
            created_at=_safe_parse_datetime(row.get("created_at")),
            updated_at=_safe_parse_datetime(row.get("updated_at")),
        )

    @staticmethod
    def _binding(row: dict) -> DeveloperAgentRuntimeBinding:
        return DeveloperAgentRuntimeBinding(
            binding_id=row["binding_id"],
            marketplace_agent_id=row["marketplace_agent_id"],
            submission_id=row.get("submission_id"),
            developer_id=row["developer_id"],
            tenant_id=row["tenant_id"],
            adapter_id=row["adapter_id"],
            adapter_type=row["adapter_type"],
            runtime_status=row.get("runtime_status", "pending"),
            sandbox_policy_id=row.get("sandbox_policy_id"),
            enabled_by=row.get("enabled_by"),
            disabled_by=row.get("disabled_by"),
            metadata=json.loads(row.get("metadata_json", "{}")),
            created_at=_safe_parse_datetime(row.get("created_at")),
            updated_at=_safe_parse_datetime(row.get("updated_at")),
        )
