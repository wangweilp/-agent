"""Enterprise RBAC Adapter — SQLite 实现 RBACStore 协议。

管理 permissions / roles / role_permissions / policies / role_assignments 五张表。

核心功能：
- RBAC: 角色 → 权限的层级授权
- ABAC: 基于属性的策略评估（支持 eq/neq/in/not_in/contains/regex 操作符）
- 禁止跨组织访问（默认 ABAC 策略强制执行）
"""
import json
import logging
import re
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any

from sqlite_utils import Database

from src.adapters.config import Settings
from src.core.rbac import (
    ABACEngine,
    AccessDecision,
    AccessRequest,
    EnterpriseRole,
    Permission,
    Policy,
    ResourceType,
    Role,
    RoleAssignment,
    get_default_abac_policies,
    get_default_role_permissions,
)

logger = logging.getLogger(__name__)

_RBAC_SCHEMA = """
CREATE TABLE IF NOT EXISTS permissions (
    id              TEXT PRIMARY KEY,
    resource        TEXT NOT NULL,
    action          TEXT NOT NULL,
    organization_id TEXT NOT NULL DEFAULT '',
    description     TEXT DEFAULT '',
    UNIQUE(resource, action, organization_id)
);
CREATE INDEX IF NOT EXISTS idx_perms_org ON permissions(organization_id);

CREATE TABLE IF NOT EXISTS roles (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    organization_id TEXT NOT NULL,
    description     TEXT DEFAULT '',
    is_system       INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(name, organization_id)
);
CREATE INDEX IF NOT EXISTS idx_roles_org ON roles(organization_id);

CREATE TABLE IF NOT EXISTS role_permissions (
    role_id       TEXT NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    permission_key TEXT NOT NULL,
    PRIMARY KEY (role_id, permission_key)
);

CREATE TABLE IF NOT EXISTS policies (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    effect          TEXT NOT NULL DEFAULT 'deny',
    organization_id TEXT NOT NULL DEFAULT '',
    description     TEXT DEFAULT '',
    priority        INTEGER NOT NULL DEFAULT 100,
    conditions_json TEXT NOT NULL DEFAULT '{}',
    enabled         INTEGER NOT NULL DEFAULT 1,
    is_system       INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_policies_org ON policies(organization_id);

CREATE TABLE IF NOT EXISTS role_assignments (
    id              TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL,
    role_id         TEXT NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    organization_id TEXT NOT NULL,
    scope_type      TEXT NOT NULL DEFAULT 'organization',
    scope_id        TEXT DEFAULT '',
    assigned_by     TEXT DEFAULT '',
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_ra_user ON role_assignments(user_id, organization_id);
CREATE INDEX IF NOT EXISTS idx_ra_role ON role_assignments(role_id);
"""


