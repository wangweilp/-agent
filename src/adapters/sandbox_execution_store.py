"""SQLite Sandbox Execution Store — audit-only execution records。Step 25-B: no queue/dispatch/execute。"""
from __future__ import annotations
import json, logging
from datetime import datetime, timezone
from typing import Any
from src.adapters.config import Settings
from src.adapters.sqlite_connection import create_sqlite_db, execute_with_retry
from src.open_platform.sandbox_execution import (
    SandboxExecutionRecord, SandboxExecutionAuditEvent, SandboxExecutionAuditEventType,
    SandboxExecutionAuditSeverity, SandboxExecutionAlreadyExistsError,
    SandboxExecutionNotFoundError, SandboxExecutionStateError,
    SandboxExecutionStatus, SandboxExecutionDecision, SandboxExecutionQueueStatus,
)

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sandbox_executions (
    execution_id TEXT PRIMARY KEY, plan_id TEXT NOT NULL, gate_id TEXT,
    marketplace_agent_id TEXT NOT NULL, tenant_id TEXT NOT NULL, user_id TEXT,
    developer_id TEXT NOT NULL, submission_id TEXT, artifact_id TEXT,
    verification_id TEXT, sandbox_policy_id TEXT, runtime_binding_id TEXT,
    worker_type TEXT, execution_status TEXT NOT NULL DEFAULT 'draft',
    decision TEXT NOT NULL DEFAULT 'blocked', queue_status TEXT NOT NULL DEFAULT 'queue_disabled',
    risk_level TEXT NOT NULL DEFAULT 'unknown', input_payload_hash TEXT,
    plan_snapshot_json TEXT NOT NULL DEFAULT '{}', gate_snapshot_json TEXT NOT NULL DEFAULT '{}',
    policy_config_snapshot_json TEXT NOT NULL DEFAULT '{}',
    artifact_snapshot_json TEXT NOT NULL DEFAULT '{}',
    verification_snapshot_json TEXT NOT NULL DEFAULT '{}',
    worker_request_snapshot_json TEXT NOT NULL DEFAULT '{}',
    no_execution_performed INTEGER NOT NULL DEFAULT 1,
    no_download_used INTEGER NOT NULL DEFAULT 1, no_network_used INTEGER NOT NULL DEFAULT 1,
    no_subprocess_used INTEGER NOT NULL DEFAULT 1, no_container_used INTEGER NOT NULL DEFAULT 1,
    no_queue_created INTEGER NOT NULL DEFAULT 1, no_job_dispatched INTEGER NOT NULL DEFAULT 1,
    no_agent_runtime_used INTEGER NOT NULL DEFAULT 1, no_agent_registry_used INTEGER NOT NULL DEFAULT 1,
    created_by TEXT, cancelled_by TEXT, expired_by TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    cancelled_at TEXT, expired_at TEXT, expires_at TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_sbxexec_plan ON sandbox_executions(plan_id);
CREATE INDEX IF NOT EXISTS idx_sbxexec_tenant ON sandbox_executions(tenant_id);
CREATE INDEX IF NOT EXISTS idx_sbxexec_marketplace_agent ON sandbox_executions(marketplace_agent_id);
CREATE INDEX IF NOT EXISTS idx_sbxexec_developer ON sandbox_executions(developer_id);
CREATE INDEX IF NOT EXISTS idx_sbxexec_status ON sandbox_executions(execution_status);
CREATE INDEX IF NOT EXISTS idx_sbxexec_decision ON sandbox_executions(decision);
CREATE INDEX IF NOT EXISTS idx_sbxexec_queue_status ON sandbox_executions(queue_status);
CREATE INDEX IF NOT EXISTS idx_sbxexec_artifact ON sandbox_executions(artifact_id);
CREATE INDEX IF NOT EXISTS idx_sbxexec_verification ON sandbox_executions(verification_id);
CREATE INDEX IF NOT EXISTS idx_sbxexec_created_at ON sandbox_executions(created_at);

CREATE TABLE IF NOT EXISTS sandbox_execution_audit_events (
    event_id TEXT PRIMARY KEY, execution_id TEXT NOT NULL, tenant_id TEXT NOT NULL,
    event_type TEXT NOT NULL, severity TEXT NOT NULL DEFAULT 'info',
    actor_id TEXT, message TEXT NOT NULL DEFAULT '', metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_sbxevt_execution ON sandbox_execution_audit_events(execution_id);
CREATE INDEX IF NOT EXISTS idx_sbxevt_tenant ON sandbox_execution_audit_events(tenant_id);
CREATE INDEX IF NOT EXISTS idx_sbxevt_type ON sandbox_execution_audit_events(event_type);
CREATE INDEX IF NOT EXISTS idx_sbxevt_created_at ON sandbox_execution_audit_events(created_at);
"""

class SQLiteSandboxExecutionStore:
    def __init__(self, config: Settings, db_path: str | None = None):
        path = db_path or config.sqlite_db_path
        self._db = create_sqlite_db(path)
        execute_with_retry(lambda: self._init_schema(), label="sbx_exec_init_schema")

    def _init_schema(self):
        for stmt in _SCHEMA.strip().split(";"):
            s = stmt.strip()
            if s: self._db.execute(s)
        try: self._db.conn.commit()
        except Exception: pass

    def flush(self) -> None:
        try:
            if hasattr(self._db,"conn") and self._db.conn: self._db.conn.commit()
        except Exception: pass

    def _exec(self, sql, params=None): return self._db.execute(sql, params or [])

    def _audit(self, execution_id, tenant_id, event_type, actor_id=None, message="", severity="info", meta=None):
        evt = SandboxExecutionAuditEvent(execution_id=execution_id, tenant_id=tenant_id,
            event_type=event_type, severity=severity, actor_id=actor_id, message=message, metadata=meta or {})
        self.add_audit_event(evt)

    # ── CRUD ──

    def create_execution(self, record: SandboxExecutionRecord) -> SandboxExecutionRecord:
        self._exec("""INSERT INTO sandbox_executions (
            execution_id,plan_id,gate_id,marketplace_agent_id,tenant_id,user_id,developer_id,
            submission_id,artifact_id,verification_id,sandbox_policy_id,runtime_binding_id,worker_type,
            execution_status,decision,queue_status,risk_level,input_payload_hash,
            plan_snapshot_json,gate_snapshot_json,policy_config_snapshot_json,
            artifact_snapshot_json,verification_snapshot_json,worker_request_snapshot_json,
            no_execution_performed,no_download_used,no_network_used,no_subprocess_used,
            no_container_used,no_queue_created,no_job_dispatched,no_agent_runtime_used,
            no_agent_registry_used,created_by,cancelled_by,expired_by,
            created_at,updated_at,cancelled_at,expired_at,expires_at,metadata_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", [
            record.execution_id,record.plan_id,record.gate_id,record.marketplace_agent_id,
            record.tenant_id,record.user_id,record.developer_id,record.submission_id,
            record.artifact_id,record.verification_id,record.sandbox_policy_id,
            record.runtime_binding_id,record.worker_type,record.execution_status,record.decision,
            record.queue_status,record.risk_level,record.input_payload_hash,
            json.dumps(record.plan_snapshot,ensure_ascii=False),
            json.dumps(record.gate_snapshot,ensure_ascii=False),
            json.dumps(record.policy_config_snapshot,ensure_ascii=False),
            json.dumps(record.artifact_snapshot,ensure_ascii=False),
            json.dumps(record.verification_snapshot,ensure_ascii=False),
            json.dumps(record.worker_request_snapshot,ensure_ascii=False),
            int(record.no_execution_performed),int(record.no_download_used),int(record.no_network_used),
            int(record.no_subprocess_used),int(record.no_container_used),int(record.no_queue_created),
            int(record.no_job_dispatched),int(record.no_agent_runtime_used),int(record.no_agent_registry_used),
            record.created_by,record.cancelled_by,record.expired_by,
            record.created_at.isoformat() if record.created_at else datetime.now(timezone.utc).isoformat(),
            record.updated_at.isoformat() if record.updated_at else datetime.now(timezone.utc).isoformat(),
            record.cancelled_at.isoformat() if record.cancelled_at else None,
            record.expired_at.isoformat() if record.expired_at else None,
            record.expires_at.isoformat() if record.expires_at else None,
            json.dumps(record.metadata,ensure_ascii=False),
        ])
        self._audit(record.execution_id,record.tenant_id,SandboxExecutionAuditEventType.CREATED,
            record.created_by,f"Execution record created for plan {record.plan_id}")
        return record

    def get_execution(self, execution_id: str) -> SandboxExecutionRecord | None:
        row = next(self._exec("SELECT * FROM sandbox_executions WHERE execution_id=?", [execution_id]), None)
        return self._row_to_record(dict(row)) if row else None

    def list_executions(self, *, tenant_id="", marketplace_agent_id="", developer_id="",
                        status="", decision="", queue_status="") -> list[SandboxExecutionRecord]:
        sql, p = "SELECT * FROM sandbox_executions WHERE 1=1", []
        if tenant_id: sql += " AND tenant_id=?"; p.append(tenant_id)
        if marketplace_agent_id: sql += " AND marketplace_agent_id=?"; p.append(marketplace_agent_id)
        if developer_id: sql += " AND developer_id=?"; p.append(developer_id)
        if status: sql += " AND execution_status=?"; p.append(status)
        if decision: sql += " AND decision=?"; p.append(decision)
        if queue_status: sql += " AND queue_status=?"; p.append(queue_status)
        return [self._row_to_record(dict(r)) for r in self._exec(sql + " ORDER BY created_at DESC", p)]

    def update_execution(self, record: SandboxExecutionRecord) -> SandboxExecutionRecord:
        record.updated_at = datetime.now(timezone.utc)
        self._exec("""UPDATE sandbox_executions SET
            execution_status=?,decision=?,queue_status=?,risk_level=?,input_payload_hash=?,
            plan_snapshot_json=?,gate_snapshot_json=?,policy_config_snapshot_json=?,
            artifact_snapshot_json=?,verification_snapshot_json=?,worker_request_snapshot_json=?,
            updated_at=?,cancelled_at=?,expired_at=?,metadata_json=? WHERE execution_id=?""", [
            record.execution_status,record.decision,record.queue_status,record.risk_level,
            record.input_payload_hash,
            json.dumps(record.plan_snapshot,ensure_ascii=False),
            json.dumps(record.gate_snapshot,ensure_ascii=False),
            json.dumps(record.policy_config_snapshot,ensure_ascii=False),
            json.dumps(record.artifact_snapshot,ensure_ascii=False),
            json.dumps(record.verification_snapshot,ensure_ascii=False),
            json.dumps(record.worker_request_snapshot,ensure_ascii=False),
            record.updated_at.isoformat(),
            record.cancelled_at.isoformat() if record.cancelled_at else None,
            record.expired_at.isoformat() if record.expired_at else None,
            json.dumps(record.metadata,ensure_ascii=False),
            record.execution_id,
        ])
        return record

    def set_execution_status(self, execution_id, status, actor_id=None, reason=None):
        rec = self.get_execution(execution_id)
        if rec is None: raise SandboxExecutionNotFoundError(f"Execution not found: {execution_id}")
        old = rec.execution_status; rec.execution_status = status; self.update_execution(rec)
        self._audit(execution_id,rec.tenant_id,SandboxExecutionAuditEventType.STATUS_CHANGED,
            actor_id,f"Status: {old} -> {status}" + (f" (reason: {reason})" if reason else ""))
        return rec

    def set_decision(self, execution_id, decision, actor_id=None, reason=None):
        rec = self.get_execution(execution_id)
        if rec is None: raise SandboxExecutionNotFoundError(f"Execution not found: {execution_id}")
        old = rec.decision; rec.decision = decision; self.update_execution(rec)
        self._audit(execution_id,rec.tenant_id,SandboxExecutionAuditEventType.DECISION_CHANGED,
            actor_id,f"Decision: {old} -> {decision}" + (f" (reason: {reason})" if reason else ""))
        return rec

    def set_queue_status(self, execution_id, queue_status, actor_id=None, reason=None):
        rec = self.get_execution(execution_id)
        if rec is None: raise SandboxExecutionNotFoundError(f"Execution not found: {execution_id}")
        old = rec.queue_status; rec.queue_status = queue_status; self.update_execution(rec)
        self._audit(execution_id,rec.tenant_id,SandboxExecutionAuditEventType.QUEUE_STATUS_CHANGED,
            actor_id,f"Queue status: {old} -> {queue_status}" + (f" (reason: {reason})" if reason else ""))
        return rec

    def cancel_execution(self, execution_id, actor_id=None, reason=None):
        rec = self.get_execution(execution_id)
        if rec is None: raise SandboxExecutionNotFoundError(f"Execution not found: {execution_id}")
        rec.execution_status = SandboxExecutionStatus.CANCELLED; rec.cancelled_by = actor_id
        rec.cancelled_at = datetime.now(timezone.utc); self.update_execution(rec)
        self._audit(execution_id,rec.tenant_id,SandboxExecutionAuditEventType.CANCELLED,
            actor_id,f"Execution cancelled" + (f" (reason: {reason})" if reason else ""))
        return rec

    def expire_execution(self, execution_id, actor_id=None, reason=None):
        rec = self.get_execution(execution_id)
        if rec is None: raise SandboxExecutionNotFoundError(f"Execution not found: {execution_id}")
        rec.execution_status = SandboxExecutionStatus.EXPIRED; rec.expired_by = actor_id
        rec.expired_at = datetime.now(timezone.utc); self.update_execution(rec)
        self._audit(execution_id,rec.tenant_id,SandboxExecutionAuditEventType.EXPIRED,
            actor_id,f"Execution expired" + (f" (reason: {reason})" if reason else ""))
        return rec

    def count_executions(self, *, tenant_id="", status="", decision="", queue_status="") -> int:
        sql, p = "SELECT COUNT(*) as cnt FROM sandbox_executions WHERE 1=1", []
        if tenant_id: sql += " AND tenant_id=?"; p.append(tenant_id)
        if status: sql += " AND execution_status=?"; p.append(status)
        if decision: sql += " AND decision=?"; p.append(decision)
        if queue_status: sql += " AND queue_status=?"; p.append(queue_status)
        row = next(self._exec(sql, p), None); return row["cnt"] if row else 0

    def add_audit_event(self, event: SandboxExecutionAuditEvent) -> SandboxExecutionAuditEvent:
        self._exec("""INSERT INTO sandbox_execution_audit_events (
            event_id,execution_id,tenant_id,event_type,severity,actor_id,message,metadata_json,created_at
        ) VALUES (?,?,?,?,?,?,?,?,?)""", [
            event.event_id,event.execution_id,event.tenant_id,event.event_type,event.severity,
            event.actor_id,event.message,json.dumps(event.metadata,ensure_ascii=False),
            event.created_at.isoformat() if event.created_at else datetime.now(timezone.utc).isoformat(),
        ])
        return event

    def list_audit_events(self, execution_id: str) -> list[SandboxExecutionAuditEvent]:
        rows = self._exec(
            "SELECT * FROM sandbox_execution_audit_events WHERE execution_id=? ORDER BY created_at ASC",
            [execution_id])
        return [self._row_to_audit(dict(r)) for r in rows]

    @staticmethod
    def _row_to_record(row: dict) -> SandboxExecutionRecord:
        return SandboxExecutionRecord(
            execution_id=row["execution_id"],plan_id=row["plan_id"],gate_id=row.get("gate_id"),
            marketplace_agent_id=row["marketplace_agent_id"],tenant_id=row["tenant_id"],
            user_id=row.get("user_id"),developer_id=row["developer_id"],
            submission_id=row.get("submission_id"),artifact_id=row.get("artifact_id"),
            verification_id=row.get("verification_id"),sandbox_policy_id=row.get("sandbox_policy_id"),
            runtime_binding_id=row.get("runtime_binding_id"),worker_type=row.get("worker_type"),
            execution_status=row.get("execution_status","draft"),decision=row.get("decision","blocked"),
            queue_status=row.get("queue_status","queue_disabled"),risk_level=row.get("risk_level","unknown"),
            input_payload_hash=row.get("input_payload_hash"),
            plan_snapshot=json.loads(row.get("plan_snapshot_json","{}")),
            gate_snapshot=json.loads(row.get("gate_snapshot_json","{}")),
            policy_config_snapshot=json.loads(row.get("policy_config_snapshot_json","{}")),
            artifact_snapshot=json.loads(row.get("artifact_snapshot_json","{}")),
            verification_snapshot=json.loads(row.get("verification_snapshot_json","{}")),
            worker_request_snapshot=json.loads(row.get("worker_request_snapshot_json","{}")),
            no_execution_performed=bool(row.get("no_execution_performed",1)),
            no_download_used=bool(row.get("no_download_used",1)),
            no_network_used=bool(row.get("no_network_used",1)),
            no_subprocess_used=bool(row.get("no_subprocess_used",1)),
            no_container_used=bool(row.get("no_container_used",1)),
            no_queue_created=bool(row.get("no_queue_created",1)),
            no_job_dispatched=bool(row.get("no_job_dispatched",1)),
            no_agent_runtime_used=bool(row.get("no_agent_runtime_used",1)),
            no_agent_registry_used=bool(row.get("no_agent_registry_used",1)),
            created_by=row.get("created_by"),cancelled_by=row.get("cancelled_by"),expired_by=row.get("expired_by"),
            created_at=_safe_dt(row.get("created_at")),updated_at=_safe_dt(row.get("updated_at")),
            cancelled_at=_safe_dt(row.get("cancelled_at"),none_ok=True),
            expired_at=_safe_dt(row.get("expired_at"),none_ok=True),
            expires_at=_safe_dt(row.get("expires_at"),none_ok=True),
            metadata=json.loads(row.get("metadata_json","{}")))

    @staticmethod
    def _row_to_audit(row: dict) -> SandboxExecutionAuditEvent:
        return SandboxExecutionAuditEvent(
            event_id=row["event_id"],execution_id=row["execution_id"],tenant_id=row["tenant_id"],
            event_type=row.get("event_type",""),severity=row.get("severity","info"),
            actor_id=row.get("actor_id"),message=row.get("message",""),
            metadata=json.loads(row.get("metadata_json","{}")),
            created_at=_safe_dt(row.get("created_at")))

def _safe_dt(raw,none_ok=False):
    if not raw: return None if none_ok else datetime.now(timezone.utc)
    try: return datetime.fromisoformat(str(raw).replace("Z","+00:00"))
    except: return None if none_ok else datetime.now(timezone.utc)
