"""SQLite Artifact Extraction Guard Store — metadata-only, no archive read, no extraction, no file write."""
from __future__ import annotations
import json, logging
from datetime import datetime, timezone
from typing import Any
from src.adapters.config import Settings
from src.adapters.sqlite_connection import create_sqlite_db, execute_with_retry
from src.open_platform.artifact_extraction_guard import *

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS artifact_extraction_guard_requests (
    request_id TEXT PRIMARY KEY, package_download_request_id TEXT, package_quarantine_id TEXT,
    artifact_id TEXT NOT NULL, tenant_id TEXT NOT NULL, developer_id TEXT, submission_id TEXT,
    requested_by TEXT, archive_format TEXT NOT NULL DEFAULT 'unknown_blocked',
    guard_request_status TEXT NOT NULL DEFAULT 'draft', decision TEXT NOT NULL DEFAULT 'blocked',
    guard_status TEXT NOT NULL DEFAULT 'not_evaluated', plan_status TEXT NOT NULL DEFAULT 'not_created',
    risk_level TEXT NOT NULL DEFAULT 'unknown', entry_count INTEGER NOT NULL DEFAULT 0,
    total_declared_size_bytes INTEGER, max_entry_count INTEGER NOT NULL DEFAULT 1000,
    max_entry_size_bytes INTEGER NOT NULL DEFAULT 50000000, max_total_size_bytes INTEGER NOT NULL DEFAULT 200000000,
    source_snapshot_json TEXT NOT NULL DEFAULT '{}', download_request_snapshot_json TEXT NOT NULL DEFAULT '{}',
    quarantine_record_snapshot_json TEXT NOT NULL DEFAULT '{}', artifact_snapshot_json TEXT NOT NULL DEFAULT '{}',
    entries_json TEXT NOT NULL DEFAULT '[]', no_archive_file_read INTEGER NOT NULL DEFAULT 1,
    no_extraction_performed INTEGER NOT NULL DEFAULT 1, no_file_written INTEGER NOT NULL DEFAULT 1,
    no_execution_performed INTEGER NOT NULL DEFAULT 1, no_subprocess_used INTEGER NOT NULL DEFAULT 1,
    no_container_used INTEGER NOT NULL DEFAULT 1, no_network_used INTEGER NOT NULL DEFAULT 1,
    no_queue_created INTEGER NOT NULL DEFAULT 1, no_job_dispatched INTEGER NOT NULL DEFAULT 1,
    no_agent_runtime_used INTEGER NOT NULL DEFAULT 1, no_agent_registry_used INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')), updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    cancelled_at TEXT, expired_at TEXT, expires_at TEXT, metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_extreq_tenant ON artifact_extraction_guard_requests(tenant_id);
CREATE INDEX IF NOT EXISTS idx_extreq_artifact ON artifact_extraction_guard_requests(artifact_id);
CREATE INDEX IF NOT EXISTS idx_extreq_dl ON artifact_extraction_guard_requests(package_download_request_id);
CREATE INDEX IF NOT EXISTS idx_extreq_status ON artifact_extraction_guard_requests(guard_request_status);
CREATE INDEX IF NOT EXISTS idx_extreq_decision ON artifact_extraction_guard_requests(decision);
CREATE INDEX IF NOT EXISTS idx_extreq_gstatus ON artifact_extraction_guard_requests(guard_status);
CREATE INDEX IF NOT EXISTS idx_extreq_pstatus ON artifact_extraction_guard_requests(plan_status);
CREATE INDEX IF NOT EXISTS idx_extreq_created ON artifact_extraction_guard_requests(created_at);

CREATE TABLE IF NOT EXISTS artifact_extraction_guard_results (
    result_id TEXT PRIMARY KEY, request_id TEXT NOT NULL, tenant_id TEXT NOT NULL,
    guard_status TEXT NOT NULL DEFAULT 'not_evaluated', decision TEXT NOT NULL DEFAULT 'blocked',
    checks_json TEXT NOT NULL DEFAULT '[]', total_entries INTEGER NOT NULL DEFAULT 0,
    accepted_entries INTEGER NOT NULL DEFAULT 0, blocked_entries INTEGER NOT NULL DEFAULT 0,
    warnings_count INTEGER NOT NULL DEFAULT 0, errors_count INTEGER NOT NULL DEFAULT 0,
    blockers_count INTEGER NOT NULL DEFAULT 0, normalized_paths_json TEXT NOT NULL DEFAULT '[]',
    blocked_entry_ids_json TEXT NOT NULL DEFAULT '[]', metadata_only INTEGER NOT NULL DEFAULT 1,
    no_archive_file_read INTEGER NOT NULL DEFAULT 1, no_extraction_performed INTEGER NOT NULL DEFAULT 1,
    no_file_written INTEGER NOT NULL DEFAULT 1, no_execution_performed INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')), metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_extres_req ON artifact_extraction_guard_results(request_id);
CREATE INDEX IF NOT EXISTS idx_extres_tenant ON artifact_extraction_guard_results(tenant_id);
CREATE INDEX IF NOT EXISTS idx_extres_gs ON artifact_extraction_guard_results(guard_status);

CREATE TABLE IF NOT EXISTS read_only_extraction_plans (
    plan_id TEXT PRIMARY KEY, request_id TEXT NOT NULL, artifact_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL, plan_status TEXT NOT NULL DEFAULT 'not_created',
    logical_extraction_ref TEXT, allowed_normalized_paths_json TEXT NOT NULL DEFAULT '[]',
    blocked_entry_ids_json TEXT NOT NULL DEFAULT '[]', extraction_allowed INTEGER NOT NULL DEFAULT 0,
    file_write_allowed INTEGER NOT NULL DEFAULT 0, execution_allowed INTEGER NOT NULL DEFAULT 0,
    metadata_only INTEGER NOT NULL DEFAULT 1, created_by TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')), updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_extplan_req ON read_only_extraction_plans(request_id);
CREATE INDEX IF NOT EXISTS idx_extplan_status ON read_only_extraction_plans(plan_status);

CREATE TABLE IF NOT EXISTS artifact_extraction_audit_events (
    event_id TEXT PRIMARY KEY, request_id TEXT NOT NULL, tenant_id TEXT NOT NULL,
    event_type TEXT NOT NULL, severity TEXT NOT NULL DEFAULT 'info',
    actor_id TEXT, message TEXT NOT NULL DEFAULT '', metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_extevt_req ON artifact_extraction_audit_events(request_id);
CREATE INDEX IF NOT EXISTS idx_extevt_tenant ON artifact_extraction_audit_events(tenant_id);
CREATE INDEX IF NOT EXISTS idx_extevt_created ON artifact_extraction_audit_events(created_at);
"""

# 42 columns, 42 ? marks
_VALUES = "?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?"

class SQLiteArtifactExtractionGuardStore:
    def __init__(self, config: Settings, db_path: str | None = None):
        path = db_path or config.sqlite_db_path
        self._db = create_sqlite_db(path)
        execute_with_retry(lambda: self._init_schema(), label="ext_guard_init_schema")

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

    def _audit(self, request_id, tenant_id, event_type, actor_id=None, message="", meta=None):
        self.add_audit_event(ArtifactExtractionAuditEvent(request_id=request_id, tenant_id=tenant_id,
            event_type=event_type, actor_id=actor_id, message=message, metadata=meta or {}))

    def create_request(self, req: ArtifactExtractionGuardRequest) -> ArtifactExtractionGuardRequest:
        self._exec(f"""INSERT INTO artifact_extraction_guard_requests (
            request_id,package_download_request_id,package_quarantine_id,artifact_id,tenant_id,developer_id,
            submission_id,requested_by,archive_format,guard_request_status,decision,guard_status,plan_status,
            risk_level,entry_count,total_declared_size_bytes,max_entry_count,max_entry_size_bytes,
            max_total_size_bytes,source_snapshot_json,download_request_snapshot_json,
            quarantine_record_snapshot_json,artifact_snapshot_json,entries_json,
            no_archive_file_read,no_extraction_performed,no_file_written,no_execution_performed,
            no_subprocess_used,no_container_used,no_network_used,no_queue_created,no_job_dispatched,
            no_agent_runtime_used,no_agent_registry_used,created_at,updated_at,cancelled_at,expired_at,expires_at,metadata_json
        ) VALUES ({_VALUES})""", [
            req.request_id,req.package_download_request_id,req.package_quarantine_id,req.artifact_id,
            req.tenant_id,req.developer_id,req.submission_id,req.requested_by,req.archive_format,
            req.guard_request_status,req.decision,req.guard_status,req.plan_status,req.risk_level,
            req.entry_count,req.total_declared_size_bytes,req.max_entry_count,req.max_entry_size_bytes,
            req.max_total_size_bytes,json.dumps(req.source_snapshot,ensure_ascii=False),
            json.dumps(req.download_request_snapshot,ensure_ascii=False),
            json.dumps(req.quarantine_record_snapshot,ensure_ascii=False),
            json.dumps(req.artifact_snapshot,ensure_ascii=False),
            json.dumps([e.to_dict() for e in req.entries],ensure_ascii=False),
            int(req.no_archive_file_read),int(req.no_extraction_performed),int(req.no_file_written),
            int(req.no_execution_performed),int(req.no_subprocess_used),int(req.no_container_used),
            int(req.no_network_used),int(req.no_queue_created),int(req.no_job_dispatched),
            int(req.no_agent_runtime_used),int(req.no_agent_registry_used),
            req.created_at.isoformat() if req.created_at else datetime.now(timezone.utc).isoformat(),
            req.updated_at.isoformat() if req.updated_at else datetime.now(timezone.utc).isoformat(),
            req.cancelled_at.isoformat() if req.cancelled_at else None,
            req.expired_at.isoformat() if req.expired_at else None,
            req.expires_at.isoformat() if req.expires_at else None,
            json.dumps(req.metadata,ensure_ascii=False)])
        self._audit(req.request_id,req.tenant_id,ArtifactExtractionAuditEventType.REQUEST_CREATED,
            req.requested_by,f"Extraction guard request created for {req.artifact_id}")
        return req

    def get_request(self, rid): row=next(self._exec("SELECT * FROM artifact_extraction_guard_requests WHERE request_id=?",[rid]),None); return self._row_to_req(dict(row)) if row else None

    def list_requests(self, *, tenant_id="", artifact_id="", status="", decision="", guard_status="", plan_status=""):
        sql,p="SELECT * FROM artifact_extraction_guard_requests WHERE 1=1",[]
        if tenant_id: sql+=" AND tenant_id=?"; p.append(tenant_id)
        if artifact_id: sql+=" AND artifact_id=?"; p.append(artifact_id)
        if status: sql+=" AND guard_request_status=?"; p.append(status)
        if decision: sql+=" AND decision=?"; p.append(decision)
        if guard_status: sql+=" AND guard_status=?"; p.append(guard_status)
        if plan_status: sql+=" AND plan_status=?"; p.append(plan_status)
        return [self._row_to_req(dict(r)) for r in self._exec(sql+" ORDER BY created_at DESC",p)]

    def update_request(self, req):
        req.updated_at=datetime.now(timezone.utc)
        self._exec("""UPDATE artifact_extraction_guard_requests SET
            guard_request_status=?,decision=?,guard_status=?,plan_status=?,risk_level=?,
            entries_json=?,updated_at=?,cancelled_at=?,expired_at=?,metadata_json=? WHERE request_id=?""",[
            req.guard_request_status,req.decision,req.guard_status,req.plan_status,req.risk_level,
            json.dumps([e.to_dict() for e in req.entries],ensure_ascii=False),
            req.updated_at.isoformat(),req.cancelled_at.isoformat() if req.cancelled_at else None,
            req.expired_at.isoformat() if req.expired_at else None,json.dumps(req.metadata,ensure_ascii=False),
            req.request_id]); return req

    def set_request_status(self,rid,status,actor_id=None,reason=None):
        r=self.get_request(rid)
        if r is None: raise ArtifactExtractionRequestNotFoundError(f"Not found: {rid}")
        old=r.guard_request_status; r.guard_request_status=status; self.update_request(r)
        self._audit(rid,r.tenant_id,ArtifactExtractionAuditEventType.STATUS_CHANGED,actor_id,
            f"Status: {old} -> {status}"+(f" (reason: {reason})" if reason else "")); return r

    def set_decision(self,rid,decision,actor_id=None,reason=None):
        r=self.get_request(rid)
        if r is None: raise ArtifactExtractionRequestNotFoundError(f"Not found: {rid}")
        old=r.decision; r.decision=decision; self.update_request(r)
        self._audit(rid,r.tenant_id,ArtifactExtractionAuditEventType.DECISION_CHANGED,actor_id,
            f"Decision: {old} -> {decision}"+(f" (reason: {reason})" if reason else "")); return r

    def create_result(self,result):
        self._exec("""INSERT INTO artifact_extraction_guard_results (
            result_id,request_id,tenant_id,guard_status,decision,checks_json,total_entries,accepted_entries,
            blocked_entries,warnings_count,errors_count,blockers_count,normalized_paths_json,
            blocked_entry_ids_json,metadata_only,no_archive_file_read,no_extraction_performed,no_file_written,
            no_execution_performed,created_at,metadata_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",[
            result.result_id,result.request_id,result.tenant_id,result.guard_status,result.decision,
            json.dumps([c.to_dict() for c in result.checks],ensure_ascii=False),result.total_entries,
            result.accepted_entries,result.blocked_entries,result.warnings_count,result.errors_count,
            result.blockers_count,json.dumps(result.normalized_paths,ensure_ascii=False),
            json.dumps(result.blocked_entry_ids,ensure_ascii=False),int(result.metadata_only),
            int(result.no_archive_file_read),int(result.no_extraction_performed),int(result.no_file_written),
            int(result.no_execution_performed),result.created_at.isoformat() if result.created_at else datetime.now(timezone.utc).isoformat(),
            json.dumps(result.metadata,ensure_ascii=False)])
        self._audit(result.request_id,result.tenant_id,ArtifactExtractionAuditEventType.GUARD_EVALUATED,
            None,f"Guard evaluated: {result.guard_status}"); return result

    def get_result(self, rid): row=next(self._exec("SELECT * FROM artifact_extraction_guard_results WHERE result_id=?",[rid]),None); return self._row_to_result(dict(row)) if row else None
    def get_result_by_request(self, rid): row=next(self._exec("SELECT * FROM artifact_extraction_guard_results WHERE request_id=? ORDER BY created_at DESC LIMIT 1",[rid]),None); return self._row_to_result(dict(row)) if row else None

    def reserve_plan(self,plan):
        self._exec("""INSERT INTO read_only_extraction_plans (
            plan_id,request_id,artifact_id,tenant_id,plan_status,logical_extraction_ref,
            allowed_normalized_paths_json,blocked_entry_ids_json,extraction_allowed,file_write_allowed,
            execution_allowed,metadata_only,created_by,created_at,updated_at,metadata_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",[
            plan.plan_id,plan.request_id,plan.artifact_id,plan.tenant_id,plan.plan_status,
            plan.logical_extraction_ref,json.dumps(plan.allowed_normalized_paths,ensure_ascii=False),
            json.dumps(plan.blocked_entry_ids,ensure_ascii=False),int(plan.extraction_allowed),
            int(plan.file_write_allowed),int(plan.execution_allowed),int(plan.metadata_only),
            plan.created_by,plan.created_at.isoformat() if plan.created_at else datetime.now(timezone.utc).isoformat(),
            plan.updated_at.isoformat() if plan.updated_at else datetime.now(timezone.utc).isoformat(),
            json.dumps(plan.metadata,ensure_ascii=False)])
        self._audit(plan.request_id,plan.tenant_id,ArtifactExtractionAuditEventType.PLAN_RESERVED,
            plan.created_by,f"Read-only extraction plan reserved: {plan.plan_id}"); return plan

    def get_plan(self,pid): row=next(self._exec("SELECT * FROM read_only_extraction_plans WHERE plan_id=?",[pid]),None); return self._row_to_plan(dict(row)) if row else None
    def get_plan_by_request(self,rid): row=next(self._exec("SELECT * FROM read_only_extraction_plans WHERE request_id=? ORDER BY created_at DESC LIMIT 1",[rid]),None); return self._row_to_plan(dict(row)) if row else None

    def cancel_request(self,rid,actor_id=None,reason=None):
        r=self.get_request(rid)
        if r is None: raise ArtifactExtractionRequestNotFoundError(f"Not found: {rid}")
        r.guard_request_status=ExtractionGuardRequestStatus.CANCELLED; r.cancelled_at=datetime.now(timezone.utc); self.update_request(r)
        self._audit(rid,r.tenant_id,ArtifactExtractionAuditEventType.CANCELLED,actor_id,"Request cancelled."); return r

    def expire_request(self,rid,actor_id=None,reason=None):
        r=self.get_request(rid)
        if r is None: raise ArtifactExtractionRequestNotFoundError(f"Not found: {rid}")
        r.guard_request_status=ExtractionGuardRequestStatus.EXPIRED; r.expired_at=datetime.now(timezone.utc); self.update_request(r)
        self._audit(rid,r.tenant_id,ArtifactExtractionAuditEventType.EXPIRED,actor_id,"Request expired."); return r

    def add_audit_event(self,evt):
        self._exec("""INSERT INTO artifact_extraction_audit_events (
            event_id,request_id,tenant_id,event_type,severity,actor_id,message,metadata_json,created_at) VALUES (?,?,?,?,?,?,?,?,?)""",[
            evt.event_id,evt.request_id,evt.tenant_id,evt.event_type,evt.severity,evt.actor_id,evt.message,
            json.dumps(evt.metadata,ensure_ascii=False),evt.created_at.isoformat() if evt.created_at else datetime.now(timezone.utc).isoformat()]); return evt

    def list_audit_events(self,rid): return [self._row_to_ae(dict(r)) for r in self._exec("SELECT * FROM artifact_extraction_audit_events WHERE request_id=? ORDER BY created_at ASC",[rid])]

    def count_requests(self, *, tenant_id="", status="", decision="", guard_status=""):
        sql,p="SELECT COUNT(*) as cnt FROM artifact_extraction_guard_requests WHERE 1=1",[]
        if tenant_id: sql+=" AND tenant_id=?"; p.append(tenant_id)
        if status: sql+=" AND guard_request_status=?"; p.append(status)
        if decision: sql+=" AND decision=?"; p.append(decision)
        if guard_status: sql+=" AND guard_status=?"; p.append(guard_status)
        row=next(self._exec(sql,p),None); return row["cnt"] if row else 0

    @staticmethod
    def _row_to_req(row): entries=[ArchiveEntryMetadata.from_dict(e) for e in json.loads(row.get("entries_json","[]"))]; return ArtifactExtractionGuardRequest(
        request_id=row["request_id"],package_download_request_id=row.get("package_download_request_id"),
        package_quarantine_id=row.get("package_quarantine_id"),artifact_id=row["artifact_id"],
        tenant_id=row["tenant_id"],developer_id=row.get("developer_id"),submission_id=row.get("submission_id"),
        requested_by=row.get("requested_by"),archive_format=row.get("archive_format","unknown_blocked"),
        guard_request_status=row.get("guard_request_status","draft"),decision=row.get("decision","blocked"),
        guard_status=row.get("guard_status","not_evaluated"),plan_status=row.get("plan_status","not_created"),
        risk_level=row.get("risk_level","unknown"),entry_count=int(row.get("entry_count",0)),
        total_declared_size_bytes=row.get("total_declared_size_bytes"),max_entry_count=int(row.get("max_entry_count",1000)),
        max_entry_size_bytes=int(row.get("max_entry_size_bytes",50000000)),max_total_size_bytes=int(row.get("max_total_size_bytes",200000000)),
        source_snapshot=json.loads(row.get("source_snapshot_json","{}")),download_request_snapshot=json.loads(row.get("download_request_snapshot_json","{}")),
        quarantine_record_snapshot=json.loads(row.get("quarantine_record_snapshot_json","{}")),artifact_snapshot=json.loads(row.get("artifact_snapshot_json","{}")),
        entries=entries,no_archive_file_read=bool(row.get("no_archive_file_read",1)),no_extraction_performed=bool(row.get("no_extraction_performed",1)),
        no_file_written=bool(row.get("no_file_written",1)),no_execution_performed=bool(row.get("no_execution_performed",1)),
        no_subprocess_used=bool(row.get("no_subprocess_used",1)),no_container_used=bool(row.get("no_container_used",1)),
        no_network_used=bool(row.get("no_network_used",1)),no_queue_created=bool(row.get("no_queue_created",1)),
        no_job_dispatched=bool(row.get("no_job_dispatched",1)),no_agent_runtime_used=bool(row.get("no_agent_runtime_used",1)),
        no_agent_registry_used=bool(row.get("no_agent_registry_used",1)),created_at=_sdt(row.get("created_at")),
        updated_at=_sdt(row.get("updated_at")),cancelled_at=_sdt(row.get("cancelled_at"),True),
        expired_at=_sdt(row.get("expired_at"),True),expires_at=_sdt(row.get("expires_at"),True),
        metadata=json.loads(row.get("metadata_json","{}")))

    @staticmethod
    def _row_to_result(row): checks=[ExtractionGuardCheck.from_dict(c) for c in json.loads(row.get("checks_json","[]"))]; return ArtifactExtractionGuardResult(
        result_id=row["result_id"],request_id=row["request_id"],tenant_id=row["tenant_id"],
        guard_status=row.get("guard_status","not_evaluated"),decision=row.get("decision","blocked"),
        checks=checks,total_entries=int(row.get("total_entries",0)),accepted_entries=int(row.get("accepted_entries",0)),
        blocked_entries=int(row.get("blocked_entries",0)),warnings_count=int(row.get("warnings_count",0)),
        errors_count=int(row.get("errors_count",0)),blockers_count=int(row.get("blockers_count",0)),
        normalized_paths=json.loads(row.get("normalized_paths_json","[]")),blocked_entry_ids=json.loads(row.get("blocked_entry_ids_json","[]")),
        metadata_only=bool(row.get("metadata_only",1)),no_archive_file_read=bool(row.get("no_archive_file_read",1)),
        no_extraction_performed=bool(row.get("no_extraction_performed",1)),no_file_written=bool(row.get("no_file_written",1)),
        no_execution_performed=bool(row.get("no_execution_performed",1)),created_at=_sdt(row.get("created_at")),
        metadata=json.loads(row.get("metadata_json","{}")))

    @staticmethod
    def _row_to_plan(row): return ReadOnlyExtractionPlan(
        plan_id=row["plan_id"],request_id=row["request_id"],artifact_id=row["artifact_id"],tenant_id=row["tenant_id"],
        plan_status=row.get("plan_status","not_created"),logical_extraction_ref=row.get("logical_extraction_ref"),
        allowed_normalized_paths=json.loads(row.get("allowed_normalized_paths_json","[]")),
        blocked_entry_ids=json.loads(row.get("blocked_entry_ids_json","[]")),
        extraction_allowed=bool(row.get("extraction_allowed",0)),file_write_allowed=bool(row.get("file_write_allowed",0)),
        execution_allowed=bool(row.get("execution_allowed",0)),metadata_only=bool(row.get("metadata_only",1)),
        created_by=row.get("created_by"),created_at=_sdt(row.get("created_at")),updated_at=_sdt(row.get("updated_at")),
        metadata=json.loads(row.get("metadata_json","{}")))

    @staticmethod
    def _row_to_ae(row): return ArtifactExtractionAuditEvent(
        event_id=row["event_id"],request_id=row["request_id"],tenant_id=row["tenant_id"],
        event_type=row.get("event_type",""),severity=row.get("severity","info"),actor_id=row.get("actor_id"),
        message=row.get("message",""),metadata=json.loads(row.get("metadata_json","{}")),created_at=_sdt(row.get("created_at")))

def _sdt(raw,none_ok=False):
    if not raw: return None if none_ok else datetime.now(timezone.utc)
    try: return datetime.fromisoformat(str(raw).replace("Z","+00:00"))
    except: return None if none_ok else datetime.now(timezone.utc)
