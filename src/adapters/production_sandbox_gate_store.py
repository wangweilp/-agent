"""SQLite Production Sandbox Gate Store — readiness assessment, never enables execution."""
from __future__ import annotations
import json, logging
from datetime import datetime, timezone
from typing import Any
from src.adapters.config import Settings
from src.adapters.sqlite_connection import create_sqlite_db, execute_with_retry
from src.open_platform.production_sandbox_gate import *

logger = logging.getLogger(__name__)
_SCHEMA = """
CREATE TABLE IF NOT EXISTS production_sandbox_gate_requests (
    gate_request_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, requested_by TEXT,
    step25_final_gate_snapshot_json TEXT NOT NULL DEFAULT '{}', red_team_snapshot_json TEXT NOT NULL DEFAULT '{}',
    docs_snapshot_json TEXT NOT NULL DEFAULT '{}', startup_snapshot_json TEXT NOT NULL DEFAULT '{}',
    runtime_endpoint_snapshot_json TEXT NOT NULL DEFAULT '{}', execution_snapshot_json TEXT NOT NULL DEFAULT '{}',
    queue_snapshot_json TEXT NOT NULL DEFAULT '{}', download_snapshot_json TEXT NOT NULL DEFAULT '{}',
    extraction_snapshot_json TEXT NOT NULL DEFAULT '{}', enforcement_snapshot_json TEXT NOT NULL DEFAULT '{}',
    trusted_fixture_snapshot_json TEXT NOT NULL DEFAULT '{}',
    gate_status TEXT NOT NULL DEFAULT 'draft', decision TEXT NOT NULL DEFAULT 'blocked', risk_level TEXT NOT NULL DEFAULT 'unknown',
    no_third_party_execution_enabled INTEGER NOT NULL DEFAULT 1, no_package_execution_enabled INTEGER NOT NULL DEFAULT 1,
    no_download_enabled INTEGER NOT NULL DEFAULT 1, no_extraction_enabled INTEGER NOT NULL DEFAULT 1,
    no_real_queue_enabled INTEGER NOT NULL DEFAULT 1, no_dispatch_enabled INTEGER NOT NULL DEFAULT 1,
    no_worker_enabled INTEGER NOT NULL DEFAULT 1, no_container_enabled INTEGER NOT NULL DEFAULT 1,
    no_microvm_enabled INTEGER NOT NULL DEFAULT 1, no_agent_runtime_enabled INTEGER NOT NULL DEFAULT 1,
    no_agent_registry_execution_enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')), updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    cancelled_at TEXT, expired_at TEXT, expires_at TEXT, metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_psgate_tenant ON production_sandbox_gate_requests(tenant_id);
CREATE INDEX IF NOT EXISTS idx_psgate_status ON production_sandbox_gate_requests(gate_status);
CREATE INDEX IF NOT EXISTS idx_psgate_decision ON production_sandbox_gate_requests(decision);
CREATE INDEX IF NOT EXISTS idx_psgate_created ON production_sandbox_gate_requests(created_at);

CREATE TABLE IF NOT EXISTS production_sandbox_gate_results (
    gate_result_id TEXT PRIMARY KEY, gate_request_id TEXT NOT NULL, tenant_id TEXT NOT NULL,
    gate_status TEXT NOT NULL DEFAULT 'blocked', decision TEXT NOT NULL DEFAULT 'blocked',
    requirements_json TEXT NOT NULL DEFAULT '[]', checks_json TEXT NOT NULL DEFAULT '[]',
    satisfied_count INTEGER NOT NULL DEFAULT 0, missing_count INTEGER NOT NULL DEFAULT 0,
    blocked_count INTEGER NOT NULL DEFAULT 0, warnings_count INTEGER NOT NULL DEFAULT 0,
    blockers_count INTEGER NOT NULL DEFAULT 0, ready_for_step26b INTEGER NOT NULL DEFAULT 0,
    ready_for_controlled_runtime_spike INTEGER NOT NULL DEFAULT 0,
    third_party_execution_allowed INTEGER NOT NULL DEFAULT 0, package_execution_allowed INTEGER NOT NULL DEFAULT 0,
    runtime_enabled INTEGER NOT NULL DEFAULT 0, metadata_only INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')), metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_psres_request ON production_sandbox_gate_results(gate_request_id);
CREATE INDEX IF NOT EXISTS idx_psres_tenant ON production_sandbox_gate_results(tenant_id);
CREATE INDEX IF NOT EXISTS idx_psres_status ON production_sandbox_gate_results(gate_status);

CREATE TABLE IF NOT EXISTS production_sandbox_gate_audit_events (
    event_id TEXT PRIMARY KEY, gate_request_id TEXT NOT NULL, tenant_id TEXT NOT NULL,
    event_type TEXT NOT NULL, severity TEXT NOT NULL DEFAULT 'info',
    actor_id TEXT, message TEXT NOT NULL DEFAULT '', metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_psevt_request ON production_sandbox_gate_audit_events(gate_request_id);
CREATE INDEX IF NOT EXISTS idx_psevt_tenant ON production_sandbox_gate_audit_events(tenant_id);
CREATE INDEX IF NOT EXISTS idx_psevt_type ON production_sandbox_gate_audit_events(event_type);
CREATE INDEX IF NOT EXISTS idx_psevt_created ON production_sandbox_gate_audit_events(created_at);
"""
_VR = "?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?"
_VRES = "?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?"

