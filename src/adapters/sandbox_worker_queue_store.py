"""SQLite Sandbox Worker Queue Store — disabled-by-default, metadata-only, no real queue."""
from __future__ import annotations
import json, logging
from datetime import datetime, timezone
from typing import Any
from src.adapters.config import Settings
from src.adapters.sqlite_connection import create_sqlite_db, execute_with_retry
from src.open_platform.sandbox_worker_queue import *

logger = logging.getLogger(__name__)
_SCHEMA = """
CREATE TABLE IF NOT EXISTS sandbox_worker_queue_records (
    queue_record_id TEXT PRIMARY KEY, execution_id TEXT, plan_id TEXT, gate_id TEXT,
    artifact_id TEXT, package_download_request_id TEXT, package_quarantine_id TEXT,
    extraction_guard_request_id TEXT, extraction_plan_id TEXT, marketplace_agent_id TEXT,
    tenant_id TEXT NOT NULL, developer_id TEXT, requested_by TEXT, worker_type TEXT,
    queue_mode TEXT NOT NULL DEFAULT 'disabled', queue_status TEXT NOT NULL DEFAULT 'queue_disabled',
    decision TEXT NOT NULL DEFAULT 'blocked_disabled', lease_status TEXT NOT NULL DEFAULT 'lease_disabled',
    dispatch_status TEXT NOT NULL DEFAULT 'dispatch_disabled', risk_level TEXT NOT NULL DEFAULT 'unknown',
    priority INTEGER NOT NULL DEFAULT 0, execution_snapshot_json TEXT NOT NULL DEFAULT '{}',
    plan_snapshot_json TEXT NOT NULL DEFAULT '{}', gate_snapshot_json TEXT NOT NULL DEFAULT '{}',
    package_download_snapshot_json TEXT NOT NULL DEFAULT '{}', quarantine_snapshot_json TEXT NOT NULL DEFAULT '{}',
    extraction_plan_snapshot_json TEXT NOT NULL DEFAULT '{}', adapter_descriptor_snapshot_json TEXT NOT NULL DEFAULT '{}',
    policy_config_snapshot_json TEXT NOT NULL DEFAULT '{}', worker_request_snapshot_json TEXT NOT NULL DEFAULT '{}',
    queue_enabled INTEGER NOT NULL DEFAULT 0, enqueue_enabled INTEGER NOT NULL DEFAULT 0,
    dispatch_enabled INTEGER NOT NULL DEFAULT 0, worker_enabled INTEGER NOT NULL DEFAULT 0,
    lease_enabled INTEGER NOT NULL DEFAULT 0, heartbeat_enabled INTEGER NOT NULL DEFAULT 0,
    execution_enabled INTEGER NOT NULL DEFAULT 0, no_queue_created INTEGER NOT NULL DEFAULT 1,
    no_job_enqueued INTEGER NOT NULL DEFAULT 1, no_job_dispatched INTEGER NOT NULL DEFAULT 1,
    no_worker_started INTEGER NOT NULL DEFAULT 1, no_worker_process_created INTEGER NOT NULL DEFAULT 1,
    no_execution_performed INTEGER NOT NULL DEFAULT 1, no_download_performed INTEGER NOT NULL DEFAULT 1,
    no_extraction_performed INTEGER NOT NULL DEFAULT 1, no_network_used INTEGER NOT NULL DEFAULT 1,
    no_subprocess_used INTEGER NOT NULL DEFAULT 1, no_container_used INTEGER NOT NULL DEFAULT 1,
    no_agent_runtime_used INTEGER NOT NULL DEFAULT 1, no_agent_registry_used INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')), updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    cancelled_at TEXT, expired_at TEXT, expires_at TEXT, metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_swq_tenant ON sandbox_worker_queue_records(tenant_id);
CREATE INDEX IF NOT EXISTS idx_swq_execution ON sandbox_worker_queue_records(execution_id);
CREATE INDEX IF NOT EXISTS idx_swq_plan ON sandbox_worker_queue_records(plan_id);
CREATE INDEX IF NOT EXISTS idx_swq_status ON sandbox_worker_queue_records(queue_status);
CREATE INDEX IF NOT EXISTS idx_swq_decision ON sandbox_worker_queue_records(decision);
CREATE INDEX IF NOT EXISTS idx_swq_lease ON sandbox_worker_queue_records(lease_status);
CREATE INDEX IF NOT EXISTS idx_swq_dispatch ON sandbox_worker_queue_records(dispatch_status);
CREATE INDEX IF NOT EXISTS idx_swq_created ON sandbox_worker_queue_records(created_at);

CREATE TABLE IF NOT EXISTS sandbox_worker_queue_gate_results (
    gate_result_id TEXT PRIMARY KEY, queue_record_id TEXT, tenant_id TEXT NOT NULL,
    decision TEXT NOT NULL DEFAULT 'blocked_disabled', queue_status TEXT NOT NULL DEFAULT 'queue_disabled',
    lease_status TEXT NOT NULL DEFAULT 'lease_disabled', dispatch_status TEXT NOT NULL DEFAULT 'dispatch_disabled',
    checks_json TEXT NOT NULL DEFAULT '[]', blockers_count INTEGER NOT NULL DEFAULT 0,
    warnings_count INTEGER NOT NULL DEFAULT 0, errors_count INTEGER NOT NULL DEFAULT 0,
    queue_enabled INTEGER NOT NULL DEFAULT 0, enqueue_enabled INTEGER NOT NULL DEFAULT 0,
    dispatch_enabled INTEGER NOT NULL DEFAULT 0, worker_enabled INTEGER NOT NULL DEFAULT 0,
    no_queue_created INTEGER NOT NULL DEFAULT 1, no_job_enqueued INTEGER NOT NULL DEFAULT 1,
    no_job_dispatched INTEGER NOT NULL DEFAULT 1, no_worker_started INTEGER NOT NULL DEFAULT 1,
    no_execution_performed INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')), metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_swqgate_qr ON sandbox_worker_queue_gate_results(queue_record_id);
CREATE INDEX IF NOT EXISTS idx_swqgate_tenant ON sandbox_worker_queue_gate_results(tenant_id);
CREATE INDEX IF NOT EXISTS idx_swqgate_decision ON sandbox_worker_queue_gate_results(decision);

CREATE TABLE IF NOT EXISTS sandbox_worker_queue_audit_events (
    event_id TEXT PRIMARY KEY, queue_record_id TEXT NOT NULL, tenant_id TEXT NOT NULL,
    event_type TEXT NOT NULL, severity TEXT NOT NULL DEFAULT 'info',
    actor_id TEXT, message TEXT NOT NULL DEFAULT '', metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_swqevt_qr ON sandbox_worker_queue_audit_events(queue_record_id);
CREATE INDEX IF NOT EXISTS idx_swqevt_tenant ON sandbox_worker_queue_audit_events(tenant_id);
CREATE INDEX IF NOT EXISTS idx_swqevt_type ON sandbox_worker_queue_audit_events(event_type);
CREATE INDEX IF NOT EXISTS idx_swqevt_created ON sandbox_worker_queue_audit_events(created_at);
"""
_V = "?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?"

