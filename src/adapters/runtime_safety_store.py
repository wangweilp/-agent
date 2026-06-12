"""SQLite Runtime Safety Store — metadata-only kill switch + incident records."""
from __future__ import annotations
import json, logging
from datetime import datetime, timezone
from typing import Any
from src.adapters.config import Settings
from src.adapters.sqlite_connection import create_sqlite_db, execute_with_retry
from src.open_platform.runtime_kill_switch import *

logger = logging.getLogger(__name__)
_SCHEMA = """
CREATE TABLE IF NOT EXISTS runtime_kill_switch_policies (
    policy_id TEXT PRIMARY KEY, tenant_id TEXT, scope TEXT NOT NULL DEFAULT 'global_runtime',
    policy_name TEXT NOT NULL DEFAULT '', enabled_metadata_only INTEGER NOT NULL DEFAULT 1,
    auto_trigger_on_critical_incident INTEGER NOT NULL DEFAULT 1,
    auto_trigger_on_test_regression INTEGER NOT NULL DEFAULT 1,
    auto_trigger_on_startup_violation INTEGER NOT NULL DEFAULT 1,
    auto_trigger_on_claim_violation INTEGER NOT NULL DEFAULT 1,
    requires_admin_release INTEGER NOT NULL DEFAULT 1,
    blocks_future_runtime_admission INTEGER NOT NULL DEFAULT 1,
    blocks_future_worker_dispatch INTEGER NOT NULL DEFAULT 1,
    blocks_future_package_execution INTEGER NOT NULL DEFAULT 1,
    blocks_future_third_party_execution INTEGER NOT NULL DEFAULT 1,
    runtime_kill_implemented INTEGER NOT NULL DEFAULT 0, process_kill_implemented INTEGER NOT NULL DEFAULT 0,
    worker_kill_implemented INTEGER NOT NULL DEFAULT 0, container_stop_implemented INTEGER NOT NULL DEFAULT 0,
    microvm_stop_implemented INTEGER NOT NULL DEFAULT 0,
    created_by TEXT, created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')), metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_rkspol_tenant ON runtime_kill_switch_policies(tenant_id);
CREATE INDEX IF NOT EXISTS idx_rkspol_scope ON runtime_kill_switch_policies(scope);

CREATE TABLE IF NOT EXISTS runtime_kill_switch_triggers (
    trigger_id TEXT PRIMARY KEY, policy_id TEXT NOT NULL, tenant_id TEXT,
    scope TEXT NOT NULL DEFAULT 'global_runtime', status TEXT NOT NULL DEFAULT 'draft',
    decision TEXT NOT NULL DEFAULT 'blocked', reason TEXT NOT NULL DEFAULT '', incident_id TEXT,
    triggered_by TEXT, released_by TEXT, triggered_at TEXT, released_at TEXT,
    no_process_killed INTEGER NOT NULL DEFAULT 1, no_runtime_terminated INTEGER NOT NULL DEFAULT 1,
    no_worker_stopped INTEGER NOT NULL DEFAULT 1, no_container_stopped INTEGER NOT NULL DEFAULT 1,
    no_microvm_stopped INTEGER NOT NULL DEFAULT 1, no_execution_performed INTEGER NOT NULL DEFAULT 1,
    no_dispatch_performed INTEGER NOT NULL DEFAULT 1, no_queue_modified INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')), updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_rkstrg_policy ON runtime_kill_switch_triggers(policy_id);
CREATE INDEX IF NOT EXISTS idx_rkstrg_tenant ON runtime_kill_switch_triggers(tenant_id);
CREATE INDEX IF NOT EXISTS idx_rkstrg_status ON runtime_kill_switch_triggers(status);
CREATE INDEX IF NOT EXISTS idx_rkstrg_created ON runtime_kill_switch_triggers(created_at);

CREATE TABLE IF NOT EXISTS runtime_incidents (
    incident_id TEXT PRIMARY KEY, tenant_id TEXT, incident_type TEXT NOT NULL DEFAULT '',
    severity TEXT NOT NULL DEFAULT 'medium', status TEXT NOT NULL DEFAULT 'open',
    decision TEXT NOT NULL DEFAULT 'triage_required', title TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '', source_component TEXT,
    related_execution_id TEXT, related_queue_record_id TEXT, related_gate_request_id TEXT,
    related_package_request_id TEXT, related_fixture_request_id TEXT,
    detected_by TEXT, triaged_by TEXT, closed_by TEXT, kill_switch_trigger_id TEXT,
    evidence_refs_json TEXT NOT NULL DEFAULT '[]', blockers_json TEXT NOT NULL DEFAULT '[]',
    remediation_notes_json TEXT NOT NULL DEFAULT '[]',
    no_runtime_killed INTEGER NOT NULL DEFAULT 1, no_process_killed INTEGER NOT NULL DEFAULT 1,
    no_worker_stopped INTEGER NOT NULL DEFAULT 1, no_execution_performed INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')), updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    triaged_at TEXT, closed_at TEXT, metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_rinc_tenant ON runtime_incidents(tenant_id);
CREATE INDEX IF NOT EXISTS idx_rinc_type ON runtime_incidents(incident_type);
CREATE INDEX IF NOT EXISTS idx_rinc_severity ON runtime_incidents(severity);
CREATE INDEX IF NOT EXISTS idx_rinc_status ON runtime_incidents(status);
CREATE INDEX IF NOT EXISTS idx_rinc_decision ON runtime_incidents(decision);
CREATE INDEX IF NOT EXISTS idx_rinc_created ON runtime_incidents(created_at);

CREATE TABLE IF NOT EXISTS runtime_safety_audit_events (
    event_id TEXT PRIMARY KEY, tenant_id TEXT, incident_id TEXT, trigger_id TEXT, policy_id TEXT,
    event_type TEXT NOT NULL, severity TEXT NOT NULL DEFAULT 'info',
    actor_id TEXT, message TEXT NOT NULL DEFAULT '', metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_rsaevt_incident ON runtime_safety_audit_events(incident_id);
CREATE INDEX IF NOT EXISTS idx_rsaevt_trigger ON runtime_safety_audit_events(trigger_id);
CREATE INDEX IF NOT EXISTS idx_rsaevt_policy ON runtime_safety_audit_events(policy_id);
CREATE INDEX IF NOT EXISTS idx_rsaevt_type ON runtime_safety_audit_events(event_type);
CREATE INDEX IF NOT EXISTS idx_rsaevt_created ON runtime_safety_audit_events(created_at);
"""
def _placeholders(count: int) -> str:
    return ",".join(["?"] * count)