def _jd(obj): return json.dumps(obj, ensure_ascii=False)

class SQLiteProductionSandboxGateStore:
    def __init__(self, config: Settings, db_path: str | None = None):
        path = db_path or config.sqlite_db_path; self._db = create_sqlite_db(path)
        execute_with_retry(lambda: self._init_schema(), label="psgate_init")

    def _init_schema(self):
        for stmt in _SCHEMA.strip().split(";"):
            s = stmt.strip()
            if s: self._db.execute(s)
        try: self._db.conn.commit()
        except Exception: pass

    def flush(self):
        try:
            if hasattr(self._db,"conn") and self._db.conn: self._db.conn.commit()
        except Exception: pass

    def _exec(self, sql, params=None): return self._db.execute(sql, params or [])

    def _audit(self, gid, tid, et, actor=None, msg=""):
        self.add_audit_event(ProductionSandboxGateAuditEvent(gate_request_id=gid, tenant_id=tid, event_type=et, actor_id=actor, message=msg))

    def create_gate_request(self, req):
        self._exec(f"""INSERT INTO production_sandbox_gate_requests (
            gate_request_id,tenant_id,requested_by,step25_final_gate_snapshot_json,red_team_snapshot_json,
            docs_snapshot_json,startup_snapshot_json,runtime_endpoint_snapshot_json,execution_snapshot_json,
            queue_snapshot_json,download_snapshot_json,extraction_snapshot_json,enforcement_snapshot_json,
            trusted_fixture_snapshot_json,gate_status,decision,risk_level,
            no_third_party_execution_enabled,no_package_execution_enabled,no_download_enabled,no_extraction_enabled,
            no_real_queue_enabled,no_dispatch_enabled,no_worker_enabled,no_container_enabled,no_microvm_enabled,
            no_agent_runtime_enabled,no_agent_registry_execution_enabled,
            created_at,updated_at,cancelled_at,expired_at,expires_at,metadata_json
        ) VALUES ({_VR})""", [
            req.gate_request_id,req.tenant_id,req.requested_by,_jd(req.step25_final_gate_snapshot),
            _jd(req.red_team_snapshot),_jd(req.docs_snapshot),_jd(req.startup_snapshot),
            _jd(req.runtime_endpoint_snapshot),_jd(req.execution_snapshot),_jd(req.queue_snapshot),
            _jd(req.download_snapshot),_jd(req.extraction_snapshot),_jd(req.enforcement_snapshot),
            _jd(req.trusted_fixture_snapshot),req.gate_status,req.decision,req.risk_level,
            int(req.no_third_party_execution_enabled),int(req.no_package_execution_enabled),
            int(req.no_download_enabled),int(req.no_extraction_enabled),int(req.no_real_queue_enabled),
            int(req.no_dispatch_enabled),int(req.no_worker_enabled),int(req.no_container_enabled),
            int(req.no_microvm_enabled),int(req.no_agent_runtime_enabled),int(req.no_agent_registry_execution_enabled),
            req.created_at.isoformat() if req.created_at else _now(),
            req.updated_at.isoformat() if req.updated_at else _now(),
            req.cancelled_at.isoformat() if req.cancelled_at else None,
            req.expired_at.isoformat() if req.expired_at else None,
            req.expires_at.isoformat() if req.expires_at else None,_jd(req.metadata)])
        self._audit(req.gate_request_id,req.tenant_id,ProductionSandboxGateAuditEventType.GATE_REQUEST_CREATED,
                    req.requested_by,"Gate request created.")
        return req

    def get_gate_request(self, gid):
        row = next(self._exec("SELECT * FROM production_sandbox_gate_requests WHERE gate_request_id=?",[gid]),None)
        return self._row_to_req(dict(row)) if row else None

    def list_gate_requests(self, *, tenant_id="", status="", decision=""):
        sql,p = "SELECT * FROM production_sandbox_gate_requests WHERE 1=1",[]
        if tenant_id: sql+=" AND tenant_id=?"; p.append(tenant_id)
        if status: sql+=" AND gate_status=?"; p.append(status)
        if decision: sql+=" AND decision=?"; p.append(decision)
        return [self._row_to_req(dict(r)) for r in self._exec(sql+" ORDER BY created_at DESC",p)]

    def update_gate_request(self, req):
        req.updated_at=datetime.now(timezone.utc)
        self._exec("UPDATE production_sandbox_gate_requests SET gate_status=?,decision=?,risk_level=?,updated_at=?,cancelled_at=?,expired_at=?,metadata_json=? WHERE gate_request_id=?",
            [req.gate_status,req.decision,req.risk_level,req.updated_at.isoformat(),
             req.cancelled_at.isoformat() if req.cancelled_at else None,
             req.expired_at.isoformat() if req.expired_at else None,_jd(req.metadata),req.gate_request_id])
        return req

    def set_gate_status(self,gid,st,actor=None,reason=None):
        r=self.get_gate_request(gid)
        if r is None: raise ProductionSandboxGateRequestNotFoundError(f"Not found: {gid}")
        old=r.gate_status; r.gate_status=st; self.update_gate_request(r)
        self._audit(gid,r.tenant_id,ProductionSandboxGateAuditEventType.STATUS_CHANGED,actor,f"Status: {old} -> {st}")
        return r

    def set_decision(self,gid,d,actor=None,reason=None):
        r=self.get_gate_request(gid)
        if r is None: raise ProductionSandboxGateRequestNotFoundError(f"Not found: {gid}")
        old=r.decision; r.decision=d; self.update_gate_request(r)
        self._audit(gid,r.tenant_id,ProductionSandboxGateAuditEventType.DECISION_CHANGED,actor,f"Decision: {old} -> {d}")
        return r

    def create_gate_result(self,result):
        self._exec(f"""INSERT INTO production_sandbox_gate_results (
            gate_result_id,gate_request_id,tenant_id,gate_status,decision,requirements_json,checks_json,
            satisfied_count,missing_count,blocked_count,warnings_count,blockers_count,ready_for_step26b,
            ready_for_controlled_runtime_spike,third_party_execution_allowed,package_execution_allowed,
            runtime_enabled,metadata_only,created_at,metadata_json
        ) VALUES ({_VRES})""", [
            result.gate_result_id,result.gate_request_id,result.tenant_id,result.gate_status,result.decision,
            _jd([r.to_dict() for r in result.requirements]),_jd([c.to_dict() for c in result.checks]),
            result.satisfied_count,result.missing_count,result.blocked_count,result.warnings_count,
            result.blockers_count,int(result.ready_for_step26b),int(result.ready_for_controlled_runtime_spike),
            int(result.third_party_execution_allowed),int(result.package_execution_allowed),
            int(result.runtime_enabled),int(result.metadata_only),
            result.created_at.isoformat() if result.created_at else _now(),_jd(result.metadata)])
        self._audit(result.gate_request_id,result.tenant_id,ProductionSandboxGateAuditEventType.GATE_EVALUATED,
                    None,"Gate evaluated.")
        return result

    def get_gate_result(self,gid):
        row=next(self._exec("SELECT * FROM production_sandbox_gate_results WHERE gate_result_id=?",[gid]),None)
        return self._row_to_res(dict(row)) if row else None

    def get_gate_result_by_request(self,gid):
        row=next(self._exec("SELECT * FROM production_sandbox_gate_results WHERE gate_request_id=? ORDER BY created_at DESC LIMIT 1",[gid]),None)
        return self._row_to_res(dict(row)) if row else None

    def cancel_gate_request(self,gid,actor=None,reason=None):
        r=self.get_gate_request(gid)
        if r is None: raise ProductionSandboxGateRequestNotFoundError(f"Not found: {gid}")
        r.gate_status=ProductionSandboxGateStatus.FAIL_CLOSED; r.cancelled_at=datetime.now(timezone.utc)
        self.update_gate_request(r)
        self._audit(gid,r.tenant_id,ProductionSandboxGateAuditEventType.CANCELLED,actor,"Cancelled.")
        return r

    def expire_gate_request(self,gid,actor=None,reason=None):
        r=self.get_gate_request(gid)
        if r is None: raise ProductionSandboxGateRequestNotFoundError(f"Not found: {gid}")
        r.gate_status=ProductionSandboxGateStatus.FAIL_CLOSED; r.expired_at=datetime.now(timezone.utc)
        self.update_gate_request(r)
        self._audit(gid,r.tenant_id,ProductionSandboxGateAuditEventType.EXPIRED,actor,"Expired.")
        return r

    def add_audit_event(self,evt):
        self._exec("""INSERT INTO production_sandbox_gate_audit_events (
            event_id,gate_request_id,tenant_id,event_type,severity,actor_id,message,metadata_json,created_at
        ) VALUES (?,?,?,?,?,?,?,?,?)""", [evt.event_id,evt.gate_request_id,evt.tenant_id,evt.event_type,
            evt.severity,evt.actor_id,evt.message,_jd(evt.metadata),
            evt.created_at.isoformat() if evt.created_at else _now()])
        return evt

    def list_audit_events(self,gid):
        return [self._row_to_ae(dict(r)) for r in self._exec(
            "SELECT * FROM production_sandbox_gate_audit_events WHERE gate_request_id=? ORDER BY created_at ASC",[gid])]

    def count_gate_requests(self, *, tenant_id="", status="", decision=""):
        sql,p = "SELECT COUNT(*) as cnt FROM production_sandbox_gate_requests WHERE 1=1",[]
        if tenant_id: sql+=" AND tenant_id=?"; p.append(tenant_id)
        if status: sql+=" AND gate_status=?"; p.append(status)
        if decision: sql+=" AND decision=?"; p.append(decision)
        row=next(self._exec(sql,p),None); return row["cnt"] if row else 0

    @staticmethod
    def _row_to_req(row): return ProductionSandboxGateRequest(
        gate_request_id=row["gate_request_id"],tenant_id=row["tenant_id"],requested_by=row.get("requested_by"),
        step25_final_gate_snapshot=json.loads(row.get("step25_final_gate_snapshot_json","{}")),
        red_team_snapshot=json.loads(row.get("red_team_snapshot_json","{}")),
        docs_snapshot=json.loads(row.get("docs_snapshot_json","{}")),
        startup_snapshot=json.loads(row.get("startup_snapshot_json","{}")),
        runtime_endpoint_snapshot=json.loads(row.get("runtime_endpoint_snapshot_json","{}")),
        execution_snapshot=json.loads(row.get("execution_snapshot_json","{}")),
        queue_snapshot=json.loads(row.get("queue_snapshot_json","{}")),
        download_snapshot=json.loads(row.get("download_snapshot_json","{}")),
        extraction_snapshot=json.loads(row.get("extraction_snapshot_json","{}")),
        enforcement_snapshot=json.loads(row.get("enforcement_snapshot_json","{}")),
        trusted_fixture_snapshot=json.loads(row.get("trusted_fixture_snapshot_json","{}")),
        gate_status=row.get("gate_status","draft"),decision=row.get("decision","blocked"),risk_level=row.get("risk_level","unknown"),
        no_third_party_execution_enabled=bool(row.get("no_third_party_execution_enabled",1)),
        no_package_execution_enabled=bool(row.get("no_package_execution_enabled",1)),
        no_download_enabled=bool(row.get("no_download_enabled",1)),no_extraction_enabled=bool(row.get("no_extraction_enabled",1)),
        no_real_queue_enabled=bool(row.get("no_real_queue_enabled",1)),no_dispatch_enabled=bool(row.get("no_dispatch_enabled",1)),
        no_worker_enabled=bool(row.get("no_worker_enabled",1)),no_container_enabled=bool(row.get("no_container_enabled",1)),
        no_microvm_enabled=bool(row.get("no_microvm_enabled",1)),no_agent_runtime_enabled=bool(row.get("no_agent_runtime_enabled",1)),
        no_agent_registry_execution_enabled=bool(row.get("no_agent_registry_execution_enabled",1)),
        created_at=_sdt(row.get("created_at")),updated_at=_sdt(row.get("updated_at")),
        cancelled_at=_sdt(row.get("cancelled_at"),True),expired_at=_sdt(row.get("expired_at"),True),
        expires_at=_sdt(row.get("expires_at"),True),metadata=json.loads(row.get("metadata_json","{}")))

    @staticmethod
    def _row_to_res(row):
        reqs = [ProductionSandboxRequirement.from_dict(r) for r in json.loads(row.get("requirements_json","[]"))]
        chks = [ProductionSandboxGateCheck.from_dict(c) for c in json.loads(row.get("checks_json","[]"))]
        return ProductionSandboxGateResult(
            gate_result_id=row["gate_result_id"],gate_request_id=row["gate_request_id"],tenant_id=row["tenant_id"],
            gate_status=row.get("gate_status","blocked"),decision=row.get("decision","blocked"),
            requirements=reqs,checks=chks,satisfied_count=int(row.get("satisfied_count",0)),
            missing_count=int(row.get("missing_count",0)),blocked_count=int(row.get("blocked_count",0)),
            warnings_count=int(row.get("warnings_count",0)),blockers_count=int(row.get("blockers_count",0)),
            ready_for_step26b=bool(row.get("ready_for_step26b",0)),
            ready_for_controlled_runtime_spike=bool(row.get("ready_for_controlled_runtime_spike",0)),
            third_party_execution_allowed=bool(row.get("third_party_execution_allowed",0)),
            package_execution_allowed=bool(row.get("package_execution_allowed",0)),
            runtime_enabled=bool(row.get("runtime_enabled",0)),metadata_only=bool(row.get("metadata_only",1)),
            created_at=_sdt(row.get("created_at")),metadata=json.loads(row.get("metadata_json","{}")))

    @staticmethod
    def _row_to_ae(row): return ProductionSandboxGateAuditEvent(
        event_id=row["event_id"],gate_request_id=row["gate_request_id"],tenant_id=row["tenant_id"],
        event_type=row.get("event_type",""),severity=row.get("severity","info"),actor_id=row.get("actor_id"),
        message=row.get("message",""),metadata=json.loads(row.get("metadata_json","{}")),created_at=_sdt(row.get("created_at")))

def _sdt(raw,none_ok=False):
    if not raw: return None if none_ok else datetime.now(timezone.utc)
    try: return datetime.fromisoformat(str(raw).replace("Z","+00:00"))
    except: return None if none_ok else datetime.now(timezone.utc)
def _now(): return datetime.now(timezone.utc).isoformat()
