"""Enterprise Organization Adapter — SQLite 实现 OrganizationStore 协议。

管理 organizations / business_units / departments / positions 四张表。
自动生成默认组织结构：集团 → 研发中心 / 产品中心 / 市场中心 / 运营中心
"""
import logging
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any

from sqlite_utils import Database

from src.adapters.config import Settings
from src.core.organization import (
    BusinessUnit,
    Department,
    Organization,
    OrgTreeNode,
    Position,
)

logger = logging.getLogger(__name__)

_ORG_SCHEMA = """
CREATE TABLE IF NOT EXISTS organizations (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    industry    TEXT DEFAULT '',
    owner_id    TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_orgs_owner ON organizations(owner_id);

CREATE TABLE IF NOT EXISTS business_units (
    id              TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    parent_id       TEXT,
    description     TEXT DEFAULT '',
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_bu_org ON business_units(organization_id);
CREATE INDEX IF NOT EXISTS idx_bu_parent ON business_units(parent_id);

CREATE TABLE IF NOT EXISTS departments (
    id              TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    business_unit_id TEXT NOT NULL REFERENCES business_units(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    parent_id       TEXT,
    description     TEXT DEFAULT '',
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_dept_org ON departments(organization_id);
CREATE INDEX IF NOT EXISTS idx_dept_bu ON departments(business_unit_id);
CREATE INDEX IF NOT EXISTS idx_dept_parent ON departments(parent_id);

CREATE TABLE IF NOT EXISTS positions (
    id              TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    department_id    TEXT NOT NULL REFERENCES departments(id) ON DELETE CASCADE,
    user_id         TEXT NOT NULL,
    title           TEXT NOT NULL DEFAULT '',
    is_manager      INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_pos_org ON positions(organization_id);
CREATE INDEX IF NOT EXISTS idx_pos_dept ON positions(department_id);
CREATE INDEX IF NOT EXISTS idx_pos_user ON positions(user_id);
"""

# 默认组织架构
DEFAULT_ORG_STRUCTURE = [
    ("研发中心", ["后端组", "前端组", "数据组", "AI组"]),
    ("产品中心", ["产品设计组", "用户体验组"]),
    ("市场中心", ["品牌组", "增长组", "渠道组"]),
    ("运营中心", ["客户成功组", "技术支持组"]),
]


