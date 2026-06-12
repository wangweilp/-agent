"""SQLite Rootless Container Gate Store — metadata-only, no container start, no Docker/Podman, no execution."""
from __future__ import annotations
import json, logging
from datetime import datetime, timezone
from typing import Any
from src.adapters.config import Settings
from src.adapters.sqlite_connection import create_sqlite_db, execute_with_retry
from src.open_platform.rootless_container_gate import *

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS rootless_container_policies (
    policy_id TEXT PRIMARY KEY, tenant_id TEXT,
    enabled_metadata_only INTEGER NOT NULL DEFAULT 1,
    rootless_container_enabled INTEGER NOT NULL DEFAULT 0,
    container_start_enabled INTEGER NOT NULL DEFAULT 0,
    docker_enabled INTEGER NOT NULL DEFAULT 0, podman_enabled INTEGER NOT NULL DEFAULT 0,
    namespace_creation_enabled INTEGER NOT NULL DEFAULT 0, cgroup_enabled INTEGER NOT NULL DEFAULT 0,
    mount_enabled INTEGER NOT NULL DEFAULT 0, network_enabled INTEGER NOT NULL DEFAULT 0,
    package_execution_enabled INTEGER NOT NULL DEFAULT 0, third_party_execution_enabled INTEGER NOT NULL DEFAULT 0,
    requires_kill_switch_clear INTEGER NOT NULL DEFAULT 1, requires_incident_clear INTEGER NOT NULL DEFAULT 1,
    requires_read_only_artifact_plan INTEGER NOT NULL DEFAULT 1, requires_download_worker_blocked INTEGER NOT NULL DEFAULT 1,
    requires_red_team_passed INTEGER NOT NULL DEFAULT 1,
    created_by TEXT, created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')), metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_rtclspol_tenant ON rootless_container_policies(tenant_id);

CREATE TABLE IF NOT EXISTS rootless_container_requests (
    request_id TEXT PRIMARY KEY, tenant_id TEXT, policy_id TEXT,
    production_gate_request_id TEXT, kill_switch_policy_id TEXT, incident_id TEXT,
    artifact_plan_id TEXT, download_worker_job_id TEXT,
    policy_snapshot_json TEXT NOT NULL DEFAULT '{}',
    production_gate_snapshot_json TEXT NOT NULL DEFAULT '{}',
    kill_switch_snapshot_json TEXT NOT NULL DEFAULT '{}',
    artifact_plan_snapshot_json TEXT NOT NULL DEFAULT '{}',
    download_worker_snapshot_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'disabled_by_default', decision TEXT NOT NULL DEFAULT 'blocked_disabled',
    container_started INTEGER NOT NULL DEFAULT 0, runtime_started INTEGER NOT NULL DEFAULT 0,
    namespace_created INTEGER NOT NULL DEFAULT 0, cgroup_created INTEGER NOT NULL DEFAULT 0,
    mount_created INTEGER NOT NULL DEFAULT 0, network_enabled INTEGER NOT NULL DEFAULT 0,
    package_executed INTEGER NOT NULL DEFAULT 0, third_party_code_executed INTEGER NOT NULL DEFAULT 0,
    no_container_started INTEGER NOT NULL DEFAULT 1, no_runtime_started INTEGER NOT NULL DEFAULT 1,
    no_namespace_created INTEGER NOT NULL DEFAULT 1, no_cgroup_created INTEGER NOT NULL DEFAULT 1,
    no_mount_created INTEGER NOT NULL DEFAULT 1, no_network_enabled INTEGER NOT NULL DEFAULT 1,
    no_execution_performed INTEGER NOT NULL DEFAULT 1, no_package_executed INTEGER NOT NULL DEFAULT 1,
    no_third_party_code_executed INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')), updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_rtclsreq_tenant ON rootless_container_requests(tenant_id);
CREATE INDEX IF NOT EXISTS idx_rtclsreq_status ON rootless_container_requests(status);
CREATE INDEX IF NOT EXISTS idx_rtclsreq_policy ON rootless_container_requests(policy_id);

CREATE TABLE IF NOT EXISTS rootless_container_capability_assessments (
    assessment_id TEXT PRIMARY KEY, tenant_id TEXT,
    capability_type TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'not_checked_runtime_disabled',
    risk_level TEXT NOT NULL DEFAULT 'unknown', name TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    blockers_json TEXT NOT NULL DEFAULT '[]', warnings_json TEXT NOT NULL DEFAULT '[]',
    required_before_container_start INTEGER NOT NULL DEFAULT 1,
    required_before_execution INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')), metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_rtclscap_tenant ON rootless_container_capability_assessments(tenant_id);
CREATE INDEX IF NOT EXISTS idx_rtclscap_type ON rootless_container_capability_assessments(capability_type);

CREATE TABLE IF NOT EXISTS rootless_container_plans (
    plan_id TEXT PRIMARY KEY, request_id TEXT NOT NULL, tenant_id TEXT, policy_id TEXT,
    capability_assessments_json TEXT NOT NULL DEFAULT '[]',
    required_controls_json TEXT NOT NULL DEFAULT '[]',
    missing_controls_json TEXT NOT NULL DEFAULT '[]',
    blocker_summary TEXT NOT NULL DEFAULT '',
    plan_status TEXT NOT NULL DEFAULT 'plan_reserved_metadata_only',
    decision TEXT NOT NULL DEFAULT 'metadata_plan_reserved',
    container_start_allowed INTEGER NOT NULL DEFAULT 0, runtime_enabled INTEGER NOT NULL DEFAULT 0,
    network_allowed INTEGER NOT NULL DEFAULT 0, mount_allowed INTEGER NOT NULL DEFAULT 0,
    package_execution_allowed INTEGER NOT NULL DEFAULT 0, third_party_execution_allowed INTEGER NOT NULL DEFAULT 0,
    metadata_only INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')), updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_rtclsplan_request ON rootless_container_plans(request_id);
CREATE INDEX IF NOT EXISTS idx_rtclsplan_tenant ON rootless_container_plans(tenant_id);

CREATE TABLE IF NOT EXISTS rootless_container_gate_results (
    gate_result_id TEXT PRIMARY KEY, request_id TEXT NOT NULL, tenant_id TEXT,
    status TEXT NOT NULL DEFAULT 'disabled_by_default', decision TEXT NOT NULL DEFAULT 'blocked_disabled',
    checks_json TEXT NOT NULL DEFAULT '[]',
    satisfied_count INTEGER NOT NULL DEFAULT 0, missing_count INTEGER NOT NULL DEFAULT 0,
    blockers_count INTEGER NOT NULL DEFAULT 0, warnings_count INTEGER NOT NULL DEFAULT 0,
    ready_for_step26f INTEGER NOT NULL DEFAULT 0,
    container_start_allowed INTEGER NOT NULL DEFAULT 0, runtime_enabled INTEGER NOT NULL DEFAULT 0,
    network_allowed INTEGER NOT NULL DEFAULT 0, mount_allowed INTEGER NOT NULL DEFAULT 0,
    execution_allowed INTEGER NOT NULL DEFAULT 0, third_party_execution_allowed INTEGER NOT NULL DEFAULT 0,
    package_execution_allowed INTEGER NOT NULL DEFAULT 0, metadata_only INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')), metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_rtclsgate_request ON rootless_container_gate_results(request_id);
CREATE INDEX IF NOT EXISTS idx_rtclsgate_tenant ON rootless_container_gate_results(tenant_id);

CREATE TABLE IF NOT EXISTS rootless_container_audit_events (
    event_id TEXT PRIMARY KEY, tenant_id TEXT, request_id TEXT, plan_id TEXT,
    policy_id TEXT, assessment_id TEXT,
    event_type TEXT NOT NULL, severity TEXT NOT NULL DEFAULT 'info',
    actor_id TEXT, message TEXT NOT NULL DEFAULT '', metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_rtclsevt_request ON rootless_container_audit_events(request_id);
CREATE INDEX IF NOT EXISTS idx_rtclsevt_policy ON rootless_container_audit_events(policy_id);
CREATE INDEX IF NOT EXISTS idx_rtclsevt_type ON rootless_container_audit_events(event_type);
CREATE INDEX IF NOT EXISTS idx_rtclsevt_created ON rootless_container_audit_events(created_at);
"""


def _placeholders(count: int) -> str:
    return ",".join(["?"] * count)


def _jd(obj):
    return json.dumps(obj, ensure_ascii=False)


def _now():
    return datetime.now(timezone.utc).isoformat()


class SQLiteRootlessContainerGateStore:
    def __init__(self, config: Settings, db_path: str | None = None):
        path = db_path or config.sqlite_db_path
        self._db = create_sqlite_db(path)
        execute_with_retry(lambda: self._init_schema(), label="rtcls_init")

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

    def _audit(self, request_id=None, plan_id=None, policy_id=None,
               assessment_id=None, tenant_id=None,
               event_type="", actor=None, msg=""):
        self.add_audit_event(RootlessContainerAuditEvent(
            request_id=request_id, plan_id=plan_id, policy_id=policy_id,
            assessment_id=assessment_id, tenant_id=tenant_id,
            event_type=event_type, actor_id=actor, message=msg))

    # ── Policy ──

    def create_policy(self, p):
        _cols = ("policy_id,tenant_id,enabled_metadata_only,rootless_container_enabled,"
                 "container_start_enabled,docker_enabled,podman_enabled,"
                 "namespace_creation_enabled,cgroup_enabled,mount_enabled,network_enabled,"
                 "package_execution_enabled,third_party_execution_enabled,"
                 "requires_kill_switch_clear,requires_incident_clear,"
                 "requires_read_only_artifact_plan,requires_download_worker_blocked,"
                 "requires_red_team_passed,created_by,created_at,updated_at,metadata_json")
        _vals = [p.policy_id, p.tenant_id, int(p.enabled_metadata_only),
                 int(p.rootless_container_enabled), int(p.container_start_enabled),
                 int(p.docker_enabled), int(p.podman_enabled),
                 int(p.namespace_creation_enabled), int(p.cgroup_enabled),
                 int(p.mount_enabled), int(p.network_enabled),
                 int(p.package_execution_enabled), int(p.third_party_execution_enabled),
                 int(p.requires_kill_switch_clear), int(p.requires_incident_clear),
                 int(p.requires_read_only_artifact_plan), int(p.requires_download_worker_blocked),
                 int(p.requires_red_team_passed), p.created_by,
                 p.created_at.isoformat() if p.created_at else _now(),
                 p.updated_at.isoformat() if p.updated_at else _now(), _jd(p.metadata)]
        self._exec(f"INSERT INTO rootless_container_policies ({_cols}) VALUES ({_placeholders(len(_vals))})", _vals)
        self._audit(policy_id=p.policy_id, tenant_id=p.tenant_id,
                    event_type=RootlessContainerAuditEventType.POLICY_CREATED,
                    actor=p.created_by, msg="Rootless container policy created (disabled).")
        return p

    def get_policy(self, pid):
        row = next(self._exec("SELECT * FROM rootless_container_policies WHERE policy_id=?", [pid]), None)
        return self._row_to_policy(dict(row)) if row else None

    def list_policies(self, *, tenant_id=""):
        sql, p = "SELECT * FROM rootless_container_policies WHERE 1=1", []
        if tenant_id:
            sql += " AND tenant_id=?"
            p.append(tenant_id)
        return [self._row_to_policy(dict(r)) for r in self._exec(sql + " ORDER BY created_at DESC", p)]

    def update_policy(self, pol):
        pol.updated_at = datetime.now(timezone.utc)
        self._exec(
            "UPDATE rootless_container_policies SET "
            "rootless_container_enabled=?,container_start_enabled=?,docker_enabled=?,podman_enabled=?,"
            "namespace_creation_enabled=?,cgroup_enabled=?,mount_enabled=?,network_enabled=?,"
            "package_execution_enabled=?,third_party_execution_enabled=?,"
            "requires_kill_switch_clear=?,requires_incident_clear=?,"
            "requires_read_only_artifact_plan=?,requires_download_worker_blocked=?,requires_red_team_passed=?,"
            "updated_at=?,metadata_json=? WHERE policy_id=?",
            [int(pol.rootless_container_enabled), int(pol.container_start_enabled),
             int(pol.docker_enabled), int(pol.podman_enabled),
             int(pol.namespace_creation_enabled), int(pol.cgroup_enabled),
             int(pol.mount_enabled), int(pol.network_enabled),
             int(pol.package_execution_enabled), int(pol.third_party_execution_enabled),
             int(pol.requires_kill_switch_clear), int(pol.requires_incident_clear),
             int(pol.requires_read_only_artifact_plan), int(pol.requires_download_worker_blocked),
             int(pol.requires_red_team_passed),
             pol.updated_at.isoformat(), _jd(pol.metadata), pol.policy_id])
        return pol

    # ── Request ──

    def create_request(self, r):
        _cols = ("request_id,tenant_id,policy_id,production_gate_request_id,kill_switch_policy_id,"
                 "incident_id,artifact_plan_id,download_worker_job_id,"
                 "policy_snapshot_json,production_gate_snapshot_json,kill_switch_snapshot_json,"
                 "artifact_plan_snapshot_json,download_worker_snapshot_json,"
                 "status,decision,container_started,runtime_started,namespace_created,cgroup_created,"
                 "mount_created,network_enabled,package_executed,third_party_code_executed,"
                 "no_container_started,no_runtime_started,no_namespace_created,no_cgroup_created,"
                 "no_mount_created,no_network_enabled,no_execution_performed,no_package_executed,"
                 "no_third_party_code_executed,created_at,updated_at,metadata_json")
        _vals = [r.request_id, r.tenant_id, r.policy_id,
                 r.production_gate_request_id, r.kill_switch_policy_id,
                 r.incident_id, r.artifact_plan_id, r.download_worker_job_id,
                 _jd(r.policy_snapshot), _jd(r.production_gate_snapshot),
                 _jd(r.kill_switch_snapshot), _jd(r.artifact_plan_snapshot),
                 _jd(r.download_worker_snapshot),
                 r.status, r.decision,
                 int(r.container_started), int(r.runtime_started),
                 int(r.namespace_created), int(r.cgroup_created),
                 int(r.mount_created), int(r.network_enabled),
                 int(r.package_executed), int(r.third_party_code_executed),
                 int(r.no_container_started), int(r.no_runtime_started),
                 int(r.no_namespace_created), int(r.no_cgroup_created),
                 int(r.no_mount_created), int(r.no_network_enabled),
                 int(r.no_execution_performed), int(r.no_package_executed),
                 int(r.no_third_party_code_executed),
                 r.created_at.isoformat() if r.created_at else _now(),
                 r.updated_at.isoformat() if r.updated_at else _now(), _jd(r.metadata)]
        self._exec(f"INSERT INTO rootless_container_requests ({_cols}) VALUES ({_placeholders(len(_vals))})", _vals)
        self._audit(request_id=r.request_id, tenant_id=r.tenant_id, policy_id=r.policy_id,
                    event_type=RootlessContainerAuditEventType.REQUEST_CREATED,
                    msg="Rootless container request created (disabled).")
        return r

    def get_request(self, rid):
        row = next(self._exec("SELECT * FROM rootless_container_requests WHERE request_id=?", [rid]), None)
        return self._row_to_request(dict(row)) if row else None

    def list_requests(self, *, tenant_id="", status="", policy_id=""):
        sql, p = "SELECT * FROM rootless_container_requests WHERE 1=1", []
        if tenant_id:
            sql += " AND tenant_id=?"
            p.append(tenant_id)
        if status:
            sql += " AND status=?"
            p.append(status)
        if policy_id:
            sql += " AND policy_id=?"
            p.append(policy_id)
        return [self._row_to_request(dict(r)) for r in self._exec(sql + " ORDER BY created_at DESC", p)]

    def update_request(self, r):
        r.updated_at = datetime.now(timezone.utc)
        self._exec("UPDATE rootless_container_requests SET status=?,decision=?,updated_at=?,metadata_json=? WHERE request_id=?",
                   [r.status, r.decision, r.updated_at.isoformat(), _jd(r.metadata), r.request_id])
        return r

    def set_request_status(self, request_id, status, actor_id=None, reason=None):
        r = self.get_request(request_id)
        if r is None: raise RootlessContainerRequestNotFoundError(f"Not found: {request_id}")
        old = r.status; r.status = status; r.updated_at = datetime.now(timezone.utc)
        self._exec("UPDATE rootless_container_requests SET status=?,updated_at=? WHERE request_id=?",
                   [status, r.updated_at.isoformat(), request_id])
        self._audit(request_id=request_id, tenant_id=r.tenant_id,
                    event_type=RootlessContainerAuditEventType.STATUS_CHANGED,
                    actor=actor_id, msg=f"Status: {old} -> {status}")
        return r

    def set_request_decision(self, request_id, decision, actor_id=None, reason=None):
        r = self.get_request(request_id)
        if r is None: raise RootlessContainerRequestNotFoundError(f"Not found: {request_id}")
        old = r.decision; r.decision = decision; r.updated_at = datetime.now(timezone.utc)
        self._exec("UPDATE rootless_container_requests SET decision=?,updated_at=? WHERE request_id=?",
                   [decision, r.updated_at.isoformat(), request_id])
        self._audit(request_id=request_id, tenant_id=r.tenant_id,
                    event_type=RootlessContainerAuditEventType.DECISION_CHANGED,
                    actor=actor_id, msg=f"Decision: {old} -> {decision}")
        return r

    # ── Capability Assessment ──

    def create_capability_assessment(self, a):
        _cols = ("assessment_id,tenant_id,capability_type,status,risk_level,name,description,"
                 "evidence_refs_json,blockers_json,warnings_json,"
                 "required_before_container_start,required_before_execution,created_at,metadata_json")
        _vals = [a.assessment_id, a.tenant_id, a.capability_type, a.status, a.risk_level,
                 a.name, a.description,
                 _jd(a.evidence_refs), _jd(a.blockers), _jd(a.warnings),
                 int(a.required_before_container_start), int(a.required_before_execution),
                 a.created_at.isoformat() if a.created_at else _now(), _jd(a.metadata)]
        self._exec(f"INSERT INTO rootless_container_capability_assessments ({_cols}) VALUES ({_placeholders(len(_vals))})", _vals)
        self._audit(assessment_id=a.assessment_id, tenant_id=a.tenant_id,
                    event_type=RootlessContainerAuditEventType.CAPABILITY_ASSESSED,
                    msg=f"Capability assessed: {a.capability_type} = {a.status}")
        return a

    def list_capability_assessments(self, *, tenant_id="", capability_type=""):
        sql, p = "SELECT * FROM rootless_container_capability_assessments WHERE 1=1", []
        if tenant_id:
            sql += " AND tenant_id=?"
            p.append(tenant_id)
        if capability_type:
            sql += " AND capability_type=?"
            p.append(capability_type)
        return [self._row_to_assessment(dict(r)) for r in self._exec(sql + " ORDER BY created_at ASC", p)]

    # ── Plan ──

    def reserve_plan_metadata_only(self, plan):
        _cols = ("plan_id,request_id,tenant_id,policy_id,"
                 "capability_assessments_json,required_controls_json,missing_controls_json,"
                 "blocker_summary,plan_status,decision,"
                 "container_start_allowed,runtime_enabled,network_allowed,mount_allowed,"
                 "package_execution_allowed,third_party_execution_allowed,metadata_only,"
                 "created_at,updated_at,metadata_json")
        _vals = [plan.plan_id, plan.request_id, plan.tenant_id, plan.policy_id,
                 _jd(plan.capability_assessments), _jd(plan.required_controls),
                 _jd(plan.missing_controls), plan.blocker_summary,
                 plan.plan_status, plan.decision,
                 int(plan.container_start_allowed), int(plan.runtime_enabled),
                 int(plan.network_allowed), int(plan.mount_allowed),
                 int(plan.package_execution_allowed), int(plan.third_party_execution_allowed),
                 int(plan.metadata_only),
                 plan.created_at.isoformat() if plan.created_at else _now(),
                 plan.updated_at.isoformat() if plan.updated_at else _now(),
                 _jd(plan.metadata)]
        self._exec(f"INSERT INTO rootless_container_plans ({_cols}) VALUES ({_placeholders(len(_vals))})", _vals)
        self._audit(request_id=plan.request_id, plan_id=plan.plan_id,
                    tenant_id=plan.tenant_id, policy_id=plan.policy_id,
                    event_type=RootlessContainerAuditEventType.PLAN_RESERVED_METADATA_ONLY,
                    msg="Rootless container plan reserved metadata-only.")
        return plan

    def get_plan(self, pid):
        row = next(self._exec("SELECT * FROM rootless_container_plans WHERE plan_id=?", [pid]), None)
        return self._row_to_plan(dict(row)) if row else None

    def get_plan_by_request(self, request_id):
        row = next(self._exec(
            "SELECT * FROM rootless_container_plans WHERE request_id=? ORDER BY created_at DESC LIMIT 1",
            [request_id]), None)
        return self._row_to_plan(dict(row)) if row else None

    # ── Gate ──

    def create_gate_result(self, g):
        _cols = ("gate_result_id,request_id,tenant_id,status,decision,checks_json,"
                 "satisfied_count,missing_count,blockers_count,warnings_count,"
                 "ready_for_step26f,container_start_allowed,runtime_enabled,"
                 "network_allowed,mount_allowed,execution_allowed,"
                 "third_party_execution_allowed,package_execution_allowed,metadata_only,"
                 "created_at,metadata_json")
        _vals = [g.gate_result_id, g.request_id, g.tenant_id, g.status, g.decision,
                 _jd(g.checks), g.satisfied_count, g.missing_count,
                 g.blockers_count, g.warnings_count,
                 int(g.ready_for_step26f), int(g.container_start_allowed),
                 int(g.runtime_enabled), int(g.network_allowed),
                 int(g.mount_allowed), int(g.execution_allowed),
                 int(g.third_party_execution_allowed), int(g.package_execution_allowed),
                 int(g.metadata_only),
                 g.created_at.isoformat() if g.created_at else _now(), _jd(g.metadata)]
        self._exec(f"INSERT INTO rootless_container_gate_results ({_cols}) VALUES ({_placeholders(len(_vals))})", _vals)
        self._audit(request_id=g.request_id, tenant_id=g.tenant_id,
                    event_type=RootlessContainerAuditEventType.GATE_EVALUATED,
                    msg=f"Gate evaluated: {g.decision}")
        return g

    def get_gate_result(self, gid):
        row = next(self._exec("SELECT * FROM rootless_container_gate_results WHERE gate_result_id=?", [gid]), None)
        return self._row_to_gate(dict(row)) if row else None

    def get_gate_result_by_request(self, request_id):
        row = next(self._exec(
            "SELECT * FROM rootless_container_gate_results WHERE request_id=? ORDER BY created_at DESC LIMIT 1",
            [request_id]), None)
        return self._row_to_gate(dict(row)) if row else None

    # ── Audit ──

    def add_audit_event(self, evt):
        self._exec(
            "INSERT INTO rootless_container_audit_events (event_id,tenant_id,request_id,plan_id,policy_id,assessment_id,event_type,severity,actor_id,message,metadata_json,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            [evt.event_id, evt.tenant_id, evt.request_id, evt.plan_id, evt.policy_id,
             evt.assessment_id, evt.event_type, evt.severity, evt.actor_id, evt.message,
             _jd(evt.metadata),
             evt.created_at.isoformat() if evt.created_at else _now()])
        return evt

    def list_audit_events(self, *, request_id="", policy_id=""):
        sql, p = "SELECT * FROM rootless_container_audit_events WHERE 1=1", []
        if request_id:
            sql += " AND request_id=?"
            p.append(request_id)
        if policy_id:
            sql += " AND policy_id=?"
            p.append(policy_id)
        return [self._row_to_ae(dict(r)) for r in self._exec(sql + " ORDER BY created_at ASC", p)]

    def count_requests(self, *, tenant_id="", status=""):
        sql, p = "SELECT COUNT(*) as cnt FROM rootless_container_requests WHERE 1=1", []
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
        return RootlessContainerPrototypePolicy(
            policy_id=row["policy_id"], tenant_id=row.get("tenant_id"),
            enabled_metadata_only=bool(row.get("enabled_metadata_only", 1)),
            rootless_container_enabled=bool(row.get("rootless_container_enabled", 0)),
            container_start_enabled=bool(row.get("container_start_enabled", 0)),
            docker_enabled=bool(row.get("docker_enabled", 0)),
            podman_enabled=bool(row.get("podman_enabled", 0)),
            namespace_creation_enabled=bool(row.get("namespace_creation_enabled", 0)),
            cgroup_enabled=bool(row.get("cgroup_enabled", 0)),
            mount_enabled=bool(row.get("mount_enabled", 0)),
            network_enabled=bool(row.get("network_enabled", 0)),
            package_execution_enabled=bool(row.get("package_execution_enabled", 0)),
            third_party_execution_enabled=bool(row.get("third_party_execution_enabled", 0)),
            requires_kill_switch_clear=bool(row.get("requires_kill_switch_clear", 1)),
            requires_incident_clear=bool(row.get("requires_incident_clear", 1)),
            requires_read_only_artifact_plan=bool(row.get("requires_read_only_artifact_plan", 1)),
            requires_download_worker_blocked=bool(row.get("requires_download_worker_blocked", 1)),
            requires_red_team_passed=bool(row.get("requires_red_team_passed", 1)),
            created_by=row.get("created_by"),
            created_at=_sdt(row.get("created_at")),
            updated_at=_sdt(row.get("updated_at")),
            metadata=json.loads(row.get("metadata_json", "{}"))
        )

    @staticmethod
    def _row_to_request(row):
        return RootlessContainerPrototypeRequest(
            request_id=row["request_id"], tenant_id=row.get("tenant_id"),
            policy_id=row.get("policy_id"),
            production_gate_request_id=row.get("production_gate_request_id"),
            kill_switch_policy_id=row.get("kill_switch_policy_id"),
            incident_id=row.get("incident_id"),
            artifact_plan_id=row.get("artifact_plan_id"),
            download_worker_job_id=row.get("download_worker_job_id"),
            policy_snapshot=json.loads(row.get("policy_snapshot_json", "{}")),
            production_gate_snapshot=json.loads(row.get("production_gate_snapshot_json", "{}")),
            kill_switch_snapshot=json.loads(row.get("kill_switch_snapshot_json", "{}")),
            artifact_plan_snapshot=json.loads(row.get("artifact_plan_snapshot_json", "{}")),
            download_worker_snapshot=json.loads(row.get("download_worker_snapshot_json", "{}")),
            status=row.get("status", "disabled_by_default"),
            decision=row.get("decision", "blocked_disabled"),
            container_started=bool(row.get("container_started", 0)),
            runtime_started=bool(row.get("runtime_started", 0)),
            namespace_created=bool(row.get("namespace_created", 0)),
            cgroup_created=bool(row.get("cgroup_created", 0)),
            mount_created=bool(row.get("mount_created", 0)),
            network_enabled=bool(row.get("network_enabled", 0)),
            package_executed=bool(row.get("package_executed", 0)),
            third_party_code_executed=bool(row.get("third_party_code_executed", 0)),
            no_container_started=bool(row.get("no_container_started", 1)),
            no_runtime_started=bool(row.get("no_runtime_started", 1)),
            no_namespace_created=bool(row.get("no_namespace_created", 1)),
            no_cgroup_created=bool(row.get("no_cgroup_created", 1)),
            no_mount_created=bool(row.get("no_mount_created", 1)),
            no_network_enabled=bool(row.get("no_network_enabled", 1)),
            no_execution_performed=bool(row.get("no_execution_performed", 1)),
            no_package_executed=bool(row.get("no_package_executed", 1)),
            no_third_party_code_executed=bool(row.get("no_third_party_code_executed", 1)),
            created_at=_sdt(row.get("created_at")),
            updated_at=_sdt(row.get("updated_at")),
            metadata=json.loads(row.get("metadata_json", "{}"))
        )

    @staticmethod
    def _row_to_assessment(row):
        return RootlessContainerCapabilityAssessment(
            assessment_id=row["assessment_id"], tenant_id=row.get("tenant_id"),
            capability_type=row["capability_type"],
            status=row.get("status", "not_checked_runtime_disabled"),
            risk_level=row.get("risk_level", "unknown"),
            name=row.get("name", ""), description=row.get("description", ""),
            evidence_refs=json.loads(row.get("evidence_refs_json", "[]")),
            blockers=json.loads(row.get("blockers_json", "[]")),
            warnings=json.loads(row.get("warnings_json", "[]")),
            required_before_container_start=bool(row.get("required_before_container_start", 1)),
            required_before_execution=bool(row.get("required_before_execution", 1)),
            created_at=_sdt(row.get("created_at")),
            metadata=json.loads(row.get("metadata_json", "{}"))
        )

    @staticmethod
    def _row_to_plan(row):
        return RootlessContainerPrototypePlan(
            plan_id=row["plan_id"], request_id=row["request_id"],
            tenant_id=row.get("tenant_id"), policy_id=row.get("policy_id"),
            capability_assessments=json.loads(row.get("capability_assessments_json", "[]")),
            required_controls=json.loads(row.get("required_controls_json", "[]")),
            missing_controls=json.loads(row.get("missing_controls_json", "[]")),
            blocker_summary=row.get("blocker_summary", ""),
            plan_status=row.get("plan_status", "plan_reserved_metadata_only"),
            decision=row.get("decision", "metadata_plan_reserved"),
            container_start_allowed=bool(row.get("container_start_allowed", 0)),
            runtime_enabled=bool(row.get("runtime_enabled", 0)),
            network_allowed=bool(row.get("network_allowed", 0)),
            mount_allowed=bool(row.get("mount_allowed", 0)),
            package_execution_allowed=bool(row.get("package_execution_allowed", 0)),
            third_party_execution_allowed=bool(row.get("third_party_execution_allowed", 0)),
            metadata_only=bool(row.get("metadata_only", 1)),
            created_at=_sdt(row.get("created_at")),
            updated_at=_sdt(row.get("updated_at")),
            metadata=json.loads(row.get("metadata_json", "{}"))
        )

    @staticmethod
    def _row_to_gate(row):
        return RootlessContainerGateResult(
            gate_result_id=row["gate_result_id"], request_id=row["request_id"],
            tenant_id=row.get("tenant_id"),
            status=row.get("status", "disabled_by_default"),
            decision=row.get("decision", "blocked_disabled"),
            checks=json.loads(row.get("checks_json", "[]")),
            satisfied_count=int(row.get("satisfied_count", 0)),
            missing_count=int(row.get("missing_count", 0)),
            blockers_count=int(row.get("blockers_count", 0)),
            warnings_count=int(row.get("warnings_count", 0)),
            ready_for_step26f=bool(row.get("ready_for_step26f", 0)),
            container_start_allowed=bool(row.get("container_start_allowed", 0)),
            runtime_enabled=bool(row.get("runtime_enabled", 0)),
            network_allowed=bool(row.get("network_allowed", 0)),
            mount_allowed=bool(row.get("mount_allowed", 0)),
            execution_allowed=bool(row.get("execution_allowed", 0)),
            third_party_execution_allowed=bool(row.get("third_party_execution_allowed", 0)),
            package_execution_allowed=bool(row.get("package_execution_allowed", 0)),
            metadata_only=bool(row.get("metadata_only", 1)),
            created_at=_sdt(row.get("created_at")),
            metadata=json.loads(row.get("metadata_json", "{}"))
        )

    @staticmethod
    def _row_to_ae(row):
        return RootlessContainerAuditEvent(
            event_id=row["event_id"], tenant_id=row.get("tenant_id"),
            request_id=row.get("request_id"), plan_id=row.get("plan_id"),
            policy_id=row.get("policy_id"), assessment_id=row.get("assessment_id"),
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
