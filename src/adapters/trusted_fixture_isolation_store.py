"""SQLite Trusted Fixture Isolation Store — metadata-only, no runtime, no container, no execution."""
from __future__ import annotations
import json, logging
from datetime import datetime, timezone
from typing import Any
from src.adapters.config import Settings
from src.adapters.sqlite_connection import create_sqlite_db, execute_with_retry
from src.open_platform.trusted_fixture_isolation import *

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS trusted_fixture_isolation_policies (
    policy_id TEXT PRIMARY KEY, tenant_id TEXT,
    enabled_metadata_only INTEGER NOT NULL DEFAULT 1,
    isolated_runtime_enabled INTEGER NOT NULL DEFAULT 0,
    container_start_enabled INTEGER NOT NULL DEFAULT 0, microvm_start_enabled INTEGER NOT NULL DEFAULT 0,
    trusted_fixture_execution_enabled INTEGER NOT NULL DEFAULT 0,
    third_party_execution_enabled INTEGER NOT NULL DEFAULT 0,
    package_execution_enabled INTEGER NOT NULL DEFAULT 0, entrypoint_execution_enabled INTEGER NOT NULL DEFAULT 0,
    network_enabled INTEGER NOT NULL DEFAULT 0, filesystem_write_enabled INTEGER NOT NULL DEFAULT 0,
    secrets_enabled INTEGER NOT NULL DEFAULT 0, subprocess_enabled INTEGER NOT NULL DEFAULT 0,
    dynamic_import_enabled INTEGER NOT NULL DEFAULT 0, eval_exec_enabled INTEGER NOT NULL DEFAULT 0,
    requires_rootless_container_gate INTEGER NOT NULL DEFAULT 1,
    requires_kill_switch_clear INTEGER NOT NULL DEFAULT 1, requires_incident_clear INTEGER NOT NULL DEFAULT 1,
    requires_red_team_passed INTEGER NOT NULL DEFAULT 1,
    created_by TEXT, created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')), metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_tfixpol_tenant ON trusted_fixture_isolation_policies(tenant_id);

CREATE TABLE IF NOT EXISTS trusted_fixture_isolation_requests (
    request_id TEXT PRIMARY KEY, tenant_id TEXT, policy_id TEXT,
    trusted_fixture_request_id TEXT, trusted_fixture_id TEXT,
    rootless_container_gate_request_id TEXT, rootless_container_plan_id TEXT,
    policy_snapshot_json TEXT NOT NULL DEFAULT '{}',
    trusted_fixture_snapshot_json TEXT NOT NULL DEFAULT '{}',
    rootless_container_snapshot_json TEXT NOT NULL DEFAULT '{}',
    kill_switch_snapshot_json TEXT NOT NULL DEFAULT '{}',
    incident_snapshot_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'disabled_by_default', decision TEXT NOT NULL DEFAULT 'blocked_disabled',
    isolated_runtime_started INTEGER NOT NULL DEFAULT 0, container_started INTEGER NOT NULL DEFAULT 0,
    microvm_started INTEGER NOT NULL DEFAULT 0,
    fixture_executed_in_isolated_runtime INTEGER NOT NULL DEFAULT 0,
    fixture_executed_in_container INTEGER NOT NULL DEFAULT 0,
    fixture_executed_in_microvm INTEGER NOT NULL DEFAULT 0,
    third_party_code_executed INTEGER NOT NULL DEFAULT 0, package_executed INTEGER NOT NULL DEFAULT 0,
    entrypoint_executed INTEGER NOT NULL DEFAULT 0, network_used INTEGER NOT NULL DEFAULT 0,
    filesystem_written INTEGER NOT NULL DEFAULT 0, secrets_read INTEGER NOT NULL DEFAULT 0,
    subprocess_used INTEGER NOT NULL DEFAULT 0,
    no_isolated_runtime_started INTEGER NOT NULL DEFAULT 1, no_container_started INTEGER NOT NULL DEFAULT 1,
    no_microvm_started INTEGER NOT NULL DEFAULT 1,
    no_third_party_code_executed INTEGER NOT NULL DEFAULT 1, no_package_executed INTEGER NOT NULL DEFAULT 1,
    no_entrypoint_executed INTEGER NOT NULL DEFAULT 1, no_network_used INTEGER NOT NULL DEFAULT 1,
    no_filesystem_written INTEGER NOT NULL DEFAULT 1, no_secrets_read INTEGER NOT NULL DEFAULT 1,
    no_subprocess_used INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')), updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_tfixreq_tenant ON trusted_fixture_isolation_requests(tenant_id);
CREATE INDEX IF NOT EXISTS idx_tfixreq_status ON trusted_fixture_isolation_requests(status);
CREATE INDEX IF NOT EXISTS idx_tfixreq_policy ON trusted_fixture_isolation_requests(policy_id);

CREATE TABLE IF NOT EXISTS trusted_fixture_isolation_requirements (
    requirement_id TEXT PRIMARY KEY, tenant_id TEXT,
    requirement_type TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'not_checked_runtime_disabled',
    name TEXT NOT NULL DEFAULT '', description TEXT NOT NULL DEFAULT '',
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    blockers_json TEXT NOT NULL DEFAULT '[]', warnings_json TEXT NOT NULL DEFAULT '[]',
    required_before_isolated_fixture INTEGER NOT NULL DEFAULT 1,
    required_before_third_party_execution INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')), metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_tfixrqmnt_type ON trusted_fixture_isolation_requirements(requirement_type);

CREATE TABLE IF NOT EXISTS trusted_fixture_isolation_plans (
    plan_id TEXT PRIMARY KEY, request_id TEXT NOT NULL, tenant_id TEXT, policy_id TEXT, fixture_id TEXT,
    isolation_requirements_json TEXT NOT NULL DEFAULT '[]',
    satisfied_requirements_json TEXT NOT NULL DEFAULT '[]',
    missing_requirements_json TEXT NOT NULL DEFAULT '[]',
    blocker_summary TEXT NOT NULL DEFAULT '',
    plan_status TEXT NOT NULL DEFAULT 'plan_reserved_metadata_only',
    decision TEXT NOT NULL DEFAULT 'metadata_plan_reserved',
    ready_for_step26g INTEGER NOT NULL DEFAULT 0,
    isolated_runtime_enabled INTEGER NOT NULL DEFAULT 0, container_start_allowed INTEGER NOT NULL DEFAULT 0,
    microvm_start_allowed INTEGER NOT NULL DEFAULT 0, fixture_execution_allowed INTEGER NOT NULL DEFAULT 0,
    third_party_execution_allowed INTEGER NOT NULL DEFAULT 0, package_execution_allowed INTEGER NOT NULL DEFAULT 0,
    entrypoint_execution_allowed INTEGER NOT NULL DEFAULT 0, network_allowed INTEGER NOT NULL DEFAULT 0,
    filesystem_write_allowed INTEGER NOT NULL DEFAULT 0, secrets_allowed INTEGER NOT NULL DEFAULT 0,
    subprocess_allowed INTEGER NOT NULL DEFAULT 0, metadata_only INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')), updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_tfixplan_request ON trusted_fixture_isolation_plans(request_id);

CREATE TABLE IF NOT EXISTS trusted_fixture_isolation_gate_results (
    gate_result_id TEXT PRIMARY KEY, request_id TEXT NOT NULL, tenant_id TEXT,
    status TEXT NOT NULL DEFAULT 'disabled_by_default', decision TEXT NOT NULL DEFAULT 'blocked_disabled',
    checks_json TEXT NOT NULL DEFAULT '[]',
    satisfied_count INTEGER NOT NULL DEFAULT 0, missing_count INTEGER NOT NULL DEFAULT 0,
    blockers_count INTEGER NOT NULL DEFAULT 0, warnings_count INTEGER NOT NULL DEFAULT 0,
    ready_for_step26g INTEGER NOT NULL DEFAULT 0,
    isolated_runtime_enabled INTEGER NOT NULL DEFAULT 0, container_start_allowed INTEGER NOT NULL DEFAULT 0,
    microvm_start_allowed INTEGER NOT NULL DEFAULT 0, fixture_execution_allowed INTEGER NOT NULL DEFAULT 0,
    third_party_execution_allowed INTEGER NOT NULL DEFAULT 0, package_execution_allowed INTEGER NOT NULL DEFAULT 0,
    execution_allowed INTEGER NOT NULL DEFAULT 0, metadata_only INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')), metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_tfixgate_request ON trusted_fixture_isolation_gate_results(request_id);

CREATE TABLE IF NOT EXISTS trusted_fixture_isolation_audit_events (
    event_id TEXT PRIMARY KEY, tenant_id TEXT, request_id TEXT, plan_id TEXT,
    policy_id TEXT, requirement_id TEXT,
    event_type TEXT NOT NULL, severity TEXT NOT NULL DEFAULT 'info',
    actor_id TEXT, message TEXT NOT NULL DEFAULT '', metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_tfixevt_request ON trusted_fixture_isolation_audit_events(request_id);
CREATE INDEX IF NOT EXISTS idx_tfixevt_policy ON trusted_fixture_isolation_audit_events(policy_id);
CREATE INDEX IF NOT EXISTS idx_tfixevt_type ON trusted_fixture_isolation_audit_events(event_type);
"""


def _placeholders(count: int) -> str:
    return ",".join(["?"] * count)


def _jd(obj):
    return json.dumps(obj, ensure_ascii=False)


def _now():
    return datetime.now(timezone.utc).isoformat()


class SQLiteTrustedFixtureIsolationStore:
    def __init__(self, config: Settings, db_path: str | None = None):
        path = db_path or config.sqlite_db_path
        self._db = create_sqlite_db(path)
        execute_with_retry(lambda: self._init_schema(), label="tfix_init")

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

    def _audit(self, request_id=None, plan_id=None, policy_id=None, requirement_id=None,
               tenant_id=None, event_type="", actor=None, msg=""):
        self.add_audit_event(TrustedFixtureIsolationAuditEvent(
            request_id=request_id, plan_id=plan_id, policy_id=policy_id,
            requirement_id=requirement_id, tenant_id=tenant_id,
            event_type=event_type, actor_id=actor, message=msg))

    # ── Policy ──

    def create_policy(self, p):
        _cols = ("policy_id,tenant_id,enabled_metadata_only,isolated_runtime_enabled,"
                 "container_start_enabled,microvm_start_enabled,trusted_fixture_execution_enabled,"
                 "third_party_execution_enabled,package_execution_enabled,entrypoint_execution_enabled,"
                 "network_enabled,filesystem_write_enabled,secrets_enabled,subprocess_enabled,"
                 "dynamic_import_enabled,eval_exec_enabled,"
                 "requires_rootless_container_gate,requires_kill_switch_clear,requires_incident_clear,"
                 "requires_red_team_passed,created_by,created_at,updated_at,metadata_json")
        _vals = [p.policy_id, p.tenant_id, int(p.enabled_metadata_only),
                 int(p.isolated_runtime_enabled), int(p.container_start_enabled),
                 int(p.microvm_start_enabled), int(p.trusted_fixture_execution_enabled),
                 int(p.third_party_execution_enabled), int(p.package_execution_enabled),
                 int(p.entrypoint_execution_enabled), int(p.network_enabled),
                 int(p.filesystem_write_enabled), int(p.secrets_enabled),
                 int(p.subprocess_enabled), int(p.dynamic_import_enabled), int(p.eval_exec_enabled),
                 int(p.requires_rootless_container_gate), int(p.requires_kill_switch_clear),
                 int(p.requires_incident_clear), int(p.requires_red_team_passed),
                 p.created_by,
                 p.created_at.isoformat() if p.created_at else _now(),
                 p.updated_at.isoformat() if p.updated_at else _now(), _jd(p.metadata)]
        self._exec(f"INSERT INTO trusted_fixture_isolation_policies ({_cols}) VALUES ({_placeholders(len(_vals))})", _vals)
        self._audit(policy_id=p.policy_id, tenant_id=p.tenant_id,
                    event_type=TrustedFixtureIsolationAuditEventType.POLICY_CREATED,
                    actor=p.created_by, msg="Isolation policy created (disabled).")
        return p

    def get_policy(self, pid):
        row = next(self._exec("SELECT * FROM trusted_fixture_isolation_policies WHERE policy_id=?", [pid]), None)
        return self._row_to_policy(dict(row)) if row else None

    def list_policies(self, *, tenant_id=""):
        sql, p = "SELECT * FROM trusted_fixture_isolation_policies WHERE 1=1", []
        if tenant_id: sql += " AND tenant_id=?"; p.append(tenant_id)
        return [self._row_to_policy(dict(r)) for r in self._exec(sql + " ORDER BY created_at DESC", p)]

    def update_policy(self, pol):
        pol.updated_at = datetime.now(timezone.utc)
        self._exec(
            "UPDATE trusted_fixture_isolation_policies SET "
            "isolated_runtime_enabled=?,container_start_enabled=?,microvm_start_enabled=?,"
            "trusted_fixture_execution_enabled=?,third_party_execution_enabled=?,"
            "package_execution_enabled=?,entrypoint_execution_enabled=?,"
            "network_enabled=?,filesystem_write_enabled=?,secrets_enabled=?,"
            "subprocess_enabled=?,dynamic_import_enabled=?,eval_exec_enabled=?,"
            "requires_rootless_container_gate=?,requires_kill_switch_clear=?,requires_incident_clear=?,"
            "requires_red_team_passed=?,updated_at=?,metadata_json=? WHERE policy_id=?",
            [int(pol.isolated_runtime_enabled), int(pol.container_start_enabled),
             int(pol.microvm_start_enabled), int(pol.trusted_fixture_execution_enabled),
             int(pol.third_party_execution_enabled), int(pol.package_execution_enabled),
             int(pol.entrypoint_execution_enabled), int(pol.network_enabled),
             int(pol.filesystem_write_enabled), int(pol.secrets_enabled),
             int(pol.subprocess_enabled), int(pol.dynamic_import_enabled), int(pol.eval_exec_enabled),
             int(pol.requires_rootless_container_gate), int(pol.requires_kill_switch_clear),
             int(pol.requires_incident_clear), int(pol.requires_red_team_passed),
             pol.updated_at.isoformat(), _jd(pol.metadata), pol.policy_id])
        return pol

    # ── Request ──

    def create_request(self, r):
        _cols = ("request_id,tenant_id,policy_id,trusted_fixture_request_id,trusted_fixture_id,"
                 "rootless_container_gate_request_id,rootless_container_plan_id,"
                 "policy_snapshot_json,trusted_fixture_snapshot_json,rootless_container_snapshot_json,"
                 "kill_switch_snapshot_json,incident_snapshot_json,"
                 "status,decision,isolated_runtime_started,container_started,microvm_started,"
                 "fixture_executed_in_isolated_runtime,fixture_executed_in_container,fixture_executed_in_microvm,"
                 "third_party_code_executed,package_executed,entrypoint_executed,"
                 "network_used,filesystem_written,secrets_read,subprocess_used,"
                 "no_isolated_runtime_started,no_container_started,no_microvm_started,"
                 "no_third_party_code_executed,no_package_executed,no_entrypoint_executed,"
                 "no_network_used,no_filesystem_written,no_secrets_read,no_subprocess_used,"
                 "created_at,updated_at,metadata_json")
        _vals = [r.request_id, r.tenant_id, r.policy_id,
                 r.trusted_fixture_request_id, r.trusted_fixture_id,
                 r.rootless_container_gate_request_id, r.rootless_container_plan_id,
                 _jd(r.policy_snapshot), _jd(r.trusted_fixture_snapshot),
                 _jd(r.rootless_container_snapshot), _jd(r.kill_switch_snapshot),
                 _jd(r.incident_snapshot),
                 r.status, r.decision,
                 int(r.isolated_runtime_started), int(r.container_started), int(r.microvm_started),
                 int(r.fixture_executed_in_isolated_runtime), int(r.fixture_executed_in_container),
                 int(r.fixture_executed_in_microvm),
                 int(r.third_party_code_executed), int(r.package_executed), int(r.entrypoint_executed),
                 int(r.network_used), int(r.filesystem_written), int(r.secrets_read),
                 int(r.subprocess_used),
                 int(r.no_isolated_runtime_started), int(r.no_container_started),
                 int(r.no_microvm_started),
                 int(r.no_third_party_code_executed), int(r.no_package_executed),
                 int(r.no_entrypoint_executed),
                 int(r.no_network_used), int(r.no_filesystem_written), int(r.no_secrets_read),
                 int(r.no_subprocess_used),
                 r.created_at.isoformat() if r.created_at else _now(),
                 r.updated_at.isoformat() if r.updated_at else _now(), _jd(r.metadata)]
        self._exec(f"INSERT INTO trusted_fixture_isolation_requests ({_cols}) VALUES ({_placeholders(len(_vals))})", _vals)
        self._audit(request_id=r.request_id, tenant_id=r.tenant_id, policy_id=r.policy_id,
                    event_type=TrustedFixtureIsolationAuditEventType.REQUEST_CREATED,
                    msg="Isolation request created (disabled).")
        return r

    def get_request(self, rid):
        row = next(self._exec("SELECT * FROM trusted_fixture_isolation_requests WHERE request_id=?", [rid]), None)
        return self._row_to_request(dict(row)) if row else None

    def list_requests(self, *, tenant_id="", status="", policy_id=""):
        sql, p = "SELECT * FROM trusted_fixture_isolation_requests WHERE 1=1", []
        if tenant_id: sql += " AND tenant_id=?"; p.append(tenant_id)
        if status: sql += " AND status=?"; p.append(status)
        if policy_id: sql += " AND policy_id=?"; p.append(policy_id)
        return [self._row_to_request(dict(r)) for r in self._exec(sql + " ORDER BY created_at DESC", p)]

    def update_request(self, r):
        r.updated_at = datetime.now(timezone.utc)
        self._exec("UPDATE trusted_fixture_isolation_requests SET status=?,decision=?,updated_at=?,metadata_json=? WHERE request_id=?",
                   [r.status, r.decision, r.updated_at.isoformat(), _jd(r.metadata), r.request_id])
        return r

    def set_request_status(self, request_id, status, actor_id=None, reason=None):
        r = self.get_request(request_id)
        if r is None: raise TrustedFixtureIsolationRequestNotFoundError(f"Not found: {request_id}")
        old = r.status; r.status = status; r.updated_at = datetime.now(timezone.utc)
        self._exec("UPDATE trusted_fixture_isolation_requests SET status=?,updated_at=? WHERE request_id=?",
                   [status, r.updated_at.isoformat(), request_id])
        self._audit(request_id=request_id, tenant_id=r.tenant_id,
                    event_type=TrustedFixtureIsolationAuditEventType.STATUS_CHANGED,
                    actor=actor_id, msg=f"Status: {old} -> {status}")
        return r

    def set_request_decision(self, request_id, decision, actor_id=None, reason=None):
        r = self.get_request(request_id)
        if r is None: raise TrustedFixtureIsolationRequestNotFoundError(f"Not found: {request_id}")
        old = r.decision; r.decision = decision; r.updated_at = datetime.now(timezone.utc)
        self._exec("UPDATE trusted_fixture_isolation_requests SET decision=?,updated_at=? WHERE request_id=?",
                   [decision, r.updated_at.isoformat(), request_id])
        self._audit(request_id=request_id, tenant_id=r.tenant_id,
                    event_type=TrustedFixtureIsolationAuditEventType.DECISION_CHANGED,
                    actor=actor_id, msg=f"Decision: {old} -> {decision}")
        return r

    # ── Requirement ──

    def create_requirement(self, req):
        _cols = ("requirement_id,tenant_id,requirement_type,status,name,description,"
                 "evidence_refs_json,blockers_json,warnings_json,"
                 "required_before_isolated_fixture,required_before_third_party_execution,"
                 "created_at,metadata_json")
        _vals = [req.requirement_id, req.tenant_id, req.requirement_type, req.status,
                 req.name, req.description,
                 _jd(req.evidence_refs), _jd(req.blockers), _jd(req.warnings),
                 int(req.required_before_isolated_fixture), int(req.required_before_third_party_execution),
                 req.created_at.isoformat() if req.created_at else _now(), _jd(req.metadata)]
        self._exec(f"INSERT INTO trusted_fixture_isolation_requirements ({_cols}) VALUES ({_placeholders(len(_vals))})", _vals)
        self._audit(requirement_id=req.requirement_id, tenant_id=req.tenant_id,
                    event_type=TrustedFixtureIsolationAuditEventType.REQUIREMENT_ASSESSED,
                    msg=f"Requirement assessed: {req.requirement_type} = {req.status}")
        return req

    def list_requirements(self, *, tenant_id="", requirement_type=""):
        sql, p = "SELECT * FROM trusted_fixture_isolation_requirements WHERE 1=1", []
        if tenant_id: sql += " AND tenant_id=?"; p.append(tenant_id)
        if requirement_type: sql += " AND requirement_type=?"; p.append(requirement_type)
        return [self._row_to_requirement(dict(r)) for r in self._exec(sql + " ORDER BY created_at ASC", p)]

    # ── Plan ──

    def reserve_plan_metadata_only(self, plan):
        _cols = ("plan_id,request_id,tenant_id,policy_id,fixture_id,"
                 "isolation_requirements_json,satisfied_requirements_json,missing_requirements_json,"
                 "blocker_summary,plan_status,decision,"
                 "ready_for_step26g,isolated_runtime_enabled,container_start_allowed,microvm_start_allowed,"
                 "fixture_execution_allowed,third_party_execution_allowed,package_execution_allowed,"
                 "entrypoint_execution_allowed,network_allowed,filesystem_write_allowed,"
                 "secrets_allowed,subprocess_allowed,metadata_only,"
                 "created_at,updated_at,metadata_json")
        _vals = [plan.plan_id, plan.request_id, plan.tenant_id, plan.policy_id, plan.fixture_id,
                 _jd(plan.isolation_requirements), _jd(plan.satisfied_requirements),
                 _jd(plan.missing_requirements), plan.blocker_summary,
                 plan.plan_status, plan.decision,
                 int(plan.ready_for_step26g), int(plan.isolated_runtime_enabled),
                 int(plan.container_start_allowed), int(plan.microvm_start_allowed),
                 int(plan.fixture_execution_allowed), int(plan.third_party_execution_allowed),
                 int(plan.package_execution_allowed), int(plan.entrypoint_execution_allowed),
                 int(plan.network_allowed), int(plan.filesystem_write_allowed),
                 int(plan.secrets_allowed), int(plan.subprocess_allowed),
                 int(plan.metadata_only),
                 plan.created_at.isoformat() if plan.created_at else _now(),
                 plan.updated_at.isoformat() if plan.updated_at else _now(),
                 _jd(plan.metadata)]
        self._exec(f"INSERT INTO trusted_fixture_isolation_plans ({_cols}) VALUES ({_placeholders(len(_vals))})", _vals)
        self._audit(request_id=plan.request_id, plan_id=plan.plan_id,
                    tenant_id=plan.tenant_id, policy_id=plan.policy_id,
                    event_type=TrustedFixtureIsolationAuditEventType.PLAN_RESERVED_METADATA_ONLY,
                    msg="Isolation plan reserved metadata-only.")
        return plan

    def get_plan(self, pid):
        row = next(self._exec("SELECT * FROM trusted_fixture_isolation_plans WHERE plan_id=?", [pid]), None)
        return self._row_to_plan(dict(row)) if row else None

    def get_plan_by_request(self, request_id):
        row = next(self._exec(
            "SELECT * FROM trusted_fixture_isolation_plans WHERE request_id=? ORDER BY created_at DESC LIMIT 1",
            [request_id]), None)
        return self._row_to_plan(dict(row)) if row else None

    # ── Gate ──

    def create_gate_result(self, g):
        _cols = ("gate_result_id,request_id,tenant_id,status,decision,checks_json,"
                 "satisfied_count,missing_count,blockers_count,warnings_count,"
                 "ready_for_step26g,isolated_runtime_enabled,container_start_allowed,"
                 "microvm_start_allowed,fixture_execution_allowed,third_party_execution_allowed,"
                 "package_execution_allowed,execution_allowed,metadata_only,"
                 "created_at,metadata_json")
        _vals = [g.gate_result_id, g.request_id, g.tenant_id, g.status, g.decision,
                 _jd(g.checks), g.satisfied_count, g.missing_count,
                 g.blockers_count, g.warnings_count,
                 int(g.ready_for_step26g), int(g.isolated_runtime_enabled),
                 int(g.container_start_allowed), int(g.microvm_start_allowed),
                 int(g.fixture_execution_allowed), int(g.third_party_execution_allowed),
                 int(g.package_execution_allowed), int(g.execution_allowed),
                 int(g.metadata_only),
                 g.created_at.isoformat() if g.created_at else _now(), _jd(g.metadata)]
        self._exec(f"INSERT INTO trusted_fixture_isolation_gate_results ({_cols}) VALUES ({_placeholders(len(_vals))})", _vals)
        self._audit(request_id=g.request_id, tenant_id=g.tenant_id,
                    event_type=TrustedFixtureIsolationAuditEventType.GATE_EVALUATED,
                    msg=f"Gate evaluated: {g.decision}")
        return g

    def get_gate_result(self, gid):
        row = next(self._exec("SELECT * FROM trusted_fixture_isolation_gate_results WHERE gate_result_id=?", [gid]), None)
        return self._row_to_gate(dict(row)) if row else None

    def get_gate_result_by_request(self, request_id):
        row = next(self._exec(
            "SELECT * FROM trusted_fixture_isolation_gate_results WHERE request_id=? ORDER BY created_at DESC LIMIT 1",
            [request_id]), None)
        return self._row_to_gate(dict(row)) if row else None

    # ── Audit ──

    def add_audit_event(self, evt):
        self._exec(
            "INSERT INTO trusted_fixture_isolation_audit_events (event_id,tenant_id,request_id,plan_id,policy_id,requirement_id,event_type,severity,actor_id,message,metadata_json,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            [evt.event_id, evt.tenant_id, evt.request_id, evt.plan_id, evt.policy_id,
             evt.requirement_id, evt.event_type, evt.severity, evt.actor_id, evt.message,
             _jd(evt.metadata),
             evt.created_at.isoformat() if evt.created_at else _now()])
        return evt

    def list_audit_events(self, *, request_id="", policy_id=""):
        sql, p = "SELECT * FROM trusted_fixture_isolation_audit_events WHERE 1=1", []
        if request_id: sql += " AND request_id=?"; p.append(request_id)
        if policy_id: sql += " AND policy_id=?"; p.append(policy_id)
        return [self._row_to_ae(dict(r)) for r in self._exec(sql + " ORDER BY created_at ASC", p)]

    def count_requests(self, *, tenant_id="", status=""):
        sql, p = "SELECT COUNT(*) as cnt FROM trusted_fixture_isolation_requests WHERE 1=1", []
        if tenant_id: sql += " AND tenant_id=?"; p.append(tenant_id)
        if status: sql += " AND status=?"; p.append(status)
        row = next(self._exec(sql, p), None)
        return row["cnt"] if row else 0

    # ── Row mappers ──

    @staticmethod
    def _row_to_policy(row):
        return TrustedFixtureIsolationPolicy(
            policy_id=row["policy_id"], tenant_id=row.get("tenant_id"),
            enabled_metadata_only=bool(row.get("enabled_metadata_only", 1)),
            isolated_runtime_enabled=bool(row.get("isolated_runtime_enabled", 0)),
            container_start_enabled=bool(row.get("container_start_enabled", 0)),
            microvm_start_enabled=bool(row.get("microvm_start_enabled", 0)),
            trusted_fixture_execution_enabled=bool(row.get("trusted_fixture_execution_enabled", 0)),
            third_party_execution_enabled=bool(row.get("third_party_execution_enabled", 0)),
            package_execution_enabled=bool(row.get("package_execution_enabled", 0)),
            entrypoint_execution_enabled=bool(row.get("entrypoint_execution_enabled", 0)),
            network_enabled=bool(row.get("network_enabled", 0)),
            filesystem_write_enabled=bool(row.get("filesystem_write_enabled", 0)),
            secrets_enabled=bool(row.get("secrets_enabled", 0)),
            subprocess_enabled=bool(row.get("subprocess_enabled", 0)),
            dynamic_import_enabled=bool(row.get("dynamic_import_enabled", 0)),
            eval_exec_enabled=bool(row.get("eval_exec_enabled", 0)),
            requires_rootless_container_gate=bool(row.get("requires_rootless_container_gate", 1)),
            requires_kill_switch_clear=bool(row.get("requires_kill_switch_clear", 1)),
            requires_incident_clear=bool(row.get("requires_incident_clear", 1)),
            requires_red_team_passed=bool(row.get("requires_red_team_passed", 1)),
            created_by=row.get("created_by"),
            created_at=_sdt(row.get("created_at")),
            updated_at=_sdt(row.get("updated_at")),
            metadata=json.loads(row.get("metadata_json", "{}"))
        )

    @staticmethod
    def _row_to_request(row):
        return TrustedFixtureIsolationRequest(
            request_id=row["request_id"], tenant_id=row.get("tenant_id"),
            policy_id=row.get("policy_id"),
            trusted_fixture_request_id=row.get("trusted_fixture_request_id"),
            trusted_fixture_id=row.get("trusted_fixture_id"),
            rootless_container_gate_request_id=row.get("rootless_container_gate_request_id"),
            rootless_container_plan_id=row.get("rootless_container_plan_id"),
            policy_snapshot=json.loads(row.get("policy_snapshot_json", "{}")),
            trusted_fixture_snapshot=json.loads(row.get("trusted_fixture_snapshot_json", "{}")),
            rootless_container_snapshot=json.loads(row.get("rootless_container_snapshot_json", "{}")),
            kill_switch_snapshot=json.loads(row.get("kill_switch_snapshot_json", "{}")),
            incident_snapshot=json.loads(row.get("incident_snapshot_json", "{}")),
            status=row.get("status", "disabled_by_default"),
            decision=row.get("decision", "blocked_disabled"),
            isolated_runtime_started=bool(row.get("isolated_runtime_started", 0)),
            container_started=bool(row.get("container_started", 0)),
            microvm_started=bool(row.get("microvm_started", 0)),
            fixture_executed_in_isolated_runtime=bool(row.get("fixture_executed_in_isolated_runtime", 0)),
            fixture_executed_in_container=bool(row.get("fixture_executed_in_container", 0)),
            fixture_executed_in_microvm=bool(row.get("fixture_executed_in_microvm", 0)),
            third_party_code_executed=bool(row.get("third_party_code_executed", 0)),
            package_executed=bool(row.get("package_executed", 0)),
            entrypoint_executed=bool(row.get("entrypoint_executed", 0)),
            network_used=bool(row.get("network_used", 0)),
            filesystem_written=bool(row.get("filesystem_written", 0)),
            secrets_read=bool(row.get("secrets_read", 0)),
            subprocess_used=bool(row.get("subprocess_used", 0)),
            no_isolated_runtime_started=bool(row.get("no_isolated_runtime_started", 1)),
            no_container_started=bool(row.get("no_container_started", 1)),
            no_microvm_started=bool(row.get("no_microvm_started", 1)),
            no_third_party_code_executed=bool(row.get("no_third_party_code_executed", 1)),
            no_package_executed=bool(row.get("no_package_executed", 1)),
            no_entrypoint_executed=bool(row.get("no_entrypoint_executed", 1)),
            no_network_used=bool(row.get("no_network_used", 1)),
            no_filesystem_written=bool(row.get("no_filesystem_written", 1)),
            no_secrets_read=bool(row.get("no_secrets_read", 1)),
            no_subprocess_used=bool(row.get("no_subprocess_used", 1)),
            created_at=_sdt(row.get("created_at")),
            updated_at=_sdt(row.get("updated_at")),
            metadata=json.loads(row.get("metadata_json", "{}"))
        )

    @staticmethod
    def _row_to_requirement(row):
        return TrustedFixtureIsolationRequirement(
            requirement_id=row["requirement_id"], tenant_id=row.get("tenant_id"),
            requirement_type=row["requirement_type"],
            status=row.get("status", "not_checked_runtime_disabled"),
            name=row.get("name", ""), description=row.get("description", ""),
            evidence_refs=json.loads(row.get("evidence_refs_json", "[]")),
            blockers=json.loads(row.get("blockers_json", "[]")),
            warnings=json.loads(row.get("warnings_json", "[]")),
            required_before_isolated_fixture=bool(row.get("required_before_isolated_fixture", 1)),
            required_before_third_party_execution=bool(row.get("required_before_third_party_execution", 1)),
            created_at=_sdt(row.get("created_at")),
            metadata=json.loads(row.get("metadata_json", "{}"))
        )

    @staticmethod
    def _row_to_plan(row):
        return TrustedFixtureIsolationPlan(
            plan_id=row["plan_id"], request_id=row["request_id"],
            tenant_id=row.get("tenant_id"), policy_id=row.get("policy_id"),
            fixture_id=row.get("fixture_id"),
            isolation_requirements=json.loads(row.get("isolation_requirements_json", "[]")),
            satisfied_requirements=json.loads(row.get("satisfied_requirements_json", "[]")),
            missing_requirements=json.loads(row.get("missing_requirements_json", "[]")),
            blocker_summary=row.get("blocker_summary", ""),
            plan_status=row.get("plan_status", "plan_reserved_metadata_only"),
            decision=row.get("decision", "metadata_plan_reserved"),
            ready_for_step26g=bool(row.get("ready_for_step26g", 0)),
            isolated_runtime_enabled=bool(row.get("isolated_runtime_enabled", 0)),
            container_start_allowed=bool(row.get("container_start_allowed", 0)),
            microvm_start_allowed=bool(row.get("microvm_start_allowed", 0)),
            fixture_execution_allowed=bool(row.get("fixture_execution_allowed", 0)),
            third_party_execution_allowed=bool(row.get("third_party_execution_allowed", 0)),
            package_execution_allowed=bool(row.get("package_execution_allowed", 0)),
            entrypoint_execution_allowed=bool(row.get("entrypoint_execution_allowed", 0)),
            network_allowed=bool(row.get("network_allowed", 0)),
            filesystem_write_allowed=bool(row.get("filesystem_write_allowed", 0)),
            secrets_allowed=bool(row.get("secrets_allowed", 0)),
            subprocess_allowed=bool(row.get("subprocess_allowed", 0)),
            metadata_only=bool(row.get("metadata_only", 1)),
            created_at=_sdt(row.get("created_at")),
            updated_at=_sdt(row.get("updated_at")),
            metadata=json.loads(row.get("metadata_json", "{}"))
        )

    @staticmethod
    def _row_to_gate(row):
        return TrustedFixtureIsolationGateResult(
            gate_result_id=row["gate_result_id"], request_id=row["request_id"],
            tenant_id=row.get("tenant_id"),
            status=row.get("status", "disabled_by_default"),
            decision=row.get("decision", "blocked_disabled"),
            checks=json.loads(row.get("checks_json", "[]")),
            satisfied_count=int(row.get("satisfied_count", 0)),
            missing_count=int(row.get("missing_count", 0)),
            blockers_count=int(row.get("blockers_count", 0)),
            warnings_count=int(row.get("warnings_count", 0)),
            ready_for_step26g=bool(row.get("ready_for_step26g", 0)),
            isolated_runtime_enabled=bool(row.get("isolated_runtime_enabled", 0)),
            container_start_allowed=bool(row.get("container_start_allowed", 0)),
            microvm_start_allowed=bool(row.get("microvm_start_allowed", 0)),
            fixture_execution_allowed=bool(row.get("fixture_execution_allowed", 0)),
            third_party_execution_allowed=bool(row.get("third_party_execution_allowed", 0)),
            package_execution_allowed=bool(row.get("package_execution_allowed", 0)),
            execution_allowed=bool(row.get("execution_allowed", 0)),
            metadata_only=bool(row.get("metadata_only", 1)),
            created_at=_sdt(row.get("created_at")),
            metadata=json.loads(row.get("metadata_json", "{}"))
        )

    @staticmethod
    def _row_to_ae(row):
        return TrustedFixtureIsolationAuditEvent(
            event_id=row["event_id"], tenant_id=row.get("tenant_id"),
            request_id=row.get("request_id"), plan_id=row.get("plan_id"),
            policy_id=row.get("policy_id"), requirement_id=row.get("requirement_id"),
            event_type=row.get("event_type", ""),
            severity=row.get("severity", "info"),
            actor_id=row.get("actor_id"), message=row.get("message", ""),
            created_at=_sdt(row.get("created_at")),
            metadata=json.loads(row.get("metadata_json", "{}"))
        )


def _sdt(raw, none_ok=False):
    if not raw: return None if none_ok else datetime.now(timezone.utc)
    try: return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except Exception: return None if none_ok else datetime.now(timezone.utc)
