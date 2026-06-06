"""Subscription Store Adapter — SQLite 实现 SubscriptionStore 协议。

管理 subscriptions 单表。
"""
import logging
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any

from src.adapters.config import Settings
from src.core.subscription import (
    BillingCycle,
    PlanTier,
    Subscription,
    SubscriptionStatus,
    SubscriptionStore,
)

logger = logging.getLogger(__name__)

_SUBSCRIPTION_SCHEMA = """
CREATE TABLE IF NOT EXISTS subscriptions (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL UNIQUE,
    plan_tier TEXT NOT NULL DEFAULT 'free',
    status TEXT NOT NULL DEFAULT 'trial',
    billing_cycle TEXT NOT NULL DEFAULT 'monthly',
    current_period_start TEXT NOT NULL DEFAULT (datetime('now')),
    current_period_end TEXT,
    trial_start TEXT,
    trial_end TEXT,
    canceled_at TEXT,
    auto_renew INTEGER NOT NULL DEFAULT 1,
    coupon_code TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_sub_tenant ON subscriptions(tenant_id);
CREATE INDEX IF NOT EXISTS idx_sub_status ON subscriptions(status);
"""


class SubscriptionStoreAdapter:
    """SubscriptionStore 的 SQLite 实现。"""

    def __init__(self, config: Settings, db_path: str | None = None) -> None:
        from sqlite_utils import Database as SqliteDB
        path = db_path or config.sqlite_db_path
        conn = sqlite3.connect(path, check_same_thread=False)
        self._db = SqliteDB(conn)
        self._db.conn.row_factory = sqlite3.Row
        self._write_lock = threading.Lock()
        self._init_schema()

    def _init_schema(self) -> None:
        for stmt in _SUBSCRIPTION_SCHEMA.strip().split(";"):
            s = stmt.strip()
            if s:
                self._db.execute(s)

    # ── SubscriptionStore 协议 ──

    def create_subscription(self, sub: Subscription) -> Subscription:
        with self._write_lock, self._db.conn:
            self._db.execute(
                """INSERT INTO subscriptions (id, tenant_id, plan_tier, status,
                   billing_cycle, current_period_start, current_period_end,
                   trial_start, trial_end, canceled_at, auto_renew, coupon_code,
                   created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (sub.id, sub.tenant_id, sub.plan_tier.value, sub.status.value,
                 sub.billing_cycle.value, sub.current_period_start.isoformat(),
                 sub.current_period_end.isoformat() if sub.current_period_end else None,
                 sub.trial_start.isoformat() if sub.trial_start else None,
                 sub.trial_end.isoformat() if sub.trial_end else None,
                 sub.canceled_at.isoformat() if sub.canceled_at else None,
                 int(sub.auto_renew), sub.coupon_code,
                 sub.created_at.isoformat(), sub.updated_at.isoformat()),
            )
        logger.info("subscription:created", extra={"tenant_id": sub.tenant_id, "tier": sub.plan_tier.value})
        return sub

    def get_subscription(self, tenant_id: str) -> Subscription | None:
        row = self._db.execute(
            "SELECT * FROM subscriptions WHERE tenant_id = ?", (tenant_id,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_subscription(dict(row))

    def update_subscription(self, sub: Subscription) -> None:
        sub.updated_at = datetime.now(timezone.utc)
        with self._write_lock, self._db.conn:
            self._db.execute(
                """UPDATE subscriptions SET plan_tier=?, status=?, billing_cycle=?,
                   current_period_start=?, current_period_end=?, trial_start=?,
                   trial_end=?, canceled_at=?, auto_renew=?, coupon_code=?,
                   updated_at=?
                   WHERE tenant_id=?""",
                (sub.plan_tier.value, sub.status.value, sub.billing_cycle.value,
                 sub.current_period_start.isoformat(),
                 sub.current_period_end.isoformat() if sub.current_period_end else None,
                 sub.trial_start.isoformat() if sub.trial_start else None,
                 sub.trial_end.isoformat() if sub.trial_end else None,
                 sub.canceled_at.isoformat() if sub.canceled_at else None,
                 int(sub.auto_renew), sub.coupon_code,
                 sub.updated_at.isoformat(), sub.tenant_id),
            )

    def change_plan(self, tenant_id: str, target_tier: PlanTier,
                    billing_cycle: BillingCycle) -> Subscription:
        current = self.get_subscription(tenant_id)
        if current is None:
            raise ValueError(f"No subscription found for tenant: {tenant_id}")
        now = datetime.now(timezone.utc)
        with self._write_lock, self._db.conn:
            self._db.execute(
                """UPDATE subscriptions SET plan_tier=?, billing_cycle=?,
                   updated_at=? WHERE tenant_id=?""",
                (target_tier.value, billing_cycle.value, now.isoformat(), tenant_id),
            )
        logger.info("subscription:plan_changed",
                     extra={"tenant_id": tenant_id, "from": current.plan_tier.value, "to": target_tier.value})
        return self.get_subscription(tenant_id)

    def cancel_subscription(self, tenant_id: str) -> Subscription:
        current = self.get_subscription(tenant_id)
        if current is None:
            raise ValueError(f"No subscription found for tenant: {tenant_id}")
        now = datetime.now(timezone.utc)
        with self._write_lock, self._db.conn:
            self._db.execute(
                """UPDATE subscriptions SET status=?, canceled_at=?,
                   auto_renew=?, updated_at=? WHERE tenant_id=?""",
                (SubscriptionStatus.CANCELED.value, now.isoformat(), 0,
                 now.isoformat(), tenant_id),
            )
        logger.info("subscription:canceled", extra={"tenant_id": tenant_id})
        return self.get_subscription(tenant_id)

    def list_subscriptions(self, status: str | None = None) -> list[Subscription]:
        if status:
            rows = self._db.execute(
                "SELECT * FROM subscriptions WHERE status = ? ORDER BY created_at DESC",
                (status,),
            ).fetchall()
        else:
            rows = self._db.execute(
                "SELECT * FROM subscriptions ORDER BY created_at DESC"
            ).fetchall()
        return [self._row_to_subscription(dict(r)) for r in rows]

    # ── 辅助方法 ──

    def list_all_subscriptions(self) -> list[Subscription]:
        rows = self._db.execute(
            "SELECT * FROM subscriptions ORDER BY created_at DESC"
        ).fetchall()
        return [self._row_to_subscription(dict(r)) for r in rows]

    def count_by_tier(self) -> dict[str, int]:
        rows = self._db.execute(
            "SELECT plan_tier, COUNT(*) as cnt FROM subscriptions GROUP BY plan_tier"
        ).fetchall()
        return {r["plan_tier"]: r["cnt"] for r in rows}

    def get_active_subscriptions(self) -> list[Subscription]:
        rows = self._db.execute(
            "SELECT * FROM subscriptions WHERE status IN (?, ?) ORDER BY created_at DESC",
            (SubscriptionStatus.ACTIVE.value, SubscriptionStatus.TRIAL.value),
        ).fetchall()
        return [self._row_to_subscription(dict(r)) for r in rows]

    # ── Internal ──

    @staticmethod
    def _row_to_subscription(row: dict) -> Subscription:
        return Subscription(
            id=row["id"],
            tenant_id=row["tenant_id"],
            plan_tier=PlanTier(row["plan_tier"]),
            status=SubscriptionStatus(row["status"]),
            billing_cycle=BillingCycle(row["billing_cycle"]),
            current_period_start=datetime.fromisoformat(row["current_period_start"]),
            current_period_end=datetime.fromisoformat(row["current_period_end"]) if row.get("current_period_end") else None,
            trial_start=datetime.fromisoformat(row["trial_start"]) if row.get("trial_start") else None,
            trial_end=datetime.fromisoformat(row["trial_end"]) if row.get("trial_end") else None,
            canceled_at=datetime.fromisoformat(row["canceled_at"]) if row.get("canceled_at") else None,
            auto_renew=bool(row["auto_renew"]),
            coupon_code=row.get("coupon_code"),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def close(self) -> None:
        if hasattr(self._db, "conn") and self._db.conn:
            self._db.conn.close()