class OrganizationStoreAdapter:
    """OrganizationStore 的 SQLite 实现。"""

    def __init__(self, config: Settings, db_path: str | None = None) -> None:
        path = db_path or config.sqlite_db_path
        conn = sqlite3.connect(path, check_same_thread=False)
        self._db = Database(conn)
        self._db.conn.row_factory = sqlite3.Row
        self._write_lock = threading.Lock()
        self._init_schema()

    def _init_schema(self) -> None:
        for stmt in _ORG_SCHEMA.strip().split(";"):
            s = stmt.strip()
            if s:
                self._db.execute(s)

    # ── Organization CRUD ──

    def create_organization(self, name: str, owner_id: str,
                            industry: str = "") -> Organization:
        org = Organization(name=name, owner_id=owner_id, industry=industry)
        with self._write_lock, self._db.conn:
            self._db.execute(
                """INSERT INTO organizations (id, name, industry, owner_id, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (org.id, org.name, org.industry, org.owner_id, org.created_at.isoformat()),
            )
        logger.info("org:created", extra={"org_id": org.id, "org_name": name})
        # 自动创建默认组织结构
        self._create_default_structure(org.id)
        return org

    def _create_default_structure(self, org_id: str) -> None:
        """为新建组织创建默认 BU + 部门结构。"""
        for bu_name, dept_names in DEFAULT_ORG_STRUCTURE:
            bu = BusinessUnit(organization_id=org_id, name=bu_name)
            with self._write_lock, self._db.conn:
                self._db.execute(
                    """INSERT INTO business_units (id, organization_id, name, created_at)
                       VALUES (?, ?, ?, ?)""",
                    (bu.id, bu.organization_id, bu.name, bu.created_at.isoformat()),
                )
            for dept_name in dept_names:
                dept = Department(organization_id=org_id, business_unit_id=bu.id, name=dept_name)
                with self._write_lock, self._db.conn:
                    self._db.execute(
                        """INSERT INTO departments (id, organization_id, business_unit_id, name, created_at)
                           VALUES (?, ?, ?, ?, ?)""",
                        (dept.id, dept.organization_id, dept.business_unit_id,
                         dept.name, dept.created_at.isoformat()),
                    )

    def get_organization(self, org_id: str) -> Organization | None:
        row = self._db.execute(
            "SELECT * FROM organizations WHERE id = ?", (org_id,)
        ).fetchone()
        return self._row_to_org(dict(row)) if row else None

    def list_organizations(self, user_id: str) -> list[Organization]:
        """列出用户所属的所有组织（通过 position 关联）。"""
        rows = self._db.execute(
            """SELECT DISTINCT o.* FROM organizations o
               JOIN positions p ON o.id = p.organization_id
               WHERE p.user_id = ?
               UNION
               SELECT * FROM organizations WHERE owner_id = ?
               ORDER BY created_at DESC""",
            (user_id, user_id),
        ).fetchall()
        return [self._row_to_org(dict(r)) for r in rows]

    def update_organization(self, org: Organization) -> None:
        with self._write_lock, self._db.conn:
            self._db.execute(
                "UPDATE organizations SET name=?, industry=? WHERE id=?",
                (org.name, org.industry, org.id),
            )

    def delete_organization(self, org_id: str) -> None:
        with self._write_lock, self._db.conn:
            self._db.execute("DELETE FROM organizations WHERE id = ?", (org_id,))

    # ── BusinessUnit CRUD ──

    def create_business_unit(self, organization_id: str, name: str,
                             parent_id: str | None = None,
                             description: str = "") -> BusinessUnit:
        bu = BusinessUnit(
            organization_id=organization_id, name=name,
            parent_id=parent_id, description=description,
        )
        with self._write_lock, self._db.conn:
            self._db.execute(
                """INSERT INTO business_units (id, organization_id, name, parent_id, description, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (bu.id, bu.organization_id, bu.name, bu.parent_id, bu.description,
                 bu.created_at.isoformat()),
            )
        return bu

    def get_business_unit(self, bu_id: str) -> BusinessUnit | None:
        row = self._db.execute(
            "SELECT * FROM business_units WHERE id = ?", (bu_id,)
        ).fetchone()
        return self._row_to_bu(dict(row)) if row else None

    def list_business_units(self, organization_id: str) -> list[BusinessUnit]:
        rows = self._db.execute(
            "SELECT * FROM business_units WHERE organization_id = ? ORDER BY created_at",
            (organization_id,),
        ).fetchall()
        return [self._row_to_bu(dict(r)) for r in rows]

    def update_business_unit(self, bu: BusinessUnit) -> None:
        with self._write_lock, self._db.conn:
            self._db.execute(
                "UPDATE business_units SET name=?, parent_id=?, description=? WHERE id=?",
                (bu.name, bu.parent_id, bu.description, bu.id),
            )

    def delete_business_unit(self, bu_id: str) -> None:
        with self._write_lock, self._db.conn:
            self._db.execute("DELETE FROM business_units WHERE id = ?", (bu_id,))

    # ── Department CRUD ──

    def create_department(self, organization_id: str, business_unit_id: str, name: str,
                          parent_id: str | None = None,
                          description: str = "") -> Department:
        dept = Department(
            organization_id=organization_id, business_unit_id=business_unit_id,
            name=name, parent_id=parent_id, description=description,
        )
        with self._write_lock, self._db.conn:
            self._db.execute(
                """INSERT INTO departments (id, organization_id, business_unit_id,
                   name, parent_id, description, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (dept.id, dept.organization_id, dept.business_unit_id,
                 dept.name, dept.parent_id, dept.description, dept.created_at.isoformat()),
            )
        return dept

    def get_department(self, dept_id: str) -> Department | None:
        row = self._db.execute(
            "SELECT * FROM departments WHERE id = ?", (dept_id,)
        ).fetchone()
        return self._row_to_dept(dict(row)) if row else None

    def list_departments(self, organization_id: str,
                         business_unit_id: str = "") -> list[Department]:
        if business_unit_id:
            rows = self._db.execute(
                """SELECT * FROM departments
                   WHERE organization_id = ? AND business_unit_id = ?
                   ORDER BY created_at""",
                (organization_id, business_unit_id),
            ).fetchall()
        else:
            rows = self._db.execute(
                "SELECT * FROM departments WHERE organization_id = ? ORDER BY created_at",
                (organization_id,),
            ).fetchall()
        return [self._row_to_dept(dict(r)) for r in rows]

    def update_department(self, dept: Department) -> None:
        with self._write_lock, self._db.conn:
            self._db.execute(
                """UPDATE departments SET name=?, business_unit_id=?, parent_id=?, description=?
                   WHERE id=?""",
                (dept.name, dept.business_unit_id, dept.parent_id, dept.description, dept.id),
            )

    def delete_department(self, dept_id: str) -> None:
        with self._write_lock, self._db.conn:
            self._db.execute("DELETE FROM departments WHERE id = ?", (dept_id,))

    # ── Position CRUD ──

    def create_position(self, organization_id: str, department_id: str,
                        user_id: str, title: str,
                        is_manager: bool = False) -> Position:
        pos = Position(
            organization_id=organization_id, department_id=department_id,
            user_id=user_id, title=title, is_manager=is_manager,
        )
        with self._write_lock, self._db.conn:
            self._db.execute(
                """INSERT INTO positions (id, organization_id, department_id,
                   user_id, title, is_manager, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (pos.id, pos.organization_id, pos.department_id,
                 pos.user_id, pos.title, int(pos.is_manager), pos.created_at.isoformat()),
            )
        return pos

    def get_position(self, position_id: str) -> Position | None:
        row = self._db.execute(
            "SELECT * FROM positions WHERE id = ?", (position_id,)
        ).fetchone()
        return self._row_to_pos(dict(row)) if row else None

    def get_position_by_user(self, user_id: str,
                             organization_id: str) -> Position | None:
        row = self._db.execute(
            """SELECT * FROM positions
               WHERE user_id = ? AND organization_id = ?
               LIMIT 1""",
            (user_id, organization_id),
        ).fetchone()
        return self._row_to_pos(dict(row)) if row else None

    def list_positions(self, organization_id: str,
                       department_id: str = "") -> list[Position]:
        if department_id:
            rows = self._db.execute(
                """SELECT * FROM positions
                   WHERE organization_id = ? AND department_id = ?
                   ORDER BY created_at""",
                (organization_id, department_id),
            ).fetchall()
        else:
            rows = self._db.execute(
                "SELECT * FROM positions WHERE organization_id = ? ORDER BY created_at",
                (organization_id,),
            ).fetchall()
        return [self._row_to_pos(dict(r)) for r in rows]

    def list_positions_by_user(self, user_id: str) -> list[Position]:
        rows = self._db.execute(
            "SELECT * FROM positions WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()
        return [self._row_to_pos(dict(r)) for r in rows]

    def update_position(self, position: Position) -> None:
        with self._write_lock, self._db.conn:
            self._db.execute(
                """UPDATE positions SET department_id=?, title=?, is_manager=?
                   WHERE id=?""",
                (position.department_id, position.title,
                 int(position.is_manager), position.id),
            )

    def delete_position(self, position_id: str) -> None:
        with self._write_lock, self._db.conn:
            self._db.execute("DELETE FROM positions WHERE id = ?", (position_id,))

    # ── Org Tree ──

    def get_org_tree(self, organization_id: str) -> OrgTreeNode | None:
        org = self.get_organization(organization_id)
        if org is None:
            return None

        bu_list = self.list_business_units(organization_id)
        all_depts = self.list_departments(organization_id)
        all_positions = self.list_positions(organization_id)

        # 按 BU 分组
        bu_children: list[OrgTreeNode] = []
        for bu in bu_list:
            bu_depts = [d for d in all_depts if d.business_unit_id == bu.id]
            dept_children: list[OrgTreeNode] = []
            for dept in bu_depts:
                dept_positions = [p for p in all_positions if p.department_id == dept.id]
                dept_children.append(OrgTreeNode(
                    id=dept.id, name=dept.name, node_type="department",
                    member_count=len(dept_positions),
                    children=[],  # 部门下不再展开
                ))
            bu_children.append(OrgTreeNode(
                id=bu.id, name=bu.name, node_type="business_unit",
                member_count=sum(d.member_count for d in dept_children),
                children=dept_children,
            ))

        total_members = sum(bu.member_count for bu in bu_children)
        return OrgTreeNode(
            id=org.id, name=org.name, node_type="organization",
            children=bu_children, member_count=total_members,
        )

    def get_member_count(self, organization_id: str) -> int:
        row = self._db.execute(
            """SELECT COUNT(DISTINCT user_id) as cnt FROM positions
               WHERE organization_id = ?""",
            (organization_id,),
        ).fetchone()
        return row["cnt"] if row else 0

    # ── Internal ──

    @staticmethod
    def _row_to_org(row: dict) -> Organization:
        return Organization(
            id=row["id"], name=row["name"],
            industry=row.get("industry", ""),
            owner_id=row["owner_id"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    @staticmethod
    def _row_to_bu(row: dict) -> BusinessUnit:
        return BusinessUnit(
            id=row["id"], organization_id=row["organization_id"],
            name=row["name"],
            parent_id=row.get("parent_id"),
            description=row.get("description", ""),
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    @staticmethod
    def _row_to_dept(row: dict) -> Department:
        return Department(
            id=row["id"], organization_id=row["organization_id"],
            business_unit_id=row["business_unit_id"],
            name=row["name"],
            parent_id=row.get("parent_id"),
            description=row.get("description", ""),
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    @staticmethod
    def _row_to_pos(row: dict) -> Position:
        return Position(
            id=row["id"], organization_id=row["organization_id"],
            department_id=row["department_id"],
            user_id=row["user_id"],
            title=row.get("title", ""),
            is_manager=bool(row.get("is_manager", 0)),
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def close(self) -> None:
        if hasattr(self._db, "conn") and self._db.conn:
            self._db.conn.close()