class DefaultABACEngine:
    """ABAC 策略评估引擎 — 支持条件匹配操作符。"""

    _OPERATORS = {
        "eq": lambda actual, expected: actual == expected,
        "neq": lambda actual, expected: actual != expected,
        "in": lambda actual, expected: actual in expected if isinstance(expected, list) else False,
        "not_in": lambda actual, expected: actual not in expected if isinstance(expected, list) else True,
        "contains": lambda actual, expected: expected in str(actual),
        "regex": lambda actual, expected: bool(re.match(str(expected), str(actual))) if expected else False,
        "gt": lambda actual, expected: float(actual) > float(expected),
        "lt": lambda actual, expected: float(actual) < float(expected),
    }

    def evaluate(self, request: AccessRequest,
                 policies: list[Policy],
                 subject_attrs: dict[str, Any],
                 resource_attrs: dict[str, Any]) -> AccessDecision:
        """评估 ABAC 策略 — deny 优先。

        规则：
        1. 无策略 → 允许（回退到 RBAC 判断）
        2. deny 策略优先 — 任一 deny 匹配则拒绝
        3. allow 策略至少一条匹配则允许
        4. 无匹配策略 → 拒绝（最小权限原则）
        """
        # 按 priority 升序排列（越小越优先）
        sorted_policies = sorted(
            [p for p in policies if p.enabled],
            key=lambda p: p.priority,
        )

        # 无 ABAC 策略 → 回退到 RBAC
        if not sorted_policies:
            return AccessDecision(
                allowed=True,
                reason="No ABAC policies — fallback to RBAC",
            )

        # 组合属性
        all_attrs = {
            "subject": subject_attrs,
            "resource": resource_attrs,
            "action": request.action.value,
            "resource_type": request.resource.value,
        }

        # 阶段 1: 检查 deny 策略
        for policy in sorted_policies:
            if policy.effect == "deny" and self._match_conditions(policy.conditions, all_attrs):
                return AccessDecision(
                    allowed=False,
                    reason=f"Denied by policy: {policy.name}",
                    matched_policy=policy.id,
                )

        # 阶段 2: 检查 allow 策略
        for policy in sorted_policies:
            if policy.effect == "allow" and self._match_conditions(policy.conditions, all_attrs):
                return AccessDecision(
                    allowed=True,
                    reason=f"Allowed by policy: {policy.name}",
                    matched_policy=policy.id,
                )

        return AccessDecision(allowed=False, reason="No matching allow policy (default deny)")

    def _match_conditions(self, conditions: dict[str, Any],
                          attrs: dict[str, Any]) -> bool:
        """检查所有条件是否匹配。

        conditions 格式:
          {"subject.org_id": {"eq": "org-1"}}
          {"resource.org_id": {"neq": "subject.org_id"}, "action": {"in": ["create", "read"]}}
        """
        if not conditions:
            return True
        for path, checks in conditions.items():
            actual = self._resolve_path(path, attrs)
            if not self._evaluate_checks(actual, checks, attrs):
                return False
        return True

    def _resolve_path(self, path: str, attrs: dict[str, Any]) -> Any:
        """解析点分路径，如 'subject.org_id' → attrs['subject']['org_id']。"""
        parts = path.split(".")
        current = attrs
        for part in parts:
            if isinstance(current, dict):
                current = current.get(part)
            else:
                return None
        return current

    def _evaluate_checks(self, actual: Any, checks: dict[str, Any],
                         attrs: dict[str, Any]) -> bool:
        """评估单个字段上的所有检查条件（AND 关系）。

        如果 expected 是路径引用（以 'subject.' 或 'resource.' 前缀），
        自动解析为实际的属性值进行比较。
        """
        for op, expected in checks.items():
            # 如果 expected 是路径引用，解析之
            resolved_expected = expected
            if isinstance(expected, str) and "." in expected:
                resolved = self._resolve_path(expected, attrs)
                if resolved is not None:
                    resolved_expected = resolved

            operator_fn = self._OPERATORS.get(op)
            if operator_fn is None:
                continue
            if actual is None:
                return False
            try:
                if not operator_fn(actual, resolved_expected):
                    return False
            except (TypeError, ValueError):
                return False
        return True


