"""SQLite Artifact Materialization Store — read-only spike, metadata-only, no file write, no mount, no extraction, no execution."""
from __future__ import annotations
import json, logging
from datetime import datetime, timezone
from typing import Any
from src.adapters.config import Settings
from src.adapters.sqlite_connection import create_sqlite_db, execute_with_retry
from src.open_platform.artifact_materialization import *

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS artifact_materialization_policies (
    policy_id TEXT PRIMARY KEY, tenant_id TEXT,
    scope TEXT NOT NULL DEFAULT 'global', enabled_metadata_only INTEGER NOT NULL DEFAULT 1,
    materialization_enabled INTEGER NOT NULL DEFAULT 0, file_write_enabled INTEGER NOT NULL DEFAULT 0,
    directory_create_enabled INTEGER NOT NULL DEFAULT 0, mount_enabled INTEGER NOT NULL DEFAULT 0,
    extraction_enabled INTEGER NOT NULL DEFAULT 0, package_execution_enabled INTEGER NOT NULL DEFAULT 0,
    requires_download_worker_gate INTEGER NOT NULL DEFAULT 1,
    requires_extraction_guard_gate INTEGER NOT NULL DEFAULT 1,
    requires_kill_switch_clear INTEGER NOT NULL DEFAULT 1,
    requires_incident_clear INTEGER NOT NULL DEFAULT 1,
    read_only_refs_only INTEGER NOT NULL DEFAULT 1,
    blocks_absolute_paths INTEGER NOT NULL DEFAULT 1, blocks_traversal INTEGER NOT NULL DEFAULT 1,
    blocks_symlink_escape INTEGER NOT NULL DEFAULT 1,
    created_by TEXT, created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')), metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_artmatpol_tenant ON artifact_materialization_policies(tenant_id);
CREATE INDEX IF NOT EXISTS idx_artmatpol_scope ON artifact_materialization_policies(scope);

CREATE TABLE IF NOT EXISTS artifact_materialization_requests (
    request_id TEXT PRIMARY KEY, tenant_id TEXT, policy_id TEXT,
    package_download_request_id TEXT, quarantine_record_id TEXT, download_worker_job_id TEXT,
    extraction_guard_request_id TEXT, extraction_plan_id TEXT,
    source_snapshot_json TEXT NOT NULL DEFAULT '{}', quarantine_snapshot_json TEXT NOT NULL DEFAULT '{}',
    download_worker_snapshot_json TEXT NOT NULL DEFAULT '{}',
    extraction_guard_snapshot_json TEXT NOT NULL DEFAULT '{}',
    kill_switch_snapshot_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'disabled_by_default', decision TEXT NOT NULL DEFAULT 'blocked_disabled',
    materialization_performed INTEGER NOT NULL DEFAULT 0, file_written INTEGER NOT NULL DEFAULT 0,
    directory_created INTEGER NOT NULL DEFAULT 0, mount_created INTEGER NOT NULL DEFAULT 0,
    archive_read INTEGER NOT NULL DEFAULT 0, archive_extracted INTEGER NOT NULL DEFAULT 0,
    package_executed INTEGER NOT NULL DEFAULT 0, entrypoint_executed INTEGER NOT NULL DEFAULT 0,
    no_file_written INTEGER NOT NULL DEFAULT 1, no_directory_created INTEGER NOT NULL DEFAULT 1,
    no_mount_created INTEGER NOT NULL DEFAULT 1, no_archive_read INTEGER NOT NULL DEFAULT 1,
    no_extraction_performed INTEGER NOT NULL DEFAULT 1, no_execution_performed INTEGER NOT NULL DEFAULT 1,
    no_worker_started INTEGER NOT NULL DEFAULT 1, no_dispatch_performed INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')), updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_artmatreq_tenant ON artifact_materialization_requests(tenant_id);
CREATE INDEX IF NOT EXISTS idx_artmatreq_status ON artifact_materialization_requests(status);
CREATE INDEX IF NOT EXISTS idx_artmatreq_policy ON artifact_materialization_requests(policy_id);

CREATE TABLE IF NOT EXISTS artifact_materialization_plans (
    plan_id TEXT PRIMARY KEY, request_id TEXT NOT NULL, tenant_id TEXT, policy_id TEXT,
    logical_artifact_ref TEXT,
    allowed_logical_paths_json TEXT NOT NULL DEFAULT '[]',
    blocked_logical_paths_json TEXT NOT NULL DEFAULT '[]',
    source_hashes_json TEXT NOT NULL DEFAULT '[]',
    metadata_manifest_json TEXT NOT NULL DEFAULT '{}',
    plan_status TEXT NOT NULL DEFAULT 'plan_reserved_metadata_only',
    decision TEXT NOT NULL DEFAULT 'metadata_plan_reserved',
    materialization_allowed INTEGER NOT NULL DEFAULT 0, file_write_allowed INTEGER NOT NULL DEFAULT 0,
    directory_create_allowed INTEGER NOT NULL DEFAULT 0, mount_allowed INTEGER NOT NULL DEFAULT 0,
    extraction_allowed INTEGER NOT NULL DEFAULT 0, execution_allowed INTEGER NOT NULL DEFAULT 0,
    metadata_only INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')), updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_artmatplan_request ON artifact_materialization_plans(request_id);
CREATE INDEX IF NOT EXISTS idx_artmatplan_tenant ON artifact_materialization_plans(tenant_id);

CREATE TABLE IF NOT EXISTS artifact_materialization_references (
    ref_id TEXT PRIMARY KEY, plan_id TEXT NOT NULL, tenant_id TEXT,
    logical_ref TEXT, ref_type TEXT NOT NULL DEFAULT 'logical_only',
    ref_status TEXT NOT NULL DEFAULT 'read_only_reference_reserved',
    content_hash TEXT, manifest_hash TEXT,
    filesystem_path TEXT, filesystem_ref_active INTEGER NOT NULL DEFAULT 0,
    file_exists_checked INTEGER NOT NULL DEFAULT 0, file_opened INTEGER NOT NULL DEFAULT 0,
    file_written INTEGER NOT NULL DEFAULT 0, mount_active INTEGER NOT NULL DEFAULT 0,
    execution_allowed INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')), metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_artmatref_plan ON artifact_materialization_references(plan_id);
CREATE INDEX IF NOT EXISTS idx_artmatref_tenant ON artifact_materialization_references(tenant_id);

CREATE TABLE IF NOT EXISTS artifact_materialization_gate_results (
    gate_result_id TEXT PRIMARY KEY, request_id TEXT NOT NULL, tenant_id TEXT,
    status TEXT NOT NULL DEFAULT 'disabled_by_default', decision TEXT NOT NULL DEFAULT 'blocked_disabled',
    checks_json TEXT NOT NULL DEFAULT '[]',
    blockers_count INTEGER NOT NULL DEFAULT 0, warnings_count INTEGER NOT NULL DEFAULT 0,
    materialization_allowed INTEGER NOT NULL DEFAULT 0, file_write_allowed INTEGER NOT NULL DEFAULT 0,
    directory_create_allowed INTEGER NOT NULL DEFAULT 0, mount_allowed INTEGER NOT NULL DEFAULT 0,
    archive_read_allowed INTEGER NOT NULL DEFAULT 0, extraction_allowed INTEGER NOT NULL DEFAULT 0,
    execution_allowed INTEGER NOT NULL DEFAULT 0, metadata_only INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')), metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_artmatgate_request ON artifact_materialization_gate_results(request_id);
CREATE INDEX IF NOT EXISTS idx_artmatgate_tenant ON artifact_materialization_gate_results(tenant_id);

CREATE TABLE IF NOT EXISTS artifact_materialization_audit_events (
    event_id TEXT PRIMARY KEY, tenant_id TEXT, request_id TEXT, plan_id TEXT,
    ref_id TEXT, policy_id TEXT,
    event_type TEXT NOT NULL, severity TEXT NOT NULL DEFAULT 'info',
    actor_id TEXT, message TEXT NOT NULL DEFAULT '', metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_artmatevt_request ON artifact_materialization_audit_events(request_id);
CREATE INDEX IF NOT EXISTS idx_artmatevt_policy ON artifact_materialization_audit_events(policy_id);
CREATE INDEX IF NOT EXISTS idx_artmatevt_type ON artifact_materialization_audit_events(event_type);
CREATE INDEX IF NOT EXISTS idx_artmatevt_created ON artifact_materialization_audit_events(created_at);
"""


def _placeholders(count: int) -> str:
    return ",".join(["?"] * count)


def _jd(obj):
    return json.dumps(obj, ensure_ascii=False)


def _now():
    return datetime.now(timezone.utc).isoformat()


class SQLiteArtifactMaterializationStore:
    def __init__(self, config: Settings, db_path: str | None = None):
        path = db_path or config.sqlite_db_path
        self._db = create_sqlite_db(path)
        execute_with_retry(lambda: self._init_schema(), label="artmat_init")

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

    def _audit(self, request_id=None, plan_id=None, ref_id=None, policy_id=None,
               tenant_id=None, event_type="", actor=None, msg=""):
        self.add_audit_event(ArtifactMaterializationAuditEvent(
            request_id=request_id, plan_id=plan_id, ref_id=ref_id,
            policy_id=policy_id, tenant_id=tenant_id,
            event_type=event_type, actor_id=actor, message=msg))

    # ── Policy ──

    def create_policy(self, p):
        _cols = ("policy_id,tenant_id,scope,enabled_metadata_only,materialization_enabled,"
                 "file_write_enabled,directory_create_enabled,mount_enabled,extraction_enabled,"
                 "package_execution_enabled,requires_download_worker_gate,requires_extraction_guard_gate,"
                 "requires_kill_switch_clear,requires_incident_clear,read_only_refs_only,"
                 "blocks_absolute_paths,blocks_traversal,blocks_symlink_escape,"
                 "created_by,created_at,updated_at,metadata_json")
        _vals = [p.policy_id, p.tenant_id, p.scope, int(p.enabled_metadata_only),
                 int(p.materialization_enabled), int(p.file_write_enabled),
                 int(p.directory_create_enabled), int(p.mount_enabled),
                 int(p.extraction_enabled), int(p.package_execution_enabled),
                 int(p.requires_download_worker_gate), int(p.requires_extraction_guard_gate),
                 int(p.requires_kill_switch_clear), int(p.requires_incident_clear),
                 int(p.read_only_refs_only), int(p.blocks_absolute_paths),
                 int(p.blocks_traversal), int(p.blocks_symlink_escape),
                 p.created_by,
                 p.created_at.isoformat() if p.created_at else _now(),
                 p.updated_at.isoformat() if p.updated_at else _now(), _jd(p.metadata)]
        self._exec(
            f"INSERT INTO artifact_materialization_policies ({_cols}) VALUES ({_placeholders(len(_vals))})",
            _vals)
        self._audit(policy_id=p.policy_id, tenant_id=p.tenant_id,
                    event_type=ArtifactMaterializationAuditEventType.MATERIALIZATION_POLICY_CREATED,
                    actor=p.created_by, msg="Materialization policy created (disabled by default).")
        return p

    def get_policy(self, pid):
        row = next(self._exec(
            "SELECT * FROM artifact_materialization_policies WHERE policy_id=?", [pid]), None)
        return self._row_to_policy(dict(row)) if row else None

    def list_policies(self, *, tenant_id="", scope=""):
        sql, p = "SELECT * FROM artifact_materialization_policies WHERE 1=1", []
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
            "UPDATE artifact_materialization_policies SET "
            "scope=?,enabled_metadata_only=?,materialization_enabled=?,file_write_enabled=?,"
            "directory_create_enabled=?,mount_enabled=?,extraction_enabled=?,package_execution_enabled=?,"
            "requires_download_worker_gate=?,requires_extraction_guard_gate=?,"
            "requires_kill_switch_clear=?,requires_incident_clear=?,"
            "read_only_refs_only=?,blocks_absolute_paths=?,blocks_traversal=?,blocks_symlink_escape=?,"
            "updated_at=?,metadata_json=? WHERE policy_id=?",
            [pol.scope, int(pol.enabled_metadata_only), int(pol.materialization_enabled),
             int(pol.file_write_enabled), int(pol.directory_create_enabled),
             int(pol.mount_enabled), int(pol.extraction_enabled),
             int(pol.package_execution_enabled),
             int(pol.requires_download_worker_gate), int(pol.requires_extraction_guard_gate),
             int(pol.requires_kill_switch_clear), int(pol.requires_incident_clear),
             int(pol.read_only_refs_only), int(pol.blocks_absolute_paths),
             int(pol.blocks_traversal), int(pol.blocks_symlink_escape),
             pol.updated_at.isoformat(), _jd(pol.metadata), pol.policy_id])
        return pol

    # ── Request ──

    def create_request(self, r):
        _cols = ("request_id,tenant_id,policy_id,package_download_request_id,quarantine_record_id,"
                 "download_worker_job_id,extraction_guard_request_id,extraction_plan_id,"
                 "source_snapshot_json,quarantine_snapshot_json,download_worker_snapshot_json,"
                 "extraction_guard_snapshot_json,kill_switch_snapshot_json,"
                 "status,decision,materialization_performed,file_written,directory_created,"
                 "mount_created,archive_read,archive_extracted,package_executed,entrypoint_executed,"
                 "no_file_written,no_directory_created,no_mount_created,no_archive_read,"
                 "no_extraction_performed,no_execution_performed,no_worker_started,no_dispatch_performed,"
                 "created_at,updated_at,metadata_json")
        _vals = [r.request_id, r.tenant_id, r.policy_id,
                 r.package_download_request_id, r.quarantine_record_id,
                 r.download_worker_job_id, r.extraction_guard_request_id, r.extraction_plan_id,
                 _jd(r.source_snapshot), _jd(r.quarantine_snapshot),
                 _jd(r.download_worker_snapshot), _jd(r.extraction_guard_snapshot),
                 _jd(r.kill_switch_snapshot),
                 r.status, r.decision,
                 int(r.materialization_performed), int(r.file_written),
                 int(r.directory_created), int(r.mount_created),
                 int(r.archive_read), int(r.archive_extracted),
                 int(r.package_executed), int(r.entrypoint_executed),
                 int(r.no_file_written), int(r.no_directory_created),
                 int(r.no_mount_created), int(r.no_archive_read),
                 int(r.no_extraction_performed), int(r.no_execution_performed),
                 int(r.no_worker_started), int(r.no_dispatch_performed),
                 r.created_at.isoformat() if r.created_at else _now(),
                 r.updated_at.isoformat() if r.updated_at else _now(), _jd(r.metadata)]
        self._exec(
            f"INSERT INTO artifact_materialization_requests ({_cols}) VALUES ({_placeholders(len(_vals))})",
            _vals)
        self._audit(request_id=r.request_id, tenant_id=r.tenant_id,
                    policy_id=r.policy_id,
                    event_type=ArtifactMaterializationAuditEventType.MATERIALIZATION_REQUEST_CREATED,
                    msg="Materialization request created (disabled by default).")
        return r

    def get_request(self, rid):
        row = next(self._exec(
            "SELECT * FROM artifact_materialization_requests WHERE request_id=?", [rid]), None)
        return self._row_to_request(dict(row)) if row else None

    def list_requests(self, *, tenant_id="", status="", policy_id=""):
        sql, p = "SELECT * FROM artifact_materialization_requests WHERE 1=1", []
        if tenant_id:
            sql += " AND tenant_id=?"
            p.append(tenant_id)
        if status:
            sql += " AND status=?"
            p.append(status)
        if policy_id:
            sql += " AND policy_id=?"
            p.append(policy_id)
        return [self._row_to_request(dict(r)) for r in
                self._exec(sql + " ORDER BY created_at DESC", p)]

    def update_request(self, r):
        r.updated_at = datetime.now(timezone.utc)
        self._exec(
            "UPDATE artifact_materialization_requests SET "
            "status=?,decision=?,updated_at=?,metadata_json=? WHERE request_id=?",
            [r.status, r.decision, r.updated_at.isoformat(), _jd(r.metadata), r.request_id])
        return r

    def set_request_status(self, request_id, status, actor_id=None, reason=None):
        r = self.get_request(request_id)
        if r is None: raise ArtifactMaterializationRequestNotFoundError(f"Not found: {request_id}")
        old = r.status; r.status = status; r.updated_at = datetime.now(timezone.utc)
        self._exec(
            "UPDATE artifact_materialization_requests SET status=?,updated_at=? WHERE request_id=?",
            [status, r.updated_at.isoformat(), request_id])
        self._audit(request_id=request_id, tenant_id=r.tenant_id,
                    event_type=ArtifactMaterializationAuditEventType.STATUS_CHANGED,
                    actor=actor_id, msg=f"Status: {old} -> {status}")
        return r

    def set_request_decision(self, request_id, decision, actor_id=None, reason=None):
        r = self.get_request(request_id)
        if r is None: raise ArtifactMaterializationRequestNotFoundError(f"Not found: {request_id}")
        old = r.decision; r.decision = decision; r.updated_at = datetime.now(timezone.utc)
        self._exec(
            "UPDATE artifact_materialization_requests SET decision=?,updated_at=? WHERE request_id=?",
            [decision, r.updated_at.isoformat(), request_id])
        self._audit(request_id=request_id, tenant_id=r.tenant_id,
                    event_type=ArtifactMaterializationAuditEventType.DECISION_CHANGED,
                    actor=actor_id, msg=f"Decision: {old} -> {decision}")
        return r

    # ── Plan ──

    def reserve_plan_metadata_only(self, plan):
        _cols = ("plan_id,request_id,tenant_id,policy_id,logical_artifact_ref,"
                 "allowed_logical_paths_json,blocked_logical_paths_json,"
                 "source_hashes_json,metadata_manifest_json,"
                 "plan_status,decision,materialization_allowed,file_write_allowed,"
                 "directory_create_allowed,mount_allowed,extraction_allowed,execution_allowed,"
                 "metadata_only,created_at,updated_at,metadata_json")
        _vals = [plan.plan_id, plan.request_id, plan.tenant_id, plan.policy_id,
                 plan.logical_artifact_ref,
                 _jd(plan.allowed_logical_paths), _jd(plan.blocked_logical_paths),
                 _jd(plan.source_hashes), _jd(plan.metadata_manifest),
                 plan.plan_status, plan.decision,
                 int(plan.materialization_allowed), int(plan.file_write_allowed),
                 int(plan.directory_create_allowed), int(plan.mount_allowed),
                 int(plan.extraction_allowed), int(plan.execution_allowed),
                 int(plan.metadata_only),
                 plan.created_at.isoformat() if plan.created_at else _now(),
                 plan.updated_at.isoformat() if plan.updated_at else _now(),
                 _jd(plan.metadata)]
        self._exec(
            f"INSERT INTO artifact_materialization_plans ({_cols}) VALUES ({_placeholders(len(_vals))})",
            _vals)
        self._audit(request_id=plan.request_id, plan_id=plan.plan_id,
                    tenant_id=plan.tenant_id, policy_id=plan.policy_id,
                    event_type=ArtifactMaterializationAuditEventType.MATERIALIZATION_PLAN_RESERVED,
                    msg="Materialization plan reserved metadata-only.")
        return plan

    def get_plan(self, pid):
        row = next(self._exec(
            "SELECT * FROM artifact_materialization_plans WHERE plan_id=?", [pid]), None)
        return self._row_to_plan(dict(row)) if row else None

    def get_plan_by_request(self, request_id):
        row = next(self._exec(
            "SELECT * FROM artifact_materialization_plans WHERE request_id=? ORDER BY created_at DESC LIMIT 1",
            [request_id]), None)
        return self._row_to_plan(dict(row)) if row else None

    # ── Reference ──

    def reserve_read_only_reference(self, ref):
        _cols = ("ref_id,plan_id,tenant_id,logical_ref,ref_type,ref_status,"
                 "content_hash,manifest_hash,filesystem_path,"
                 "filesystem_ref_active,file_exists_checked,file_opened,file_written,"
                 "mount_active,execution_allowed,created_at,metadata_json")
        _vals = [ref.ref_id, ref.plan_id, ref.tenant_id, ref.logical_ref,
                 ref.ref_type, ref.ref_status,
                 ref.content_hash, ref.manifest_hash, ref.filesystem_path,
                 int(ref.filesystem_ref_active), int(ref.file_exists_checked),
                 int(ref.file_opened), int(ref.file_written),
                 int(ref.mount_active), int(ref.execution_allowed),
                 ref.created_at.isoformat() if ref.created_at else _now(),
                 _jd(ref.metadata)]
        self._exec(
            f"INSERT INTO artifact_materialization_references ({_cols}) VALUES ({_placeholders(len(_vals))})",
            _vals)
        self._audit(ref_id=ref.ref_id, plan_id=ref.plan_id,
                    tenant_id=ref.tenant_id,
                    event_type=ArtifactMaterializationAuditEventType.READ_ONLY_REFERENCE_RESERVED,
                    msg="Read-only artifact reference reserved.")
        return ref

    def get_reference(self, rid):
        row = next(self._exec(
            "SELECT * FROM artifact_materialization_references WHERE ref_id=?", [rid]), None)
        return self._row_to_ref(dict(row)) if row else None

    def list_references(self, *, plan_id=""):
        sql, p = "SELECT * FROM artifact_materialization_references WHERE 1=1", []
        if plan_id:
            sql += " AND plan_id=?"
            p.append(plan_id)
        return [self._row_to_ref(dict(r)) for r in
                self._exec(sql + " ORDER BY created_at DESC", p)]

    # ── Gate ──

    def create_gate_result(self, g):
        _cols = ("gate_result_id,request_id,tenant_id,status,decision,"
                 "checks_json,blockers_count,warnings_count,"
                 "materialization_allowed,file_write_allowed,directory_create_allowed,"
                 "mount_allowed,archive_read_allowed,extraction_allowed,execution_allowed,"
                 "metadata_only,created_at,metadata_json")
        _vals = [g.gate_result_id, g.request_id, g.tenant_id, g.status, g.decision,
                 _jd(g.checks), g.blockers_count, g.warnings_count,
                 int(g.materialization_allowed), int(g.file_write_allowed),
                 int(g.directory_create_allowed), int(g.mount_allowed),
                 int(g.archive_read_allowed), int(g.extraction_allowed),
                 int(g.execution_allowed), int(g.metadata_only),
                 g.created_at.isoformat() if g.created_at else _now(), _jd(g.metadata)]
        self._exec(
            f"INSERT INTO artifact_materialization_gate_results ({_cols}) VALUES ({_placeholders(len(_vals))})",
            _vals)
        self._audit(request_id=g.request_id, tenant_id=g.tenant_id,
                    event_type=ArtifactMaterializationAuditEventType.GATE_EVALUATED,
                    msg=f"Gate evaluated: {g.decision}")
        return g

    def get_gate_result(self, gid):
        row = next(self._exec(
            "SELECT * FROM artifact_materialization_gate_results WHERE gate_result_id=?", [gid]),
            None)
        return self._row_to_gate(dict(row)) if row else None

    def get_gate_result_by_request(self, request_id):
        row = next(self._exec(
            "SELECT * FROM artifact_materialization_gate_results WHERE request_id=? ORDER BY created_at DESC LIMIT 1",
            [request_id]), None)
        return self._row_to_gate(dict(row)) if row else None

    # ── Audit ──

    def add_audit_event(self, evt):
        self._exec(
            "INSERT INTO artifact_materialization_audit_events (event_id,tenant_id,request_id,plan_id,ref_id,policy_id,event_type,severity,actor_id,message,metadata_json,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            [evt.event_id, evt.tenant_id, evt.request_id, evt.plan_id, evt.ref_id,
             evt.policy_id, evt.event_type, evt.severity, evt.actor_id, evt.message,
             _jd(evt.metadata),
             evt.created_at.isoformat() if evt.created_at else _now()])
        return evt

    def list_audit_events(self, *, request_id="", policy_id=""):
        sql, p = "SELECT * FROM artifact_materialization_audit_events WHERE 1=1", []
        if request_id:
            sql += " AND request_id=?"
            p.append(request_id)
        if policy_id:
            sql += " AND policy_id=?"
            p.append(policy_id)
        return [self._row_to_ae(dict(r)) for r in
                self._exec(sql + " ORDER BY created_at ASC", p)]

    def count_requests(self, *, tenant_id="", status=""):
        sql, p = "SELECT COUNT(*) as cnt FROM artifact_materialization_requests WHERE 1=1", []
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
        return ArtifactMaterializationPolicy(
            policy_id=row["policy_id"], tenant_id=row.get("tenant_id"),
            scope=row.get("scope", "global"),
            enabled_metadata_only=bool(row.get("enabled_metadata_only", 1)),
            materialization_enabled=bool(row.get("materialization_enabled", 0)),
            file_write_enabled=bool(row.get("file_write_enabled", 0)),
            directory_create_enabled=bool(row.get("directory_create_enabled", 0)),
            mount_enabled=bool(row.get("mount_enabled", 0)),
            extraction_enabled=bool(row.get("extraction_enabled", 0)),
            package_execution_enabled=bool(row.get("package_execution_enabled", 0)),
            requires_download_worker_gate=bool(row.get("requires_download_worker_gate", 1)),
            requires_extraction_guard_gate=bool(row.get("requires_extraction_guard_gate", 1)),
            requires_kill_switch_clear=bool(row.get("requires_kill_switch_clear", 1)),
            requires_incident_clear=bool(row.get("requires_incident_clear", 1)),
            read_only_refs_only=bool(row.get("read_only_refs_only", 1)),
            blocks_absolute_paths=bool(row.get("blocks_absolute_paths", 1)),
            blocks_traversal=bool(row.get("blocks_traversal", 1)),
            blocks_symlink_escape=bool(row.get("blocks_symlink_escape", 1)),
            created_by=row.get("created_by"),
            created_at=_sdt(row.get("created_at")),
            updated_at=_sdt(row.get("updated_at")),
            metadata=json.loads(row.get("metadata_json", "{}"))
        )

    @staticmethod
    def _row_to_request(row):
        return ArtifactMaterializationRequest(
            request_id=row["request_id"], tenant_id=row.get("tenant_id"),
            policy_id=row.get("policy_id"),
            package_download_request_id=row.get("package_download_request_id"),
            quarantine_record_id=row.get("quarantine_record_id"),
            download_worker_job_id=row.get("download_worker_job_id"),
            extraction_guard_request_id=row.get("extraction_guard_request_id"),
            extraction_plan_id=row.get("extraction_plan_id"),
            source_snapshot=json.loads(row.get("source_snapshot_json", "{}")),
            quarantine_snapshot=json.loads(row.get("quarantine_snapshot_json", "{}")),
            download_worker_snapshot=json.loads(row.get("download_worker_snapshot_json", "{}")),
            extraction_guard_snapshot=json.loads(row.get("extraction_guard_snapshot_json", "{}")),
            kill_switch_snapshot=json.loads(row.get("kill_switch_snapshot_json", "{}")),
            status=row.get("status", "disabled_by_default"),
            decision=row.get("decision", "blocked_disabled"),
            materialization_performed=bool(row.get("materialization_performed", 0)),
            file_written=bool(row.get("file_written", 0)),
            directory_created=bool(row.get("directory_created", 0)),
            mount_created=bool(row.get("mount_created", 0)),
            archive_read=bool(row.get("archive_read", 0)),
            archive_extracted=bool(row.get("archive_extracted", 0)),
            package_executed=bool(row.get("package_executed", 0)),
            entrypoint_executed=bool(row.get("entrypoint_executed", 0)),
            no_file_written=bool(row.get("no_file_written", 1)),
            no_directory_created=bool(row.get("no_directory_created", 1)),
            no_mount_created=bool(row.get("no_mount_created", 1)),
            no_archive_read=bool(row.get("no_archive_read", 1)),
            no_extraction_performed=bool(row.get("no_extraction_performed", 1)),
            no_execution_performed=bool(row.get("no_execution_performed", 1)),
            no_worker_started=bool(row.get("no_worker_started", 1)),
            no_dispatch_performed=bool(row.get("no_dispatch_performed", 1)),
            created_at=_sdt(row.get("created_at")),
            updated_at=_sdt(row.get("updated_at")),
            metadata=json.loads(row.get("metadata_json", "{}"))
        )

    @staticmethod
    def _row_to_plan(row):
        return ReadOnlyArtifactMaterializationPlan(
            plan_id=row["plan_id"], request_id=row["request_id"],
            tenant_id=row.get("tenant_id"), policy_id=row.get("policy_id"),
            logical_artifact_ref=row.get("logical_artifact_ref"),
            allowed_logical_paths=json.loads(row.get("allowed_logical_paths_json", "[]")),
            blocked_logical_paths=json.loads(row.get("blocked_logical_paths_json", "[]")),
            source_hashes=json.loads(row.get("source_hashes_json", "[]")),
            metadata_manifest=json.loads(row.get("metadata_manifest_json", "{}")),
            plan_status=row.get("plan_status", "plan_reserved_metadata_only"),
            decision=row.get("decision", "metadata_plan_reserved"),
            materialization_allowed=bool(row.get("materialization_allowed", 0)),
            file_write_allowed=bool(row.get("file_write_allowed", 0)),
            directory_create_allowed=bool(row.get("directory_create_allowed", 0)),
            mount_allowed=bool(row.get("mount_allowed", 0)),
            extraction_allowed=bool(row.get("extraction_allowed", 0)),
            execution_allowed=bool(row.get("execution_allowed", 0)),
            metadata_only=bool(row.get("metadata_only", 1)),
            created_at=_sdt(row.get("created_at")),
            updated_at=_sdt(row.get("updated_at")),
            metadata=json.loads(row.get("metadata_json", "{}"))
        )

    @staticmethod
    def _row_to_ref(row):
        return ReadOnlyArtifactReference(
            ref_id=row["ref_id"], plan_id=row["plan_id"],
            tenant_id=row.get("tenant_id"), logical_ref=row.get("logical_ref"),
            ref_type=row.get("ref_type", "logical_only"),
            ref_status=row.get("ref_status", "read_only_reference_reserved"),
            content_hash=row.get("content_hash"), manifest_hash=row.get("manifest_hash"),
            filesystem_path=row.get("filesystem_path"),
            filesystem_ref_active=bool(row.get("filesystem_ref_active", 0)),
            file_exists_checked=bool(row.get("file_exists_checked", 0)),
            file_opened=bool(row.get("file_opened", 0)),
            file_written=bool(row.get("file_written", 0)),
            mount_active=bool(row.get("mount_active", 0)),
            execution_allowed=bool(row.get("execution_allowed", 0)),
            created_at=_sdt(row.get("created_at")),
            metadata=json.loads(row.get("metadata_json", "{}"))
        )

    @staticmethod
    def _row_to_gate(row):
        return ArtifactMaterializationGateResult(
            gate_result_id=row["gate_result_id"], request_id=row["request_id"],
            tenant_id=row.get("tenant_id"),
            status=row.get("status", "disabled_by_default"),
            decision=row.get("decision", "blocked_disabled"),
            checks=json.loads(row.get("checks_json", "[]")),
            blockers_count=int(row.get("blockers_count", 0)),
            warnings_count=int(row.get("warnings_count", 0)),
            materialization_allowed=bool(row.get("materialization_allowed", 0)),
            file_write_allowed=bool(row.get("file_write_allowed", 0)),
            directory_create_allowed=bool(row.get("directory_create_allowed", 0)),
            mount_allowed=bool(row.get("mount_allowed", 0)),
            archive_read_allowed=bool(row.get("archive_read_allowed", 0)),
            extraction_allowed=bool(row.get("extraction_allowed", 0)),
            execution_allowed=bool(row.get("execution_allowed", 0)),
            metadata_only=bool(row.get("metadata_only", 1)),
            created_at=_sdt(row.get("created_at")),
            metadata=json.loads(row.get("metadata_json", "{}"))
        )

    @staticmethod
    def _row_to_ae(row):
        return ArtifactMaterializationAuditEvent(
            event_id=row["event_id"], tenant_id=row.get("tenant_id"),
            request_id=row.get("request_id"), plan_id=row.get("plan_id"),
            ref_id=row.get("ref_id"), policy_id=row.get("policy_id"),
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
