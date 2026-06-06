"""Growth Store Adapter — SQLite 实现 GrowthStore 协议。

管理 invites / referrals / coupons / coupon_redemptions / trial_records 五张表。
"""
import json
import logging
import secrets
import sqlite3
import threading
from datetime import datetime, timezone, timedelta
from typing import Any

from src.adapters.config import Settings
from src.core.growth import (
    Coupon,
    CouponRedemption,
    CouponStatus,
    CouponType,
    Invite,
    InviteStatus,
    Referral,
    ReferralStatus,
    TrialRecord,
    TrialStatus,
)

logger = logging.getLogger(__name__)

_GROWTH_SCHEMA = """
CREATE TABLE IF NOT EXISTS invites (
    id TEXT PRIMARY KEY,
    inviter_tenant_id TEXT NOT NULL,
    inviter_user_id TEXT NOT NULL,
    invitee_email TEXT NOT NULL,
    invite_code TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'pending',
    workspace_id TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    accepted_at TEXT,
    expires_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_inv_code ON invites(invite_code);
CREATE INDEX IF NOT EXISTS idx_inv_tenant ON invites(inviter_tenant_id);

CREATE TABLE IF NOT EXISTS referrals (
    id TEXT PRIMARY KEY,
    referrer_tenant_id TEXT NOT NULL,
    referrer_user_id TEXT NOT NULL,
    referred_tenant_id TEXT NOT NULL DEFAULT '',
    referred_user_id TEXT NOT NULL DEFAULT '',
    referral_code TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'pending',
    reward_granted INTEGER NOT NULL DEFAULT 0,
    reward_amount_cents INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_ref_code ON referrals(referral_code);
CREATE INDEX IF NOT EXISTS idx_ref_tenant ON referrals(referrer_tenant_id);

CREATE TABLE IF NOT EXISTS coupons (
    id TEXT PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    coupon_type TEXT NOT NULL DEFAULT 'percentage',
    value INTEGER NOT NULL DEFAULT 0,
    min_amount_cents INTEGER NOT NULL DEFAULT 0,
    max_discount_cents INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'active',
    applicable_plans_json TEXT NOT NULL DEFAULT '[]',
    usage_limit INTEGER NOT NULL DEFAULT 0,
    usage_count INTEGER NOT NULL DEFAULT 0,
    valid_from TEXT NOT NULL DEFAULT (datetime('now')),
    valid_until TEXT NOT NULL,
    created_by TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_cpn_code ON coupons(code);

CREATE TABLE IF NOT EXISTS coupon_redemptions (
    id TEXT PRIMARY KEY,
    coupon_id TEXT NOT NULL REFERENCES coupons(id),
    tenant_id TEXT NOT NULL,
    code TEXT NOT NULL,
    discount_cents INTEGER NOT NULL DEFAULT 0,
    invoice_id TEXT NOT NULL DEFAULT '',
    redeemed_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_cpr_tenant ON coupon_redemptions(tenant_id);

CREATE TABLE IF NOT EXISTS trial_records (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL UNIQUE,
    plan_tier TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    trial_days INTEGER NOT NULL DEFAULT 14,
    started_at TEXT NOT NULL DEFAULT (datetime('now')),
    ends_at TEXT NOT NULL,
    converted_at TEXT,
    converted_to_plan TEXT NOT NULL DEFAULT '',
    extended_count INTEGER NOT NULL DEFAULT 0,
    source TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_tri_tenant ON trial_records(tenant_id);
"""


