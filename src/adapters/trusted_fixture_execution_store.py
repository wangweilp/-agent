"""SQLite Trusted Fixture Execution Store — built-in fixtures only, no third-party/package/entrypoint execution."""
from __future__ import annotations
import json, logging
from datetime import datetime, timezone
from typing import Any
from src.adapters.config import Settings
from src.adapters.sqlite_connection import create_sqlite_db, execute_with_retry
from src.open_platform.trusted_fixture_execution import *

logger = logging.getLogger(__name__)
_SCHEMA = """
CREATE TABLE IF NOT EXISTS trusted_fixture_execution_requests (
    request_id TEXT PRIMARY KEY, fixture_id TEXT NOT NULL, tenant_id TEXT NOT NULL,
    execution_id TEXT, queue_record_id TEXT, enforcement_proof_request_id TEXT, requested_by TEXT,
    input_payload_hash TEXT, input_metadata_json TEXT NOT NULL DEFAULT '{}',
    fixture_snapshot_json TEXT NOT NULL DEFAULT '{}', execution_snapshot_json TEXT NOT NULL DEFAULT '{}',
    queue_snapshot_json TEXT NOT NULL DEFAULT '{}', enforcement_snapshot_json TEXT NOT NULL DEFAULT '{}',
    request_status TEXT NOT NULL DEFAULT 'draft', decision TEXT NOT NULL DEFAULT 'fail_closed',
    safety_level TEXT NOT NULL DEFAULT 'unknown',
    no_third_party_code_executed INTEGER NOT NULL DEFAULT 1, no_package_executed INTEGER NOT NULL DEFAULT 1,
    no_entrypoint_executed INTEGER NOT NULL DEFAULT 1, no_dynamic_import_used INTEGER NOT NULL DEFAULT 1,
    no_eval_exec_used INTEGER NOT NULL DEFAULT 1, no_network_used INTEGER NOT NULL DEFAULT 1,
    no_filesystem_used INTEGER NOT NULL DEFAULT 1, no_secret_read INTEGER NOT NULL DEFAULT 1,
    no_subprocess_used INTEGER NOT NULL DEFAULT 1, no_container_used INTEGER NOT NULL DEFAULT 1,
    no_worker_queue_used INTEGER NOT NULL DEFAULT 1, no_job_dispatched INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')), updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    cancelled_at TEXT, expired_at TEXT, expires_at TEXT, metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_tfixreq_tenant ON trusted_fixture_execution_requests(tenant_id);
CREATE INDEX IF NOT EXISTS idx_tfixreq_fixture ON trusted_fixture_execution_requests(fixture_id);
CREATE INDEX IF NOT EXISTS idx_tfixreq_execution ON trusted_fixture_execution_requests(execution_id);
CREATE INDEX IF NOT EXISTS idx_tfixreq_status ON trusted_fixture_execution_requests(request_status);
CREATE INDEX IF NOT EXISTS idx_tfixreq_decision ON trusted_fixture_execution_requests(decision);
CREATE INDEX IF NOT EXISTS idx_tfixreq_created ON trusted_fixture_execution_requests(created_at);

CREATE TABLE IF NOT EXISTS trusted_fixture_execution_results (
    result_id TEXT PRIMARY KEY, request_id TEXT NOT NULL, fixture_id TEXT NOT NULL, tenant_id TEXT NOT NULL,
    result_status TEXT NOT NULL DEFAULT 'blocked', output_metadata_json TEXT NOT NULL DEFAULT '{}',
    output_payload_hash TEXT, duration_ms INTEGER,
    trusted_fixture_executed INTEGER NOT NULL DEFAULT 0, third_party_code_executed INTEGER NOT NULL DEFAULT 0,
    package_executed INTEGER NOT NULL DEFAULT 0, entrypoint_executed INTEGER NOT NULL DEFAULT 0,
    dynamic_import_used INTEGER NOT NULL DEFAULT 0, eval_exec_used INTEGER NOT NULL DEFAULT 0,
    network_used INTEGER NOT NULL DEFAULT 0, filesystem_used INTEGER NOT NULL DEFAULT 0,
    secrets_used INTEGER NOT NULL DEFAULT 0, subprocess_used INTEGER NOT NULL DEFAULT 0,
    container_used INTEGER NOT NULL DEFAULT 0, worker_queue_used INTEGER NOT NULL DEFAULT 0,
    job_dispatched INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')), metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_tfixres_request ON trusted_fixture_execution_results(request_id);
CREATE INDEX IF NOT EXISTS idx_tfixres_fixture ON trusted_fixture_execution_results(fixture_id);
CREATE INDEX IF NOT EXISTS idx_tfixres_tenant ON trusted_fixture_execution_results(tenant_id);
CREATE INDEX IF NOT EXISTS idx_tfixres_status ON trusted_fixture_execution_results(result_status);

CREATE TABLE IF NOT EXISTS trusted_fixture_audit_events (
    event_id TEXT PRIMARY KEY, request_id TEXT NOT NULL, tenant_id TEXT NOT NULL,
    event_type TEXT NOT NULL, severity TEXT NOT NULL DEFAULT 'info',
    actor_id TEXT, message TEXT NOT NULL DEFAULT '', metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_tfixevt_request ON trusted_fixture_audit_events(request_id);
CREATE INDEX IF NOT EXISTS idx_tfixevt_tenant ON trusted_fixture_audit_events(tenant_id);
CREATE INDEX IF NOT EXISTS idx_tfixevt_type ON trusted_fixture_audit_events(event_type);
CREATE INDEX IF NOT EXISTS idx_tfixevt_created ON trusted_fixture_audit_events(created_at);
"""
_VR = "?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?"
_VRES = "?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?"

