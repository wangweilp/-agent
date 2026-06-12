"""SQLite Policy Decision Store — metadata-only, no execution."""
from __future__ import annotations
import json, logging
from datetime import datetime, timezone
from typing import Any
from src.adapters.config import Settings
from src.adapters.sqlite_connection import create_sqlite_db, execute_with_retry
from src.open_platform.policy_enforcement import *

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS policy_decisions (
    decision_id TEXT PRIMARY KEY, request_id TEXT NOT NULL, request_type TEXT NOT NULL,
    capability_name TEXT NOT NULL DEFAULT '', capability_status TEXT NOT NULL DEFAULT 'blocked',
    allowed INTEGER NOT NULL DEFAULT 0, reason TEXT NOT NULL DEFAULT '',
    source_policy TEXT NOT NULL DEFAULT '', enforcement_type TEXT NOT NULL DEFAULT 'metadata_only',
    execution_allowed INTEGER NOT NULL DEFAULT 0, runtime_enabled INTEGER NOT NULL DEFAULT 0,
    metadata_only INTEGER NOT NULL DEFAULT 1, tenant_id TEXT,
    decided_at TEXT NOT NULL DEFAULT (datetime('now')), metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_poldec_type ON policy_decisions(request_type);
CREATE INDEX IF NOT EXISTS idx_poldec_tenant ON policy_decisions(tenant_id);

CREATE TABLE IF NOT EXISTS policy_enforcement_audit_events (
    event_id TEXT PRIMARY KEY, decision_id TEXT NOT NULL,
    event_type TEXT NOT NULL, tenant_id TEXT,
    message TEXT NOT NULL DEFAULT '', metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_penfevt_decision ON policy_enforcement_audit_events(decision_id);
"""

def _placeholders(count: int) -> str: return ",".join(["?"] * count)
def _jd(obj): return json.dumps(obj, ensure_ascii=False)
def _now(): return datetime.now(timezone.utc).isoformat()


class SQLitePolicyDecisionStore:
    def __init__(self, config: Settings, db_path: str | None = None):
        path = db_path or config.sqlite_db_path
        self._db = create_sqlite_db(path)
        execute_with_retry(lambda: self._init_schema(), label="poldec_init")

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

    def create_decision(self, d):
        _cols = ("decision_id,request_id,request_type,capability_name,capability_status,"
                 "allowed,reason,source_policy,enforcement_type,"
                 "execution_allowed,runtime_enabled,metadata_only,"
                 "tenant_id,decided_at,metadata_json")
        _vals = [d.decision_id, d.request_id, d.request_type, d.capability_name,
                 d.capability_status, int(d.allowed), d.reason, d.source_policy,
                 d.enforcement_type, int(d.execution_allowed), int(d.runtime_enabled),
                 int(d.metadata_only), d.tenant_id,
                 d.decided_at.isoformat() if d.decided_at else _now(),
                 _jd(d.metadata)]
        self._exec(f"INSERT INTO policy_decisions ({_cols}) VALUES ({_placeholders(len(_vals))})", _vals)
        self.add_audit_event(PolicyEnforcementAuditEvent(
            decision_id=d.decision_id, event_type=PolicyEnforcementAuditEventType.DECISION_CREATED,
            tenant_id=d.tenant_id, message=f"Decision: {d.capability_name} = denied"))
        return d

    def get_decision(self, decision_id):
        row = next(self._exec("SELECT * FROM policy_decisions WHERE decision_id=?", [decision_id]), None)
        return PolicyDecision.from_dict(dict(row)) if row else None

    def list_decisions(self, *, request_type=""):
        sql, p = "SELECT * FROM policy_decisions WHERE 1=1", []
        if request_type: sql += " AND request_type=?"; p.append(request_type)
        return [PolicyDecision.from_dict(dict(r)) for r in self._exec(sql + " ORDER BY decided_at DESC", p)]

    def export_decisions(self) -> dict[str, Any]:
        decisions = self.list_decisions()
        return {
            "total": len(decisions),
            "decisions": [d.to_dict() for d in decisions],
            "summary": {"allowed_any": any(d.allowed for d in decisions),
                         "execution_allowed_any": any(d.execution_allowed for d in decisions),
                         "runtime_enabled_any": any(d.runtime_enabled for d in decisions),
                         "all_denied": all(not d.allowed for d in decisions),
                         "metadata_only_all": all(d.metadata_only for d in decisions)},
            "exported_at": _now(),
        }

    def add_audit_event(self, evt):
        self._exec("INSERT INTO policy_enforcement_audit_events (event_id,decision_id,event_type,tenant_id,message,metadata_json,created_at) VALUES (?,?,?,?,?,?,?)",
                   [evt.event_id, evt.decision_id, evt.event_type, evt.tenant_id,
                    evt.message, _jd(evt.metadata),
                    evt.created_at.isoformat() if evt.created_at else _now()])
        return evt

    def list_audit_events(self):
        rows = self._exec("SELECT * FROM policy_enforcement_audit_events ORDER BY created_at ASC")
        return [PolicyEnforcementAuditEvent(
            event_id=r["event_id"], decision_id=r["decision_id"],
            event_type=r["event_type"], tenant_id=r["tenant_id"],
            message=r["message"],
            created_at=_sdt(r["created_at"]),
            metadata=json.loads(r["metadata_json"])) for r in rows]

    def seed_all_rules(self):
        engine = PolicyEnforcementEngine()
        decisions = engine.evaluate_all()
        for d in decisions: self.create_decision(d)
        self.flush()


def _sdt(raw, none_ok=False):
    if not raw: return None if none_ok else datetime.now(timezone.utc)
    try: return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except Exception: return None if none_ok else datetime.now(timezone.utc)
