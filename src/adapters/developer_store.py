"""SQLite Developer Store — 实现 DeveloperStore 协议。"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from src.adapters.config import Settings
from src.adapters.sqlite_connection import create_sqlite_db, execute_with_retry
from src.open_platform.developer import (
    ApiKeyScopeError,
    ApiKeyStatus,
    DeveloperAccount,
    DeveloperAlreadyExistsError,
    DeveloperApiKey,
    DeveloperNotFoundError,
    DeveloperStatus,
    DuplicateApiKeyError,
    generate_api_key,
    get_api_key_prefix,
    hash_api_key,
    verify_api_key,
)

logger = logging.getLogger(__name__)

_DEVELOPER_SCHEMA = """
CREATE TABLE IF NOT EXISTS developer_accounts (
    developer_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    display_name TEXT NOT NULL DEFAULT '',
    organization_name TEXT,
    website TEXT,
    contact_email TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active',
    verified INTEGER NOT NULL DEFAULT 0,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_dev_user_tenant
    ON developer_accounts(user_id, tenant_id);
CREATE INDEX IF NOT EXISTS idx_dev_tenant_id ON developer_accounts(tenant_id);
CREATE INDEX IF NOT EXISTS idx_dev_status ON developer_accounts(status);

CREATE TABLE IF NOT EXISTS developer_api_keys (
    api_key_id TEXT PRIMARY KEY,
    developer_id TEXT NOT NULL,
    key_prefix TEXT NOT NULL UNIQUE,
    key_hash TEXT NOT NULL,
    name TEXT NOT NULL DEFAULT '',
    scopes_json TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'active',
    expires_at TEXT,
    last_used_at TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_apk_developer_id ON developer_api_keys(developer_id);
CREATE INDEX IF NOT EXISTS idx_apk_status ON developer_api_keys(status);
CREATE INDEX IF NOT EXISTS idx_apk_key_prefix ON developer_api_keys(key_prefix);
"""


class SQLiteDeveloperStore:
    def __init__(self, config: Settings, db_path: str | None = None) -> None:
        path = db_path or config.sqlite_db_path
        self._db = create_sqlite_db(path)
        execute_with_retry(lambda: self._init_schema(), label="developer_init_schema")

    def _init_schema(self) -> None:
        for stmt in _DEVELOPER_SCHEMA.strip().split(";"):
            s = stmt.strip()
            if s:
                self._db.execute(s)
        try:
            self._db.conn.commit()
        except Exception:
            pass

    def flush(self) -> None:
        """显式提交底层连接事务，释放写锁。autocommit 模式下为安全 no-op。"""
        try:
            if hasattr(self._db, "conn") and self._db.conn:
                self._db.conn.commit()
        except Exception:
            pass

    def _exec(self, sql: str, params: list[Any] | None = None) -> Any:
        return self._db.execute(sql, params or [])

    # ── Developer Account ──

    def create_developer(self, account: DeveloperAccount) -> DeveloperAccount:
        existing = self.get_developer_by_user(account.user_id, account.tenant_id)
        if existing is not None:
            raise DeveloperAlreadyExistsError(
                f"开发者已存在: user={account.user_id} tenant={account.tenant_id}")
        self._exec("""INSERT INTO developer_accounts (
            developer_id, user_id, tenant_id, display_name, organization_name,
            website, contact_email, status, verified, metadata_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?)""", [
            account.developer_id, account.user_id, account.tenant_id,
            account.display_name, account.organization_name,
            account.website, account.contact_email, account.status,
            int(account.verified), json.dumps(account.metadata, ensure_ascii=False),
        ])
        return account

    def get_developer(self, developer_id: str) -> DeveloperAccount | None:
        row = next(self._exec("SELECT * FROM developer_accounts WHERE developer_id=?", [developer_id]), None)
        return self._dev(dict(row)) if row else None

    def get_developer_by_user(self, user_id: str, tenant_id: str) -> DeveloperAccount | None:
        row = next(self._exec(
            "SELECT * FROM developer_accounts WHERE user_id=? AND tenant_id=?", [user_id, tenant_id]), None)
        return self._dev(dict(row)) if row else None

    def list_developers(self, *, tenant_id: str = "", status: str = "") -> list[DeveloperAccount]:
        sql = "SELECT * FROM developer_accounts WHERE 1=1"
        p: list[Any] = []
        if tenant_id:
            sql += " AND tenant_id=?"
            p.append(tenant_id)
        if status:
            sql += " AND status=?"
            p.append(status)
        sql += " ORDER BY created_at DESC"
        return [self._dev(dict(r)) for r in self._exec(sql, p)]

    def update_developer(self, account: DeveloperAccount) -> None:
        self._exec("""UPDATE developer_accounts SET display_name=?, organization_name=?,
            website=?, contact_email=?, metadata_json=?, updated_at=?
            WHERE developer_id=?""", [
            account.display_name, account.organization_name,
            account.website, account.contact_email,
            json.dumps(account.metadata, ensure_ascii=False),
            datetime.now(timezone.utc).isoformat(), account.developer_id,
        ])

    def update_developer_status(self, developer_id: str, status: str) -> bool:
        dev = self.get_developer(developer_id)
        if dev is None:
            return False
        self._exec("UPDATE developer_accounts SET status=?, updated_at=? WHERE developer_id=?",
                   [status, datetime.now(timezone.utc).isoformat(), developer_id])
        return True

    def verify_developer(self, developer_id: str) -> bool:
        dev = self.get_developer(developer_id)
        if dev is None:
            return False
        self._exec("UPDATE developer_accounts SET verified=1, updated_at=? WHERE developer_id=?",
                   [datetime.now(timezone.utc).isoformat(), developer_id])
        return True

    def suspend_developer(self, developer_id: str) -> bool:
        return self.update_developer_status(developer_id, DeveloperStatus.SUSPENDED)

    # ── API Key ──

    def create_api_key(self, api_key: DeveloperApiKey) -> DeveloperApiKey:
        if not api_key.scopes:
            raise ApiKeyScopeError("API Key scopes 不能为空")

        existing = self.get_api_key_by_prefix(api_key.key_prefix)
        if existing is not None:
            raise DuplicateApiKeyError(f"API Key prefix 已存在: {api_key.key_prefix}")

        self._exec("""INSERT INTO developer_api_keys (
            api_key_id, developer_id, key_prefix, key_hash, name,
            scopes_json, status, expires_at, metadata_json
        ) VALUES (?,?,?,?,?,?,?,?,?)""", [
            api_key.api_key_id, api_key.developer_id,
            api_key.key_prefix, api_key.key_hash, api_key.name,
            json.dumps(api_key.scopes, ensure_ascii=False),
            api_key.status,
            api_key.expires_at.isoformat() if api_key.expires_at else None,
            json.dumps(api_key.metadata, ensure_ascii=False),
        ])
        return api_key

    def get_api_key(self, api_key_id: str) -> DeveloperApiKey | None:
        row = next(self._exec("SELECT * FROM developer_api_keys WHERE api_key_id=?", [api_key_id]), None)
        return self._apk(dict(row)) if row else None

    def get_api_key_by_prefix(self, key_prefix: str) -> DeveloperApiKey | None:
        row = next(self._exec("SELECT * FROM developer_api_keys WHERE key_prefix=?", [key_prefix]), None)
        return self._apk(dict(row)) if row else None

    def list_api_keys(self, developer_id: str, *, include_revoked: bool = False) -> list[DeveloperApiKey]:
        sql = "SELECT * FROM developer_api_keys WHERE developer_id=?"
        p: list[Any] = [developer_id]
        if not include_revoked:
            sql += " AND status='active'"
        sql += " ORDER BY created_at DESC"
        return [self._apk(dict(r)) for r in self._exec(sql, p)]

    def revoke_api_key(self, api_key_id: str, developer_id: str) -> bool:
        key = self.get_api_key(api_key_id)
        if key is None or key.developer_id != developer_id:
            return False
        self._exec(
            "UPDATE developer_api_keys SET status=?, last_used_at=? WHERE api_key_id=? AND developer_id=?",
            [ApiKeyStatus.REVOKED, None, api_key_id, developer_id],
        )
        return True

    def update_api_key_last_used(self, api_key_id: str) -> None:
        self._exec(
            "UPDATE developer_api_keys SET last_used_at=? WHERE api_key_id=?",
            [datetime.now(timezone.utc).isoformat(), api_key_id],
        )

    def verify_and_lookup_api_key(self, raw_key: str) -> DeveloperApiKey | None:
        """通过 raw key 查找并验证 API Key。

        1. 从 raw_key 提取 key_prefix
        2. 按 prefix 查 DB
        3. verify hash
        4. 检查 status / expires_at
        5. 更新 last_used_at
        """
        key_prefix = get_api_key_prefix(raw_key)
        key = self.get_api_key_by_prefix(key_prefix)
        if key is None:
            return None

        # Verify hash
        if not verify_api_key(raw_key, key.key_hash):
            return None

        # Check status
        if not key.is_usable():
            return None

        # Update last_used_at
        self.update_api_key_last_used(key.api_key_id)

        return key

    def delete_api_key(self, api_key_id: str, developer_id: str) -> bool:
        """软删除（revoke）API Key。"""
        return self.revoke_api_key(api_key_id, developer_id)

    # ── Converters ──

    @staticmethod
    def _dev(row: dict) -> DeveloperAccount:
        return DeveloperAccount(
            developer_id=row["developer_id"],
            user_id=row["user_id"],
            tenant_id=row["tenant_id"],
            display_name=row.get("display_name", ""),
            organization_name=row.get("organization_name"),
            website=row.get("website"),
            contact_email=row.get("contact_email", ""),
            status=row.get("status", "active"),
            verified=bool(row.get("verified", 0)),
            metadata=json.loads(row.get("metadata_json", "{}")),
            created_at=_safe_parse_datetime(row.get("created_at")),
            updated_at=_safe_parse_datetime(row.get("updated_at")),
        )

    @staticmethod
    def _apk(row: dict) -> DeveloperApiKey:
        ea = None
        if row.get("expires_at"):
            try:
                ea = datetime.fromisoformat(str(row["expires_at"]).replace("Z", "+00:00"))
            except (ValueError, OSError):
                pass
        lua = None
        if row.get("last_used_at"):
            try:
                lua = datetime.fromisoformat(str(row["last_used_at"]).replace("Z", "+00:00"))
            except (ValueError, OSError):
                pass
        return DeveloperApiKey(
            api_key_id=row["api_key_id"],
            developer_id=row["developer_id"],
            key_prefix=row["key_prefix"],
            key_hash=row["key_hash"],
            name=row.get("name", ""),
            scopes=json.loads(row.get("scopes_json", "[]")),
            status=row.get("status", "active"),
            expires_at=ea,
            last_used_at=lua,
            metadata=json.loads(row.get("metadata_json", "{}")),
            created_at=_safe_parse_datetime(row.get("created_at")),
        )


def _safe_parse_datetime(raw: str | None) -> datetime:
    if not raw:
        return datetime.now(timezone.utc)
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return datetime.now(timezone.utc)
