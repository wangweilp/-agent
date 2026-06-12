"""SQLite Marketplace Governance Store — reviews/reports/trust_scores/governance_events。
metadata_only，不执行任何 runtime/container/microVM 代码。
"""

from __future__ import annotations

import json, logging
from datetime import datetime, timezone
from typing import Any

from src.adapters.config import Settings
from src.adapters.sqlite_connection import create_sqlite_db, execute_with_retry
from src.open_platform.marketplace_governance import (
    Review, ReviewAlreadyExistsError, ReviewNotFoundError, ReviewStatus, ReviewValidationError,
    Report, ReportNotFoundError, ReportStatus, ReportValidationError,
    TrustScore, GovernanceEvent, _safe_dt,
)

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS governance_reviews (
    id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, agent_module_id TEXT NOT NULL,
    rating INTEGER NOT NULL DEFAULT 5, title TEXT NOT NULL DEFAULT '',
    content TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'active',
    created_by TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_grev_unique_active
    ON governance_reviews(workspace_id, agent_module_id) WHERE status='active';
CREATE INDEX IF NOT EXISTS idx_grev_module ON governance_reviews(agent_module_id);

CREATE TABLE IF NOT EXISTS governance_reports (
    id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, agent_module_id TEXT NOT NULL,
    report_type TEXT NOT NULL DEFAULT 'other', title TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'open',
    created_by TEXT NOT NULL DEFAULT '', resolved_by TEXT NOT NULL DEFAULT '',
    resolved_at TEXT, resolution_note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_grep_module ON governance_reports(agent_module_id);
CREATE INDEX IF NOT EXISTS idx_grep_status ON governance_reports(status);

CREATE TABLE IF NOT EXISTS governance_trust_scores (
    agent_module_id TEXT PRIMARY KEY, score REAL NOT NULL DEFAULT 50.0,
    published_days INTEGER NOT NULL DEFAULT 0, review_count INTEGER NOT NULL DEFAULT 0,
    average_rating REAL NOT NULL DEFAULT 0.0, report_count INTEGER NOT NULL DEFAULT 0,
    resolved_report_count INTEGER NOT NULL DEFAULT 0,
    risk_level TEXT NOT NULL DEFAULT 'low',
    calculated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS governance_events (
    id TEXT PRIMARY KEY, agent_module_id TEXT NOT NULL,
    event_type TEXT NOT NULL DEFAULT '', description TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_gevt_module ON governance_events(agent_module_id);
CREATE INDEX IF NOT EXISTS idx_gevt_type ON governance_events(event_type);
"""


class SQLiteMarketplaceGovernanceStore:
    def __init__(self, config: Settings, db_path: str | None = None):
        path = db_path or config.sqlite_db_path
        self._db = create_sqlite_db(path)
        execute_with_retry(lambda: self._init_schema(), label="gv_init_schema")

    def _init_schema(self):
        for stmt in _SCHEMA.strip().split(";"):
            if stmt.strip(): self._db.execute(stmt.strip())
        try: self._db.conn.commit()
        except Exception: pass

    def flush(self):
        try:
            if hasattr(self._db, "conn") and self._db.conn: self._db.conn.commit()
        except Exception: pass

    def _exec(self, sql, params=None): return self._db.execute(sql, params or [])

    # ═══════════════ Review ═══════════════

    def create_review(self, r: Review) -> Review:
        errors = r.validate()
        if errors: raise ReviewValidationError(f"校验失败: {'; '.join(errors)}", errors)
        existing = self._exec(
            "SELECT id FROM governance_reviews WHERE workspace_id=? AND agent_module_id=? AND status='active'",
            [r.workspace_id, r.agent_module_id])
        if next(existing, None):
            raise ReviewAlreadyExistsError(f"workspace {r.workspace_id} 已评价 {r.agent_module_id}")
        self._exec("""INSERT INTO governance_reviews (id, workspace_id, agent_module_id, rating,
            title, content, status, created_by, updated_at) VALUES (?,?,?,?,?,?,?,?,?)""",
            [r.id, r.workspace_id, r.agent_module_id, r.rating, r.title, r.content,
             ReviewStatus.ACTIVE, r.created_by, r.updated_at.isoformat()])
        return r

    def get_review(self, review_id: str) -> Review | None:
        row = next(self._exec("SELECT * FROM governance_reviews WHERE id=?", [review_id]), None)
        return self._row_review(dict(row)) if row else None

    def get_active_review(self, workspace_id: str, agent_module_id: str) -> Review | None:
        row = next(self._exec(
            "SELECT * FROM governance_reviews WHERE workspace_id=? AND agent_module_id=? AND status='active'",
            [workspace_id, agent_module_id]), None)
        return self._row_review(dict(row)) if row else None

    def list_reviews(self, *, agent_module_id="", workspace_id="",
                     limit=50, offset=0) -> list[Review]:
        sql = "SELECT * FROM governance_reviews WHERE status='active'"
        params: list[Any] = []
        if agent_module_id:
            sql += " AND agent_module_id=?"; params.append(agent_module_id)
        if workspace_id:
            sql += " AND workspace_id=?"; params.append(workspace_id)
        sql += f" ORDER BY created_at DESC LIMIT {int(limit)} OFFSET {int(offset)}"
        return [self._row_review(dict(r)) for r in self._exec(sql, params)]

    def update_review(self, r: Review) -> None:
        existing = self.get_review(r.id)
        if existing is None: raise ReviewNotFoundError(f"Review 不存在: {r.id}")
        errors = r.validate()
        if errors: raise ReviewValidationError(f"校验失败: {'; '.join(errors)}", errors)
        self._exec("""UPDATE governance_reviews SET rating=?, title=?, content=?,
            updated_at=? WHERE id=?""", [r.rating, r.title, r.content,
            datetime.now(timezone.utc).isoformat(), r.id])

    def delete_review(self, review_id: str) -> None:
        existing = self.get_review(review_id)
        if existing is None: raise ReviewNotFoundError(f"Review 不存在: {review_id}")
        self._exec("UPDATE governance_reviews SET status=?, updated_at=? WHERE id=?",
                   [ReviewStatus.DELETED, datetime.now(timezone.utc).isoformat(), review_id])

    def get_rating_aggregation(self, agent_module_id: str) -> dict[str, Any]:
        rows = list(self._exec(
            "SELECT rating FROM governance_reviews WHERE agent_module_id=? AND status='active'",
            [agent_module_id]))
        if not rows: return {"average_rating": 0.0, "count": 0, "distribution": {"1": 0, "2": 0, "3": 0, "4": 0, "5": 0}}
        ratings = [dict(r)["rating"] for r in rows]
        dist = {str(x): ratings.count(x) for x in range(1, 6)}
        return {"average_rating": round(sum(ratings) / len(ratings), 2),
                "count": len(ratings), "distribution": {str(k): dist.get(str(k), 0) for k in range(1, 6)}}

    # ═══════════════ Report ═══════════════

    def create_report(self, r: Report) -> Report:
        errors = r.validate()
        if errors: raise ReportValidationError(f"校验失败: {'; '.join(errors)}", errors)
        self._exec("""INSERT INTO governance_reports (id, workspace_id, agent_module_id,
            report_type, title, description, status, created_by)
            VALUES (?,?,?,?,?,?,?,?)""",
            [r.id, r.workspace_id, r.agent_module_id, r.report_type, r.title,
             r.description, ReportStatus.OPEN, r.created_by])
        return r

    def get_report(self, report_id: str) -> Report | None:
        row = next(self._exec("SELECT * FROM governance_reports WHERE id=?", [report_id]), None)
        return self._row_report(dict(row)) if row else None

    def list_reports(self, *, agent_module_id="", status="", limit=50, offset=0) -> list[Report]:
        sql = "SELECT * FROM governance_reports WHERE 1=1"
        params: list[Any] = []
        if agent_module_id: sql += " AND agent_module_id=?"; params.append(agent_module_id)
        if status: sql += " AND status=?"; params.append(status)
        sql += f" ORDER BY created_at DESC LIMIT {int(limit)} OFFSET {int(offset)}"
        return [self._row_report(dict(r)) for r in self._exec(sql, params)]

    def update_report(self, r: Report) -> None:
        if not self.get_report(r.id): raise ReportNotFoundError(f"Report 不存在: {r.id}")
        errors = r.validate()
        if errors: raise ReportValidationError(f"校验失败: {'; '.join(errors)}", errors)
        self._exec("UPDATE governance_reports SET report_type=?, title=?, description=?, status=? WHERE id=?",
                   [r.report_type, r.title, r.description, r.status, r.id])

    def resolve_report(self, report_id: str, status: str, resolved_by: str,
                       resolution_note: str) -> None:
        if not self.get_report(report_id): raise ReportNotFoundError(f"Report 不存在: {report_id}")
        now = datetime.now(timezone.utc).isoformat()
        self._exec("UPDATE governance_reports SET status=?, resolved_by=?, resolved_at=?, resolution_note=? WHERE id=?",
                   [status, resolved_by, now, resolution_note, report_id])

    # ═══════════════ TrustScore ═══════════════

    def upsert_trust_score(self, ts: TrustScore) -> None:
        self._exec("""INSERT INTO governance_trust_scores (agent_module_id, score, published_days,
            review_count, average_rating, report_count, resolved_report_count, risk_level, calculated_at)
            VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(agent_module_id) DO UPDATE SET
            score=excluded.score, published_days=excluded.published_days,
            review_count=excluded.review_count, average_rating=excluded.average_rating,
            report_count=excluded.report_count, resolved_report_count=excluded.resolved_report_count,
            risk_level=excluded.risk_level, calculated_at=excluded.calculated_at""",
            [ts.agent_module_id, ts.score, ts.published_days, ts.review_count,
             ts.average_rating, ts.report_count, ts.resolved_report_count,
             ts.risk_level, ts.calculated_at.isoformat()])

    def get_trust_score(self, agent_module_id: str) -> TrustScore | None:
        row = next(self._exec(
            "SELECT * FROM governance_trust_scores WHERE agent_module_id=?", [agent_module_id]), None)
        return self._row_trust_score(dict(row)) if row else None

    def list_trust_scores(self, *, min_score=0.0, limit=50) -> list[TrustScore]:
        rows = self._exec(
            "SELECT * FROM governance_trust_scores WHERE score>=? ORDER BY score DESC LIMIT ?",
            [min_score, int(limit)])
        return [self._row_trust_score(dict(r)) for r in rows]

    # ═══════════════ GovernanceEvent ═══════════════

    def record_event(self, evt: GovernanceEvent) -> None:
        self._exec("INSERT INTO governance_events (id, agent_module_id, event_type, description, metadata_json) VALUES (?,?,?,?,?)",
                   [evt.id, evt.agent_module_id, evt.event_type, evt.description,
                    json.dumps(evt.metadata, ensure_ascii=False)])

    def get_timeline(self, agent_module_id: str, *, limit=50) -> list[GovernanceEvent]:
        rows = self._exec(
            "SELECT * FROM governance_events WHERE agent_module_id=? ORDER BY created_at DESC LIMIT ?",
            [agent_module_id, int(limit)])
        return [self._row_event(dict(r)) for r in rows]

    # ═══════════════ Row mappers ═══════════════

    @staticmethod
    def _row_review(row: dict) -> Review:
        return Review(id=row["id"], workspace_id=row.get("workspace_id", ""),
            agent_module_id=row.get("agent_module_id", ""), rating=int(row.get("rating", 5)),
            title=row.get("title", ""), content=row.get("content", ""),
            status=row.get("status", "active"), created_by=row.get("created_by", ""),
            created_at=_safe_dt(row.get("created_at")), updated_at=_safe_dt(row.get("updated_at")))

    @staticmethod
    def _row_report(row: dict) -> Report:
        return Report(id=row["id"], workspace_id=row.get("workspace_id", ""),
            agent_module_id=row.get("agent_module_id", ""),
            report_type=row.get("report_type", "other"), title=row.get("title", ""),
            description=row.get("description", ""), status=row.get("status", "open"),
            created_by=row.get("created_by", ""), resolved_by=row.get("resolved_by", ""),
            resolved_at=_safe_dt(row.get("resolved_at")),
            resolution_note=row.get("resolution_note", ""), created_at=_safe_dt(row.get("created_at")))

    @staticmethod
    def _row_trust_score(row: dict) -> TrustScore:
        return TrustScore(
            agent_module_id=row["agent_module_id"], score=float(row.get("score", 50.0)),
            published_days=int(row.get("published_days", 0)),
            review_count=int(row.get("review_count", 0)),
            average_rating=float(row.get("average_rating", 0.0)),
            report_count=int(row.get("report_count", 0)),
            resolved_report_count=int(row.get("resolved_report_count", 0)),
            risk_level=row.get("risk_level", "low"), calculated_at=_safe_dt(row.get("calculated_at")))

    @staticmethod
    def _row_event(row: dict) -> GovernanceEvent:
        return GovernanceEvent(id=row["id"], agent_module_id=row.get("agent_module_id", ""),
            event_type=row.get("event_type", ""), description=row.get("description", ""),
            metadata=json.loads(row.get("metadata_json", "{}")),
            created_at=_safe_dt(row.get("created_at")))
