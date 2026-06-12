"""Open Platform API Auth — DeveloperApiPrincipal。

与 JWT TokenPayload 的边界：
- DeveloperApiPrincipal 不含 role、不含 super_admin、不含 email
- 只能在 Developer API 的 API Key 路径中使用
- 不可用于 Admin Review / Publish / Tenant Admin
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class DeveloperApiPrincipal:
    """API Key 认证后的 principal。

    安全约束：
    - 不包含 raw_key（绝不泄露）
    - 不包含 key_hash（绝不泄露）
    - 不包含 role（API Key 不是 user role）
    - 不包含 is_super_admin（永远 False）
    - auth_type 固定为 "developer_api_key"
    """

    developer_id: str
    user_id: str
    tenant_id: str
    api_key_id: str
    key_prefix: str
    scopes: list[str] = field(default_factory=list)
    auth_type: str = "developer_api_key"

    def has_scope(self, scope: str) -> bool:
        """检查是否拥有指定 scope。"""
        return scope in self.scopes

    def has_all_scopes(self, scopes: list[str]) -> bool:
        """检查是否拥有所有指定 scopes。"""
        from src.open_platform.developer import has_required_scopes
        return has_required_scopes(self.scopes, scopes)

    def to_dict(self) -> dict[str, Any]:
        """Public dict — 不泄露 key_prefix（仅前 4 字符用于日志）。"""
        return {
            "developer_id": self.developer_id,
            "user_id": self.user_id,
            "tenant_id": self.tenant_id,
            "api_key_id": self.api_key_id,
            "scopes": list(self.scopes),
            "auth_type": self.auth_type,
        }

    def to_safe_dict(self) -> dict[str, Any]:
        """安全 dict — key_prefix 仅展示前 4 字符。"""
        d = self.to_dict()
        d["key_prefix_hint"] = self.key_prefix[:4] + "****" if len(self.key_prefix) >= 4 else "****"
        return d