def _jd(obj): return json.dumps(obj, ensure_ascii=False)

class SQLiteSandboxWorkerQueueStore:
    def __init__(self, config: Settings, db_path: str | None = None):
        path = db_path or config.sqlite_db_path
        self._db = create_sqlite_db(path)
        execute_with_retry(lambda: self._init_schema(), label="swq_init_schema")

    def _init_schema(self):
        for stmt in _SCHEMA.strip().split(";"):
            s = stmt.strip()
            if s: self._db.execute(s)
        try: self._db.conn.commit()
        except Exception: pass

    def flush(self):
        try:
            if hasattr(self._db, "conn") and self._db.conn: self._db.conn.commit()
        except Exception: pass

    def _exec(self, sql, params=None): return self._db.execute(sql, params or [])

    def _audit(self, qrid, tid, et, actor=None, msg=""):
        evt = SandboxWorkerQueueAuditEvent(queue_record_id=qrid, tenant_id=tid, event_type=et, actor_id=actor, message=msg)
        self.add_audit_event(evt)

    def create_queue_record(self, rec):
        self._exec(f"""INSERT INTO sandbox_worker_queue_records (
            queue_record_id,execution_id,plan_id,gate_id,artifact_id,package_download_request_id,package_quarantine_id,
            extraction_guard_request_id,extraction_plan_id,marketplace_agent_id,tenant_id,developer_id,requested_by,
            worker_type,queue_mode,queue_status,decision,lease_status,dispatch_status,risk_level,priority,
            execution_snapshot_json,plan_snapshot_json,gate_snapshot_json,package_download_snapshot_json,
            quarantine_snapshot_json,extraction_plan_snapshot_json,adapter_descriptor_snapshot_json,
            policy_config_snapshot_json,worker_request_snapshot_json,queue_enabled,enqueue_enabled,dispatch_enabled,
            worker_enabled,lease_enabled,heartbeat_enabled,execution_enabled,no_queue_created,no_job_enqueued,
            no_job_dispatched,no_worker_started,no_worker_process_created,no_execution_performed,no_download_performed,
            no_extraction_performed,no_network_used,no_subprocess_used,no_container_used,no_agent_runtime_used,
            no_agent_registry_used,created_at,updated_at,cancelled_at,expired_at,expires_at,metadata_json
        ) VALUES ({_V})""", [
            rec.queue_record_id, rec.execution_id, rec.plan_id, rec.gate_id, rec.artifact_id,
            rec.package_download_request_id, rec.package_quarantine_id, rec.extraction_guard_request_id,
            rec.extraction_plan_id, rec.marketplace_agent_id, rec.tenant_id, rec.developer_id,
            rec.requested_by, rec.worker_type, rec.queue_mode, rec.queue_status, rec.decision,
            rec.lease_status, rec.dispatch_status, rec.risk_level, rec.priority,
            _jd(rec.execution_snapshot), _jd(rec.plan_snapshot), _jd(rec.gate_snapshot),
            _jd(rec.package_download_snapshot), _jd(rec.quarantine_snapshot),
            _jd(rec.extraction_plan_snapshot), _jd(rec.adapter_descriptor_snapshot),
            _jd(rec.policy_config_snapshot), _jd(rec.worker_request_snapshot),
            int(rec.queue_enabled), int(rec.enqueue_enabled), int(rec.dispatch_enabled),
            int(rec.worker_enabled), int(rec.lease_enabled), int(rec.heartbeat_enabled),
            int(rec.execution_enabled), int(rec.no_queue_created), int(rec.no_job_enqueued),
            int(rec.no_job_dispatched), int(rec.no_worker_started), int(rec.no_worker_process_created),
            int(rec.no_execution_performed), int(rec.no_download_performed), int(rec.no_extraction_performed),
            int(rec.no_network_used), int(rec.no_subprocess_used), int(rec.no_container_used),
            int(rec.no_agent_runtime_used), int(rec.no_agent_registry_used),
            rec.created_at.isoformat() if rec.created_at else _now(),
            rec.updated_at.isoformat() if rec.updated_at else _now(),
            rec.cancelled_at.isoformat() if rec.cancelled_at else None,
            rec.expired_at.isoformat() if rec.expired_at else None,
            rec.expires_at.isoformat() if rec.expires_at else None,
            _jd(rec.metadata),
        ])
        self._audit(rec.queue_record_id, rec.tenant_id, SandboxWorkerQueueAuditEventType.QUEUE_RECORD_CREATED,
                    rec.requested_by, "Queue record created.")
        return rec

    def get_queue_record(self, qid):
        row = next(self._exec("SELECT * FROM sandbox_worker_queue_records WHERE queue_record_id=?", [qid]), None)
        return self._row_to_rec(dict(row)) if row else None

    def list_queue_records(self, *, tenant_id="", execution_id="", plan_id="", status="",
                           decision="", lease_status="", dispatch_status=""):
        sql, p = "SELECT * FROM sandbox_worker_queue_records WHERE 1=1", []
        if tenant_id: sql += " AND tenant_id=?"; p.append(tenant_id)
        if execution_id: sql += " AND execution_id=?"; p.append(execution_id)
        if plan_id: sql += " AND plan_id=?"; p.append(plan_id)
        if status: sql += " AND queue_status=?"; p.append(status)
        if decision: sql += " AND decision=?"; p.append(decision)
        if lease_status: sql += " AND lease_status=?"; p.append(lease_status)
        if dispatch_status: sql += " AND dispatch_status=?"; p.append(dispatch_status)
        return [self._row_to_rec(dict(r)) for r in self._exec(sql + " ORDER BY created_at DESC", p)]

    def update_queue_record(self, rec):
        rec.updated_at = datetime.now(timezone.utc)
        self._exec("""UPDATE sandbox_worker_queue_records SET
            queue_status=?,decision=?,lease_status=?,dispatch_status=?,risk_level=?,priority=?,
            queue_enabled=?,enqueue_enabled=?,dispatch_enabled=?,worker_enabled=?,lease_enabled=?,
            heartbeat_enabled=?,execution_enabled=?,updated_at=?,cancelled_at=?,expired_at=?,
            metadata_json=? WHERE queue_record_id=?""",
            [rec.queue_status, rec.decision, rec.lease_status, rec.dispatch_status, rec.risk_level,
             rec.priority, int(rec.queue_enabled), int(rec.enqueue_enabled), int(rec.dispatch_enabled),
             int(rec.worker_enabled), int(rec.lease_enabled), int(rec.heartbeat_enabled),
             int(rec.execution_enabled),
             rec.updated_at.isoformat(),
             rec.cancelled_at.isoformat() if rec.cancelled_at else None,
             rec.expired_at.isoformat() if rec.expired_at else None,
             _jd(rec.metadata), rec.queue_record_id])
        return rec

    def set_queue_status(self, qid, st, actor=None, reason=None):
        r = self.get_queue_record(qid)
        if r is None: raise SandboxWorkerQueueRecordNotFoundError(f"Not found: {qid}")
        old = r.queue_status; r.queue_status = st; self.update_queue_record(r)
        self._audit(qid, r.tenant_id, SandboxWorkerQueueAuditEventType.QUEUE_STATUS_CHANGED,
                    actor, f"Queue status: {old} -> {st}")
        return r

    def set_decision(self, qid, d, actor=None, reason=None):
        r = self.get_queue_record(qid)
        if r is None: raise SandboxWorkerQueueRecordNotFoundError(f"Not found: {qid}")
        old = r.decision; r.decision = d; self.update_queue_record(r)
        self._audit(qid, r.tenant_id, SandboxWorkerQueueAuditEventType.DECISION_CHANGED,
                    actor, f"Decision: {old} -> {d}")
        return r

    def set_lease_status(self, qid, ls, actor=None, reason=None):
        r = self.get_queue_record(qid)
        if r is None: raise SandboxWorkerQueueRecordNotFoundError(f"Not found: {qid}")
        old = r.lease_status; r.lease_status = ls; self.update_queue_record(r)
        self._audit(qid, r.tenant_id, SandboxWorkerQueueAuditEventType.LEASE_STATUS_CHANGED,
                    actor, f"Lease: {old} -> {ls}")
        return r

    def set_dispatch_status(self, qid, ds, actor=None, reason=None):
        r = self.get_queue_record(qid)
        if r is None: raise SandboxWorkerQueueRecordNotFoundError(f"Not found: {qid}")
        old = r.dispatch_status; r.dispatch_status = ds; self.update_queue_record(r)
        self._audit(qid, r.tenant_id, SandboxWorkerQueueAuditEventType.DISPATCH_STATUS_CHANGED,
                    actor, f"Dispatch: {old} -> {ds}")
        return r

    def cancel_queue_record(self, qid, actor=None, reason=None):
        r = self.get_queue_record(qid)
        if r is None: raise SandboxWorkerQueueRecordNotFoundError(f"Not found: {qid}")
        r.queue_status = SandboxWorkerQueueStatus.CANCELLED
        r.cancelled_at = datetime.now(timezone.utc)
        self.update_queue_record(r)
        self._audit(qid, r.tenant_id, SandboxWorkerQueueAuditEventType.CANCELLED, actor, "Cancelled.")
        return r

    def expire_queue_record(self, qid, actor=None, reason=None):
        r = self.get_queue_record(qid)
        if r is None: raise SandboxWorkerQueueRecordNotFoundError(f"Not found: {qid}")
        r.queue_status = SandboxWorkerQueueStatus.EXPIRED
        r.expired_at = datetime.now(timezone.utc)
        self.update_queue_record(r)
        self._audit(qid, r.tenant_id, SandboxWorkerQueueAuditEventType.EXPIRED, actor, "Expired.")
        return r

    def create_gate_result(self, gate):
        self._exec("""INSERT INTO sandbox_worker_queue_gate_results (
            gate_result_id,queue_record_id,tenant_id,decision,queue_status,lease_status,dispatch_status,
            checks_json,blockers_count,warnings_count,errors_count,queue_enabled,enqueue_enabled,
            dispatch_enabled,worker_enabled,no_queue_created,no_job_enqueued,no_job_dispatched,
            no_worker_started,no_execution_performed,created_at,metadata_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", [
            gate.gate_result_id, gate.queue_record_id, gate.tenant_id, gate.decision,
            gate.queue_status, gate.lease_status, gate.dispatch_status, _jd(gate.checks),
            gate.blockers_count, gate.warnings_count, gate.errors_count,
            int(gate.queue_enabled), int(gate.enqueue_enabled), int(gate.dispatch_enabled),
            int(gate.worker_enabled), int(gate.no_queue_created), int(gate.no_job_enqueued),
            int(gate.no_job_dispatched), int(gate.no_worker_started), int(gate.no_execution_performed),
            gate.created_at.isoformat() if gate.created_at else _now(),
            _jd(gate.metadata)])
        self._audit(gate.queue_record_id or "", gate.tenant_id,
                    SandboxWorkerQueueAuditEventType.QUEUE_GATE_EVALUATED, None, "Gate evaluated.")
        return gate

    def get_gate_result(self, gid):
        row = next(self._exec(
            "SELECT * FROM sandbox_worker_queue_gate_results WHERE gate_result_id=?", [gid]), None)
        return self._row_to_gate(dict(row)) if row else None

    def get_gate_result_by_queue_record(self, qid):
        row = next(self._exec(
            "SELECT * FROM sandbox_worker_queue_gate_results WHERE queue_record_id=? ORDER BY created_at DESC LIMIT 1",
            [qid]), None)
        return self._row_to_gate(dict(row)) if row else None

    def add_audit_event(self, evt):
        self._exec("""INSERT INTO sandbox_worker_queue_audit_events (
            event_id,queue_record_id,tenant_id,event_type,severity,actor_id,message,metadata_json,created_at
        ) VALUES (?,?,?,?,?,?,?,?,?)""", [
            evt.event_id, evt.queue_record_id, evt.tenant_id, evt.event_type, evt.severity,
            evt.actor_id, evt.message, _jd(evt.metadata),
            evt.created_at.isoformat() if evt.created_at else _now()])
        return evt

    def list_audit_events(self, qid):
        return [self._row_to_ae(dict(r)) for r in self._exec(
            "SELECT * FROM sandbox_worker_queue_audit_events WHERE queue_record_id=? ORDER BY created_at ASC", [qid])]

    def count_queue_records(self, *, tenant_id="", status="", decision="", dispatch_status=""):
        sql, p = "SELECT COUNT(*) as cnt FROM sandbox_worker_queue_records WHERE 1=1", []
        if tenant_id: sql += " AND tenant_id=?"; p.append(tenant_id)
        if status: sql += " AND queue_status=?"; p.append(status)
        if decision: sql += " AND decision=?"; p.append(decision)
        if dispatch_status: sql += " AND dispatch_status=?"; p.append(dispatch_status)
        row = next(self._exec(sql, p), None)
        return row["cnt"] if row else 0

    @staticmethod
    def _row_to_rec(row):
        return SandboxWorkerQueueRecord(
            queue_record_id=row["queue_record_id"], execution_id=row.get("execution_id"),
            plan_id=row.get("plan_id"), gate_id=row.get("gate_id"),
            artifact_id=row.get("artifact_id"),
            package_download_request_id=row.get("package_download_request_id"),
            package_quarantine_id=row.get("package_quarantine_id"),
            extraction_guard_request_id=row.get("extraction_guard_request_id"),
            extraction_plan_id=row.get("extraction_plan_id"),
            marketplace_agent_id=row.get("marketplace_agent_id"),
            tenant_id=row["tenant_id"], developer_id=row.get("developer_id"),
            requested_by=row.get("requested_by"), worker_type=row.get("worker_type"),
            queue_mode=row.get("queue_mode", "disabled"),
            queue_status=row.get("queue_status", "queue_disabled"),
            decision=row.get("decision", "blocked_disabled"),
            lease_status=row.get("lease_status", "lease_disabled"),
            dispatch_status=row.get("dispatch_status", "dispatch_disabled"),
            risk_level=row.get("risk_level", "unknown"), priority=int(row.get("priority", 0)),
            execution_snapshot=json.loads(row.get("execution_snapshot_json", "{}")),
            plan_snapshot=json.loads(row.get("plan_snapshot_json", "{}")),
            gate_snapshot=json.loads(row.get("gate_snapshot_json", "{}")),
            package_download_snapshot=json.loads(row.get("package_download_snapshot_json", "{}")),
            quarantine_snapshot=json.loads(row.get("quarantine_snapshot_json", "{}")),
            extraction_plan_snapshot=json.loads(row.get("extraction_plan_snapshot_json", "{}")),
            adapter_descriptor_snapshot=json.loads(row.get("adapter_descriptor_snapshot_json", "{}")),
            policy_config_snapshot=json.loads(row.get("policy_config_snapshot_json", "{}")),
            worker_request_snapshot=json.loads(row.get("worker_request_snapshot_json", "{}")),
            queue_enabled=bool(row.get("queue_enabled", 0)),
            enqueue_enabled=bool(row.get("enqueue_enabled", 0)),
            dispatch_enabled=bool(row.get("dispatch_enabled", 0)),
            worker_enabled=bool(row.get("worker_enabled", 0)),
            lease_enabled=bool(row.get("lease_enabled", 0)),
            heartbeat_enabled=bool(row.get("heartbeat_enabled", 0)),
            execution_enabled=bool(row.get("execution_enabled", 0)),
            no_queue_created=bool(row.get("no_queue_created", 1)),
            no_job_enqueued=bool(row.get("no_job_enqueued", 1)),
            no_job_dispatched=bool(row.get("no_job_dispatched", 1)),
            no_worker_started=bool(row.get("no_worker_started", 1)),
            no_worker_process_created=bool(row.get("no_worker_process_created", 1)),
            no_execution_performed=bool(row.get("no_execution_performed", 1)),
            no_download_performed=bool(row.get("no_download_performed", 1)),
            no_extraction_performed=bool(row.get("no_extraction_performed", 1)),
            no_network_used=bool(row.get("no_network_used", 1)),
            no_subprocess_used=bool(row.get("no_subprocess_used", 1)),
            no_container_used=bool(row.get("no_container_used", 1)),
            no_agent_runtime_used=bool(row.get("no_agent_runtime_used", 1)),
            no_agent_registry_used=bool(row.get("no_agent_registry_used", 1)),
            created_at=_sdt(row.get("created_at")), updated_at=_sdt(row.get("updated_at")),
            cancelled_at=_sdt(row.get("cancelled_at"), True), expired_at=_sdt(row.get("expired_at"), True),
            expires_at=_sdt(row.get("expires_at"), True),
            metadata=json.loads(row.get("metadata_json", "{}")))

    @staticmethod
    def _row_to_gate(row):
        return SandboxWorkerQueueGateResult(
            gate_result_id=row["gate_result_id"], queue_record_id=row.get("queue_record_id"),
            tenant_id=row["tenant_id"], decision=row.get("decision", "blocked_disabled"),
            queue_status=row.get("queue_status", "queue_disabled"),
            lease_status=row.get("lease_status", "lease_disabled"),
            dispatch_status=row.get("dispatch_status", "dispatch_disabled"),
            checks=json.loads(row.get("checks_json", "[]")),
            blockers_count=int(row.get("blockers_count", 0)),
            warnings_count=int(row.get("warnings_count", 0)),
            errors_count=int(row.get("errors_count", 0)),
            queue_enabled=bool(row.get("queue_enabled", 0)),
            enqueue_enabled=bool(row.get("enqueue_enabled", 0)),
            dispatch_enabled=bool(row.get("dispatch_enabled", 0)),
            worker_enabled=bool(row.get("worker_enabled", 0)),
            no_queue_created=bool(row.get("no_queue_created", 1)),
            no_job_enqueued=bool(row.get("no_job_enqueued", 1)),
            no_job_dispatched=bool(row.get("no_job_dispatched", 1)),
            no_worker_started=bool(row.get("no_worker_started", 1)),
            no_execution_performed=bool(row.get("no_execution_performed", 1)),
            created_at=_sdt(row.get("created_at")),
            metadata=json.loads(row.get("metadata_json", "{}")))

    @staticmethod
    def _row_to_ae(row):
        return SandboxWorkerQueueAuditEvent(
            event_id=row["event_id"], queue_record_id=row["queue_record_id"],
            tenant_id=row["tenant_id"], event_type=row.get("event_type", ""),
            severity=row.get("severity", "info"), actor_id=row.get("actor_id"),
            message=row.get("message", ""),
            metadata=json.loads(row.get("metadata_json", "{}")),
            created_at=_sdt(row.get("created_at")))

def _sdt(raw, none_ok=False):
    if not raw: return None if none_ok else datetime.now(timezone.utc)
    try: return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except: return None if none_ok else datetime.now(timezone.utc)

def _now():
    return datetime.now(timezone.utc).isoformat()
