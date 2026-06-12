"""SQLite Runtime Execution Plan Store — 实现 RuntimeExecutionPlanStore 协议。

Step 24-D:
- runtime_execution_plans + runtime_execution_plan_audit_events 表
- 状态变更自动 audit
- 不物理删除 / 不 dispatch / 不执行 / 不联网
"""

from __future__ import annotations

import json, logging
from datetime import datetime, timezone
from typing import Any

from src.adapters.config import Settings
from src.adapters.sqlite_connection import create_sqlite_db, execute_with_retry
from src.open_platform.runtime_execution_plan import (
    RuntimeExecutionPlan, RuntimeExecutionPlanAuditEvent,
    RuntimeExecutionPlanAuditEventType, RuntimeExecutionPlanAlreadyExistsError,
    RuntimeExecutionPlanNotFoundError, RuntimeExecutionPlanStateError,
    RuntimeExecutionPlanError,
)

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runtime_execution_plans (
    plan_id TEXT PRIMARY KEY,
    marketplace_agent_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    user_id TEXT,
    developer_id TEXT NOT NULL,
    submission_id TEXT,
    runtime_binding_id TEXT,
    adapter_id TEXT,
    adapter_type TEXT,
    sandbox_policy_id TEXT,
    artifact_id TEXT,
    verification_id TEXT,
    execution_mode TEXT NOT NULL DEFAULT 'sandbox_reserved',
    plan_status TEXT NOT NULL DEFAULT 'draft',
    dispatch_status TEXT NOT NULL DEFAULT 'reserved_for_step24e',
    decision TEXT NOT NULL DEFAULT 'reserved_only',
    risk_level TEXT NOT NULL DEFAULT 'unknown',
    checks_json TEXT NOT NULL DEFAULT '[]',
    warnings_count INTEGER NOT NULL DEFAULT 0,
    errors_count INTEGER NOT NULL DEFAULT 0,
    blockers_count INTEGER NOT NULL DEFAULT 0,
    input_payload_hash TEXT,
    output_contract_json TEXT NOT NULL DEFAULT '{}',
    policy_snapshot_json TEXT NOT NULL DEFAULT '{}',
    artifact_snapshot_json TEXT NOT NULL DEFAULT '{}',
    verification_snapshot_json TEXT NOT NULL DEFAULT '{}',
    no_download_planned INTEGER NOT NULL DEFAULT 1,
    no_network_planned INTEGER NOT NULL DEFAULT 1,
    no_execution_performed INTEGER NOT NULL DEFAULT 1,
    worker_required INTEGER NOT NULL DEFAULT 0,
    worker_available INTEGER NOT NULL DEFAULT 0,
    expires_at TEXT,
    created_by TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_replan_tenant ON runtime_execution_plans(tenant_id);
CREATE INDEX IF NOT EXISTS idx_replan_marketplace_agent ON runtime_execution_plans(marketplace_agent_id);
CREATE INDEX IF NOT EXISTS idx_replan_developer ON runtime_execution_plans(developer_id);
CREATE INDEX IF NOT EXISTS idx_replan_status ON runtime_execution_plans(plan_status);
CREATE INDEX IF NOT EXISTS idx_replan_decision ON runtime_execution_plans(decision);
CREATE INDEX IF NOT EXISTS idx_replan_artifact ON runtime_execution_plans(artifact_id);
CREATE INDEX IF NOT EXISTS idx_replan_verification ON runtime_execution_plans(verification_id);
CREATE INDEX IF NOT EXISTS idx_replan_created_at ON runtime_execution_plans(created_at);

CREATE TABLE IF NOT EXISTS runtime_execution_plan_audit_events (
    event_id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    actor_id TEXT,
    message TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_replan_ae_plan ON runtime_execution_plan_audit_events(plan_id);
CREATE INDEX IF NOT EXISTS idx_replan_ae_tenant ON runtime_execution_plan_audit_events(tenant_id);
CREATE INDEX IF NOT EXISTS idx_replan_ae_type ON runtime_execution_plan_audit_events(event_type);
CREATE INDEX IF NOT EXISTS idx_replan_ae_created_at ON runtime_execution_plan_audit_events(created_at);
"""


class SQLiteRuntimeExecutionPlanStore:
    def __init__(self, config: Settings, db_path: str | None = None):
        path = db_path or config.sqlite_db_path
        self._db = create_sqlite_db(path)
        execute_with_retry(lambda: self._init_schema(), label="rt_execution_plan_init_schema")

    def _init_schema(self):
        for stmt in _SCHEMA.strip().split(";"):
            s = stmt.strip()
            if s: self._db.execute(s)
        try: self._db.conn.commit()
        except Exception: pass

    def flush(self) -> None:
        try:
            if hasattr(self._db, "conn") and self._db.conn: self._db.conn.commit()
        except Exception: pass

    def _exec(self, sql: str, params=None): return self._db.execute(sql, params or [])

    def _audit(self, plan_id: str, tenant_id: str, event_type: str, actor_id: str | None = None,
               message: str = "", meta: dict[str, Any] | None = None):
        evt = RuntimeExecutionPlanAuditEvent(plan_id=plan_id, tenant_id=tenant_id, event_type=event_type,
                                             actor_id=actor_id, message=message, metadata=meta or {})
        self.add_audit_event(evt)

    # ── Plan CRUD ──

    def create_plan(self, plan: RuntimeExecutionPlan) -> RuntimeExecutionPlan:
        self._exec("""INSERT INTO runtime_execution_plans (
            plan_id, marketplace_agent_id, tenant_id, user_id, developer_id,
            submission_id, runtime_binding_id, adapter_id, adapter_type,
            sandbox_policy_id, artifact_id, verification_id,
            execution_mode, plan_status, dispatch_status, decision, risk_level,
            checks_json, warnings_count, errors_count, blockers_count,
            input_payload_hash, output_contract_json,
            policy_snapshot_json, artifact_snapshot_json, verification_snapshot_json,
            no_download_planned, no_network_planned, no_execution_performed,
            worker_required, worker_available,
            expires_at, created_by, created_at, updated_at, metadata_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", [
            plan.plan_id, plan.marketplace_agent_id, plan.tenant_id, plan.user_id, plan.developer_id,
            plan.submission_id, plan.runtime_binding_id, plan.adapter_id, plan.adapter_type,
            plan.sandbox_policy_id, plan.artifact_id, plan.verification_id,
            plan.execution_mode, plan.plan_status, plan.dispatch_status, plan.decision, plan.risk_level,
            json.dumps([c.to_dict() for c in plan.checks], ensure_ascii=False),
            plan.warnings_count, plan.errors_count, plan.blockers_count,
            plan.input_payload_hash,
            json.dumps(plan.output_contract, ensure_ascii=False),
            json.dumps(plan.policy_snapshot, ensure_ascii=False),
            json.dumps(plan.artifact_snapshot, ensure_ascii=False),
            json.dumps(plan.verification_snapshot, ensure_ascii=False),
            int(plan.no_download_planned), int(plan.no_network_planned), int(plan.no_execution_performed),
            int(plan.worker_required), int(plan.worker_available),
            plan.expires_at.isoformat() if plan.expires_at else None,
            plan.created_by,
            plan.created_at.isoformat() if plan.created_at else datetime.now(timezone.utc).isoformat(),
            plan.updated_at.isoformat() if plan.updated_at else datetime.now(timezone.utc).isoformat(),
            json.dumps(plan.metadata, ensure_ascii=False),
        ])
        self._audit(plan.plan_id, plan.tenant_id, RuntimeExecutionPlanAuditEventType.CREATED, plan.created_by,
                    f"Plan created for {plan.marketplace_agent_id}")
        return plan

    def get_plan(self, plan_id: str) -> RuntimeExecutionPlan | None:
        row = next(self._exec("SELECT * FROM runtime_execution_plans WHERE plan_id=?", [plan_id]), None)
        return self._row_to_plan(dict(row)) if row else None

    def list_plans(self, *, tenant_id="", marketplace_agent_id="", developer_id="",
                   status="", decision="") -> list[RuntimeExecutionPlan]:
        sql, p = "SELECT * FROM runtime_execution_plans WHERE 1=1", []
        if tenant_id: sql += " AND tenant_id=?"; p.append(tenant_id)
        if marketplace_agent_id: sql += " AND marketplace_agent_id=?"; p.append(marketplace_agent_id)
        if developer_id: sql += " AND developer_id=?"; p.append(developer_id)
        if status: sql += " AND plan_status=?"; p.append(status)
        if decision: sql += " AND decision=?"; p.append(decision)
        return [self._row_to_plan(dict(r)) for r in self._exec(sql + " ORDER BY created_at DESC", p)]

    def update_plan(self, plan: RuntimeExecutionPlan) -> RuntimeExecutionPlan:
        plan.updated_at = datetime.now(timezone.utc)
        self._exec("""UPDATE runtime_execution_plans SET
            execution_mode=?, plan_status=?, dispatch_status=?, decision=?, risk_level=?,
            checks_json=?, warnings_count=?, errors_count=?, blockers_count=?,
            input_payload_hash=?, output_contract_json=?,
            policy_snapshot_json=?, artifact_snapshot_json=?, verification_snapshot_json=?,
            worker_required=?, worker_available=?, expires_at=?, updated_at=?, metadata_json=?
            WHERE plan_id=?""", [
            plan.execution_mode, plan.plan_status, plan.dispatch_status, plan.decision, plan.risk_level,
            json.dumps([c.to_dict() for c in plan.checks], ensure_ascii=False),
            plan.warnings_count, plan.errors_count, plan.blockers_count,
            plan.input_payload_hash,
            json.dumps(plan.output_contract, ensure_ascii=False),
            json.dumps(plan.policy_snapshot, ensure_ascii=False),
            json.dumps(plan.artifact_snapshot, ensure_ascii=False),
            json.dumps(plan.verification_snapshot, ensure_ascii=False),
            int(plan.worker_required), int(plan.worker_available),
            plan.expires_at.isoformat() if plan.expires_at else None,
            plan.updated_at.isoformat(),
            json.dumps(plan.metadata, ensure_ascii=False),
            plan.plan_id,
        ])
        return plan

    def set_plan_status(self, plan_id: str, status: str, actor_id=None, reason=None) -> RuntimeExecutionPlan:
        plan = self.get_plan(plan_id)
        if plan is None: raise RuntimeExecutionPlanNotFoundError(f"Plan not found: {plan_id}")
        old = plan.plan_status; plan.plan_status = status; self.update_plan(plan)
        self._audit(plan_id, plan.tenant_id, RuntimeExecutionPlanAuditEventType.STATUS_CHANGED,
                    actor_id, f"Status: {old} -> {status}" + (f" (reason: {reason})" if reason else ""))
        return plan

    def cancel_plan(self, plan_id: str, actor_id=None, reason=None) -> RuntimeExecutionPlan:
        plan = self.get_plan(plan_id)
        if plan is None: raise RuntimeExecutionPlanNotFoundError(f"Plan not found: {plan_id}")
        plan.plan_status = RuntimeExecutionPlanAuditEventType.CANCELLED.value if hasattr(RuntimeExecutionPlanAuditEventType, 'CANCELLED') else "cancelled"
        from src.open_platform.runtime_execution_plan import RuntimeExecutionPlanStatus
        plan.plan_status = RuntimeExecutionPlanStatus.CANCELLED; self.update_plan(plan)
        self._audit(plan_id, plan.tenant_id, RuntimeExecutionPlanAuditEventType.CANCELLED,
                    actor_id, f"Plan cancelled" + (f" (reason: {reason})" if reason else ""))
        return plan

    def expire_plan(self, plan_id: str, actor_id=None, reason=None) -> RuntimeExecutionPlan:
        plan = self.get_plan(plan_id)
        if plan is None: raise RuntimeExecutionPlanNotFoundError(f"Plan not found: {plan_id}")
        from src.open_platform.runtime_execution_plan import RuntimeExecutionPlanStatus
        plan.plan_status = RuntimeExecutionPlanStatus.EXPIRED; self.update_plan(plan)
        self._audit(plan_id, plan.tenant_id, RuntimeExecutionPlanAuditEventType.EXPIRED,
                    actor_id, f"Plan expired" + (f" (reason: {reason})" if reason else ""))
        return plan

    def count_plans(self, *, tenant_id="", status="", decision="") -> int:
        sql, p = "SELECT COUNT(*) as cnt FROM runtime_execution_plans WHERE 1=1", []
        if tenant_id: sql += " AND tenant_id=?"; p.append(tenant_id)
        if status: sql += " AND plan_status=?"; p.append(status)
        if decision: sql += " AND decision=?"; p.append(decision)
        row = next(self._exec(sql, p), None); return row["cnt"] if row else 0

    # ── Audit ──

    def add_audit_event(self, event: RuntimeExecutionPlanAuditEvent) -> RuntimeExecutionPlanAuditEvent:
        self._exec("""INSERT INTO runtime_execution_plan_audit_events (
            event_id, plan_id, tenant_id, event_type, actor_id, message, metadata_json, created_at
        ) VALUES (?,?,?,?,?,?,?,?)""", [
            event.event_id, event.plan_id, event.tenant_id, event.event_type,
            event.actor_id, event.message,
            json.dumps(event.metadata, ensure_ascii=False),
            event.created_at.isoformat() if event.created_at else datetime.now(timezone.utc).isoformat(),
        ])
        return event

    def list_audit_events(self, plan_id: str) -> list[RuntimeExecutionPlanAuditEvent]:
        rows = self._exec(
            "SELECT * FROM runtime_execution_plan_audit_events WHERE plan_id=? ORDER BY created_at ASC", [plan_id])
        return [self._row_to_audit(dict(r)) for r in rows]

    # ── Row converters ──

    @staticmethod
    def _row_to_plan(row: dict) -> RuntimeExecutionPlan:
        from src.open_platform.runtime_execution_plan import RuntimeExecutionPlanCheck
        checks = [RuntimeExecutionPlanCheck.from_dict(c) for c in json.loads(row.get("checks_json", "[]"))]
        return RuntimeExecutionPlan(
            plan_id=row["plan_id"], marketplace_agent_id=row["marketplace_agent_id"],
            tenant_id=row["tenant_id"], user_id=row.get("user_id"),
            developer_id=row["developer_id"], submission_id=row.get("submission_id"),
            runtime_binding_id=row.get("runtime_binding_id"), adapter_id=row.get("adapter_id"),
            adapter_type=row.get("adapter_type"), sandbox_policy_id=row.get("sandbox_policy_id"),
            artifact_id=row.get("artifact_id"), verification_id=row.get("verification_id"),
            execution_mode=row.get("execution_mode", "sandbox_reserved"),
            plan_status=row.get("plan_status", "draft"),
            dispatch_status=row.get("dispatch_status", "reserved_for_step24e"),
            decision=row.get("decision", "reserved_only"), risk_level=row.get("risk_level", "unknown"),
            checks=checks, warnings_count=int(row.get("warnings_count", 0)),
            errors_count=int(row.get("errors_count", 0)), blockers_count=int(row.get("blockers_count", 0)),
            input_payload_hash=row.get("input_payload_hash"),
            output_contract=json.loads(row.get("output_contract_json", "{}")),
            policy_snapshot=json.loads(row.get("policy_snapshot_json", "{}")),
            artifact_snapshot=json.loads(row.get("artifact_snapshot_json", "{}")),
            verification_snapshot=json.loads(row.get("verification_snapshot_json", "{}")),
            no_download_planned=bool(row.get("no_download_planned", 1)),
            no_network_planned=bool(row.get("no_network_planned", 1)),
            no_execution_performed=bool(row.get("no_execution_performed", 1)),
            worker_required=bool(row.get("worker_required", 0)),
            worker_available=bool(row.get("worker_available", 0)),
            expires_at=_safe_dt(row.get("expires_at"), none_ok=True),
            created_by=row.get("created_by"),
            created_at=_safe_dt(row.get("created_at")), updated_at=_safe_dt(row.get("updated_at")),
            metadata=json.loads(row.get("metadata_json", "{}")),
        )

    @staticmethod
    def _row_to_audit(row: dict) -> RuntimeExecutionPlanAuditEvent:
        return RuntimeExecutionPlanAuditEvent(
            event_id=row["event_id"], plan_id=row["plan_id"], tenant_id=row["tenant_id"],
            event_type=row.get("event_type", ""), actor_id=row.get("actor_id"),
            message=row.get("message", ""), metadata=json.loads(row.get("metadata_json", "{}")),
            created_at=_safe_dt(row.get("created_at")),
        )


def _safe_dt(raw: str | None, none_ok: bool = False) -> datetime | None:
    if not raw: return None if none_ok else datetime.now(timezone.utc)
    try: return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (ValueError, TypeError): return None if none_ok else datetime.now(timezone.utc)
