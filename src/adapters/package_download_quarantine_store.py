"""SQLite Package Download Quarantine Store — admin-gated, no download, no network, no file write."""
from __future__ import annotations
import json, logging
from datetime import datetime, timezone
from typing import Any
from src.adapters.config import Settings
from src.adapters.sqlite_connection import create_sqlite_db, execute_with_retry
from src.open_platform.package_download_quarantine import *

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS package_download_requests (
    request_id TEXT PRIMARY KEY, artifact_id TEXT NOT NULL, marketplace_agent_id TEXT,
    tenant_id TEXT NOT NULL, developer_id TEXT, submission_id TEXT, requested_by TEXT,
    source_metadata_json TEXT NOT NULL DEFAULT '{}',
    request_status TEXT NOT NULL DEFAULT 'draft', decision TEXT NOT NULL DEFAULT 'blocked',
    gate_status TEXT NOT NULL DEFAULT 'closed', quarantine_status TEXT NOT NULL DEFAULT 'not_created',
    risk_level TEXT NOT NULL DEFAULT 'unknown',
    admin_approved_by TEXT, admin_rejected_by TEXT, cancelled_by TEXT, expired_by TEXT,
    approval_reason TEXT, rejection_reason TEXT, input_payload_hash TEXT,
    artifact_snapshot_json TEXT NOT NULL DEFAULT '{}',
    verification_snapshot_json TEXT NOT NULL DEFAULT '{}',
    execution_snapshot_json TEXT NOT NULL DEFAULT '{}',
    no_download_performed INTEGER NOT NULL DEFAULT 1, no_network_used INTEGER NOT NULL DEFAULT 1,
    no_file_written INTEGER NOT NULL DEFAULT 1, no_package_extracted INTEGER NOT NULL DEFAULT 1,
    no_execution_performed INTEGER NOT NULL DEFAULT 1, no_subprocess_used INTEGER NOT NULL DEFAULT 1,
    no_container_used INTEGER NOT NULL DEFAULT 1, no_queue_created INTEGER NOT NULL DEFAULT 1,
    no_job_dispatched INTEGER NOT NULL DEFAULT 1, no_agent_runtime_used INTEGER NOT NULL DEFAULT 1,
    no_agent_registry_used INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')), updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    approved_at TEXT, rejected_at TEXT, cancelled_at TEXT, expired_at TEXT, expires_at TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_pkgdl_tenant ON package_download_requests(tenant_id);
CREATE INDEX IF NOT EXISTS idx_pkgdl_artifact ON package_download_requests(artifact_id);
CREATE INDEX IF NOT EXISTS idx_pkgdl_mkp ON package_download_requests(marketplace_agent_id);
CREATE INDEX IF NOT EXISTS idx_pkgdl_status ON package_download_requests(request_status);
CREATE INDEX IF NOT EXISTS idx_pkgdl_decision ON package_download_requests(decision);
CREATE INDEX IF NOT EXISTS idx_pkgdl_gate ON package_download_requests(gate_status);
CREATE INDEX IF NOT EXISTS idx_pkgdl_qstatus ON package_download_requests(quarantine_status);
CREATE INDEX IF NOT EXISTS idx_pkgdl_created ON package_download_requests(created_at);

CREATE TABLE IF NOT EXISTS package_download_quarantine_records (
    quarantine_id TEXT PRIMARY KEY, request_id TEXT NOT NULL, artifact_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL, quarantine_status TEXT NOT NULL DEFAULT 'not_created',
    logical_quarantine_ref TEXT, file_materialized INTEGER NOT NULL DEFAULT 0,
    file_size_bytes INTEGER, content_sha256 TEXT, extraction_allowed INTEGER NOT NULL DEFAULT 0,
    execution_allowed INTEGER NOT NULL DEFAULT 0, created_by TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')), updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_pkgq_request ON package_download_quarantine_records(request_id);
CREATE INDEX IF NOT EXISTS idx_pkgq_artifact ON package_download_quarantine_records(artifact_id);
CREATE INDEX IF NOT EXISTS idx_pkgq_tenant ON package_download_quarantine_records(tenant_id);
CREATE INDEX IF NOT EXISTS idx_pkgq_status ON package_download_quarantine_records(quarantine_status);

CREATE TABLE IF NOT EXISTS package_download_audit_events (
    event_id TEXT PRIMARY KEY, request_id TEXT NOT NULL, tenant_id TEXT NOT NULL,
    event_type TEXT NOT NULL, severity TEXT NOT NULL DEFAULT 'info',
    actor_id TEXT, message TEXT NOT NULL DEFAULT '', metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_pkgdlevt_request ON package_download_audit_events(request_id);
CREATE INDEX IF NOT EXISTS idx_pkgdlevt_tenant ON package_download_audit_events(tenant_id);
CREATE INDEX IF NOT EXISTS idx_pkgdlevt_type ON package_download_audit_events(event_type);
CREATE INDEX IF NOT EXISTS idx_pkgdlevt_created ON package_download_audit_events(created_at);
"""

class SQLitePackageDownloadQuarantineStore:
    def __init__(self, config: Settings, db_path: str | None = None):
        path = db_path or config.sqlite_db_path
        self._db = create_sqlite_db(path)
        execute_with_retry(lambda: self._init_schema(), label="pkgdl_init_schema")

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

    def _audit(self, request_id, tenant_id, event_type, actor_id=None, message="", severity="INFO", meta=None):
        self.add_audit_event(PackageDownloadAuditEvent(request_id=request_id, tenant_id=tenant_id,
            event_type=event_type, severity=severity, actor_id=actor_id, message=message, metadata=meta or {}))

    # ── Request CRUD ──
    def create_request(self, req: PackageDownloadRequest) -> PackageDownloadRequest:
        self._exec("""INSERT INTO package_download_requests (
            request_id,artifact_id,marketplace_agent_id,tenant_id,developer_id,submission_id,requested_by,
            source_metadata_json,request_status,decision,gate_status,quarantine_status,risk_level,
            admin_approved_by,admin_rejected_by,cancelled_by,expired_by,approval_reason,rejection_reason,
            input_payload_hash,artifact_snapshot_json,verification_snapshot_json,execution_snapshot_json,
            no_download_performed,no_network_used,no_file_written,no_package_extracted,
            no_execution_performed,no_subprocess_used,no_container_used,no_queue_created,
            no_job_dispatched,no_agent_runtime_used,no_agent_registry_used,
            created_at,updated_at,approved_at,rejected_at,cancelled_at,expired_at,expires_at,metadata_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", [
            req.request_id,req.artifact_id,req.marketplace_agent_id,req.tenant_id,req.developer_id,
            req.submission_id,req.requested_by,json.dumps(req.source_metadata.to_dict(),ensure_ascii=False),
            req.request_status,req.decision,req.gate_status,req.quarantine_status,req.risk_level,
            req.admin_approved_by,req.admin_rejected_by,req.cancelled_by,req.expired_by,
            req.approval_reason,req.rejection_reason,req.input_payload_hash,
            json.dumps(req.artifact_snapshot,ensure_ascii=False),
            json.dumps(req.verification_snapshot,ensure_ascii=False),
            json.dumps(req.execution_snapshot,ensure_ascii=False),
            int(req.no_download_performed),int(req.no_network_used),int(req.no_file_written),
            int(req.no_package_extracted),int(req.no_execution_performed),int(req.no_subprocess_used),
            int(req.no_container_used),int(req.no_queue_created),int(req.no_job_dispatched),
            int(req.no_agent_runtime_used),int(req.no_agent_registry_used),
            req.created_at.isoformat() if req.created_at else datetime.now(timezone.utc).isoformat(),
            req.updated_at.isoformat() if req.updated_at else datetime.now(timezone.utc).isoformat(),
            req.approved_at.isoformat() if req.approved_at else None,
            req.rejected_at.isoformat() if req.rejected_at else None,
            req.cancelled_at.isoformat() if req.cancelled_at else None,
            req.expired_at.isoformat() if req.expired_at else None,
            req.expires_at.isoformat() if req.expires_at else None,
            json.dumps(req.metadata,ensure_ascii=False),
        ])
        self._audit(req.request_id,req.tenant_id,PackageDownloadAuditEventType.REQUEST_CREATED,
            req.requested_by,f"Download request created for artifact {req.artifact_id}")
        return req

    def get_request(self, request_id: str) -> PackageDownloadRequest | None:
        row = next(self._exec("SELECT * FROM package_download_requests WHERE request_id=?", [request_id]), None)
        return self._row_to_req(dict(row)) if row else None

    def list_requests(self, *, tenant_id="", artifact_id="", marketplace_agent_id="",
                      status="", decision="", gate_status="", quarantine_status="") -> list[PackageDownloadRequest]:
        sql, p = "SELECT * FROM package_download_requests WHERE 1=1", []
        if tenant_id: sql += " AND tenant_id=?"; p.append(tenant_id)
        if artifact_id: sql += " AND artifact_id=?"; p.append(artifact_id)
        if marketplace_agent_id: sql += " AND marketplace_agent_id=?"; p.append(marketplace_agent_id)
        if status: sql += " AND request_status=?"; p.append(status)
        if decision: sql += " AND decision=?"; p.append(decision)
        if gate_status: sql += " AND gate_status=?"; p.append(gate_status)
        if quarantine_status: sql += " AND quarantine_status=?"; p.append(quarantine_status)
        return [self._row_to_req(dict(r)) for r in self._exec(sql+" ORDER BY created_at DESC", p)]

    def update_request(self, req: PackageDownloadRequest) -> PackageDownloadRequest:
        req.updated_at = datetime.now(timezone.utc)
        self._exec("""UPDATE package_download_requests SET
            source_metadata_json=?,request_status=?,decision=?,gate_status=?,quarantine_status=?,
            risk_level=?,admin_approved_by=?,admin_rejected_by=?,cancelled_by=?,expired_by=?,
            approval_reason=?,rejection_reason=?,input_payload_hash=?,
            artifact_snapshot_json=?,verification_snapshot_json=?,execution_snapshot_json=?,
            updated_at=?,approved_at=?,rejected_at=?,cancelled_at=?,expired_at=?,metadata_json=? WHERE request_id=?""", [
            json.dumps(req.source_metadata.to_dict(),ensure_ascii=False),
            req.request_status,req.decision,req.gate_status,req.quarantine_status,req.risk_level,
            req.admin_approved_by,req.admin_rejected_by,req.cancelled_by,req.expired_by,
            req.approval_reason,req.rejection_reason,req.input_payload_hash,
            json.dumps(req.artifact_snapshot,ensure_ascii=False),
            json.dumps(req.verification_snapshot,ensure_ascii=False),
            json.dumps(req.execution_snapshot,ensure_ascii=False),
            req.updated_at.isoformat(),
            req.approved_at.isoformat() if req.approved_at else None,
            req.rejected_at.isoformat() if req.rejected_at else None,
            req.cancelled_at.isoformat() if req.cancelled_at else None,
            req.expired_at.isoformat() if req.expired_at else None,
            json.dumps(req.metadata,ensure_ascii=False), req.request_id])
        return req

    def set_request_status(self, rid, status, actor_id=None, reason=None):
        r = self.get_request(rid)
        if r is None: raise PackageDownloadRequestNotFoundError(f"Not found: {rid}")
        old = r.request_status; r.request_status = status; self.update_request(r)
        self._audit(rid,r.tenant_id,PackageDownloadAuditEventType.STATUS_CHANGED,actor_id,
            f"Status: {old} -> {status}" + (f" (reason: {reason})" if reason else ""))
        return r

    def set_decision(self, rid, decision, actor_id=None, reason=None):
        r = self.get_request(rid)
        if r is None: raise PackageDownloadRequestNotFoundError(f"Not found: {rid}")
        old = r.decision; r.decision = decision; self.update_request(r)
        self._audit(rid,r.tenant_id,PackageDownloadAuditEventType.DECISION_CHANGED,actor_id,
            f"Decision: {old} -> {decision}" + (f" (reason: {reason})" if reason else ""))
        return r

    def set_gate_status(self, rid, gs, actor_id=None, reason=None):
        r = self.get_request(rid)
        if r is None: raise PackageDownloadRequestNotFoundError(f"Not found: {rid}")
        old = r.gate_status; r.gate_status = gs; self.update_request(r)
        self._audit(rid,r.tenant_id,PackageDownloadAuditEventType.ADMIN_GATE_EVALUATED,actor_id,
            f"Gate: {old} -> {gs}" + (f" (reason: {reason})" if reason else ""))
        return r

    def approve_for_future_download(self, rid, actor_id=None, reason=None):
        r = self.get_request(rid)
        if r is None: raise PackageDownloadRequestNotFoundError(f"Not found: {rid}")
        r.request_status = PackageDownloadRequestStatus.ADMIN_APPROVED_FOR_FUTURE_DOWNLOAD
        r.decision = PackageDownloadDecision.APPROVED_FOR_FUTURE_DOWNLOAD
        r.gate_status = PackageDownloadGateStatus.ADMIN_APPROVED_RESERVED
        r.admin_approved_by = actor_id; r.approved_at = datetime.now(timezone.utc)
        r.approval_reason = reason; self.update_request(r)
        self._audit(rid,r.tenant_id,PackageDownloadAuditEventType.ADMIN_APPROVED_RESERVED,actor_id,
            "Admin approved for future download (no download performed).")
        return r

    def reject_request(self, rid, actor_id=None, reason=None):
        r = self.get_request(rid)
        if r is None: raise PackageDownloadRequestNotFoundError(f"Not found: {rid}")
        r.request_status = PackageDownloadRequestStatus.ADMIN_REJECTED
        r.decision = PackageDownloadDecision.REJECTED
        r.gate_status = PackageDownloadGateStatus.ADMIN_REJECTED
        r.admin_rejected_by = actor_id; r.rejected_at = datetime.now(timezone.utc)
        r.rejection_reason = reason; self.update_request(r)
        self._audit(rid,r.tenant_id,PackageDownloadAuditEventType.ADMIN_REJECTED,actor_id,
            "Admin rejected download request.")
        return r

    def cancel_request(self, rid, actor_id=None, reason=None):
        r = self.get_request(rid)
        if r is None: raise PackageDownloadRequestNotFoundError(f"Not found: {rid}")
        r.request_status = PackageDownloadRequestStatus.CANCELLED; r.cancelled_by = actor_id
        r.cancelled_at = datetime.now(timezone.utc); self.update_request(r)
        self._audit(rid,r.tenant_id,PackageDownloadAuditEventType.CANCELLED,actor_id,"Request cancelled.")
        return r

    def expire_request(self, rid, actor_id=None, reason=None):
        r = self.get_request(rid)
        if r is None: raise PackageDownloadRequestNotFoundError(f"Not found: {rid}")
        r.request_status = PackageDownloadRequestStatus.EXPIRED; r.expired_by = actor_id
        r.expired_at = datetime.now(timezone.utc); self.update_request(r)
        self._audit(rid,r.tenant_id,PackageDownloadAuditEventType.EXPIRED,actor_id,"Request expired.")
        return r

    # ── Quarantine ──
    def reserve_quarantine_record(self, rec: PackageDownloadQuarantineRecord) -> PackageDownloadQuarantineRecord:
        self._exec("""INSERT INTO package_download_quarantine_records (
            quarantine_id,request_id,artifact_id,tenant_id,quarantine_status,logical_quarantine_ref,
            file_materialized,file_size_bytes,content_sha256,extraction_allowed,execution_allowed,
            created_by,created_at,updated_at,metadata_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", [
            rec.quarantine_id,rec.request_id,rec.artifact_id,rec.tenant_id,rec.quarantine_status,
            rec.logical_quarantine_ref,int(rec.file_materialized),rec.file_size_bytes,rec.content_sha256,
            int(rec.extraction_allowed),int(rec.execution_allowed),rec.created_by,
            rec.created_at.isoformat() if rec.created_at else datetime.now(timezone.utc).isoformat(),
            rec.updated_at.isoformat() if rec.updated_at else datetime.now(timezone.utc).isoformat(),
            json.dumps(rec.metadata,ensure_ascii=False)])
        self._audit(rec.request_id,rec.tenant_id,PackageDownloadAuditEventType.QUARANTINE_RESERVED,
            rec.created_by,f"Quarantine metadata reserved: {rec.quarantine_id}")
        return rec

    def get_quarantine_record(self, qid: str) -> PackageDownloadQuarantineRecord | None:
        row = next(self._exec("SELECT * FROM package_download_quarantine_records WHERE quarantine_id=?", [qid]), None)
        return self._row_to_q(dict(row)) if row else None

    def get_quarantine_by_request(self, rid: str) -> PackageDownloadQuarantineRecord | None:
        row = next(self._exec("SELECT * FROM package_download_quarantine_records WHERE request_id=? ORDER BY created_at DESC LIMIT 1", [rid]), None)
        return self._row_to_q(dict(row)) if row else None

    # ── Audit ──
    def add_audit_event(self, evt: PackageDownloadAuditEvent) -> PackageDownloadAuditEvent:
        self._exec("""INSERT INTO package_download_audit_events (
            event_id,request_id,tenant_id,event_type,severity,actor_id,message,metadata_json,created_at
        ) VALUES (?,?,?,?,?,?,?,?,?)""", [
            evt.event_id,evt.request_id,evt.tenant_id,evt.event_type,evt.severity,
            evt.actor_id,evt.message,json.dumps(evt.metadata,ensure_ascii=False),
            evt.created_at.isoformat() if evt.created_at else datetime.now(timezone.utc).isoformat()])
        return evt

    def list_audit_events(self, rid: str) -> list[PackageDownloadAuditEvent]:
        rows = self._exec("SELECT * FROM package_download_audit_events WHERE request_id=? ORDER BY created_at ASC", [rid])
        return [self._row_to_ae(dict(r)) for r in rows]

    def count_requests(self, *, tenant_id="", status="", decision="", gate_status="") -> int:
        sql, p = "SELECT COUNT(*) as cnt FROM package_download_requests WHERE 1=1", []
        if tenant_id: sql += " AND tenant_id=?"; p.append(tenant_id)
        if status: sql += " AND request_status=?"; p.append(status)
        if decision: sql += " AND decision=?"; p.append(decision)
        if gate_status: sql += " AND gate_status=?"; p.append(gate_status)
        row = next(self._exec(sql, p), None); return row["cnt"] if row else 0

    # ── Row converters ──
    @staticmethod
    def _row_to_req(row: dict) -> PackageDownloadRequest:
        src = PackageSourceMetadata.from_dict(json.loads(row.get("source_metadata_json","{}")))
        return PackageDownloadRequest(
            request_id=row["request_id"],artifact_id=row["artifact_id"],
            marketplace_agent_id=row.get("marketplace_agent_id"),tenant_id=row["tenant_id"],
            developer_id=row.get("developer_id"),submission_id=row.get("submission_id"),
            requested_by=row.get("requested_by"),source_metadata=src,
            request_status=row.get("request_status","draft"),decision=row.get("decision","blocked"),
            gate_status=row.get("gate_status","closed"),quarantine_status=row.get("quarantine_status","not_created"),
            risk_level=row.get("risk_level","unknown"),
            admin_approved_by=row.get("admin_approved_by"),admin_rejected_by=row.get("admin_rejected_by"),
            cancelled_by=row.get("cancelled_by"),expired_by=row.get("expired_by"),
            approval_reason=row.get("approval_reason"),rejection_reason=row.get("rejection_reason"),
            input_payload_hash=row.get("input_payload_hash"),
            artifact_snapshot=json.loads(row.get("artifact_snapshot_json","{}")),
            verification_snapshot=json.loads(row.get("verification_snapshot_json","{}")),
            execution_snapshot=json.loads(row.get("execution_snapshot_json","{}")),
            no_download_performed=bool(row.get("no_download_performed",1)),
            no_network_used=bool(row.get("no_network_used",1)),no_file_written=bool(row.get("no_file_written",1)),
            no_package_extracted=bool(row.get("no_package_extracted",1)),
            no_execution_performed=bool(row.get("no_execution_performed",1)),
            no_subprocess_used=bool(row.get("no_subprocess_used",1)),
            no_container_used=bool(row.get("no_container_used",1)),
            no_queue_created=bool(row.get("no_queue_created",1)),
            no_job_dispatched=bool(row.get("no_job_dispatched",1)),
            no_agent_runtime_used=bool(row.get("no_agent_runtime_used",1)),
            no_agent_registry_used=bool(row.get("no_agent_registry_used",1)),
            created_at=_safe_dt(row.get("created_at")),updated_at=_safe_dt(row.get("updated_at")),
            approved_at=_safe_dt(row.get("approved_at"),True),rejected_at=_safe_dt(row.get("rejected_at"),True),
            cancelled_at=_safe_dt(row.get("cancelled_at"),True),expired_at=_safe_dt(row.get("expired_at"),True),
            expires_at=_safe_dt(row.get("expires_at"),True),metadata=json.loads(row.get("metadata_json","{}")))

    @staticmethod
    def _row_to_q(row: dict) -> PackageDownloadQuarantineRecord:
        return PackageDownloadQuarantineRecord(
            quarantine_id=row["quarantine_id"],request_id=row["request_id"],artifact_id=row["artifact_id"],
            tenant_id=row["tenant_id"],quarantine_status=row.get("quarantine_status","not_created"),
            logical_quarantine_ref=row.get("logical_quarantine_ref"),
            file_materialized=bool(row.get("file_materialized",0)),file_size_bytes=row.get("file_size_bytes"),
            content_sha256=row.get("content_sha256"),extraction_allowed=bool(row.get("extraction_allowed",0)),
            execution_allowed=bool(row.get("execution_allowed",0)),created_by=row.get("created_by"),
            created_at=_safe_dt(row.get("created_at")),updated_at=_safe_dt(row.get("updated_at")),
            metadata=json.loads(row.get("metadata_json","{}")))

    @staticmethod
    def _row_to_ae(row: dict) -> PackageDownloadAuditEvent:
        return PackageDownloadAuditEvent(event_id=row["event_id"],request_id=row["request_id"],
            tenant_id=row["tenant_id"],event_type=row.get("event_type",""),severity=row.get("severity","info"),
            actor_id=row.get("actor_id"),message=row.get("message",""),
            metadata=json.loads(row.get("metadata_json","{}")),created_at=_safe_dt(row.get("created_at")))

def _safe_dt(raw,none_ok=False):
    if not raw: return None if none_ok else datetime.now(timezone.utc)
    try: return datetime.fromisoformat(str(raw).replace("Z","+00:00"))
    except: return None if none_ok else datetime.now(timezone.utc)