def _jd(obj): return json.dumps(obj, ensure_ascii=False)

class SQLiteTrustedFixtureExecutionStore:
    def __init__(self, config: Settings, db_path: str | None = None):
        path = db_path or config.sqlite_db_path
        self._db = create_sqlite_db(path)
        execute_with_retry(lambda: self._init_schema(), label="tfix_init_schema")
    def _init_schema(self):
        for stmt in _SCHEMA.strip().split(";") :
            s = stmt.strip()
            if s: self._db.execute(s)
        try: self._db.conn.commit()
        except Exception: pass
    def flush(self):
        try:
            if hasattr(self._db,"conn") and self._db.conn: self._db.conn.commit()
        except Exception: pass
    def _exec(self, sql, params=None): return self._db.execute(sql, params or [])
    def _audit(self, rid, tid, et, actor=None, msg=""):
        self.add_audit_event(TrustedFixtureAuditEvent(request_id=rid, tenant_id=tid, event_type=et, actor_id=actor, message=msg))

    def create_request(self, req):
        self._exec(f"""INSERT INTO trusted_fixture_execution_requests (
            request_id,fixture_id,tenant_id,execution_id,queue_record_id,enforcement_proof_request_id,requested_by,
            input_payload_hash,input_metadata_json,fixture_snapshot_json,execution_snapshot_json,
            queue_snapshot_json,enforcement_snapshot_json,request_status,decision,safety_level,
            no_third_party_code_executed,no_package_executed,no_entrypoint_executed,no_dynamic_import_used,
            no_eval_exec_used,no_network_used,no_filesystem_used,no_secret_read,no_subprocess_used,
            no_container_used,no_worker_queue_used,no_job_dispatched,
            created_at,updated_at,cancelled_at,expired_at,expires_at,metadata_json
        ) VALUES ({_VR})""", [
            req.request_id,req.fixture_id,req.tenant_id,req.execution_id,req.queue_record_id,
            req.enforcement_proof_request_id,req.requested_by,req.input_payload_hash,
            _jd(req.input_metadata),_jd(req.fixture_snapshot),_jd(req.execution_snapshot),
            _jd(req.queue_snapshot),_jd(req.enforcement_snapshot),req.request_status,req.decision,req.safety_level,
            int(req.no_third_party_code_executed),int(req.no_package_executed),int(req.no_entrypoint_executed),
            int(req.no_dynamic_import_used),int(req.no_eval_exec_used),int(req.no_network_used),
            int(req.no_filesystem_used),int(req.no_secret_read),int(req.no_subprocess_used),
            int(req.no_container_used),int(req.no_worker_queue_used),int(req.no_job_dispatched),
            req.created_at.isoformat() if req.created_at else _now(),
            req.updated_at.isoformat() if req.updated_at else _now(),
            req.cancelled_at.isoformat() if req.cancelled_at else None,
            req.expired_at.isoformat() if req.expired_at else None,
            req.expires_at.isoformat() if req.expires_at else None, _jd(req.metadata)])
        self._audit(req.request_id,req.tenant_id,TrustedFixtureAuditEventType.FIXTURE_REQUEST_CREATED,req.requested_by,"Request created.")
        return req

    def get_request(self, rid):
        row = next(self._exec("SELECT * FROM trusted_fixture_execution_requests WHERE request_id=?",[rid]),None)
        return self._row_to_req(dict(row)) if row else None

    def list_requests(self, *, tenant_id="", fixture_id="", status="", decision=""):
        sql,p = "SELECT * FROM trusted_fixture_execution_requests WHERE 1=1",[]
        if tenant_id: sql+=" AND tenant_id=?"; p.append(tenant_id)
        if fixture_id: sql+=" AND fixture_id=?"; p.append(fixture_id)
        if status: sql+=" AND request_status=?"; p.append(status)
        if decision: sql+=" AND decision=?"; p.append(decision)
        return [self._row_to_req(dict(r)) for r in self._exec(sql+" ORDER BY created_at DESC",p)]

    def update_request(self, req):
        req.updated_at=datetime.now(timezone.utc)
        self._exec("""UPDATE trusted_fixture_execution_requests SET
            request_status=?,decision=?,safety_level=?,updated_at=?,cancelled_at=?,expired_at=?,
            metadata_json=? WHERE request_id=?""",
            [req.request_status,req.decision,req.safety_level,req.updated_at.isoformat(),
             req.cancelled_at.isoformat() if req.cancelled_at else None,
             req.expired_at.isoformat() if req.expired_at else None,_jd(req.metadata),req.request_id])
        return req

    def set_request_status(self,rid,st,actor=None,reason=None):
        r=self.get_request(rid)
        if r is None: raise TrustedFixtureNotFoundError(f"Not found: {rid}")
        old=r.request_status; r.request_status=st; self.update_request(r)
        self._audit(rid,r.tenant_id,TrustedFixtureAuditEventType.STATUS_CHANGED,actor,f"Status: {old} -> {st}")
        return r

    def set_decision(self,rid,d,actor=None,reason=None):
        r=self.get_request(rid)
        if r is None: raise TrustedFixtureNotFoundError(f"Not found: {rid}")
        old=r.decision; r.decision=d; self.update_request(r)
        self._audit(rid,r.tenant_id,TrustedFixtureAuditEventType.DECISION_CHANGED,actor,f"Decision: {old} -> {d}")
        return r

    def create_result(self, result):
        self._exec(f"""INSERT INTO trusted_fixture_execution_results (
            result_id,request_id,fixture_id,tenant_id,result_status,output_metadata_json,output_payload_hash,
            duration_ms,trusted_fixture_executed,third_party_code_executed,package_executed,entrypoint_executed,
            dynamic_import_used,eval_exec_used,network_used,filesystem_used,secrets_used,subprocess_used,
            container_used,worker_queue_used,job_dispatched,created_at,metadata_json
        ) VALUES ({_VRES})""", [
            result.result_id,result.request_id,result.fixture_id,result.tenant_id,result.result_status,
            _jd(result.output_metadata),result.output_payload_hash,result.duration_ms,
            int(result.trusted_fixture_executed),int(result.third_party_code_executed),
            int(result.package_executed),int(result.entrypoint_executed),int(result.dynamic_import_used),
            int(result.eval_exec_used),int(result.network_used),int(result.filesystem_used),
            int(result.secrets_used),int(result.subprocess_used),int(result.container_used),
            int(result.worker_queue_used),int(result.job_dispatched),
            result.created_at.isoformat() if result.created_at else _now(), _jd(result.metadata)])
        self._audit(result.request_id,result.tenant_id,TrustedFixtureAuditEventType.TRUSTED_FIXTURE_EXECUTED,
                    None,"Trusted fixture executed.")
        return result

    def get_result(self, rid): row=next(self._exec("SELECT * FROM trusted_fixture_execution_results WHERE result_id=?",[rid]),None); return self._row_to_res(dict(row)) if row else None
    def get_result_by_request(self, rid): row=next(self._exec("SELECT * FROM trusted_fixture_execution_results WHERE request_id=? ORDER BY created_at DESC LIMIT 1",[rid]),None); return self._row_to_res(dict(row)) if row else None

    def cancel_request(self,rid,actor=None,reason=None):
        r=self.get_request(rid)
        if r is None: raise TrustedFixtureNotFoundError(f"Not found: {rid}")
        r.request_status=TrustedFixtureExecutionStatus.CANCELLED; r.cancelled_at=datetime.now(timezone.utc)
        self.update_request(r)
        self._audit(rid,r.tenant_id,TrustedFixtureAuditEventType.CANCELLED,actor,"Cancelled.")
        return r

    def expire_request(self,rid,actor=None,reason=None):
        r=self.get_request(rid)
        if r is None: raise TrustedFixtureNotFoundError(f"Not found: {rid}")
        r.request_status=TrustedFixtureExecutionStatus.EXPIRED; r.expired_at=datetime.now(timezone.utc)
        self.update_request(r)
        self._audit(rid,r.tenant_id,TrustedFixtureAuditEventType.EXPIRED,actor,"Expired.")
        return r

    def add_audit_event(self, evt):
        self._exec("""INSERT INTO trusted_fixture_audit_events (
            event_id,request_id,tenant_id,event_type,severity,actor_id,message,metadata_json,created_at
        ) VALUES (?,?,?,?,?,?,?,?,?)""", [
            evt.event_id,evt.request_id,evt.tenant_id,evt.event_type,evt.severity,
            evt.actor_id,evt.message,_jd(evt.metadata),
            evt.created_at.isoformat() if evt.created_at else _now()])
        return evt

    def list_audit_events(self,rid):
        return [self._row_to_ae(dict(r)) for r in self._exec(
            "SELECT * FROM trusted_fixture_audit_events WHERE request_id=? ORDER BY created_at ASC",[rid])]

    def count_requests(self, *, tenant_id="", fixture_id="", status="", decision=""):
        sql,p = "SELECT COUNT(*) as cnt FROM trusted_fixture_execution_requests WHERE 1=1",[]
        if tenant_id: sql+=" AND tenant_id=?"; p.append(tenant_id)
        if fixture_id: sql+=" AND fixture_id=?"; p.append(fixture_id)
        if status: sql+=" AND request_status=?"; p.append(status)
        if decision: sql+=" AND decision=?"; p.append(decision)
        row=next(self._exec(sql,p),None); return row["cnt"] if row else 0

    @staticmethod
    def _row_to_req(row): return TrustedFixtureExecutionRequest(
        request_id=row["request_id"],fixture_id=row["fixture_id"],tenant_id=row["tenant_id"],
        execution_id=row.get("execution_id"),queue_record_id=row.get("queue_record_id"),
        enforcement_proof_request_id=row.get("enforcement_proof_request_id"),requested_by=row.get("requested_by"),
        input_payload_hash=row.get("input_payload_hash"),
        input_metadata=json.loads(row.get("input_metadata_json","{}")),
        fixture_snapshot=json.loads(row.get("fixture_snapshot_json","{}")),
        execution_snapshot=json.loads(row.get("execution_snapshot_json","{}")),
        queue_snapshot=json.loads(row.get("queue_snapshot_json","{}")),
        enforcement_snapshot=json.loads(row.get("enforcement_snapshot_json","{}")),
        request_status=row.get("request_status","draft"),decision=row.get("decision","fail_closed"),
        safety_level=row.get("safety_level","unknown"),
        no_third_party_code_executed=bool(row.get("no_third_party_code_executed",1)),
        no_package_executed=bool(row.get("no_package_executed",1)),no_entrypoint_executed=bool(row.get("no_entrypoint_executed",1)),
        no_dynamic_import_used=bool(row.get("no_dynamic_import_used",1)),no_eval_exec_used=bool(row.get("no_eval_exec_used",1)),
        no_network_used=bool(row.get("no_network_used",1)),no_filesystem_used=bool(row.get("no_filesystem_used",1)),
        no_secret_read=bool(row.get("no_secret_read",1)),no_subprocess_used=bool(row.get("no_subprocess_used",1)),
        no_container_used=bool(row.get("no_container_used",1)),no_worker_queue_used=bool(row.get("no_worker_queue_used",1)),
        no_job_dispatched=bool(row.get("no_job_dispatched",1)),created_at=_sdt(row.get("created_at")),
        updated_at=_sdt(row.get("updated_at")),cancelled_at=_sdt(row.get("cancelled_at"),True),
        expired_at=_sdt(row.get("expired_at"),True),expires_at=_sdt(row.get("expires_at"),True),
        metadata=json.loads(row.get("metadata_json","{}")))

    @staticmethod
    def _row_to_res(row): return TrustedFixtureExecutionResult(
        result_id=row["result_id"],request_id=row["request_id"],fixture_id=row["fixture_id"],tenant_id=row["tenant_id"],
        result_status=row.get("result_status","blocked"),output_metadata=json.loads(row.get("output_metadata_json","{}")),
        output_payload_hash=row.get("output_payload_hash"),duration_ms=row.get("duration_ms"),
        trusted_fixture_executed=bool(row.get("trusted_fixture_executed",0)),
        third_party_code_executed=bool(row.get("third_party_code_executed",0)),
        package_executed=bool(row.get("package_executed",0)),entrypoint_executed=bool(row.get("entrypoint_executed",0)),
        dynamic_import_used=bool(row.get("dynamic_import_used",0)),eval_exec_used=bool(row.get("eval_exec_used",0)),
        network_used=bool(row.get("network_used",0)),filesystem_used=bool(row.get("filesystem_used",0)),
        secrets_used=bool(row.get("secrets_used",0)),subprocess_used=bool(row.get("subprocess_used",0)),
        container_used=bool(row.get("container_used",0)),worker_queue_used=bool(row.get("worker_queue_used",0)),
        job_dispatched=bool(row.get("job_dispatched",0)),created_at=_sdt(row.get("created_at")),
        metadata=json.loads(row.get("metadata_json","{}")))

    @staticmethod
    def _row_to_ae(row): return TrustedFixtureAuditEvent(
        event_id=row["event_id"],request_id=row["request_id"],tenant_id=row["tenant_id"],
        event_type=row.get("event_type",""),severity=row.get("severity","info"),actor_id=row.get("actor_id"),
        message=row.get("message",""),metadata=json.loads(row.get("metadata_json","{}")),created_at=_sdt(row.get("created_at")))

def _sdt(raw, none_ok=False):
    if not raw: return None if none_ok else datetime.now(timezone.utc)
    try: return datetime.fromisoformat(str(raw).replace("Z","+00:00"))
    except: return None if none_ok else datetime.now(timezone.utc)

def _now(): return datetime.now(timezone.utc).isoformat()
