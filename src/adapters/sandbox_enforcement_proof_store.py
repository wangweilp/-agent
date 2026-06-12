"""SQLite Enforcement Proof Store — metadata-only proof, no real enforcement."""
from __future__ import annotations
import json, logging
from datetime import datetime, timezone
from typing import Any
from src.adapters.config import Settings
from src.adapters.sqlite_connection import create_sqlite_db, execute_with_retry
from src.open_platform.sandbox_enforcement_proof import *

logger = logging.getLogger(__name__)
_SCHEMA = """
CREATE TABLE IF NOT EXISTS sandbox_enforcement_proof_requests (
    request_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, execution_id TEXT, queue_record_id TEXT,
    policy_id TEXT, adapter_id TEXT, requested_by TEXT, scope TEXT NOT NULL DEFAULT 'combined',
    network_rule_json TEXT NOT NULL DEFAULT '{}', filesystem_rule_json TEXT NOT NULL DEFAULT '{}',
    secret_rule_json TEXT NOT NULL DEFAULT '{}', policy_config_snapshot_json TEXT NOT NULL DEFAULT '{}',
    adapter_descriptor_snapshot_json TEXT NOT NULL DEFAULT '{}', execution_snapshot_json TEXT NOT NULL DEFAULT '{}',
    queue_snapshot_json TEXT NOT NULL DEFAULT '{}', proof_status TEXT NOT NULL DEFAULT 'draft',
    decision TEXT NOT NULL DEFAULT 'blocked', risk_level TEXT NOT NULL DEFAULT 'unknown',
    no_network_enforcement_applied INTEGER NOT NULL DEFAULT 1, no_filesystem_enforcement_applied INTEGER NOT NULL DEFAULT 1,
    no_secret_read_performed INTEGER NOT NULL DEFAULT 1, no_runtime_started INTEGER NOT NULL DEFAULT 1,
    no_worker_started INTEGER NOT NULL DEFAULT 1, no_queue_created INTEGER NOT NULL DEFAULT 1,
    no_job_dispatched INTEGER NOT NULL DEFAULT 1, no_execution_performed INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')), updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    cancelled_at TEXT, expired_at TEXT, expires_at TEXT, metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_enfreq_tenant ON sandbox_enforcement_proof_requests(tenant_id);
CREATE INDEX IF NOT EXISTS idx_enfreq_execution ON sandbox_enforcement_proof_requests(execution_id);
CREATE INDEX IF NOT EXISTS idx_enfreq_queue ON sandbox_enforcement_proof_requests(queue_record_id);
CREATE INDEX IF NOT EXISTS idx_enfreq_scope ON sandbox_enforcement_proof_requests(scope);
CREATE INDEX IF NOT EXISTS idx_enfreq_status ON sandbox_enforcement_proof_requests(proof_status);
CREATE INDEX IF NOT EXISTS idx_enfreq_decision ON sandbox_enforcement_proof_requests(decision);
CREATE INDEX IF NOT EXISTS idx_enfreq_created ON sandbox_enforcement_proof_requests(created_at);

CREATE TABLE IF NOT EXISTS sandbox_enforcement_proof_results (
    result_id TEXT PRIMARY KEY, request_id TEXT NOT NULL, tenant_id TEXT NOT NULL,
    proof_status TEXT NOT NULL DEFAULT 'blocked', decision TEXT NOT NULL DEFAULT 'blocked',
    checks_json TEXT NOT NULL DEFAULT '[]', warnings_count INTEGER NOT NULL DEFAULT 0,
    errors_count INTEGER NOT NULL DEFAULT 0, blockers_count INTEGER NOT NULL DEFAULT 0,
    metadata_only INTEGER NOT NULL DEFAULT 1, no_network_enforcement_applied INTEGER NOT NULL DEFAULT 1,
    no_filesystem_enforcement_applied INTEGER NOT NULL DEFAULT 1, no_secret_read_performed INTEGER NOT NULL DEFAULT 1,
    no_runtime_started INTEGER NOT NULL DEFAULT 1, no_execution_performed INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')), metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_enfres_request ON sandbox_enforcement_proof_results(request_id);
CREATE INDEX IF NOT EXISTS idx_enfres_tenant ON sandbox_enforcement_proof_results(tenant_id);
CREATE INDEX IF NOT EXISTS idx_enfres_status ON sandbox_enforcement_proof_results(proof_status);

CREATE TABLE IF NOT EXISTS sandbox_enforcement_proof_audit_events (
    event_id TEXT PRIMARY KEY, request_id TEXT NOT NULL, tenant_id TEXT NOT NULL,
    event_type TEXT NOT NULL, severity TEXT NOT NULL DEFAULT 'info',
    actor_id TEXT, message TEXT NOT NULL DEFAULT '', metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_enfevt_request ON sandbox_enforcement_proof_audit_events(request_id);
CREATE INDEX IF NOT EXISTS idx_enfevt_tenant ON sandbox_enforcement_proof_audit_events(tenant_id);
CREATE INDEX IF NOT EXISTS idx_enfevt_type ON sandbox_enforcement_proof_audit_events(event_type);
CREATE INDEX IF NOT EXISTS idx_enfevt_created ON sandbox_enforcement_proof_audit_events(created_at);
"""
_V = "?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?"

