"""Open Platform Developer Domain Model — 第三方开发者账号与 API Key。

提供：
- DeveloperAccount — 开发者身份（绑定 user_id + tenant_id）
- DeveloperApiKey — API Key（hash 存储，绝不存明文）
- DeveloperStore Protocol — 存储层抽象
- API Key 安全工具（generate / hash / verify）
- 相关错误类

安全边界：
- API Key 明文仅在创建时返回一次
- DB 只存 key_hash + key_prefix
- verify 使用 constant-time comparison
- public to_dict() 不暴露 key_hash
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable
from uuid import uuid4


# ═══════════════════════════════════════════
# Enums
# ═══════════════════════════════════════════


class DeveloperStatus(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    REJECTED = "rejected"


class ApiKeyStatus(StrEnum):
    ACTIVE = "active"
    REVOKED = "revoked"
    EXPIRED = "expired"


# ═══════════════════════════════════════════
# Domain Models
# ═══════════════════════════════════════════


@dataclass
class DeveloperAccount:
    """开发者账号 — 绑定现有 User 体系。

    user_id + tenant_id 应唯一。status 默认 active（MVP）。
    """

    developer_id: str = field(default_factory=lambda: f"dev_{uuid4().hex[:12]}")
    user_id: str = ""
    tenant_id: str = ""
    display_name: str = ""
    organization_name: str | None = None
    website: str | None = None
    contact_email: str = ""
    status: str = "active"  # pending | active | suspended | rejected
    verified: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def is_active(self) -> bool:
        return self.status == DeveloperStatus.ACTIVE

    def to_dict(self) -> dict[str, Any]:
        return {
            "developer_id": self.developer_id,
            "user_id": self.user_id,
            "tenant_id": self.tenant_id,
            "display_name": self.display_name,
            "organization_name": self.organization_name,
            "website": self.website,
            "contact_email": self.contact_email,
            "status": self.status,
            "verified": self.verified,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


@dataclass
class DeveloperApiKey:
    """开发者 API Key — 安全存储。

    - key_hash: PBKDF2 hash，绝不存明文
    - key_prefix: 前缀，用于 UI 识别和 DB 索引
    - 明文 key 仅在创建时返回一次
    """

    api_key_id: str = field(default_factory=lambda: f"apk_{uuid4().hex[:12]}")
    developer_id: str = ""
    key_prefix: str = ""   # 8 字符前缀，用于 UI 识别和索引查询
    key_hash: str = ""     # PBKDF2 hash，绝不暴露
    name: str = ""         # 开发者自定义名称
    scopes: list[str] = field(default_factory=list)
    status: str = "active"  # active | revoked | expired
    expires_at: datetime | None = None
    last_used_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def is_active(self) -> bool:
        return self.status == ApiKeyStatus.ACTIVE

    def is_expired(self, at: datetime | None = None) -> bool:
        if self.expires_at is None:
            return False
        return (at or datetime.now(timezone.utc)) > self.expires_at

    def is_usable(self) -> bool:
        return self.is_active() and not self.is_expired()

    def to_dict(self) -> dict[str, Any]:
        """Public dict — 不暴露 key_hash。"""
        return {
            "api_key_id": self.api_key_id,
            "developer_id": self.developer_id,
            "key_prefix": self.key_prefix,
            "name": self.name,
            "scopes": self.scopes,
            "status": self.status,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "last_used_at": self.last_used_at.isoformat() if self.last_used_at else None,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def to_internal_dict(self) -> dict[str, Any]:
        """Internal dict (for store/serialization only — still does NOT expose hash)."""
        return self.to_dict()


# ═══════════════════════════════════════════
# API Key Security Tools
# ═══════════════════════════════════════════

_API_KEY_PREFIX = "cos_dev"
_PREFIX_LENGTH = 8           # key_prefix 长度
_SECRET_LENGTH = 32          # raw key 中 secret 部分的熵长度
_PBKDF2_ITERATIONS = 260_000
_PBKDF2_SALT_LENGTH = 16
_PBKDF2_DIGEST = "sha256"


def generate_api_key(prefix: str = _API_KEY_PREFIX) -> str:
    """生成一个新的 API Key。

    格式: cos_dev_<key_prefix>_<secret>

    - key_prefix: 8 位随机 hex，用于索引
    - secret: 64 字符 hex 高熵随机串（不含 _，方便 split 提取 prefix）

    返回完整 key。只应返回一次给调用者。
    """
    key_prefix = secrets.token_hex(_PREFIX_LENGTH // 2)
    secret = secrets.token_hex(_SECRET_LENGTH)
    return f"{prefix}_{key_prefix}_{secret}"


def _extract_prefix(raw_key: str) -> str:
    """从 raw key 中提取 key_prefix。"""
    parts = raw_key.split("_")
    if len(parts) >= 3:
        return parts[-2]
    return raw_key[:8]


def hash_api_key(raw_key: str) -> str:
    """使用 PBKDF2-HMAC-SHA256 对 API Key 进行 hash。

    返回格式: pbkdf2_sha256$iterations$salt$derived_key

    这个格式可直接用于 verify_api_key。
    """
    salt = secrets.token_bytes(_PBKDF2_SALT_LENGTH)
    derived = hashlib.pbkdf2_hmac(
        _PBKDF2_DIGEST,
        raw_key.encode("utf-8"),
        salt,
        _PBKDF2_ITERATIONS,
    )
    salt_hex = salt.hex()
    derived_hex = derived.hex()
    return f"pbkdf2_sha256${_PBKDF2_ITERATIONS}${salt_hex}${derived_hex}"


def verify_api_key(raw_key: str, stored_hash: str) -> bool:
    """使用 constant-time comparison 验证 API Key 是否匹配 hash。

    stored_hash 格式: pbkdf2_sha256$iterations$salt$derived_key
    """
    try:
        algo, iterations_str, salt_hex, stored_derived_hex = stored_hash.split("$")
        if algo != "pbkdf2_sha256":
            return False
        iterations = int(iterations_str)
        salt = bytes.fromhex(salt_hex)
        derived = hashlib.pbkdf2_hmac(
            _PBKDF2_DIGEST,
            raw_key.encode("utf-8"),
            salt,
            iterations,
        )
        return hmac.compare_digest(derived.hex(), stored_derived_hex)
    except (ValueError, AttributeError):
        return False


def get_api_key_prefix(raw_key: str) -> str:
    """从原始 key 中提取 prefix 用于 DB lookup。"""
    return _extract_prefix(raw_key)


# ═══════════════════════════════════════════
# DeveloperStore Protocol
# ═══════════════════════════════════════════


@runtime_checkable
class DeveloperStore(Protocol):
    """开发者存储协议 — 开发者账号与 API Key 管理。

    所有 tenant 操作必须按 tenant_id 隔离。
    """

    # ── Developer Account ──

    def create_developer(self, account: DeveloperAccount) -> DeveloperAccount: ...

    def get_developer(self, developer_id: str) -> DeveloperAccount | None: ...

    def get_developer_by_user(self, user_id: str, tenant_id: str) -> DeveloperAccount | None: ...

    def list_developers(
        self, *, tenant_id: str = "", status: str = "",
    ) -> list[DeveloperAccount]: ...

    def update_developer(self, account: DeveloperAccount) -> None: ...

    def update_developer_status(self, developer_id: str, status: str) -> bool: ...

    def verify_developer(self, developer_id: str) -> bool: ...

    def suspend_developer(self, developer_id: str) -> bool: ...

    # ── API Key ──

    def create_api_key(self, api_key: DeveloperApiKey) -> DeveloperApiKey: ...

    def get_api_key(self, api_key_id: str) -> DeveloperApiKey | None: ...

    def get_api_key_by_prefix(self, key_prefix: str) -> DeveloperApiKey | None: ...

    def list_api_keys(
        self, developer_id: str, *, include_revoked: bool = False,
    ) -> list[DeveloperApiKey]: ...

    def revoke_api_key(self, api_key_id: str, developer_id: str) -> bool: ...

    def update_api_key_last_used(self, api_key_id: str) -> None: ...

    def verify_and_lookup_api_key(self, raw_key: str) -> DeveloperApiKey | None: ...

    def delete_api_key(self, api_key_id: str, developer_id: str) -> bool: ...


# ═══════════════════════════════════════════
# API Key Scopes
# ═══════════════════════════════════════════

ALLOWED_DEVELOPER_API_SCOPES: frozenset[str] = frozenset({
    "developer:read",
    "developer:write",
    "api_keys:read",
    "api_keys:write",
    "submissions:read",
    "submissions:write",
    "submissions:submit",
    "marketplace:read",
    "agent:simulate",
    "agent:execute:simulation",
    "usage:read",
})

# Legacy scope aliases — maps old scope names to new canonical names
# Preserved for backward compatibility with existing API keys and tests.
# Deprecated: new keys should use canonical scopes.
LEGACY_SCOPE_ALIASES: dict[str, str] = {
    "agent:read": "submissions:read",
    "agent:write": "submissions:write",
    "agent:submit": "submissions:submit",
}

FORBIDDEN_DEVELOPER_API_SCOPES: frozenset[str] = frozenset({
    "admin:review",
    "admin:publish",
    "tenant:admin",
    "workspace:admin",
    "org:admin",
    "billing:write",
    "revenue:write",
    "system:super_admin",
    "runtime:unsafe_execute",
    "agent:execute:unsafe",
})


def normalize_api_scopes(scopes: list[str]) -> list[str]:
    """去重、排序、strip 空白。应用 legacy aliases。"""
    cleaned: list[str] = []
    seen: set[str] = set()
    for s in scopes:
        s = s.strip()
        if not s:
            continue
        # Apply legacy alias
        canonical = LEGACY_SCOPE_ALIASES.get(s, s)
        if canonical in seen:
            continue
        seen.add(canonical)
        cleaned.append(canonical)
    cleaned.sort()
    return cleaned


def validate_api_key_scopes(scopes: list[str]) -> None:
    """校验 API Key scopes。

    Raises:
        ApiKeyScopeError: scopes 为空、含未知 scope、含禁止 scope。
    """
    if not scopes:
        raise ApiKeyScopeError("API Key scopes 不能为空")

    normalized = normalize_api_scopes(scopes)

    for s in normalized:
        # 禁止 wildcard（在所有其他检查之前）
        if s == "*" or s.endswith(":*"):
            raise ApiKeyScopeError(f"不允许 wildcard scope: '{s}'")
        if s in FORBIDDEN_DEVELOPER_API_SCOPES:
            raise ApiKeyScopeError(f"scope '{s}' 不被允许用于 API Key")
        if s not in ALLOWED_DEVELOPER_API_SCOPES:
            raise ApiKeyScopeError(
                f"scope '{s}' 不在允许列表中。"
                f"允许的 scopes: {sorted(ALLOWED_DEVELOPER_API_SCOPES)}"
            )


def has_required_scopes(granted: list[str], required: list[str]) -> bool:
    """检查 granted scopes 是否包含所有 required scopes。"""
    granted_set = set(normalize_api_scopes(granted))
    required_set = set(normalize_api_scopes(required))
    return required_set.issubset(granted_set)


# ═══════════════════════════════════════════
# Error Classes
# ═══════════════════════════════════════════


class DeveloperAlreadyExistsError(Exception):
    def __init__(self, message: str = "开发者账号已存在"):
        super().__init__(message)


class DeveloperNotFoundError(Exception):
    def __init__(self, message: str = "开发者账号不存在"):
        super().__init__(message)


class ApiKeyNotFoundError(Exception):
    def __init__(self, message: str = "API Key 不存在"):
        super().__init__(message)


class ApiKeyScopeError(Exception):
    def __init__(self, message: str = "API Key scopes 不能为空"):
        super().__init__(message)


class DuplicateApiKeyError(Exception):
    def __init__(self, message: str = "API Key prefix 已存在"):
        super().__init__(message)