class RBACStoreAdapter:
    """RBACStore 的 SQLite 实现。"""

    def __init__(self, config: Settings, db_path: str | None = None) -> None:
        path = db_path or config.sqlite_db_path
        conn = sqlite3.connect(path, check_same_thread=False)
        self._db = Database(conn)
        self._db.conn.row_factory = sqlite3.Row
        self._write_lock = threading.Lock()
        self._abac_engine: ABACEngine = DefaultABACEngine()
        self._init_schema()

    def _init_schema(self) -> None:
        for stmt in _RBAC_SCHEMA.strip().split(";"):
            s = stmt.strip()
            if s:
                self._db.execute(s)

    # ── Permission CRUD ──

    def create_permission(self, p: Permission) -> Permission:
        with self._write_lock, self._db.conn:
            self._db.execute(
                """INSERT OR IGNORE INTO permissions (id, resource, action, organization_id, description)
                   VALUES (?, ?, ?, ?, ?)""",
                (p.id, p.resource.value, p.action.value, p.organization_id, p.description),
            )
        return p

    def get_permission(self, perm_id: str) -> Permission | None:
        row = self._db.execute(
            "SELECT * FROM permissions WHERE id = ?", (perm_id,)
        ).fetchone()
        return self._row_to_permission(dict(row)) if row else None

    def list_permissions(self, organization_id: str) -> list[Permission]:
        rows = self._db.execute(
            """SELECT * FROM permissions
               WHERE organization_id = ? OR organization_id = ''
               ORDER BY resource, action""",
            (organization_id,),
        ).fetchall()
        return [self._row_to_permission(dict(r)) for r in rows]

    def delete_permission(self, perm_id: str) -> None:
        with self._write_lock, self._db.conn:
            self._db.execute("DELETE FROM permissions WHERE id = ?", (perm_id,))

    # ── Role CRUD ──

    def create_role(self, role: Role) -> Role:
        with self._write_lock, self._db.conn:
            self._db.execute(
                """INSERT OR IGNORE INTO roles (id, name, organization_id, description, is_system, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (role.id, role.name, role.organization_id, role.description,
                 int(role.is_system), role.created_at.isoformat()),
            )
            # 写入权限关联
            for pk in role.permissions:
                self._db.execute(
                    "INSERT OR IGNORE INTO role_permissions (role_id, permission_key) VALUES (?, ?)",
                    (role.id, pk),
                )
        logger.info("rbac:role_created", extra={"role_id": role.id, "role_name": role.name})
        return role

    def get_role(self, role_id: str) -> Role | None:
        row = self._db.execute(
            "SELECT * FROM roles WHERE id = ?", (role_id,)
        ).fetchone()
        if row is None:
            return None
        r = dict(row)
        perms = self._get_role_permission_keys(role_id)
        return self._row_to_role(r, perms)

    def get_role_by_name(self, name: str, organization_id: str) -> Role | None:
        row = self._db.execute(
            "SELECT * FROM roles WHERE name = ? AND organization_id = ?",
            (name, organization_id),
        ).fetchone()
        if row is None:
            return None
        r = dict(row)
        perms = self._get_role_permission_keys(r["id"])
        return self._row_to_role(r, perms)

    def list_roles(self, organization_id: str) -> list[Role]:
        rows = self._db.execute(
            "SELECT * FROM roles WHERE organization_id = ? ORDER BY is_system DESC, name",
            (organization_id,),
        ).fetchall()
        result: list[Role] = []
        for row in rows:
            r = dict(row)
            perms = self._get_role_permission_keys(r["id"])
            result.append(self._row_to_role(r, perms))
        return result

    def update_role(self, role: Role) -> None:
        with self._write_lock, self._db.conn:
            self._db.execute(
                "UPDATE roles SET name=?, description=? WHERE id=?",
                (role.name, role.description, role.id),
            )

    def delete_role(self, role_id: str) -> None:
        with self._write_lock, self._db.conn:
            self._db.execute("DELETE FROM role_permissions WHERE role_id = ?", (role_id,))
            self._db.execute("DELETE FROM roles WHERE id = ? AND is_system = 0", (role_id,))

    def add_permission_to_role(self, role_id: str, permission_key: str) -> None:
        with self._write_lock, self._db.conn:
            self._db.execute(
                "INSERT OR IGNORE INTO role_permissions (role_id, permission_key) VALUES (?, ?)",
                (role_id, permission_key),
            )

    def remove_permission_from_role(self, role_id: str, permission_key: str) -> None:
        with self._write_lock, self._db.conn:
            self._db.execute(
                "DELETE FROM role_permissions WHERE role_id = ? AND permission_key = ?",
                (role_id, permission_key),
            )

    # ── Policy (ABAC) CRUD ──

    def create_policy(self, policy: Policy) -> Policy:
        with self._write_lock, self._db.conn:
            self._db.execute(
                """INSERT INTO policies (id, name, effect, organization_id, description,
                   priority, conditions_json, enabled, is_system, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (policy.id, policy.name, policy.effect, policy.organization_id,
                 policy.description, policy.priority,
                 json.dumps(policy.conditions, ensure_ascii=False),
                 int(policy.enabled), int(False),  # is_system not stored per-instance
                 policy.created_at.isoformat()),
            )
        return policy

    def get_policy(self, policy_id: str) -> Policy | None:
        row = self._db.execute(
            "SELECT * FROM policies WHERE id = ?", (policy_id,)
        ).fetchone()
        return self._row_to_policy(dict(row)) if row else None

    def list_policies(self, organization_id: str) -> list[Policy]:
        rows = self._db.execute(
            """SELECT * FROM policies
               WHERE organization_id = ? OR organization_id = ''
               ORDER BY priority, created_at DESC""",
            (organization_id,),
        ).fetchall()
        return [self._row_to_policy(dict(r)) for r in rows]

    def update_policy(self, policy: Policy) -> None:
        with self._write_lock, self._db.conn:
            self._db.execute(
                """UPDATE policies SET name=?, effect=?, description=?, priority=?,
                   conditions_json=?, enabled=? WHERE id=?""",
                (policy.name, policy.effect, policy.description, policy.priority,
                 json.dumps(policy.conditions, ensure_ascii=False),
                 int(policy.enabled), policy.id),
            )

    def delete_policy(self, policy_id: str) -> None:
        with self._write_lock, self._db.conn:
            self._db.execute("DELETE FROM policies WHERE id = ? AND is_system = 0", (policy_id,))

    # ── Role Assignment ──

    def assign_role(self, assignment: RoleAssignment) -> RoleAssignment:
        with self._write_lock, self._db.conn:
            self._db.execute(
                """INSERT OR REPLACE INTO role_assignments
                   (id, user_id, role_id, organization_id, scope_type, scope_id, assigned_by, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (assignment.id, assignment.user_id, assignment.role_id,
                 assignment.organization_id, assignment.scope_type,
                 assignment.scope_id, assignment.assigned_by,
                 assignment.created_at.isoformat()),
            )
        return assignment

    def get_user_assignments(self, user_id: str,
                             organization_id: str) -> list[RoleAssignment]:
        rows = self._db.execute(
            """SELECT * FROM role_assignments
               WHERE user_id = ? AND organization_id = ?
               ORDER BY created_at DESC""",
            (user_id, organization_id),
        ).fetchall()
        return [self._row_to_assignment(dict(r)) for r in rows]

    def remove_assignment(self, assignment_id: str) -> None:
        with self._write_lock, self._db.conn:
            self._db.execute(
                "DELETE FROM role_assignments WHERE id = ?", (assignment_id,)
            )

    def get_user_roles(self, user_id: str, organization_id: str) -> list[Role]:
        rows = self._db.execute(
            """SELECT DISTINCT r.* FROM roles r
               JOIN role_assignments ra ON r.id = ra.role_id
               WHERE ra.user_id = ? AND ra.organization_id = ?""",
            (user_id, organization_id),
        ).fetchall()
        result: list[Role] = []
        for row in rows:
            r = dict(row)
            perms = self._get_role_permission_keys(r["id"])
            result.append(self._row_to_role(r, perms))
        return result

    # ── Access Check ──

    def check_access(self, request: AccessRequest) -> AccessDecision:
        """完整的 RBAC + ABAC 权限检查。

        流程：
        0. 超级管理员直接通过（绕过所有检查）
        1. ABAC 策略检查（跨组织隔离等）
        2. RBAC 角色权限检查
        3. 合并结果：两者都允许才允许
        """
        # Step 0: 超级管理员绕过所有检查
        if request.is_super_admin:
            return AccessDecision(
                allowed=True,
                reason="Super admin — bypass all RBAC/ABAC checks",
            )

        # Step 1: ABAC check
        policies = self.list_policies(request.organization_id)
        subject_attrs = {
            "user_id": request.user_id,
            "org_id": request.organization_id,
        }
        resource_attrs = {
            "org_id": request.organization_id,
            "resource_type": request.resource.value,
            "resource_id": request.resource_id,
        }
        abac_decision = self._abac_engine.evaluate(
            request, policies, subject_attrs, resource_attrs,
        )
        if not abac_decision.allowed:
            return abac_decision

        # Step 2: RBAC check
        user_roles = self.get_user_roles(request.user_id, request.organization_id)
        required_perm = f"{request.resource.value}:{request.action.value}:*"

        for role in user_roles:
            if required_perm in role.permissions:
                return AccessDecision(
                    allowed=True,
                    reason=f"Allowed by role: {role.name}",
                    matched_role=role.id,
                )

        # 检查全局权限（无组织限制）
        global_perm = f"{request.resource.value}:{request.action.value}:"
        for role in user_roles:
            for pk in role.permissions:
                if pk.startswith(global_perm):
                    return AccessDecision(
                        allowed=True,
                        reason=f"Allowed by role: {role.name} (global perm)",
                        matched_role=role.id,
                    )

        return AccessDecision(
            allowed=False,
            reason=f"No role has permission {required_perm}",
        )

    # ── Bootstrap ──

    def bootstrap_organization_roles(self, organization_id: str) -> dict[str, Role]:
        """为组织创建所有系统预定义角色和默认 ABAC 策略。

        Returns:
            {role_name: Role} 映射
        """
        existing = self.list_roles(organization_id)
        if existing:
            return {r.name: r for r in existing}

        role_perms = get_default_role_permissions()
        created: dict[str, Role] = {}

        for enterprise_role, perm_keys in role_perms.items():
            role = Role(
                name=enterprise_role.value,
                organization_id=organization_id,
                permissions=perm_keys,
                is_system=True,
                description=f"System role: {enterprise_role.value}",
            )
            created[enterprise_role.value] = self.create_role(role)

        # 创建默认 ABAC 策略
        for policy in get_default_abac_policies(organization_id):
            self.create_policy(policy)

        logger.info(
            "rbac:bootstrap_complete",
            extra={"org_id": organization_id, "roles": len(created)},
        )
        return created

    # ── Internal ──

    def _get_role_permission_keys(self, role_id: str) -> list[str]:
        rows = self._db.execute(
            "SELECT permission_key FROM role_permissions WHERE role_id = ?",
            (role_id,),
        ).fetchall()
        return [r["permission_key"] for r in rows]

    @staticmethod
    def _row_to_permission(row: dict) -> Permission:
        return Permission(
            id=row["id"],
            resource=ResourceType(row["resource"]),
            action=row["action"],
            organization_id=row.get("organization_id", ""),
            description=row.get("description", ""),
        )

    @staticmethod
    def _row_to_role(row: dict, permissions: list[str]) -> Role:
        return Role(
            id=row["id"],
            name=row["name"],
            organization_id=row["organization_id"],
            permissions=permissions,
            description=row.get("description", ""),
            is_system=bool(row.get("is_system", 0)),
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    @staticmethod
    def _row_to_policy(row: dict) -> Policy:
        return Policy(
            id=row["id"],
            name=row["name"],
            effect=row["effect"],
            organization_id=row.get("organization_id", ""),
            description=row.get("description", ""),
            priority=row.get("priority", 100),
            conditions=json.loads(row.get("conditions_json") or "{}"),
            enabled=bool(row.get("enabled", 1)),
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    @staticmethod
    def _row_to_assignment(row: dict) -> RoleAssignment:
        return RoleAssignment(
            id=row["id"],
            user_id=row["user_id"],
            role_id=row["role_id"],
            organization_id=row["organization_id"],
            scope_type=row.get("scope_type", "organization"),
            scope_id=row.get("scope_id", ""),
            assigned_by=row.get("assigned_by", ""),
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def close(self) -> None:
        if hasattr(self._db, "conn") and self._db.conn:
            self._db.conn.close()