def _jd(obj): return json.dumps(obj, ensure_ascii=False)

class SQLiteRuntimeSafetyStore:
    def __init__(self, config: Settings, db_path: str | None = None):
        path = db_path or config.sqlite_db_path; self._db = create_sqlite_db(path)
        execute_with_retry(lambda: self._init_schema(), label="rtsafety_init")

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

    def _audit(self, incident_id=None, trigger_id=None, policy_id=None, tenant_id=None, event_type="", actor=None, msg=""):
        self.add_audit_event(RuntimeSafetyAuditEvent(incident_id=incident_id, trigger_id=trigger_id,
            policy_id=policy_id, tenant_id=tenant_id, event_type=event_type, actor_id=actor, message=msg))

    # ── Policy ──
    def create_policy(self, p):
        _cols = "policy_id,tenant_id,scope,policy_name,enabled_metadata_only,auto_trigger_on_critical_incident,auto_trigger_on_test_regression,auto_trigger_on_startup_violation,auto_trigger_on_claim_violation,requires_admin_release,blocks_future_runtime_admission,blocks_future_worker_dispatch,blocks_future_package_execution,blocks_future_third_party_execution,runtime_kill_implemented,process_kill_implemented,worker_kill_implemented,container_stop_implemented,microvm_stop_implemented,created_by,created_at,updated_at,metadata_json"
        _vals = [p.policy_id,p.tenant_id,p.scope,p.policy_name,int(p.enabled_metadata_only),int(p.auto_trigger_on_critical_incident),int(p.auto_trigger_on_test_regression),int(p.auto_trigger_on_startup_violation),int(p.auto_trigger_on_claim_violation),int(p.requires_admin_release),int(p.blocks_future_runtime_admission),int(p.blocks_future_worker_dispatch),int(p.blocks_future_package_execution),int(p.blocks_future_third_party_execution),int(p.runtime_kill_implemented),int(p.process_kill_implemented),int(p.worker_kill_implemented),int(p.container_stop_implemented),int(p.microvm_stop_implemented),p.created_by,p.created_at.isoformat() if p.created_at else _now(),p.updated_at.isoformat() if p.updated_at else _now(),_jd(p.metadata)]
        self._exec(f"INSERT INTO runtime_kill_switch_policies ({_cols}) VALUES ({_placeholders(len(_vals))})", _vals)
        self._audit(policy_id=p.policy_id,tenant_id=p.tenant_id,event_type=RuntimeSafetyAuditEventType.KILL_SWITCH_POLICY_CREATED,actor=p.created_by,msg="Policy created.")
        return p

    def get_policy(self, pid):
        row = next(self._exec("SELECT * FROM runtime_kill_switch_policies WHERE policy_id=?",[pid]),None)
        return self._row_to_policy(dict(row)) if row else None

    def list_policies(self, *, tenant_id="", scope=""):
        sql,p = "SELECT * FROM runtime_kill_switch_policies WHERE 1=1",[]
        if tenant_id: sql+=" AND tenant_id=?"; p.append(tenant_id)
        if scope: sql+=" AND scope=?"; p.append(scope)
        return [self._row_to_policy(dict(r)) for r in self._exec(sql+" ORDER BY created_at DESC",p)]

    def update_policy(self, pol):
        pol.updated_at=datetime.now(timezone.utc)
        self._exec("""UPDATE runtime_kill_switch_policies SET
            policy_name=?,scope=?,enabled_metadata_only=?,auto_trigger_on_critical_incident=?,
            auto_trigger_on_test_regression=?,auto_trigger_on_startup_violation=?,
            auto_trigger_on_claim_violation=?,requires_admin_release=?,
            blocks_future_runtime_admission=?,blocks_future_worker_dispatch=?,blocks_future_package_execution=?,
            blocks_future_third_party_execution=?,updated_at=?,metadata_json=? WHERE policy_id=?""",
            [pol.policy_name,pol.scope,int(pol.enabled_metadata_only),int(pol.auto_trigger_on_critical_incident),
             int(pol.auto_trigger_on_test_regression),int(pol.auto_trigger_on_startup_violation),
             int(pol.auto_trigger_on_claim_violation),int(pol.requires_admin_release),
             int(pol.blocks_future_runtime_admission),int(pol.blocks_future_worker_dispatch),
             int(pol.blocks_future_package_execution),int(pol.blocks_future_third_party_execution),
             pol.updated_at.isoformat(),_jd(pol.metadata),pol.policy_id])
        return pol

    # ── Trigger ──
    def create_trigger(self, tr):
        _cols = "trigger_id,policy_id,tenant_id,scope,status,decision,reason,incident_id,triggered_by,released_by,triggered_at,released_at,no_process_killed,no_runtime_terminated,no_worker_stopped,no_container_stopped,no_microvm_stopped,no_execution_performed,no_dispatch_performed,no_queue_modified,created_at,updated_at,metadata_json"
        _vals = [tr.trigger_id,tr.policy_id,tr.tenant_id,tr.scope,tr.status,tr.decision,tr.reason,tr.incident_id,tr.triggered_by,tr.released_by,tr.triggered_at.isoformat() if tr.triggered_at else _now(),
            tr.released_at.isoformat() if tr.released_at else None,int(tr.no_process_killed),int(tr.no_runtime_terminated),int(tr.no_worker_stopped),int(tr.no_container_stopped),int(tr.no_microvm_stopped),
            int(tr.no_execution_performed),int(tr.no_dispatch_performed),int(tr.no_queue_modified),
            tr.created_at.isoformat() if tr.created_at else _now(),tr.updated_at.isoformat() if tr.updated_at else _now(),_jd(tr.metadata)]
        self._exec(f"INSERT INTO runtime_kill_switch_triggers ({_cols}) VALUES ({_placeholders(len(_vals))})", _vals)
        self._audit(trigger_id=tr.trigger_id,policy_id=tr.policy_id,tenant_id=tr.tenant_id,
                    event_type=RuntimeSafetyAuditEventType.KILL_SWITCH_TRIGGERED_METADATA_ONLY,actor=tr.triggered_by,msg="Trigger set metadata-only.")
        return tr

    def get_trigger(self, tid):
        row = next(self._exec("SELECT * FROM runtime_kill_switch_triggers WHERE trigger_id=?",[tid]),None)
        return self._row_to_trigger(dict(row)) if row else None

    def get_latest_trigger(self, pid):
        row = next(self._exec("SELECT * FROM runtime_kill_switch_triggers WHERE policy_id=? ORDER BY created_at DESC LIMIT 1",[pid]),None)
        return self._row_to_trigger(dict(row)) if row else None

    def release_trigger(self, tid, actor_id=None, reason=None):
        t = self.get_trigger(tid)
        if t is None: raise RuntimeKillSwitchPolicyNotFoundError(f"Not found: {tid}")
        t.status=RuntimeKillSwitchStatus.RELEASED_METADATA_ONLY; t.decision=RuntimeKillSwitchDecision.METADATA_RELEASE_ALLOWED
        t.released_by=actor_id; t.released_at=datetime.now(timezone.utc); t.updated_at=datetime.now(timezone.utc)
        self._exec("UPDATE runtime_kill_switch_triggers SET status=?,decision=?,released_by=?,released_at=?,updated_at=?,metadata_json=? WHERE trigger_id=?",
            [t.status,t.decision,t.released_by,t.released_at.isoformat(),t.updated_at.isoformat(),_jd(t.metadata),t.trigger_id])
        self._audit(trigger_id=t.trigger_id,policy_id=t.policy_id,tenant_id=t.tenant_id,
                    event_type=RuntimeSafetyAuditEventType.KILL_SWITCH_RELEASED_METADATA_ONLY,actor=actor_id,msg="Trigger released metadata-only.")
        return t

    # ── Incident ──
    def create_incident(self, inc):
        _cols = "incident_id,tenant_id,incident_type,severity,status,decision,title,description,source_component,related_execution_id,related_queue_record_id,related_gate_request_id,related_package_request_id,related_fixture_request_id,detected_by,triaged_by,closed_by,kill_switch_trigger_id,evidence_refs_json,blockers_json,remediation_notes_json,no_runtime_killed,no_process_killed,no_worker_stopped,no_execution_performed,created_at,updated_at,triaged_at,closed_at,metadata_json"
        _vals = [inc.incident_id,inc.tenant_id,inc.incident_type,inc.severity,inc.status,inc.decision,inc.title,inc.description,inc.source_component,inc.related_execution_id,inc.related_queue_record_id,inc.related_gate_request_id,inc.related_package_request_id,inc.related_fixture_request_id,inc.detected_by,inc.triaged_by,
            inc.closed_by,inc.kill_switch_trigger_id,_jd(inc.evidence_refs),_jd(inc.blockers),_jd(inc.remediation_notes),
            int(inc.no_runtime_killed),int(inc.no_process_killed),int(inc.no_worker_stopped),int(inc.no_execution_performed),
            inc.created_at.isoformat() if inc.created_at else _now(),inc.updated_at.isoformat() if inc.updated_at else _now(),
            inc.triaged_at.isoformat() if inc.triaged_at else None,inc.closed_at.isoformat() if inc.closed_at else None,_jd(inc.metadata)]
        self._exec(f"INSERT INTO runtime_incidents ({_cols}) VALUES ({_placeholders(len(_vals))})", _vals)
        self._audit(incident_id=inc.incident_id,tenant_id=inc.tenant_id,event_type=RuntimeSafetyAuditEventType.INCIDENT_CREATED,actor=inc.detected_by,msg="Incident created.")
        return inc

    def get_incident(self, iid):
        row = next(self._exec("SELECT * FROM runtime_incidents WHERE incident_id=?",[iid]),None)
        return self._row_to_incident(dict(row)) if row else None

    def list_incidents(self, *, tenant_id="", incident_type="", severity="", status="", decision=""):
        sql,p = "SELECT * FROM runtime_incidents WHERE 1=1",[]
        if tenant_id: sql+=" AND tenant_id=?"; p.append(tenant_id)
        if incident_type: sql+=" AND incident_type=?"; p.append(incident_type)
        if severity: sql+=" AND severity=?"; p.append(severity)
        if status: sql+=" AND status=?"; p.append(status)
        if decision: sql+=" AND decision=?"; p.append(decision)
        return [self._row_to_incident(dict(r)) for r in self._exec(sql+" ORDER BY created_at DESC",p)]

    def update_incident(self, inc):
        inc.updated_at=datetime.now(timezone.utc)
        self._exec("""UPDATE runtime_incidents SET
            severity=?,status=?,decision=?,title=?,description=?,triaged_by=?,closed_by=?,
            kill_switch_trigger_id=?,evidence_refs_json=?,blockers_json=?,remediation_notes_json=?,
            updated_at=?,triaged_at=?,closed_at=?,metadata_json=? WHERE incident_id=?""",
            [inc.severity,inc.status,inc.decision,inc.title,inc.description,inc.triaged_by,inc.closed_by,
             inc.kill_switch_trigger_id,_jd(inc.evidence_refs),_jd(inc.blockers),_jd(inc.remediation_notes),
             inc.updated_at.isoformat(),inc.triaged_at.isoformat() if inc.triaged_at else None,
             inc.closed_at.isoformat() if inc.closed_at else None,_jd(inc.metadata),inc.incident_id])
        return inc

    def set_incident_status(self, iid, st, actor=None, reason=None):
        inc = self.get_incident(iid)
        if inc is None: raise RuntimeIncidentNotFoundError(f"Not found: {iid}")
        old=inc.status; inc.status=st; self.update_incident(inc)
        self._audit(incident_id=iid,tenant_id=inc.tenant_id,event_type=RuntimeSafetyAuditEventType.INCIDENT_STATUS_CHANGED,actor=actor,msg=f"Status: {old} -> {st}")
        return inc

    def set_incident_decision(self, iid, d, actor=None, reason=None):
        inc = self.get_incident(iid)
        if inc is None: raise RuntimeIncidentNotFoundError(f"Not found: {iid}")
        old=inc.decision; inc.decision=d; self.update_incident(inc)
        self._audit(incident_id=iid,tenant_id=inc.tenant_id,event_type=RuntimeSafetyAuditEventType.INCIDENT_DECISION_CHANGED,actor=actor,msg=f"Decision: {old} -> {d}")
        return inc

    def triage_incident(self, iid, actor=None, notes=None):
        inc = self.get_incident(iid)
        if inc is None: raise RuntimeIncidentNotFoundError(f"Not found: {iid}")
        inc.status=RuntimeIncidentStatus.TRIAGED; inc.triaged_by=actor; inc.triaged_at=datetime.now(timezone.utc)
        if notes: inc.remediation_notes = list(inc.remediation_notes) + [notes]
        self.update_incident(inc)
        self._audit(incident_id=iid,tenant_id=inc.tenant_id,event_type=RuntimeSafetyAuditEventType.INCIDENT_TRIAGED,actor=actor,msg="Incident triaged.")
        return inc

    def close_incident_metadata_only(self, iid, actor=None, notes=None):
        inc = self.get_incident(iid)
        if inc is None: raise RuntimeIncidentNotFoundError(f"Not found: {iid}")
        inc.status=RuntimeIncidentStatus.CLOSED_METADATA_ONLY; inc.closed_by=actor; inc.closed_at=datetime.now(timezone.utc)
        if notes: inc.remediation_notes = list(inc.remediation_notes) + [notes]
        self.update_incident(inc)
        self._audit(incident_id=iid,tenant_id=inc.tenant_id,event_type=RuntimeSafetyAuditEventType.INCIDENT_CLOSED_METADATA_ONLY,actor=actor,msg="Incident closed metadata-only.")
        return inc

    def add_audit_event(self, evt):
        self._exec("INSERT INTO runtime_safety_audit_events (event_id,tenant_id,incident_id,trigger_id,policy_id,event_type,severity,actor_id,message,metadata_json,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            [evt.event_id,evt.tenant_id,evt.incident_id,evt.trigger_id,evt.policy_id,evt.event_type,evt.severity,evt.actor_id,evt.message,_jd(evt.metadata),evt.created_at.isoformat() if evt.created_at else _now()])
        return evt

    def list_audit_events(self, *, incident_id="", trigger_id="", policy_id=""):
        sql,p = "SELECT * FROM runtime_safety_audit_events WHERE 1=1",[]
        if incident_id: sql+=" AND incident_id=?"; p.append(incident_id)
        if trigger_id: sql+=" AND trigger_id=?"; p.append(trigger_id)
        if policy_id: sql+=" AND policy_id=?"; p.append(policy_id)
        return [self._row_to_ae(dict(r)) for r in self._exec(sql+" ORDER BY created_at ASC",p)]

    def count_incidents(self, *, tenant_id="", severity="", status="", decision=""):
        sql,p = "SELECT COUNT(*) as cnt FROM runtime_incidents WHERE 1=1",[]
        if tenant_id: sql+=" AND tenant_id=?"; p.append(tenant_id)
        if severity: sql+=" AND severity=?"; p.append(severity)
        if status: sql+=" AND status=?"; p.append(status)
        if decision: sql+=" AND decision=?"; p.append(decision)
        row=next(self._exec(sql,p),None); return row["cnt"] if row else 0

    @staticmethod
    def _row_to_policy(row): return RuntimeKillSwitchPolicy(
        policy_id=row["policy_id"],tenant_id=row.get("tenant_id"),scope=row.get("scope","global_runtime"),policy_name=row.get("policy_name",""),enabled_metadata_only=bool(row.get("enabled_metadata_only",1)),auto_trigger_on_critical_incident=bool(row.get("auto_trigger_on_critical_incident",1)),auto_trigger_on_test_regression=bool(row.get("auto_trigger_on_test_regression",1)),auto_trigger_on_startup_violation=bool(row.get("auto_trigger_on_startup_violation",1)),auto_trigger_on_claim_violation=bool(row.get("auto_trigger_on_claim_violation",1)),requires_admin_release=bool(row.get("requires_admin_release",1)),blocks_future_runtime_admission=bool(row.get("blocks_future_runtime_admission",1)),blocks_future_worker_dispatch=bool(row.get("blocks_future_worker_dispatch",1)),blocks_future_package_execution=bool(row.get("blocks_future_package_execution",1)),blocks_future_third_party_execution=bool(row.get("blocks_future_third_party_execution",1)),runtime_kill_implemented=bool(row.get("runtime_kill_implemented",0)),process_kill_implemented=bool(row.get("process_kill_implemented",0)),worker_kill_implemented=bool(row.get("worker_kill_implemented",0)),container_stop_implemented=bool(row.get("container_stop_implemented",0)),microvm_stop_implemented=bool(row.get("microvm_stop_implemented",0)),created_by=row.get("created_by"),created_at=_sdt(row.get("created_at")),updated_at=_sdt(row.get("updated_at")),metadata=json.loads(row.get("metadata_json","{}")))

    @staticmethod
    def _row_to_trigger(row): return RuntimeKillSwitchTrigger(
        trigger_id=row["trigger_id"],policy_id=row["policy_id"],tenant_id=row.get("tenant_id"),scope=row.get("scope","global_runtime"),status=row.get("status","draft"),decision=row.get("decision","blocked"),reason=row.get("reason",""),incident_id=row.get("incident_id"),triggered_by=row.get("triggered_by"),released_by=row.get("released_by"),triggered_at=_sdt(row.get("triggered_at"),True),released_at=_sdt(row.get("released_at"),True),no_process_killed=bool(row.get("no_process_killed",1)),no_runtime_terminated=bool(row.get("no_runtime_terminated",1)),no_worker_stopped=bool(row.get("no_worker_stopped",1)),no_container_stopped=bool(row.get("no_container_stopped",1)),no_microvm_stopped=bool(row.get("no_microvm_stopped",1)),no_execution_performed=bool(row.get("no_execution_performed",1)),no_dispatch_performed=bool(row.get("no_dispatch_performed",1)),no_queue_modified=bool(row.get("no_queue_modified",1)),created_at=_sdt(row.get("created_at")),updated_at=_sdt(row.get("updated_at")),metadata=json.loads(row.get("metadata_json","{}")))

    @staticmethod
    def _row_to_incident(row): return RuntimeIncidentRecord(
        incident_id=row["incident_id"],tenant_id=row.get("tenant_id"),incident_type=row.get("incident_type",""),severity=row.get("severity","medium"),status=row.get("status","open"),decision=row.get("decision","triage_required"),title=row.get("title",""),description=row.get("description",""),source_component=row.get("source_component"),related_execution_id=row.get("related_execution_id"),related_queue_record_id=row.get("related_queue_record_id"),related_gate_request_id=row.get("related_gate_request_id"),related_package_request_id=row.get("related_package_request_id"),related_fixture_request_id=row.get("related_fixture_request_id"),detected_by=row.get("detected_by"),triaged_by=row.get("triaged_by"),closed_by=row.get("closed_by"),kill_switch_trigger_id=row.get("kill_switch_trigger_id"),evidence_refs=json.loads(row.get("evidence_refs_json","[]")),blockers=json.loads(row.get("blockers_json","[]")),remediation_notes=json.loads(row.get("remediation_notes_json","[]")),no_runtime_killed=bool(row.get("no_runtime_killed",1)),no_process_killed=bool(row.get("no_process_killed",1)),no_worker_stopped=bool(row.get("no_worker_stopped",1)),no_execution_performed=bool(row.get("no_execution_performed",1)),created_at=_sdt(row.get("created_at")),updated_at=_sdt(row.get("updated_at")),triaged_at=_sdt(row.get("triaged_at"),True),closed_at=_sdt(row.get("closed_at"),True),metadata=json.loads(row.get("metadata_json","{}")))

    @staticmethod
    def _row_to_ae(row): return RuntimeSafetyAuditEvent(event_id=row["event_id"],tenant_id=row.get("tenant_id"),incident_id=row.get("incident_id"),trigger_id=row.get("trigger_id"),policy_id=row.get("policy_id"),event_type=row.get("event_type",""),severity=row.get("severity","info"),actor_id=row.get("actor_id"),message=row.get("message",""),metadata=json.loads(row.get("metadata_json","{}")),created_at=_sdt(row.get("created_at")))

def _sdt(raw, none_ok=False):
    if not raw: return None if none_ok else datetime.now(timezone.utc)
    try: return datetime.fromisoformat(str(raw).replace("Z","+00:00"))
    except: return None if none_ok else datetime.now(timezone.utc)
def _now(): return datetime.now(timezone.utc).isoformat()
