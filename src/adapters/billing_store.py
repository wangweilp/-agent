"""Billing Store Adapter — SQLite 实现 BillingStore 协议。

管理 billing_accounts / invoices / payments / refunds 四张表。
"""
import logging
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any

from src.adapters.config import Settings
from src.core.billing import (
    BillingAccount, BillingStore,
    Currency,
    Invoice, InvoiceStatus,
    Payment, PaymentProvider, PaymentStatus,
    Refund, RefundStatus,
)

logger = logging.getLogger(__name__)

_BILLING_SCHEMA = """
CREATE TABLE IF NOT EXISTS billing_accounts (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL UNIQUE,
    currency TEXT NOT NULL DEFAULT 'cny',
    balance INTEGER NOT NULL DEFAULT 0,
    credit_limit INTEGER NOT NULL DEFAULT 0,
    wechat_openid TEXT,
    alipay_user_id TEXT,
    stripe_customer_id TEXT,
    billing_email TEXT NOT NULL DEFAULT '',
    billing_address TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_ba_tenant ON billing_accounts(tenant_id);

CREATE TABLE IF NOT EXISTS invoices (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    billing_account_id TEXT NOT NULL REFERENCES billing_accounts(id),
    invoice_number TEXT NOT NULL DEFAULT '',
    amount INTEGER NOT NULL DEFAULT 0,
    currency TEXT NOT NULL DEFAULT 'cny',
    status TEXT NOT NULL DEFAULT 'draft',
    description TEXT NOT NULL DEFAULT '',
    line_items_json TEXT NOT NULL DEFAULT '[]',
    due_date TEXT,
    paid_at TEXT,
    period_start TEXT,
    period_end TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_inv_tenant ON invoices(tenant_id);
CREATE INDEX IF NOT EXISTS idx_inv_status ON invoices(status);

CREATE TABLE IF NOT EXISTS payments (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    billing_account_id TEXT NOT NULL REFERENCES billing_accounts(id),
    invoice_id TEXT REFERENCES invoices(id),
    amount INTEGER NOT NULL DEFAULT 0,
    currency TEXT NOT NULL DEFAULT 'cny',
    provider TEXT NOT NULL DEFAULT 'wechat',
    provider_payment_id TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending',
    description TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_pay_tenant ON payments(tenant_id);
CREATE INDEX IF NOT EXISTS idx_pay_invoice ON payments(invoice_id);

CREATE TABLE IF NOT EXISTS refunds (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    payment_id TEXT NOT NULL REFERENCES payments(id),
    amount INTEGER NOT NULL DEFAULT 0,
    provider_refund_id TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending',
    reason TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_ref_tenant ON refunds(tenant_id);
CREATE INDEX IF NOT EXISTS idx_ref_payment ON refunds(payment_id);
"""


