"""Alert Store Adapter — SQLite 实现 AlertStore 协议。

管理 alert_rules / alert_events 表。
"""
import json
import logging
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any

from sqlite_utils import Database as SqliteDB

from src.adapters.config import Settings
from src.core.alert import (
    AlertCondition,
    AlertEvent,
    AlertMetric,
    AlertRule,
    AlertSeverity,
    AlertStore,
    NotificationChannel,
    get_preset_rules,
)

logger = logging.getLogger(__name__)

_ALERT_SCHEMA = """
CREATE TABLE IF NOT EXISTS alert_rules (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    name TEXT NOT NULL,
    metric TEXT NOT NULL,
    condition TEXT NOT NULL,
    threshold REAL NOT NULL,
    severity TEXT NOT NULL DEFAULT 'warning',
    channel TEXT NOT NULL DEFAULT 'system',
    enabled INTEGER NOT NULL DEFAULT 1,
    cooldown_minutes INTEGER NOT NULL DEFAULT 60,
    last_triggered_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_ar_tenant ON alert_rules(tenant_id);
CREATE INDEX IF NOT EXISTS idx_ar_metric ON alert_rules(tenant_id, metric);

CREATE TABLE IF NOT EXISTS alert_events (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    rule_id TEXT NOT NULL,
    rule_name TEXT NOT NULL,
    metric TEXT NOT NULL,
    current_value REAL NOT NULL,
    threshold REAL NOT NULL,
    severity TEXT NOT NULL,
    channel TEXT NOT NULL,
    message TEXT NOT NULL,
    acknowledged INTEGER NOT NULL DEFAULT 0,
    triggered_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_ae_tenant ON alert_events(tenant_id);
CREATE INDEX IF NOT EXISTS idx_ae_rule ON alert_events(rule_id);
CREATE INDEX IF NOT EXISTS idx_ae_ts ON alert_events(triggered_at);
CREATE INDEX IF NOT EXISTS idx_ae_tenant_ts ON alert_events(tenant_id, triggered_at);
"""


