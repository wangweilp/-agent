"""SQLite Runtime Capability Store — metadata registry, no runtime, no container, no execution."""
from __future__ import annotations
import json, logging
from datetime import datetime, timezone
from src.adapters.config import Settings
from src.adapters.sqlite_connection import create_sqlite_db, execute_with_retry
from src.open_platform.runtime_capability import *

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runtime_capabilities (
    capability_id TEXT PRIMARY KEY, name TEXT NOT NULL, category TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'blocked', description TEXT NOT NULL DEFAULT '',
    reason TEXT NOT NULL DEFAULT '',
    execution_allowed INTEGER NOT NULL DEFAULT 0, fixture_execution_allowed INTEGER NOT NULL DEFAULT 0,
    runtime_enabled INTEGER NOT NULL DEFAULT 0, metadata_only INTEGER NOT NULL DEFAULT 1,
    source_policy TEXT NOT NULL DEFAULT '', source_step TEXT NOT NULL DEFAULT '',
    requires_additional_gate INTEGER NOT NULL DEFAULT 0, required_gate TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')), updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_rtcap_category ON runtime_capabilities(category);
CREATE INDEX IF NOT EXISTS idx_rtcap_status ON runtime_capabilities(status);
"""

def _placeholders(count: int) -> str: return ",".join(["?"] * count)
def _jd(obj): return json.dumps(obj, ensure_ascii=False)
def _now(): return datetime.now(timezone.utc).isoformat()


class SQLiteRuntimeCapabilityStore:
    def __init__(self, config: Settings, db_path: str | None = None):
        path = db_path or config.sqlite_db_path
        self._db = create_sqlite_db(path)
        execute_with_retry(lambda: self._init_schema(), label="rtcap_init")

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

    def create_capability(self, cap):
        _cols = ("capability_id,name,category,status,description,reason,"
                 "execution_allowed,fixture_execution_allowed,runtime_enabled,metadata_only,"
                 "source_policy,source_step,requires_additional_gate,required_gate,"
                 "created_at,updated_at,metadata_json")
        _vals = [cap.capability_id, cap.name, cap.category, cap.status,
                 cap.description, cap.reason,
                 int(cap.execution_allowed), int(cap.fixture_execution_allowed),
                 int(cap.runtime_enabled), int(cap.metadata_only),
                 cap.source_policy, cap.source_step,
                 int(cap.requires_additional_gate), cap.required_gate,
                 cap.created_at.isoformat() if cap.created_at else _now(),
                 cap.updated_at.isoformat() if cap.updated_at else _now(),
                 _jd(cap.metadata)]
        self._exec(f"INSERT INTO runtime_capabilities ({_cols}) VALUES ({_placeholders(len(_vals))})", _vals)
        return cap

    def get_capability(self, capability_id):
        row = next(self._exec("SELECT * FROM runtime_capabilities WHERE capability_id=?", [capability_id]), None)
        return self._row_to_cap(dict(row)) if row else None

    def list_capabilities(self, *, category="", status=""):
        sql, p = "SELECT * FROM runtime_capabilities WHERE 1=1", []
        if category: sql += " AND category=?"; p.append(category)
        if status: sql += " AND status=?"; p.append(status)
        return [self._row_to_cap(dict(r)) for r in self._exec(sql + " ORDER BY category, name", p)]

    def update_capability(self, cap):
        cap.updated_at = datetime.now(timezone.utc)
        self._exec("UPDATE runtime_capabilities SET status=?,reason=?,updated_at=?,metadata_json=? WHERE capability_id=?",
                   [cap.status, cap.reason, cap.updated_at.isoformat(), _jd(cap.metadata), cap.capability_id])
        return cap

    def export_matrix(self) -> dict[str, Any]:
        caps = self.list_capabilities()
        return {
            "total": len(caps),
            "by_category": {
                cat.value: [c.to_dict() for c in caps if c.category == cat.value]
                for cat in CapabilityCategory if any(c.category == cat.value for c in caps)
            },
            "by_status": {
                st.value: [c.to_dict() for c in caps if c.status == st.value]
                for st in CapabilityStatus if any(c.status == st.value for c in caps)
            },
            "summary": {
                "execution_allowed_any": any(c.execution_allowed for c in caps),
                "runtime_enabled_any": any(c.runtime_enabled for c in caps),
                "metadata_only_all": all(c.metadata_only for c in caps),
            },
            "exported_at": _now()
        }

    def seed_default_capabilities(self):
        """Idempotent: only inserts if table is empty."""
        if len(self.list_capabilities()) > 0: return
        for cap in build_default_capability_matrix():
            self.create_capability(cap)
        self.flush()

    @staticmethod
    def _row_to_cap(row):
        return RuntimeCapability(
            capability_id=row["capability_id"], name=row.get("name", ""),
            category=row.get("category", ""), status=row.get("status", "blocked"),
            description=row.get("description", ""), reason=row.get("reason", ""),
            execution_allowed=bool(row.get("execution_allowed", 0)),
            fixture_execution_allowed=bool(row.get("fixture_execution_allowed", 0)),
            runtime_enabled=bool(row.get("runtime_enabled", 0)),
            metadata_only=bool(row.get("metadata_only", 1)),
            source_policy=row.get("source_policy", ""),
            source_step=row.get("source_step", ""),
            requires_additional_gate=bool(row.get("requires_additional_gate", 0)),
            required_gate=row.get("required_gate", ""),
            created_at=_sdt(row.get("created_at")),
            updated_at=_sdt(row.get("updated_at")),
            metadata=json.loads(row.get("metadata_json", "{}"))
        )

def _sdt(raw, none_ok=False):
    if not raw: return None if none_ok else datetime.now(timezone.utc)
    try: return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except Exception: return None if none_ok else datetime.now(timezone.utc)