class GrowthStoreAdapter:
    """GrowthStore 的 SQLite 实现。"""

    def __init__(self, config: Settings, db_path: str | None = None) -> None:
        from sqlite_utils import Database as SqliteDB

        path = db_path or config.sqlite_db_path
        conn = sqlite3.connect(path, check_same_thread=False)
        self._db = SqliteDB(conn)
        self._db.conn.row_factory = sqlite3.Row
        self._write_lock = threading.Lock()
        self._init_schema()

    def _init_schema(self) -> None:
        for stmt in _GROWTH_SCHEMA.strip().split(";"):
            s = stmt.strip()
            if s:
                self._db.execute(s)

    # ── Invite ─────────────────────────────────────────────────────────

    def create_invite(self, invite: Invite) -> Invite:
        if not invite.invite_code:
            invite.invite_code = secrets.token_hex(4)
        with self._write_lock, self._db.conn:
            self._db.execute(
                """INSERT INTO invites (id, inviter_tenant_id, inviter_user_id,
                   invitee_email, invite_code, status, workspace_id,
                   created_at, accepted_at, expires_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (invite.id, invite.inviter_tenant_id, invite.inviter_user_id,
                 invite.invitee_email, invite.invite_code, invite.status.value,
                 invite.workspace_id, invite.created_at.isoformat(),
                 invite.accepted_at.isoformat() if invite.accepted_at else None,
                 invite.expires_at.isoformat()),
            )
        logger.info("growth:invite_created", extra={"invite_id": invite.id})
        return invite

    def get_invite(self, invite_id: str) -> Invite | None:
        row = self._db.execute(
            "SELECT * FROM invites WHERE id = ?", (invite_id,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_invite(dict(row))

    def get_invite_by_code(self, code: str) -> Invite | None:
        row = self._db.execute(
            "SELECT * FROM invites WHERE invite_code = ?", (code,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_invite(dict(row))

    def accept_invite(self, invite_id: str, invitee_user_id: str,
                      invitee_tenant_id: str) -> Invite:
        now = datetime.now(timezone.utc)
        with self._write_lock, self._db.conn:
            self._db.execute(
                """UPDATE invites SET status = ?, accepted_at = ?
                   WHERE id = ?""",
                (InviteStatus.ACCEPTED.value, now.isoformat(), invite_id),
            )
            row = self._db.execute(
                "SELECT * FROM invites WHERE id = ?", (invite_id,)
            ).fetchone()
        logger.info("growth:invite_accepted", extra={
            "invite_id": invite_id,
            "invitee_user_id": invitee_user_id,
            "invitee_tenant_id": invitee_tenant_id,
        })
        return self._row_to_invite(dict(row))

    def list_invites(self, tenant_id: str) -> list[Invite]:
        rows = self._db.execute(
            "SELECT * FROM invites WHERE inviter_tenant_id = ? ORDER BY created_at DESC",
            (tenant_id,),
        ).fetchall()
        return [self._row_to_invite(dict(r)) for r in rows]

    # ── Referral ───────────────────────────────────────────────────────

    def create_referral(self, referral: Referral) -> Referral:
        if not referral.referral_code:
            referral.referral_code = secrets.token_hex(4)
        with self._write_lock, self._db.conn:
            self._db.execute(
                """INSERT INTO referrals (id, referrer_tenant_id, referrer_user_id,
                   referred_tenant_id, referred_user_id, referral_code, status,
                   reward_granted, reward_amount_cents, created_at, completed_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (referral.id, referral.referrer_tenant_id, referral.referrer_user_id,
                 referral.referred_tenant_id, referral.referred_user_id,
                 referral.referral_code, referral.status.value,
                 int(referral.reward_granted), referral.reward_amount_cents,
                 referral.created_at.isoformat(),
                 referral.completed_at.isoformat() if referral.completed_at else None),
            )
        logger.info("growth:referral_created", extra={"referral_id": referral.id})
        return referral

    def get_referral(self, referral_id: str) -> Referral | None:
        row = self._db.execute(
            "SELECT * FROM referrals WHERE id = ?", (referral_id,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_referral(dict(row))

    def get_referral_by_code(self, code: str) -> Referral | None:
        row = self._db.execute(
            "SELECT * FROM referrals WHERE referral_code = ?", (code,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_referral(dict(row))

    def complete_referral(self, referral_id: str,
                          referred_tenant_id: str, referred_user_id: str) -> Referral:
        now = datetime.now(timezone.utc)
        with self._write_lock, self._db.conn:
            self._db.execute(
                """UPDATE referrals SET status = ?, referred_tenant_id = ?,
                   referred_user_id = ?, completed_at = ?
                   WHERE id = ?""",
                (ReferralStatus.COMPLETED.value, referred_tenant_id,
                 referred_user_id, now.isoformat(), referral_id),
            )
            row = self._db.execute(
                "SELECT * FROM referrals WHERE id = ?", (referral_id,)
            ).fetchone()
        logger.info("growth:referral_completed", extra={"referral_id": referral_id})
        return self._row_to_referral(dict(row))

    def list_referrals(self, tenant_id: str) -> list[Referral]:
        rows = self._db.execute(
            "SELECT * FROM referrals WHERE referrer_tenant_id = ? ORDER BY created_at DESC",
            (tenant_id,),
        ).fetchall()
        return [self._row_to_referral(dict(r)) for r in rows]

    def get_referral_stats(self, tenant_id: str) -> dict:
        row = self._db.execute(
            """SELECT
               COUNT(*) as total_referrals,
               SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed_referrals,
               SUM(reward_amount_cents) as total_rewards_cents
               FROM referrals WHERE referrer_tenant_id = ?""",
            (tenant_id,),
        ).fetchone()
        r = dict(row)
        return {
            "total_referrals": r["total_referrals"],
            "completed_referrals": r["completed_referrals"] or 0,
            "total_rewards_cents": r["total_rewards_cents"] or 0,
        }

    # ── Coupon ─────────────────────────────────────────────────────────

    def create_coupon(self, coupon: Coupon) -> Coupon:
        with self._write_lock, self._db.conn:
            self._db.execute(
                """INSERT INTO coupons (id, code, coupon_type, value,
                   min_amount_cents, max_discount_cents, status,
                   applicable_plans_json, usage_limit, usage_count,
                   valid_from, valid_until, created_by, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (coupon.id, coupon.code, coupon.coupon_type.value, coupon.value,
                 coupon.min_amount_cents, coupon.max_discount_cents,
                 coupon.status.value,
                 json.dumps(coupon.applicable_plans, ensure_ascii=False),
                 coupon.usage_limit, coupon.usage_count,
                 coupon.valid_from.isoformat(), coupon.valid_until.isoformat(),
                 coupon.created_by, coupon.created_at.isoformat()),
            )
        logger.info("growth:coupon_created", extra={"coupon_id": coupon.id, "code": coupon.code})
        return coupon

    def get_coupon(self, coupon_id: str) -> Coupon | None:
        row = self._db.execute(
            "SELECT * FROM coupons WHERE id = ?", (coupon_id,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_coupon(dict(row))

    def get_coupon_by_code(self, code: str) -> Coupon | None:
        with self._write_lock, self._db.conn:
            row = self._db.execute(
                "SELECT * FROM coupons WHERE code = ?", (code,)
            ).fetchone()
            if row is None:
                return None
            self._db.execute(
                "UPDATE coupons SET usage_count = usage_count + 1 WHERE code = ?",
                (code,),
            )
            row = self._db.execute(
                "SELECT * FROM coupons WHERE code = ?", (code,)
            ).fetchone()
        return self._row_to_coupon(dict(row))

    def redeem_coupon(self, redemption: CouponRedemption) -> CouponRedemption:
        with self._write_lock, self._db.conn:
            self._db.execute(
                """INSERT INTO coupon_redemptions (id, coupon_id, tenant_id, code,
                   discount_cents, invoice_id, redeemed_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (redemption.id, redemption.coupon_id, redemption.tenant_id,
                 redemption.code, redemption.discount_cents,
                 redemption.invoice_id, redemption.redeemed_at.isoformat()),
            )
            self._db.execute(
                "UPDATE coupons SET usage_count = usage_count + 1 WHERE id = ?",
                (redemption.coupon_id,),
            )
        logger.info("growth:coupon_redeemed", extra={
            "coupon_id": redemption.coupon_id,
            "tenant_id": redemption.tenant_id,
        })
        return redemption

    def list_coupons(self, status: str | None = None) -> list[Coupon]:
        if status:
            rows = self._db.execute(
                "SELECT * FROM coupons WHERE status = ? ORDER BY created_at DESC",
                (status,),
            ).fetchall()
        else:
            rows = self._db.execute(
                "SELECT * FROM coupons ORDER BY created_at DESC"
            ).fetchall()
        return [self._row_to_coupon(dict(r)) for r in rows]

    def update_coupon(self, coupon: Coupon) -> None:
        with self._write_lock, self._db.conn:
            self._db.execute(
                """UPDATE coupons SET code=?, coupon_type=?, value=?,
                   min_amount_cents=?, max_discount_cents=?, status=?,
                   applicable_plans_json=?, usage_limit=?, usage_count=?,
                   valid_from=?, valid_until=?, created_by=?
                   WHERE id=?""",
                (coupon.code, coupon.coupon_type.value, coupon.value,
                 coupon.min_amount_cents, coupon.max_discount_cents,
                 coupon.status.value,
                 json.dumps(coupon.applicable_plans, ensure_ascii=False),
                 coupon.usage_limit, coupon.usage_count,
                 coupon.valid_from.isoformat(), coupon.valid_until.isoformat(),
                 coupon.created_by, coupon.id),
            )

    # ── Trial ──────────────────────────────────────────────────────────

    def create_trial(self, trial: TrialRecord) -> TrialRecord:
        with self._write_lock, self._db.conn:
            self._db.execute(
                """INSERT INTO trial_records (id, tenant_id, plan_tier, status,
                   trial_days, started_at, ends_at, converted_at,
                   converted_to_plan, extended_count, source)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (trial.id, trial.tenant_id, trial.plan_tier, trial.status.value,
                 trial.trial_days, trial.started_at.isoformat(),
                 trial.ends_at.isoformat(),
                 trial.converted_at.isoformat() if trial.converted_at else None,
                 trial.converted_to_plan, trial.extended_count, trial.source),
            )
        logger.info("growth:trial_created", extra={"tenant_id": trial.tenant_id, "plan": trial.plan_tier})
        return trial

    def get_trial(self, tenant_id: str) -> TrialRecord | None:
        row = self._db.execute(
            "SELECT * FROM trial_records WHERE tenant_id = ?", (tenant_id,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_trial(dict(row))

    def extend_trial(self, tenant_id: str, days: int) -> TrialRecord:
        with self._write_lock, self._db.conn:
            row = self._db.execute(
                "SELECT * FROM trial_records WHERE tenant_id = ?", (tenant_id,)
            ).fetchone()
            if row is None:
                raise ValueError(f"Trial not found for tenant: {tenant_id}")
            current_ends_at = datetime.fromisoformat(row["ends_at"])
            new_ends_at = current_ends_at + timedelta(days=days)
            self._db.execute(
                """UPDATE trial_records SET
                   extended_count = extended_count + 1,
                   ends_at = ?,
                   status = ?
                   WHERE tenant_id = ?""",
                (new_ends_at.isoformat(), TrialStatus.EXTENDED.value, tenant_id),
            )
            row = self._db.execute(
                "SELECT * FROM trial_records WHERE tenant_id = ?", (tenant_id,)
            ).fetchone()
        logger.info("growth:trial_extended", extra={"tenant_id": tenant_id, "days": days})
        return self._row_to_trial(dict(row))

    def convert_trial(self, tenant_id: str, plan_tier: str) -> TrialRecord:
        now = datetime.now(timezone.utc)
        with self._write_lock, self._db.conn:
            self._db.execute(
                """UPDATE trial_records SET
                   status = ?, converted_at = ?, converted_to_plan = ?
                   WHERE tenant_id = ?""",
                (TrialStatus.CONVERTED.value, now.isoformat(), plan_tier, tenant_id),
            )
            row = self._db.execute(
                "SELECT * FROM trial_records WHERE tenant_id = ?", (tenant_id,)
            ).fetchone()
        logger.info("growth:trial_converted", extra={"tenant_id": tenant_id, "plan": plan_tier})
        return self._row_to_trial(dict(row))

    def list_trials(self, status: str | None = None) -> list[TrialRecord]:
        if status:
            rows = self._db.execute(
                "SELECT * FROM trial_records WHERE status = ? ORDER BY started_at DESC",
                (status,),
            ).fetchall()
        else:
            rows = self._db.execute(
                "SELECT * FROM trial_records ORDER BY started_at DESC"
            ).fetchall()
        return [self._row_to_trial(dict(r)) for r in rows]

    def get_trial_conversion_stats(self) -> dict:
        row = self._db.execute(
            """SELECT
               COUNT(*) as total_trials,
               SUM(CASE WHEN status = 'converted' THEN 1 ELSE 0 END) as converted_trials,
               AVG(CASE WHEN status = 'converted'
                   THEN julianday(converted_at) - julianday(started_at)
                   END) as avg_days_to_convert
               FROM trial_records"""
        ).fetchone()
        r = dict(row)
        total = r["total_trials"]
        converted = r["converted_trials"] or 0
        return {
            "total_trials": total,
            "converted_trials": converted,
            "conversion_rate": (converted / total) if total > 0 else 0.0,
            "avg_days_to_convert": round(r["avg_days_to_convert"] or 0.0, 1),
        }

    # ── Internal ───────────────────────────────────────────────────────

    @staticmethod
    def _row_to_invite(row: dict) -> Invite:
        return Invite(
            id=row["id"],
            inviter_tenant_id=row["inviter_tenant_id"],
            inviter_user_id=row["inviter_user_id"],
            invitee_email=row["invitee_email"],
            invite_code=row["invite_code"],
            status=InviteStatus(row["status"]),
            workspace_id=row.get("workspace_id", ""),
            created_at=datetime.fromisoformat(row["created_at"]),
            accepted_at=datetime.fromisoformat(row["accepted_at"]) if row.get("accepted_at") else None,
            expires_at=datetime.fromisoformat(row["expires_at"]),
        )

    @staticmethod
    def _row_to_referral(row: dict) -> Referral:
        return Referral(
            id=row["id"],
            referrer_tenant_id=row["referrer_tenant_id"],
            referrer_user_id=row["referrer_user_id"],
            referred_tenant_id=row.get("referred_tenant_id", ""),
            referred_user_id=row.get("referred_user_id", ""),
            referral_code=row["referral_code"],
            status=ReferralStatus(row["status"]),
            reward_granted=bool(row.get("reward_granted", 0)),
            reward_amount_cents=row.get("reward_amount_cents", 0),
            created_at=datetime.fromisoformat(row["created_at"]),
            completed_at=datetime.fromisoformat(row["completed_at"]) if row.get("completed_at") else None,
        )

    @staticmethod
    def _row_to_coupon(row: dict) -> Coupon:
        return Coupon(
            id=row["id"],
            code=row["code"],
            coupon_type=CouponType(row["coupon_type"]),
            value=row["value"],
            min_amount_cents=row.get("min_amount_cents", 0),
            max_discount_cents=row.get("max_discount_cents", 0),
            status=CouponStatus(row["status"]),
            applicable_plans=json.loads(row.get("applicable_plans_json") or "[]"),
            usage_limit=row.get("usage_limit", 0),
            usage_count=row.get("usage_count", 0),
            valid_from=datetime.fromisoformat(row["valid_from"]),
            valid_until=datetime.fromisoformat(row["valid_until"]),
            created_by=row.get("created_by", ""),
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    @staticmethod
    def _row_to_trial(row: dict) -> TrialRecord:
        return TrialRecord(
            id=row["id"],
            tenant_id=row["tenant_id"],
            plan_tier=row["plan_tier"],
            status=TrialStatus(row["status"]),
            trial_days=row.get("trial_days", 14),
            started_at=datetime.fromisoformat(row["started_at"]),
            ends_at=datetime.fromisoformat(row["ends_at"]),
            converted_at=datetime.fromisoformat(row["converted_at"]) if row.get("converted_at") else None,
            converted_to_plan=row.get("converted_to_plan", ""),
            extended_count=row.get("extended_count", 0),
            source=row.get("source", ""),
        )

    def close(self) -> None:
        if hasattr(self._db, "conn") and self._db.conn:
            self._db.conn.close()

    def __enter__(self) -> "GrowthStoreAdapter":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()
