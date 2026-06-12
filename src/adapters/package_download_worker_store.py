"""SQLite Package Download Worker Store — disabled-by-default, metadata-only, no real download."""
from __future__ import annotations
import json, logging
from datetime import datetime, timezone
from typing import Any
from src.adapters.config import Settings
from src.adapters.sqlite_connection import create_sqlite_db, execute_with_retry
from src.open_platform.package_download_worker import *

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS package_download_worker_policies (
    policy_id TEXT PRIMARY KEY, tenant_id TEXT,
    scope TEXT NOT NULL DEFAULT 'global', enabled_metadata_only INTEGER NOT NULL DEFAULT 1,
    worker_enabled INTEGER NOT NULL DEFAULT 0, network_enabled INTEGER NOT NULL DEFAULT 0,
    download_enabled INTEGER NOT NULL DEFAULT 0, file_write_enabled INTEGER NOT NULL DEFAULT 0,
    extraction_enabled INTEGER NOT NULL DEFAULT 0, package_execution_enabled INTEGER NOT NULL DEFAULT 0,
    requires_admin_approval INTEGER NOT NULL DEFAULT 1, requires_kill_switch_clear INTEGER NOT NULL DEFAULT 1,
    requires_incident_clear INTEGER NOT NULL DEFAULT 1, blocks_private_network_sources INTEGER NOT NULL DEFAULT 1,
    blocks_metadata_ip INTEGER NOT NULL DEFAULT 1, blocks_localhost INTEGER NOT NULL DEFAULT 1,
    created_by TEXT, created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')), metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_pkgwkpol_tenant ON package_download_worker_policies(tenant_id);
CREATE INDEX IF NOT EXISTS idx_pkgwkpol_scope ON package_download_worker_policies(scope);

CREATE TABLE IF NOT EXISTS package_download_worker_jobs (
    job_id TEXT PRIMARY KEY, tenant_id TEXT,
    package_download_request_id TEXT, quarantine_record_id TEXT,
    worker_policy_id TEXT, kill_switch_policy_id TEXT, incident_id TEXT,
    source_snapshot_json TEXT NOT NULL DEFAULT '{}', package_request_snapshot_json TEXT NOT NULL DEFAULT '{}',
    quarantine_snapshot_json TEXT NOT NULL DEFAULT '{}', kill_switch_snapshot_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'disabled_by_default', decision TEXT NOT NULL DEFAULT 'blocked_disabled',
    download_performed INTEGER NOT NULL DEFAULT 0, network_used INTEGER NOT NULL DEFAULT 0,
    file_written INTEGER NOT NULL DEFAULT 0, package_materialized INTEGER NOT NULL DEFAULT 0,
    package_executed INTEGER NOT NULL DEFAULT 0, entrypoint_executed INTEGER NOT NULL DEFAULT 0,
    worker_started INTEGER NOT NULL DEFAULT 0, job_dispatched INTEGER NOT NULL DEFAULT 0,
    no_network_used INTEGER NOT NULL DEFAULT 1, no_download_performed INTEGER NOT NULL DEFAULT 1,
    no_file_written INTEGER NOT NULL DEFAULT 1, no_extraction_performed INTEGER NOT NULL DEFAULT 1,
    no_execution_performed INTEGER NOT NULL DEFAULT 1, no_worker_started INTEGER NOT NULL DEFAULT 1,
    no_dispatch_performed INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')), updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_pkgwkjob_tenant ON package_download_worker_jobs(tenant_id);
CREATE INDEX IF NOT EXISTS idx_pkgwkjob_status ON package_download_worker_jobs(status);
CREATE INDEX IF NOT EXISTS idx_pkgwkjob_policy ON package_download_worker_jobs(worker_policy_id);
CREATE INDEX IF NOT EXISTS idx_pkgwkjob_request ON package_download_worker_jobs(package_download_request_id);

CREATE TABLE IF NOT EXISTS package_download_worker_leases (
    lease_id TEXT PRIMARY KEY, job_id TEXT NOT NULL,
    policy_id TEXT, tenant_id TEXT,
    status TEXT NOT NULL DEFAULT 'disabled_by_default', decision TEXT NOT NULL DEFAULT 'blocked_disabled',
    lease_active INTEGER NOT NULL DEFAULT 0, worker_started INTEGER NOT NULL DEFAULT 0,
    heartbeat_enabled INTEGER NOT NULL DEFAULT 0, download_allowed INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')), released_at TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_pkgwklease_job ON package_download_worker_leases(job_id);
CREATE INDEX IF NOT EXISTS idx_pkgwklease_tenant ON package_download_worker_leases(tenant_id);

CREATE TABLE IF NOT EXISTS package_download_worker_gate_results (
    gate_result_id TEXT PRIMARY KEY, job_id TEXT NOT NULL,
    tenant_id TEXT, status TEXT NOT NULL DEFAULT 'disabled_by_default',
    decision TEXT NOT NULL DEFAULT 'blocked_disabled',
    checks_json TEXT NOT NULL DEFAULT '[]',
    blockers_count INTEGER NOT NULL DEFAULT 0, warnings_count INTEGER NOT NULL DEFAULT 0,
    worker_start_allowed INTEGER NOT NULL DEFAULT 0, network_allowed INTEGER NOT NULL DEFAULT 0,
    download_allowed INTEGER NOT NULL DEFAULT 0, file_write_allowed INTEGER NOT NULL DEFAULT 0,
    execution_allowed INTEGER NOT NULL DEFAULT 0, metadata_only INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')), metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_pkgwkgate_job ON package_download_worker_gate_results(job_id);
CREATE INDEX IF NOT EXISTS idx_pkgwkgate_tenant ON package_download_worker_gate_results(tenant_id);

CREATE TABLE IF NOT EXISTS package_download_worker_audit_events (
    event_id TEXT PRIMARY KEY, tenant_id TEXT, incident_id TEXT, job_id TEXT, policy_id TEXT, request_id TEXT,
    event_type TEXT NOT NULL, severity TEXT NOT NULL DEFAULT 'info',
    actor_id TEXT, message TEXT NOT NULL DEFAULT '', metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_pkgwkevt_job ON package_download_worker_audit_events(job_id);
CREATE INDEX IF NOT EXISTS idx_pkgwkevt_policy ON package_download_worker_audit_events(policy_id);
CREATE INDEX IF NOT EXISTS idx_pkgwkevt_type ON package_download_worker_audit_events(event_type);
CREATE INDEX IF NOT EXISTS idx_pkgwkevt_created ON package_download_worker_audit_events(created_at);
"""


def _placeholders(count: int) -> str:
    return ",".join(["?"] * count)


def _jd(obj):
    return json.dumps(obj, ensure_ascii=False)


def _now():
    return datetime.now(timezone.utc).isoformat()


class SQLitePackageDownloadWorkerStore:
    def __init__(self, config: Settings, db_path: str | None = None):
        path = db_path or config.sqlite_db_path
        self._db = create_sqlite_db(path)
        execute_with_retry(lambda: self._init_schema(), label="pkgdlwk_init")

    def _init_schema(self):
        for stmt in _SCHEMA.strip().split(";"):
            s = stmt.strip()
            if s:
                self._db.execute(s)
        try:
            self._db.conn.commit()
        except Exception:
            pass

    def flush(self):
        try:
            if hasattr(self._db, "conn") and self._db.conn:
                self._db.conn.commit()
        except Exception:
            pass

    def _exec(self, sql, params=None):
        return self._db.execute(sql, params or [])

    def _audit(self, job_id=None, policy_id=None, tenant_id=None, request_id=None,
               event_type="", actor=None, msg=""):
        self.add_audit_event(PackageDownloadWorkerAuditEvent(
            job_id=job_id, policy_id=policy_id, tenant_id=tenant_id,
            request_id=request_id, event_type=event_type, actor_id=actor, message=msg))

    # ── Policy ──

    def create_policy(self, p):
        _cols = "policy_id,tenant_id,scope,enabled_metadata_only,worker_enabled,network_enabled,download_enabled,file_write_enabled,extraction_enabled,package_execution_enabled,requires_admin_approval,requires_kill_switch_clear,requires_incident_clear,blocks_private_network_sources,blocks_metadata_ip,blocks_localhost,created_by,created_at,updated_at,metadata_json"
        _vals = [p.policy_id, p.tenant_id, p.scope, int(p.enabled_metadata_only),
                 int(p.worker_enabled), int(p.network_enabled), int(p.download_enabled),
                 int(p.file_write_enabled), int(p.extraction_enabled), int(p.package_execution_enabled),
                 int(p.requires_admin_approval), int(p.requires_kill_switch_clear),
                 int(p.requires_incident_clear), int(p.blocks_private_network_sources),
                 int(p.blocks_metadata_ip), int(p.blocks_localhost),
                 p.created_by, p.created_at.isoformat() if p.created_at else _now(),
                 p.updated_at.isoformat() if p.updated_at else _now(), _jd(p.metadata)]
        self._exec(
            f"INSERT INTO package_download_worker_policies ({_cols}) VALUES ({_placeholders(len(_vals))})",
            _vals)
        self._audit(policy_id=p.policy_id, tenant_id=p.tenant_id,
                    event_type=PackageDownloadWorkerAuditEventType.WORKER_POLICY_CREATED,
                    actor=p.created_by, msg="Worker policy created (disabled by default).")
        return p

    def get_policy(self, pid):
        row = next(self._exec(
            "SELECT * FROM package_download_worker_policies WHERE policy_id=?", [pid]), None)
        return self._row_to_policy(dict(row)) if row else None

    def list_policies(self, *, tenant_id="", scope=""):
        sql, p = "SELECT * FROM package_download_worker_policies WHERE 1=1", []
        if tenant_id:
            sql += " AND tenant_id=?"
            p.append(tenant_id)
        if scope:
            sql += " AND scope=?"
            p.append(scope)
        return [self._row_to_policy(dict(r)) for r in
                self._exec(sql + " ORDER BY created_at DESC", p)]

    def update_policy(self, pol):
        pol.updated_at = datetime.now(timezone.utc)
        self._exec(
            "UPDATE package_download_worker_policies SET "
            "scope=?,enabled_metadata_only=?,worker_enabled=?,network_enabled=?,"
            "download_enabled=?,file_write_enabled=?,extraction_enabled=?,package_execution_enabled=?,"
            "requires_admin_approval=?,requires_kill_switch_clear=?,requires_incident_clear=?,"
            "blocks_private_network_sources=?,blocks_metadata_ip=?,blocks_localhost=?,"
            "updated_at=?,metadata_json=? WHERE policy_id=?",
            [pol.scope, int(pol.enabled_metadata_only), int(pol.worker_enabled),
             int(pol.network_enabled), int(pol.download_enabled), int(pol.file_write_enabled),
             int(pol.extraction_enabled), int(pol.package_execution_enabled),
             int(pol.requires_admin_approval), int(pol.requires_kill_switch_clear),
             int(pol.requires_incident_clear), int(pol.blocks_private_network_sources),
             int(pol.blocks_metadata_ip), int(pol.blocks_localhost),
             pol.updated_at.isoformat(), _jd(pol.metadata), pol.policy_id])
        return pol

    # ── Job ──

    def create_job(self, j):
        _cols = ("job_id,tenant_id,package_download_request_id,quarantine_record_id,"
                 "worker_policy_id,kill_switch_policy_id,incident_id,"
                 "source_snapshot_json,package_request_snapshot_json,quarantine_snapshot_json,"
                 "kill_switch_snapshot_json,status,decision,"
                 "download_performed,network_used,file_written,package_materialized,package_executed,"
                 "entrypoint_executed,worker_started,job_dispatched,"
                 "no_network_used,no_download_performed,no_file_written,no_extraction_performed,"
                 "no_execution_performed,no_worker_started,no_dispatch_performed,"
                 "created_at,updated_at,metadata_json")
        _vals = [j.job_id, j.tenant_id, j.package_download_request_id, j.quarantine_record_id,
                 j.worker_policy_id, j.kill_switch_policy_id, j.incident_id,
                 _jd(j.source_snapshot), _jd(j.package_request_snapshot), _jd(j.quarantine_snapshot),
                 _jd(j.kill_switch_snapshot), j.status, j.decision,
                 int(j.download_performed), int(j.network_used), int(j.file_written),
                 int(j.package_materialized), int(j.package_executed), int(j.entrypoint_executed),
                 int(j.worker_started), int(j.job_dispatched),
                 int(j.no_network_used), int(j.no_download_performed), int(j.no_file_written),
                 int(j.no_extraction_performed), int(j.no_execution_performed),
                 int(j.no_worker_started), int(j.no_dispatch_performed),
                 j.created_at.isoformat() if j.created_at else _now(),
                 j.updated_at.isoformat() if j.updated_at else _now(), _jd(j.metadata)]
        self._exec(
            f"INSERT INTO package_download_worker_jobs ({_cols}) VALUES ({_placeholders(len(_vals))})",
            _vals)
        self._audit(job_id=j.job_id, tenant_id=j.tenant_id, request_id=j.package_download_request_id,
                    event_type=PackageDownloadWorkerAuditEventType.DOWNLOAD_JOB_CREATED,
                    msg="Download job created (disabled by default).")
        return j

    def get_job(self, jid):
        row = next(self._exec(
            "SELECT * FROM package_download_worker_jobs WHERE job_id=?", [jid]), None)
        return self._row_to_job(dict(row)) if row else None

    def list_jobs(self, *, tenant_id="", status="", policy_id=""):
        sql, p = "SELECT * FROM package_download_worker_jobs WHERE 1=1", []
        if tenant_id:
            sql += " AND tenant_id=?"
            p.append(tenant_id)
        if status:
            sql += " AND status=?"
            p.append(status)
        if policy_id:
            sql += " AND worker_policy_id=?"
            p.append(policy_id)
        return [self._row_to_job(dict(r)) for r in
                self._exec(sql + " ORDER BY created_at DESC", p)]

    def update_job(self, j):
        j.updated_at = datetime.now(timezone.utc)
        self._exec(
            "UPDATE package_download_worker_jobs SET "
            "status=?,decision=?,updated_at=?,metadata_json=? WHERE job_id=?",
            [j.status, j.decision, j.updated_at.isoformat(), _jd(j.metadata), j.job_id])
        return j

    def set_job_status(self, job_id, status, actor_id=None, reason=None):
        j = self.get_job(job_id)
        if j is None: raise PackageDownloadWorkerJobNotFoundError(f"Not found: {job_id}")
        old = j.status; j.status = status; j.updated_at = datetime.now(timezone.utc)
        self._exec("UPDATE package_download_worker_jobs SET status=?,updated_at=? WHERE job_id=?",
                   [status, j.updated_at.isoformat(), job_id])
        self._audit(job_id=job_id, tenant_id=j.tenant_id,
                    event_type=PackageDownloadWorkerAuditEventType.STATUS_CHANGED,
                    actor=actor_id, msg=f"Status: {old} -> {status}")
        return j

    def set_job_decision(self, job_id, decision, actor_id=None, reason=None):
        j = self.get_job(job_id)
        if j is None: raise PackageDownloadWorkerJobNotFoundError(f"Not found: {job_id}")
        old = j.decision; j.decision = decision; j.updated_at = datetime.now(timezone.utc)
        self._exec("UPDATE package_download_worker_jobs SET decision=?,updated_at=? WHERE job_id=?",
                   [decision, j.updated_at.isoformat(), job_id])
        self._audit(job_id=job_id, tenant_id=j.tenant_id,
                    event_type=PackageDownloadWorkerAuditEventType.DECISION_CHANGED,
                    actor=actor_id, msg=f"Decision: {old} -> {decision}")
        return j

    # ── Lease ──

    def reserve_lease_metadata_only(self, lease):
        _cols = ("lease_id,job_id,policy_id,tenant_id,status,decision,"
                 "lease_active,worker_started,heartbeat_enabled,download_allowed,"
                 "created_at,released_at,metadata_json")
        _vals = [lease.lease_id, lease.job_id, lease.policy_id, lease.tenant_id,
                 lease.status, lease.decision,
                 int(lease.lease_active), int(lease.worker_started),
                 int(lease.heartbeat_enabled), int(lease.download_allowed),
                 lease.created_at.isoformat() if lease.created_at else _now(),
                 lease.released_at.isoformat() if lease.released_at else None,
                 _jd(lease.metadata)]
        self._exec(
            f"INSERT INTO package_download_worker_leases ({_cols}) VALUES ({_placeholders(len(_vals))})",
            _vals)
        self._audit(job_id=lease.job_id, policy_id=lease.policy_id, tenant_id=lease.tenant_id,
                    event_type=PackageDownloadWorkerAuditEventType.LEASE_RESERVED_METADATA_ONLY,
                    msg="Lease reserved metadata-only (not active).")
        return lease

    def get_lease(self, lid):
        row = next(self._exec(
            "SELECT * FROM package_download_worker_leases WHERE lease_id=?", [lid]), None)
        return self._row_to_lease(dict(row)) if row else None

    def get_lease_by_job(self, job_id):
        row = next(self._exec(
            "SELECT * FROM package_download_worker_leases WHERE job_id=? ORDER BY created_at DESC LIMIT 1",
            [job_id]), None)
        return self._row_to_lease(dict(row)) if row else None

    def release_lease_metadata_only(self, lease_id, actor_id=None, reason=None):
        lease = self.get_lease(lease_id)
        if lease is None: raise PackageDownloadWorkerLeaseNotFoundError(f"Not found: {lease_id}")
        lease.status = PackageDownloadWorkerStatus.RELEASED_METADATA_ONLY
        lease.decision = PackageDownloadWorkerDecision.METADATA_LEASE_RESERVED
        lease.released_at = datetime.now(timezone.utc)
        self._exec(
            "UPDATE package_download_worker_leases SET status=?,decision=?,released_at=?,metadata_json=? WHERE lease_id=?",
            [lease.status, lease.decision, lease.released_at.isoformat(),
             _jd(lease.metadata), lease.lease_id])
        self._audit(job_id=lease.job_id, policy_id=lease.policy_id, tenant_id=lease.tenant_id,
                    event_type=PackageDownloadWorkerAuditEventType.STATUS_CHANGED,
                    actor=actor_id, msg=f"Lease released: {reason or 'metadata-only'}")
        return lease

    # ── Gate ──

    def create_gate_result(self, g):
        _cols = ("gate_result_id,job_id,tenant_id,status,decision,"
                 "checks_json,blockers_count,warnings_count,"
                 "worker_start_allowed,network_allowed,download_allowed,"
                 "file_write_allowed,execution_allowed,metadata_only,"
                 "created_at,metadata_json")
        _vals = [g.gate_result_id, g.job_id, g.tenant_id, g.status, g.decision,
                 _jd(g.checks), g.blockers_count, g.warnings_count,
                 int(g.worker_start_allowed), int(g.network_allowed), int(g.download_allowed),
                 int(g.file_write_allowed), int(g.execution_allowed), int(g.metadata_only),
                 g.created_at.isoformat() if g.created_at else _now(), _jd(g.metadata)]
        self._exec(
            f"INSERT INTO package_download_worker_gate_results ({_cols}) VALUES ({_placeholders(len(_vals))})",
            _vals)
        self._audit(job_id=g.job_id, tenant_id=g.tenant_id,
                    event_type=PackageDownloadWorkerAuditEventType.GATE_EVALUATED,
                    msg=f"Gate evaluated: {g.decision}")
        return g

    def get_gate_result(self, gid):
        row = next(self._exec(
            "SELECT * FROM package_download_worker_gate_results WHERE gate_result_id=?", [gid]),
            None)
        return self._row_to_gate(dict(row)) if row else None

    def get_gate_result_by_job(self, job_id):
        row = next(self._exec(
            "SELECT * FROM package_download_worker_gate_results WHERE job_id=? ORDER BY created_at DESC LIMIT 1",
            [job_id]), None)
        return self._row_to_gate(dict(row)) if row else None

    # ── Audit ──

    def add_audit_event(self, evt):
        self._exec(
            "INSERT INTO package_download_worker_audit_events (event_id,tenant_id,incident_id,job_id,policy_id,request_id,event_type,severity,actor_id,message,metadata_json,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            [evt.event_id, evt.tenant_id, evt.incident_id, evt.job_id, evt.policy_id,
             evt.request_id, evt.event_type, evt.severity, evt.actor_id, evt.message,
             _jd(evt.metadata),
             evt.created_at.isoformat() if evt.created_at else _now()])
        return evt

    def list_audit_events(self, *, job_id="", policy_id=""):
        sql, p = "SELECT * FROM package_download_worker_audit_events WHERE 1=1", []
        if job_id:
            sql += " AND job_id=?"
            p.append(job_id)
        if policy_id:
            sql += " AND policy_id=?"
            p.append(policy_id)
        return [self._row_to_ae(dict(r)) for r in
                self._exec(sql + " ORDER BY created_at ASC", p)]

    # ── Count ──

    def count_jobs(self, *, tenant_id="", status=""):
        sql, p = "SELECT COUNT(*) as cnt FROM package_download_worker_jobs WHERE 1=1", []
        if tenant_id:
            sql += " AND tenant_id=?"
            p.append(tenant_id)
        if status:
            sql += " AND status=?"
            p.append(status)
        row = next(self._exec(sql, p), None)
        return row["cnt"] if row else 0

    # ── Row mappers ──

    @staticmethod
    def _row_to_policy(row):
        return PackageDownloadWorkerPolicy(
            policy_id=row["policy_id"], tenant_id=row.get("tenant_id"),
            scope=row.get("scope", "global"),
            enabled_metadata_only=bool(row.get("enabled_metadata_only", 1)),
            worker_enabled=bool(row.get("worker_enabled", 0)),
            network_enabled=bool(row.get("network_enabled", 0)),
            download_enabled=bool(row.get("download_enabled", 0)),
            file_write_enabled=bool(row.get("file_write_enabled", 0)),
            extraction_enabled=bool(row.get("extraction_enabled", 0)),
            package_execution_enabled=bool(row.get("package_execution_enabled", 0)),
            requires_admin_approval=bool(row.get("requires_admin_approval", 1)),
            requires_kill_switch_clear=bool(row.get("requires_kill_switch_clear", 1)),
            requires_incident_clear=bool(row.get("requires_incident_clear", 1)),
            blocks_private_network_sources=bool(row.get("blocks_private_network_sources", 1)),
            blocks_metadata_ip=bool(row.get("blocks_metadata_ip", 1)),
            blocks_localhost=bool(row.get("blocks_localhost", 1)),
            created_by=row.get("created_by"),
            created_at=_sdt(row.get("created_at")),
            updated_at=_sdt(row.get("updated_at")),
            metadata=json.loads(row.get("metadata_json", "{}"))
        )

    @staticmethod
    def _row_to_job(row):
        return PackageDownloadWorkerJob(
            job_id=row["job_id"], tenant_id=row.get("tenant_id"),
            package_download_request_id=row.get("package_download_request_id"),
            quarantine_record_id=row.get("quarantine_record_id"),
            worker_policy_id=row.get("worker_policy_id"),
            kill_switch_policy_id=row.get("kill_switch_policy_id"),
            incident_id=row.get("incident_id"),
            source_snapshot=json.loads(row.get("source_snapshot_json", "{}")),
            package_request_snapshot=json.loads(row.get("package_request_snapshot_json", "{}")),
            quarantine_snapshot=json.loads(row.get("quarantine_snapshot_json", "{}")),
            kill_switch_snapshot=json.loads(row.get("kill_switch_snapshot_json", "{}")),
            status=row.get("status", "disabled_by_default"),
            decision=row.get("decision", "blocked_disabled"),
            download_performed=bool(row.get("download_performed", 0)),
            network_used=bool(row.get("network_used", 0)),
            file_written=bool(row.get("file_written", 0)),
            package_materialized=bool(row.get("package_materialized", 0)),
            package_executed=bool(row.get("package_executed", 0)),
            entrypoint_executed=bool(row.get("entrypoint_executed", 0)),
            worker_started=bool(row.get("worker_started", 0)),
            job_dispatched=bool(row.get("job_dispatched", 0)),
            no_network_used=bool(row.get("no_network_used", 1)),
            no_download_performed=bool(row.get("no_download_performed", 1)),
            no_file_written=bool(row.get("no_file_written", 1)),
            no_extraction_performed=bool(row.get("no_extraction_performed", 1)),
            no_execution_performed=bool(row.get("no_execution_performed", 1)),
            no_worker_started=bool(row.get("no_worker_started", 1)),
            no_dispatch_performed=bool(row.get("no_dispatch_performed", 1)),
            created_at=_sdt(row.get("created_at")),
            updated_at=_sdt(row.get("updated_at")),
            metadata=json.loads(row.get("metadata_json", "{}"))
        )

    @staticmethod
    def _row_to_lease(row):
        return PackageDownloadWorkerLease(
            lease_id=row["lease_id"], job_id=row["job_id"],
            policy_id=row.get("policy_id"), tenant_id=row.get("tenant_id"),
            status=row.get("status", "disabled_by_default"),
            decision=row.get("decision", "blocked_disabled"),
            lease_active=bool(row.get("lease_active", 0)),
            worker_started=bool(row.get("worker_started", 0)),
            heartbeat_enabled=bool(row.get("heartbeat_enabled", 0)),
            download_allowed=bool(row.get("download_allowed", 0)),
            created_at=_sdt(row.get("created_at")),
            released_at=_sdt(row.get("released_at"), True),
            metadata=json.loads(row.get("metadata_json", "{}"))
        )

    @staticmethod
    def _row_to_gate(row):
        return PackageDownloadWorkerGateResult(
            gate_result_id=row["gate_result_id"], job_id=row["job_id"],
            tenant_id=row.get("tenant_id"),
            status=row.get("status", "disabled_by_default"),
            decision=row.get("decision", "blocked_disabled"),
            checks=json.loads(row.get("checks_json", "[]")),
            blockers_count=int(row.get("blockers_count", 0)),
            warnings_count=int(row.get("warnings_count", 0)),
            worker_start_allowed=bool(row.get("worker_start_allowed", 0)),
            network_allowed=bool(row.get("network_allowed", 0)),
            download_allowed=bool(row.get("download_allowed", 0)),
            file_write_allowed=bool(row.get("file_write_allowed", 0)),
            execution_allowed=bool(row.get("execution_allowed", 0)),
            metadata_only=bool(row.get("metadata_only", 1)),
            created_at=_sdt(row.get("created_at")),
            metadata=json.loads(row.get("metadata_json", "{}"))
        )

    @staticmethod
    def _row_to_ae(row):
        return PackageDownloadWorkerAuditEvent(
            event_id=row["event_id"], tenant_id=row.get("tenant_id"),
            incident_id=row.get("incident_id"), job_id=row.get("job_id"),
            policy_id=row.get("policy_id"), request_id=row.get("request_id"),
            event_type=row.get("event_type", ""),
            severity=row.get("severity", "info"),
            actor_id=row.get("actor_id"), message=row.get("message", ""),
            created_at=_sdt(row.get("created_at")),
            metadata=json.loads(row.get("metadata_json", "{}"))
        )


def _sdt(raw, none_ok=False):
    if not raw:
        return None if none_ok else datetime.now(timezone.utc)
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except Exception:
        return None if none_ok else datetime.now(timezone.utc)