class AlertStoreAdapter:
    """AlertStore 的 SQLite 实现。"""

    def __init__(self, config: Settings, db_path: str | None = None) -> None:
        path = db_path or config.sqlite_db_path
        if path == ":memory:":
            self._db = SqliteDB(memory=True)
        else:
            conn = sqlite3.connect(path, check_same_thread=False)
            self._db = SqliteDB(conn)
        self._db.conn.row_factory = sqlite3.Row
        self._write_lock = threading.Lock()
        self._init_schema()

    def _init_schema(self) -> None:
        for stmt in _ALERT_SCHEMA.strip().split(";"):
            s = stmt.strip()
            if s:
                self._db.execute(s)

    # ── AlertStore 协议 ──────────────────────────────────────────────

    def create_rule(self, rule: AlertRule) -> str:
        with self._write_lock, self._db.conn:
            self._db.execute(
                """INSERT INTO alert_rules (id, tenant_id, name, metric, condition,
                   threshold, severity, channel, enabled, cooldown_minutes,
                   last_triggered_at, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    rule.id,
                    rule.tenant_id,
                    rule.name,
                    rule.metric.value,
                    rule.condition.value,
                    rule.threshold,
                    rule.severity.value,
                    rule.channel.value,
                    int(rule.enabled),
                    rule.cooldown_minutes,
                    rule.last_triggered_at.isoformat() if rule.last_triggered_at else None,
                    rule.created_at.isoformat(),
                    rule.updated_at.isoformat(),
                ),
            )
        logger.debug("alert:rule_created", extra={"rule_id": rule.id, "tenant_id": rule.tenant_id})
        return rule.id

    def get_rule(self, tenant_id: str, rule_id: str) -> AlertRule | None:
        row = self._db.execute(
            "SELECT * FROM alert_rules WHERE id = ? AND tenant_id = ?",
            (rule_id, tenant_id),
        ).fetchone()
        if row is None:
            return None
        return self._row_to_rule(dict(row))

    def list_rules(self, tenant_id: str, enabled_only: bool = False) -> list[AlertRule]:
        sql = "SELECT * FROM alert_rules WHERE tenant_id = ?"
        if enabled_only:
            sql += " AND enabled = 1"
        sql += " ORDER BY created_at DESC"
        rows = self._db.execute(sql, (tenant_id,)).fetchall()
        return [self._row_to_rule(dict(r)) for r in rows]

    def update_rule(self, tenant_id: str, rule_id: str, updates: dict) -> AlertRule | None:
        existing = self.get_rule(tenant_id, rule_id)
        if existing is None:
            return None

        allowed = {"name", "threshold", "severity", "channel", "enabled",
                    "cooldown_minutes", "condition", "metric"}
        filtered = {k: v for k, v in updates.items() if k in allowed}

        if not filtered:
            return existing

        filtered["updated_at"] = datetime.now(timezone.utc).isoformat()

        set_clause = ", ".join(f"{k} = ?" for k in filtered)
        values = list(filtered.values()) + [rule_id, tenant_id]

        with self._write_lock, self._db.conn:
            self._db.execute(
                f"UPDATE alert_rules SET {set_clause} WHERE id = ? AND tenant_id = ?",
                tuple(values),
            )

        return self.get_rule(tenant_id, rule_id)

    def delete_rule(self, tenant_id: str, rule_id: str) -> bool:
        with self._write_lock, self._db.conn:
            cursor = self._db.execute(
                "DELETE FROM alert_rules WHERE id = ? AND tenant_id = ?",
                (rule_id, tenant_id),
            )
            return cursor.rowcount > 0

    def record_event(self, event: AlertEvent) -> str:
        with self._write_lock, self._db.conn:
            self._db.execute(
                """INSERT INTO alert_events (id, tenant_id, rule_id, rule_name, metric,
                   current_value, threshold, severity, channel, message, acknowledged, triggered_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    event.id,
                    event.tenant_id,
                    event.rule_id,
                    event.rule_name,
                    event.metric.value,
                    event.current_value,
                    event.threshold,
                    event.severity.value,
                    event.channel.value,
                    event.message,
                    int(event.acknowledged),
                    event.triggered_at.isoformat(),
                ),
            )
        logger.info("alert:event_recorded", extra={
            "event_id": event.id, "rule": event.rule_name,
            "severity": event.severity.value, "tenant_id": event.tenant_id,
        })
        return event.id

    def list_events(
        self, tenant_id: str, rule_id: str | None = None,
        severity: str | None = None, acknowledged: bool | None = None,
        limit: int = 50, offset: int = 0,
    ) -> list[AlertEvent]:
        sql = "SELECT * FROM alert_events WHERE tenant_id = ?"
        params: list[Any] = [tenant_id]

        if rule_id:
            sql += " AND rule_id = ?"
            params.append(rule_id)
        if severity:
            sql += " AND severity = ?"
            params.append(severity)
        if acknowledged is not None:
            sql += " AND acknowledged = ?"
            params.append(int(acknowledged))

        sql += " ORDER BY triggered_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        rows = self._db.execute(sql, tuple(params)).fetchall()
        return [self._row_to_event(dict(r)) for r in rows]

    def acknowledge_event(self, tenant_id: str, event_id: str) -> bool:
        with self._write_lock, self._db.conn:
            cursor = self._db.execute(
                "UPDATE alert_events SET acknowledged = 1 WHERE id = ? AND tenant_id = ?",
                (event_id, tenant_id),
            )
            return cursor.rowcount > 0

    def get_active_rules(self, tenant_id: str) -> list[AlertRule]:
        """获取已启用且在冷却期之外的规则。"""
        all_enabled = self.list_rules(tenant_id, enabled_only=True)
        now = datetime.now(timezone.utc)
        active = []
        for rule in all_enabled:
            if rule.last_triggered_at is None:
                active.append(rule)
                continue
            since_last = (now - rule.last_triggered_at).total_seconds() / 60
            if since_last >= rule.cooldown_minutes:
                active.append(rule)
        return active

    def seed_presets(self, tenant_id: str) -> list[str]:
        """为新租户初始化预设告警规则。仅当该租户尚无规则时执行。"""
        existing = self.list_rules(tenant_id)
        if existing:
            return []
        preset_ids = []
        for rule in get_preset_rules(tenant_id):
            self.create_rule(rule)
            preset_ids.append(rule.id)
        logger.info("alert:presets_seeded", extra={
            "tenant_id": tenant_id, "count": len(preset_ids),
        })
        return preset_ids

    # ── 内部方法 ────────────────────────────────────────────────────

    @staticmethod
    def _row_to_rule(row: dict) -> AlertRule:
        return AlertRule(
            id=row["id"],
            tenant_id=row["tenant_id"],
            name=row["name"],
            metric=AlertMetric(row["metric"]),
            condition=AlertCondition(row["condition"]),
            threshold=float(row["threshold"]),
            severity=AlertSeverity(row["severity"]),
            channel=NotificationChannel(row["channel"]),
            enabled=bool(row.get("enabled", 1)),
            cooldown_minutes=int(row.get("cooldown_minutes", 60)),
            last_triggered_at=_safe_parse_datetime(row.get("last_triggered_at")),
            created_at=_safe_parse_datetime(row.get("created_at")),
            updated_at=_safe_parse_datetime(row.get("updated_at")),
        )

    @staticmethod
    def _row_to_event(row: dict) -> AlertEvent:
        return AlertEvent(
            id=row["id"],
            tenant_id=row["tenant_id"],
            rule_id=row["rule_id"],
            rule_name=row["rule_name"],
            metric=AlertMetric(row["metric"]),
            current_value=float(row["current_value"]),
            threshold=float(row["threshold"]),
            severity=AlertSeverity(row["severity"]),
            channel=NotificationChannel(row["channel"]),
            message=row["message"],
            acknowledged=bool(row.get("acknowledged", 0)),
            triggered_at=_safe_parse_datetime(row.get("triggered_at")),
        )

    def close(self) -> None:
        if hasattr(self._db, "conn") and self._db.conn:
            self._db.conn.close()

    def __enter__(self) -> "AlertStoreAdapter":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()


def _safe_parse_datetime(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except (ValueError, TypeError):
        return None