class BillingStoreAdapter:
    """BillingStore 的 SQLite 实现。"""

    def __init__(self, config: Settings, db_path: str | None = None) -> None:
        from sqlite_utils import Database as SqliteDB
        path = db_path or config.sqlite_db_path
        conn = sqlite3.connect(path, check_same_thread=False)
        self._db = SqliteDB(conn)
        self._db.conn.row_factory = sqlite3.Row
        self._write_lock = threading.Lock()
        self._init_schema()

    def _init_schema(self) -> None:
        all_tables = {r["name"] for r in self._db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        for stmt in _BILLING_SCHEMA.strip().split(";"):
            s = stmt.strip()
            if s:
                self._db.execute(s)

    # ── BillingAccount ──

    def create_account(self, account: BillingAccount) -> BillingAccount:
        with self._write_lock, self._db.conn:
            self._db.execute(
                """INSERT INTO billing_accounts (id, tenant_id, currency, balance,
                   credit_limit, wechat_openid, alipay_user_id, stripe_customer_id,
                   billing_email, billing_address, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (account.id, account.tenant_id, account.currency.value,
                 account.balance, account.credit_limit,
                 account.wechat_openid, account.alipay_user_id, account.stripe_customer_id,
                 account.billing_email, account.billing_address,
                 account.created_at.isoformat(), account.updated_at.isoformat()),
            )
        logger.info("billing:account_created", extra={"tenant_id": account.tenant_id})
        return account

    def get_account(self, tenant_id: str) -> BillingAccount | None:
        row = self._db.execute(
            "SELECT * FROM billing_accounts WHERE tenant_id = ?", (tenant_id,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_account(dict(row))

    def update_account(self, account: BillingAccount) -> None:
        account.updated_at = datetime.now(timezone.utc)
        with self._write_lock, self._db.conn:
            self._db.execute(
                """UPDATE billing_accounts SET currency=?, balance=?, credit_limit=?,
                   wechat_openid=?, alipay_user_id=?, stripe_customer_id=?,
                   billing_email=?, billing_address=?, updated_at=?
                   WHERE tenant_id=?""",
                (account.currency.value, account.balance, account.credit_limit,
                 account.wechat_openid, account.alipay_user_id, account.stripe_customer_id,
                 account.billing_email, account.billing_address,
                 account.updated_at.isoformat(), account.tenant_id),
            )

    # ── Invoice ──

    def create_invoice(self, invoice: Invoice) -> Invoice:
        import json
        if not invoice.invoice_number:
            # Auto-generate invoice number
            count = self._db.execute(
                "SELECT COUNT(*) as c FROM invoices"
            ).fetchone()["c"]
            invoice.invoice_number = f"INV-{datetime.now(timezone.utc).year}-{count + 1:05d}"
        with self._write_lock, self._db.conn:
            self._db.execute(
                """INSERT INTO invoices (id, tenant_id, billing_account_id, invoice_number,
                   amount, currency, status, description, line_items_json,
                   due_date, paid_at, period_start, period_end, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (invoice.id, invoice.tenant_id, invoice.billing_account_id,
                 invoice.invoice_number, invoice.amount, invoice.currency.value,
                 invoice.status.value, invoice.description,
                 json.dumps(invoice.line_items, ensure_ascii=False),
                 invoice.due_date.isoformat() if invoice.due_date else None,
                 invoice.paid_at.isoformat() if invoice.paid_at else None,
                 invoice.period_start.isoformat() if invoice.period_start else None,
                 invoice.period_end.isoformat() if invoice.period_end else None,
                 invoice.created_at.isoformat()),
            )
        return invoice

    def get_invoice(self, invoice_id: str) -> Invoice | None:
        row = self._db.execute(
            "SELECT * FROM invoices WHERE id = ?", (invoice_id,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_invoice(dict(row))

    def list_invoices(self, tenant_id: str, status: str | None = None) -> list[Invoice]:
        if status:
            rows = self._db.execute(
                "SELECT * FROM invoices WHERE tenant_id = ? AND status = ? ORDER BY created_at DESC",
                (tenant_id, status),
            ).fetchall()
        else:
            rows = self._db.execute(
                "SELECT * FROM invoices WHERE tenant_id = ? ORDER BY created_at DESC",
                (tenant_id,),
            ).fetchall()
        return [self._row_to_invoice(dict(r)) for r in rows]

    def update_invoice(self, invoice: Invoice) -> None:
        import json
        with self._write_lock, self._db.conn:
            self._db.execute(
                """UPDATE invoices SET status=?, paid_at=?, line_items_json=?
                   WHERE id=?""",
                (invoice.status.value,
                 invoice.paid_at.isoformat() if invoice.paid_at else None,
                 json.dumps(invoice.line_items, ensure_ascii=False),
                 invoice.id),
            )

    # ── Payment ──

    def create_payment(self, payment: Payment) -> Payment:
        import json
        with self._write_lock, self._db.conn:
            self._db.execute(
                """INSERT INTO payments (id, tenant_id, billing_account_id, invoice_id,
                   amount, currency, provider, provider_payment_id, status,
                   description, metadata_json, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (payment.id, payment.tenant_id, payment.billing_account_id,
                 payment.invoice_id, payment.amount, payment.currency.value,
                 payment.provider.value, payment.provider_payment_id,
                 payment.status.value, payment.description,
                 json.dumps(payment.metadata, ensure_ascii=False),
                 payment.created_at.isoformat(), payment.updated_at.isoformat()),
            )
        return payment

    def get_payment(self, payment_id: str) -> Payment | None:
        row = self._db.execute(
            "SELECT * FROM payments WHERE id = ?", (payment_id,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_payment(dict(row))

    def list_payments(self, tenant_id: str) -> list[Payment]:
        rows = self._db.execute(
            "SELECT * FROM payments WHERE tenant_id = ? ORDER BY created_at DESC",
            (tenant_id,),
        ).fetchall()
        return [self._row_to_payment(dict(r)) for r in rows]

    def update_payment(self, payment: Payment) -> None:
        import json
        payment.updated_at = datetime.now(timezone.utc)
        with self._write_lock, self._db.conn:
            self._db.execute(
                """UPDATE payments SET provider_payment_id=?, status=?, metadata_json=?,
                   updated_at=? WHERE id=?""",
                (payment.provider_payment_id, payment.status.value,
                 json.dumps(payment.metadata, ensure_ascii=False),
                 payment.updated_at.isoformat(), payment.id),
            )

    # ── Refund ──

    def create_refund(self, refund: Refund) -> Refund:
        with self._write_lock, self._db.conn:
            self._db.execute(
                """INSERT INTO refunds (id, tenant_id, payment_id, amount,
                   provider_refund_id, status, reason, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (refund.id, refund.tenant_id, refund.payment_id, refund.amount,
                 refund.provider_refund_id, refund.status.value, refund.reason,
                 refund.created_at.isoformat(), refund.updated_at.isoformat()),
            )
        return refund

    def get_refund(self, refund_id: str) -> Refund | None:
        row = self._db.execute(
            "SELECT * FROM refunds WHERE id = ?", (refund_id,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_refund(dict(row))

    def list_refunds(self, tenant_id: str) -> list[Refund]:
        rows = self._db.execute(
            "SELECT * FROM refunds WHERE tenant_id = ? ORDER BY created_at DESC",
            (tenant_id,),
        ).fetchall()
        return [self._row_to_refund(dict(r)) for r in rows]

    # ── Internal ──

    @staticmethod
    def _row_to_account(row: dict) -> BillingAccount:
        return BillingAccount(
            id=row["id"],
            tenant_id=row["tenant_id"],
            currency=Currency(row["currency"]),
            balance=row["balance"],
            credit_limit=row["credit_limit"],
            wechat_openid=row.get("wechat_openid"),
            alipay_user_id=row.get("alipay_user_id"),
            stripe_customer_id=row.get("stripe_customer_id"),
            billing_email=row.get("billing_email", ""),
            billing_address=row.get("billing_address", ""),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    @staticmethod
    def _row_to_invoice(row: dict) -> Invoice:
        import json
        return Invoice(
            id=row["id"],
            tenant_id=row["tenant_id"],
            billing_account_id=row["billing_account_id"],
            invoice_number=row.get("invoice_number", ""),
            amount=row["amount"],
            currency=Currency(row["currency"]),
            status=InvoiceStatus(row["status"]),
            description=row.get("description", ""),
            line_items=json.loads(row.get("line_items_json") or "[]"),
            due_date=datetime.fromisoformat(row["due_date"]) if row.get("due_date") else None,
            paid_at=datetime.fromisoformat(row["paid_at"]) if row.get("paid_at") else None,
            period_start=datetime.fromisoformat(row["period_start"]) if row.get("period_start") else None,
            period_end=datetime.fromisoformat(row["period_end"]) if row.get("period_end") else None,
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    @staticmethod
    def _row_to_payment(row: dict) -> Payment:
        import json
        return Payment(
            id=row["id"],
            tenant_id=row["tenant_id"],
            billing_account_id=row["billing_account_id"],
            invoice_id=row.get("invoice_id"),
            amount=row["amount"],
            currency=Currency(row["currency"]),
            provider=PaymentProvider(row["provider"]),
            provider_payment_id=row.get("provider_payment_id", ""),
            status=PaymentStatus(row["status"]),
            description=row.get("description", ""),
            metadata=json.loads(row.get("metadata_json") or "{}"),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    @staticmethod
    def _row_to_refund(row: dict) -> Refund:
        return Refund(
            id=row["id"],
            tenant_id=row["tenant_id"],
            payment_id=row["payment_id"],
            amount=row["amount"],
            provider_refund_id=row.get("provider_refund_id", ""),
            status=RefundStatus(row["status"]),
            reason=row.get("reason", ""),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def close(self) -> None:
        if hasattr(self._db, "conn") and self._db.conn:
            self._db.conn.close()