def _jd(obj): return json.dumps(obj, ensure_ascii=False)

class SQLiteEnforcementProofStore:
    def __init__(self, config: Settings, db_path: str | None = None):
        path = db_path or config.sqlite_db_path
        self._db = create_sqlite_db(path)
        execute_with_retry(lambda: self._init_schema(), label="enfproof_init_schema")

    def _init_schema(self):
        for stmt in _SCHEMA.strip().split(";") :
            s = stmt.strip()
            if s: self._db.execute(s)
        try: self._db.conn.commit()
        except Exception: pass

    def flush(self):
        try:
            if hasattr(self._db, "conn") and self._db.conn: self._db.conn.commit()
        except Exception: pass

    def _exec(self, sql, params=None): return self._db.execute(sql, params or [])

    def _audit(self, rid, tid, et, actor=None, msg=""):
        evt = EnforcementProofAuditEvent(request_id=rid, tenant_id=tid, event_type=et, actor_id=actor, message=msg)
        self.add_audit_event(evt)

    def create_request(self, req):
        self._exec(f"""INSERT INTO sandbox_enforcement_proof_requests (
            request_id,tenant_id,execution_id,queue_record_id,policy_id,adapter_id,requested_by,scope,
            network_rule_json,filesystem_rule_json,secret_rule_json,policy_config_snapshot_json,
            adapter_descriptor_snapshot_json,execution_snapshot_json,queue_snapshot_json,
            proof_status,decision,risk_level,no_network_enforcement_applied,no_filesystem_enforcement_applied,
            no_secret_read_performed,no_runtime_started,no_worker_started,no_queue_created,no_job_dispatched,
            no_execution_performed,created_at,updated_at,cancelled_at,expired_at,expires_at,metadata_json
        ) VALUES ({_V})""", [
            req.request_id, req.tenant_id, req.execution_id, req.queue_record_id, req.policy_id,
            req.adapter_id, req.requested_by, req.scope, _jd(req.network_rule.to_dict()),
            _jd(req.filesystem_rule.to_dict()), _jd(req.secret_rule.to_dict()),
            _jd(req.policy_config_snapshot), _jd(req.adapter_descriptor_snapshot),
            _jd(req.execution_snapshot), _jd(req.queue_snapshot),
            req.proof_status, req.decision, req.risk_level,
            int(req.no_network_enforcement_applied), int(req.no_filesystem_enforcement_applied),
            int(req.no_secret_read_performed), int(req.no_runtime_started), int(req.no_worker_started),
            int(req.no_queue_created), int(req.no_job_dispatched), int(req.no_execution_performed),
            req.created_at.isoformat() if req.created_at else _now(),
            req.updated_at.isoformat() if req.updated_at else _now(),
            req.cancelled_at.isoformat() if req.cancelled_at else None,
            req.expired_at.isoformat() if req.expired_at else None,
            req.expires_at.isoformat() if req.expires_at else None, _jd(req.metadata)])
        self._audit(req.request_id, req.tenant_id, EnforcementAuditEventType.PROOF_REQUEST_CREATED,
                    req.requested_by, "Proof request created.")
        return req

    def get_request(self, rid):
        row = next(self._exec("SELECT * FROM sandbox_enforcement_proof_requests WHERE request_id=?", [rid]), None)
        return self._row_to_req(dict(row)) if row else None

    def list_requests(self, *, tenant_id="", execution_id="", queue_record_id="", status="", decision="", scope=""):
        sql, p = "SELECT * FROM sandbox_enforcement_proof_requests WHERE 1=1", []
        if tenant_id: sql += " AND tenant_id=?"; p.append(tenant_id)
        if execution_id: sql += " AND execution_id=?"; p.append(execution_id)
        if queue_record_id: sql += " AND queue_record_id=?"; p.append(queue_record_id)
        if status: sql += " AND proof_status=?"; p.append(status)
        if decision: sql += " AND decision=?"; p.append(decision)
        if scope: sql += " AND scope=?"; p.append(scope)
        return [self._row_to_req(dict(r)) for r in self._exec(sql + " ORDER BY created_at DESC", p)]

    def update_request(self, req):
        req.updated_at = datetime.now(timezone.utc)
        self._exec("""UPDATE sandbox_enforcement_proof_requests SET
            proof_status=?,decision=?,risk_level=?,updated_at=?,cancelled_at=?,expired_at=?,
            metadata_json=? WHERE request_id=?""",
            [req.proof_status, req.decision, req.risk_level, req.updated_at.isoformat(),
             req.cancelled_at.isoformat() if req.cancelled_at else None,
             req.expired_at.isoformat() if req.expired_at else None,
             _jd(req.metadata), req.request_id])
        return req

    def set_request_status(self, rid, st, actor=None, reason=None):
        r = self.get_request(rid)
        if r is None: raise EnforcementProofRequestNotFoundError(f"Not found: {rid}")
        old = r.proof_status; r.proof_status = st; self.update_request(r)
        self._audit(rid, r.tenant_id, EnforcementAuditEventType.STATUS_CHANGED, actor, f"Status: {old} -> {st}")
        return r

    def set_decision(self, rid, d, actor=None, reason=None):
        r = self.get_request(rid)
        if r is None: raise EnforcementProofRequestNotFoundError(f"Not found: {rid}")
        old = r.decision; r.decision = d; self.update_request(r)
        self._audit(rid, r.tenant_id, EnforcementAuditEventType.DECISION_CHANGED, actor, f"Decision: {old} -> {d}")
        return r

    def create_result(self, result):
        self._exec("""INSERT INTO sandbox_enforcement_proof_results (
            result_id,request_id,tenant_id,proof_status,decision,checks_json,warnings_count,
            errors_count,blockers_count,metadata_only,no_network_enforcement_applied,
            no_filesystem_enforcement_applied,no_secret_read_performed,no_runtime_started,
            no_execution_performed,created_at,metadata_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", [
            result.result_id, result.request_id, result.tenant_id, result.proof_status,
            result.decision, _jd([c.to_dict() for c in result.checks]),
            result.warnings_count, result.errors_count, result.blockers_count,
            int(result.metadata_only), int(result.no_network_enforcement_applied),
            int(result.no_filesystem_enforcement_applied), int(result.no_secret_read_performed),
            int(result.no_runtime_started), int(result.no_execution_performed),
            result.created_at.isoformat() if result.created_at else _now(), _jd(result.metadata)])
        self._audit(result.request_id, result.tenant_id, EnforcementAuditEventType.PROOF_EVALUATED,
                    None, "Proof evaluated.")
        return result

    def get_result(self, rid):
        row = next(self._exec("SELECT * FROM sandbox_enforcement_proof_results WHERE result_id=?", [rid]), None)
        return self._row_to_res(dict(row)) if row else None

    def get_result_by_request(self, rid):
        row = next(self._exec(
            "SELECT * FROM sandbox_enforcement_proof_results WHERE request_id=? ORDER BY created_at DESC LIMIT 1",
            [rid]), None)
        return self._row_to_res(dict(row)) if row else None

    def cancel_request(self, rid, actor=None, reason=None):
        r = self.get_request(rid)
        if r is None: raise EnforcementProofRequestNotFoundError(f"Not found: {rid}")
        r.proof_status = EnforcementProofStatus.FAIL_CLOSED; r.cancelled_at = datetime.now(timezone.utc)
        self.update_request(r)
        self._audit(rid, r.tenant_id, EnforcementAuditEventType.CANCELLED, actor, "Cancelled.")
        return r

    def expire_request(self, rid, actor=None, reason=None):
        r = self.get_request(rid)
        if r is None: raise EnforcementProofRequestNotFoundError(f"Not found: {rid}")
        r.proof_status = EnforcementProofStatus.FAIL_CLOSED; r.expired_at = datetime.now(timezone.utc)
        self.update_request(r)
        self._audit(rid, r.tenant_id, EnforcementAuditEventType.EXPIRED, actor, "Expired.")
        return r

    def add_audit_event(self, evt):
        self._exec("""INSERT INTO sandbox_enforcement_proof_audit_events (
            event_id,request_id,tenant_id,event_type,severity,actor_id,message,metadata_json,created_at
        ) VALUES (?,?,?,?,?,?,?,?,?)""", [
            evt.event_id, evt.request_id, evt.tenant_id, evt.event_type, evt.severity,
            evt.actor_id, evt.message, _jd(evt.metadata),
            evt.created_at.isoformat() if evt.created_at else _now()])
        return evt

    def list_audit_events(self, rid):
        return [self._row_to_ae(dict(r)) for r in self._exec(
            "SELECT * FROM sandbox_enforcement_proof_audit_events WHERE request_id=? ORDER BY created_at ASC", [rid])]

    def count_requests(self, *, tenant_id="", status="", decision="", scope=""):
        sql, p = "SELECT COUNT(*) as cnt FROM sandbox_enforcement_proof_requests WHERE 1=1", []
        if tenant_id: sql += " AND tenant_id=?"; p.append(tenant_id)
        if status: sql += " AND proof_status=?"; p.append(status)
        if decision: sql += " AND decision=?"; p.append(decision)
        if scope: sql += " AND scope=?"; p.append(scope)
        row = next(self._exec(sql, p), None)
        return row["cnt"] if row else 0

    @staticmethod
    def _row_to_req(row):
        nw = NetworkEnforcementRule.from_dict(json.loads(row.get("network_rule_json", "{}")))
        fs = FilesystemEnforcementRule.from_dict(json.loads(row.get("filesystem_rule_json", "{}")))
        sc = SecretEnforcementRule.from_dict(json.loads(row.get("secret_rule_json", "{}")))
        return EnforcementProofRequest(
            request_id=row["request_id"], tenant_id=row["tenant_id"], execution_id=row.get("execution_id"),
            queue_record_id=row.get("queue_record_id"), policy_id=row.get("policy_id"),
            adapter_id=row.get("adapter_id"), requested_by=row.get("requested_by"),
            scope=row.get("scope", "combined"), network_rule=nw, filesystem_rule=fs, secret_rule=sc,
            policy_config_snapshot=json.loads(row.get("policy_config_snapshot_json", "{}")),
            adapter_descriptor_snapshot=json.loads(row.get("adapter_descriptor_snapshot_json", "{}")),
            execution_snapshot=json.loads(row.get("execution_snapshot_json", "{}")),
            queue_snapshot=json.loads(row.get("queue_snapshot_json", "{}")),
            proof_status=row.get("proof_status", "draft"), decision=row.get("decision", "blocked"),
            risk_level=row.get("risk_level", "unknown"),
            no_network_enforcement_applied=bool(row.get("no_network_enforcement_applied", 1)),
            no_filesystem_enforcement_applied=bool(row.get("no_filesystem_enforcement_applied", 1)),
            no_secret_read_performed=bool(row.get("no_secret_read_performed", 1)),
            no_runtime_started=bool(row.get("no_runtime_started", 1)), no_worker_started=bool(row.get("no_worker_started", 1)),
            no_queue_created=bool(row.get("no_queue_created", 1)), no_job_dispatched=bool(row.get("no_job_dispatched", 1)),
            no_execution_performed=bool(row.get("no_execution_performed", 1)),
            created_at=_sdt(row.get("created_at")), updated_at=_sdt(row.get("updated_at")),
            cancelled_at=_sdt(row.get("cancelled_at"), True), expired_at=_sdt(row.get("expired_at"), True),
            expires_at=_sdt(row.get("expires_at"), True), metadata=json.loads(row.get("metadata_json", "{}")))

    @staticmethod
    def _row_to_res(row):
        checks = [EnforcementCheck.from_dict(c) for c in json.loads(row.get("checks_json", "[]"))]
        return EnforcementProofResult(
            result_id=row["result_id"], request_id=row["request_id"], tenant_id=row["tenant_id"],
            proof_status=row.get("proof_status", "blocked"), decision=row.get("decision", "blocked"),
            checks=checks, warnings_count=int(row.get("warnings_count", 0)),
            errors_count=int(row.get("errors_count", 0)), blockers_count=int(row.get("blockers_count", 0)),
            metadata_only=bool(row.get("metadata_only", 1)),
            no_network_enforcement_applied=bool(row.get("no_network_enforcement_applied", 1)),
            no_filesystem_enforcement_applied=bool(row.get("no_filesystem_enforcement_applied", 1)),
            no_secret_read_performed=bool(row.get("no_secret_read_performed", 1)),
            no_runtime_started=bool(row.get("no_runtime_started", 1)),
            no_execution_performed=bool(row.get("no_execution_performed", 1)),
            created_at=_sdt(row.get("created_at")), metadata=json.loads(row.get("metadata_json", "{}")))

    @staticmethod
    def _row_to_ae(row):
        return EnforcementProofAuditEvent(
            event_id=row["event_id"], request_id=row["request_id"], tenant_id=row["tenant_id"],
            event_type=row.get("event_type", ""), severity=row.get("severity", "info"),
            actor_id=row.get("actor_id"), message=row.get("message", ""),
            metadata=json.loads(row.get("metadata_json", "{}")), created_at=_sdt(row.get("created_at")))

def _sdt(raw, none_ok=False):
    if not raw: return None if none_ok else datetime.now(timezone.utc)
    try: return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except: return None if none_ok else datetime.now(timezone.utc)

def _now(): return datetime.now(timezone.utc).isoformat()
