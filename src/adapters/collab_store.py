"""Collaboration Adapters — SQLite 实现 ActionPlan/AuditLog/Notification/Activity 存储。"""
import json
import logging
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from typing import Any

from src.adapters.config import Settings
from src.adapters.auth_store import WorkspaceContext
from src.core.audit import AuditSummary, NotificationPreferences, UserActivity
from src.core.collaboration import (
    ActionPlan, ActionPriority, ActionStatus,
    ActivityEvent, AuditAction, AuditLog,
    Notification, TeamStats,
)
from src.core.types import Memory

logger = logging.getLogger(__name__)

# ── Collab Table Schema ──

_COLLAB_SCHEMA = """
    CREATE TABLE IF NOT EXISTS action_plans (
        id                  TEXT PRIMARY KEY,
        workspace_id        TEXT NOT NULL,
        title               TEXT NOT NULL,
        description         TEXT DEFAULT '',
        assigned_to         TEXT,
        assigned_by         TEXT,
        priority            TEXT NOT NULL DEFAULT 'medium',
        status              TEXT NOT NULL DEFAULT 'pending',
        due_date            TEXT,
        related_memory_ids  TEXT DEFAULT '[]',
        created_at          TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at          TEXT NOT NULL DEFAULT (datetime('now')),
        completed_at        TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_ap_workspace ON action_plans(workspace_id);
    CREATE INDEX IF NOT EXISTS idx_ap_assignee ON action_plans(assigned_to);

    CREATE TABLE IF NOT EXISTS audit_logs (
        id              TEXT PRIMARY KEY,
        workspace_id    TEXT NOT NULL,
        user_id         TEXT NOT NULL,
        action          TEXT NOT NULL,
        resource_type   TEXT NOT NULL,
        resource_id     TEXT NOT NULL,
        detail          TEXT DEFAULT '',
        timestamp       TEXT NOT NULL DEFAULT (datetime('now'))
    );
    CREATE INDEX IF NOT EXISTS idx_audit_workspace ON audit_logs(workspace_id);
    CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_logs(user_id);
    CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_logs(timestamp);

    CREATE TABLE IF NOT EXISTS notifications (
        id              TEXT PRIMARY KEY,
        user_id         TEXT NOT NULL,
        workspace_id    TEXT NOT NULL,
        title           TEXT NOT NULL,
        body            TEXT DEFAULT '',
        read            INTEGER NOT NULL DEFAULT 0,
        created_at      TEXT NOT NULL DEFAULT (datetime('now')),
        link            TEXT DEFAULT ''
    );
    CREATE INDEX IF NOT EXISTS idx_notif_user ON notifications(user_id, workspace_id);

    CREATE TABLE IF NOT EXISTS activity_events (
        id              TEXT PRIMARY KEY,
        workspace_id    TEXT NOT NULL,
        user_id         TEXT NOT NULL,
        user_name       TEXT NOT NULL DEFAULT '',
        event_type      TEXT NOT NULL,
        message         TEXT NOT NULL,
        timestamp       TEXT NOT NULL DEFAULT (datetime('now')),
        metadata_json   TEXT DEFAULT '{}'
    );
    CREATE INDEX IF NOT EXISTS idx_activity_workspace ON activity_events(workspace_id);
    CREATE INDEX IF NOT EXISTS idx_activity_timestamp ON activity_events(timestamp);

    CREATE TABLE IF NOT EXISTS notification_preferences (
        user_id         TEXT NOT NULL,
        workspace_id    TEXT NOT NULL,
        email_enabled   INTEGER NOT NULL DEFAULT 1,
        push_enabled    INTEGER NOT NULL DEFAULT 1,
        digest_frequency TEXT NOT NULL DEFAULT 'daily',
        PRIMARY KEY (user_id, workspace_id)
    );
"""


class CollabStore:
    """协作存储 — 单例包装 ActionPlan + AuditLog + Notification + Activity。"""

    def __init__(self, config: Settings, db_path: str | None = None) -> None:
        path = db_path or config.sqlite_db_path
        conn = sqlite3.connect(path, check_same_thread=False)
        self._db = __import__("sqlite_utils").Database(conn)
        self._db.conn.row_factory = sqlite3.Row
        self._write_lock = threading.Lock()
        self._init_schema()

    def _init_schema(self):
        for stmt in _COLLAB_SCHEMA.strip().split(";"):
            s = stmt.strip()
            if s:
                try:
                    self._db.execute(s)
                except Exception:
                    pass

    # ── Action Plan ──

    def create_action_plan(self, plan: ActionPlan) -> ActionPlan:
        with self._write_lock, self._db.conn:
            self._db.execute(
                """INSERT INTO action_plans (id, workspace_id, title, description,
                   assigned_to, assigned_by, priority, status, due_date,
                   related_memory_ids, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (plan.id, plan.workspace_id, plan.title, plan.description,
                 plan.assigned_to, plan.assigned_by, plan.priority.value, plan.status.value,
                 plan.due_date.isoformat() if plan.due_date else None,
                 json.dumps(plan.related_memory_ids), plan.created_at.isoformat(),
                 plan.updated_at.isoformat()),
            )
        return plan

    def get_action_plan(self, workspace_id: str, plan_id: str) -> ActionPlan | None:
        row = self._db.execute(
            "SELECT * FROM action_plans WHERE id = ? AND workspace_id = ?",
            (plan_id, workspace_id),
        ).fetchone()
        return self._row_to_plan(dict(row)) if row else None

    def list_action_plans(self, workspace_id: str, assignee: str = "",
                          status: str = "", limit: int = 50) -> list[ActionPlan]:
        where = ["workspace_id = ?"]
        params: list = [workspace_id]
        if assignee:
            where.append("assigned_to = ?")
            params.append(assignee)
        if status:
            where.append("status = ?")
            params.append(status)
        sql = f"SELECT * FROM action_plans WHERE {' AND '.join(where)} ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        rows = self._db.execute(sql, params).fetchall()
        return [self._row_to_plan(dict(r)) for r in rows]

    def update_action_plan(self, plan: ActionPlan) -> None:
        plan.updated_at = datetime.now(timezone.utc)
        with self._write_lock, self._db.conn:
            self._db.execute(
                """UPDATE action_plans SET title=?, description=?, assigned_to=?,
                   priority=?, status=?, due_date=?, related_memory_ids=?,
                   updated_at=?, completed_at=? WHERE id=? AND workspace_id=?""",
                (plan.title, plan.description, plan.assigned_to,
                 plan.priority.value, plan.status.value,
                 plan.due_date.isoformat() if plan.due_date else None,
                 json.dumps(plan.related_memory_ids),
                 plan.updated_at.isoformat(),
                 plan.completed_at.isoformat() if plan.completed_at else None,
                 plan.id, plan.workspace_id),
            )

    def delete_action_plan(self, workspace_id: str, plan_id: str) -> None:
        with self._write_lock, self._db.conn:
            self._db.execute("DELETE FROM action_plans WHERE id=? AND workspace_id=?", (plan_id, workspace_id))

    # ── Audit Log ──

    def log_audit(self, entry: AuditLog) -> None:
        with self._write_lock, self._db.conn:
            self._db.execute(
                """INSERT INTO audit_logs (id, workspace_id, user_id, action,
                   resource_type, resource_id, detail, timestamp)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (entry.id, entry.workspace_id, entry.user_id, entry.action.value,
                 entry.resource_type, entry.resource_id, entry.detail,
                 entry.timestamp.isoformat()),
            )

    def list_audit_logs(self, workspace_id: str, limit: int = 50,
                        action: str = "", user_id: str = "") -> list[AuditLog]:
        where = ["workspace_id = ?"]
        params: list = [workspace_id]
        if action:
            where.append("action = ?")
            params.append(action)
        if user_id:
            where.append("user_id = ?")
            params.append(user_id)
        sql = f"SELECT * FROM audit_logs WHERE {' AND '.join(where)} ORDER BY timestamp DESC, rowid DESC LIMIT ?"
        params.append(limit)
        rows = self._db.execute(sql, params).fetchall()
        return [self._row_to_audit(dict(r)) for r in rows]

    # ── Notifications ──

    def send_notification(self, n: Notification) -> None:
        with self._write_lock, self._db.conn:
            self._db.execute(
                """INSERT INTO notifications (id, user_id, workspace_id, title, body, read, created_at, link)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (n.id, n.user_id, n.workspace_id, n.title, n.body, int(n.read),
                 n.created_at.isoformat(), n.link),
            )

    def list_notifications(self, user_id: str, workspace_id: str,
                           unread_only: bool = False, limit: int = 30) -> list[Notification]:
        where = ["user_id = ?", "workspace_id = ?"]
        params: list = [user_id, workspace_id]
        if unread_only:
            where.append("read = 0")
        sql = f"SELECT * FROM notifications WHERE {' AND '.join(where)} ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        rows = self._db.execute(sql, params).fetchall()
        return [self._row_to_notif(dict(r)) for r in rows]

    def mark_notification_read(self, notif_id: str, user_id: str) -> None:
        with self._write_lock, self._db.conn:
            self._db.execute("UPDATE notifications SET read=1 WHERE id=? AND user_id=?", (notif_id, user_id))

    def mark_all_read(self, user_id: str, workspace_id: str) -> None:
        with self._write_lock, self._db.conn:
            self._db.execute("UPDATE notifications SET read=1 WHERE user_id=? AND workspace_id=?", (user_id, workspace_id))

    def unread_count(self, user_id: str, workspace_id: str) -> int:
        row = self._db.execute(
            "SELECT COUNT(*) as cnt FROM notifications WHERE user_id=? AND workspace_id=? AND read=0",
            (user_id, workspace_id),
        ).fetchone()
        return row["cnt"] if row else 0

    # ── Activity Events ──

    def log_activity(self, event: ActivityEvent) -> None:
        with self._write_lock, self._db.conn:
            self._db.execute(
                """INSERT INTO activity_events (id, workspace_id, user_id, user_name,
                   event_type, message, timestamp, metadata_json)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (event.id, event.workspace_id, event.user_id, event.user_name,
                 event.event_type, event.message, event.timestamp.isoformat(),
                 json.dumps(event.metadata)),
            )

    def recent_activity(self, workspace_id: str, limit: int = 30) -> list[dict]:
        rows = self._db.execute(
            "SELECT * FROM activity_events WHERE workspace_id = ? ORDER BY timestamp DESC LIMIT ?",
            (workspace_id, limit),
        ).fetchall()
        return [
            {
                "id": r["id"], "user_id": r["user_id"], "user_name": r["user_name"],
                "event_type": r["event_type"], "message": r["message"],
                "timestamp": r["timestamp"],
                "metadata": json.loads(r["metadata_json"]) if r["metadata_json"] else {},
            }
            for r in rows
        ]

    # ── Team Stats ──

    def get_team_stats(self, workspace_id: str, memory_store) -> TeamStats:
        try:
            all_mems = memory_store.list_all() if hasattr(memory_store, "list_all") else []
            actions = self.list_action_plans(workspace_id, limit=200)
            member_count_row = self._db.execute(
                "SELECT COUNT(*) as cnt FROM memberships WHERE workspace_id = ?",
                (workspace_id,),
            ).fetchone()

            # 成员贡献
            contrib = self._db.execute(
                """SELECT user_id, COUNT(*) as cnt FROM audit_logs
                   WHERE workspace_id = ? AND action LIKE 'memory_%'
                   GROUP BY user_id ORDER BY cnt DESC LIMIT 10""",
                (workspace_id,),
            ).fetchall()

            member_contrib = [
                {"user_id": r["user_id"], "contributions": r["cnt"]}
                for r in contrib
            ]

            # 最近活动
            recent = self.recent_activity(workspace_id, limit=20)

            return TeamStats(
                total_members=member_count_row["cnt"] if member_count_row else 0,
                total_memories=len(all_mems),
                total_actions=len(actions),
                completed_actions=sum(1 for a in actions if a.status == ActionStatus.COMPLETED),
                member_contributions=member_contrib,
                recent_activity=recent,
            )
        except Exception:
            logger.warning("team_stats_failed", exc_info=True)
            return TeamStats()

    # ── Audit Summary ──

    def get_audit_summary(self, workspace_id: str) -> AuditSummary:
        """返回 workspace 的审计摘要：24h / 7d / 30d 各操作计数。"""
        now = datetime.now(timezone.utc)
        windows = {"last_24h": 1, "last_7d": 7, "last_30d": 30}
        result = AuditSummary(workspace_id=workspace_id)

        for key, days in windows.items():
            cutoff = (now - timedelta(days=days)).isoformat()
            rows = self._db.execute(
                """SELECT action, COUNT(*) as cnt FROM audit_logs
                   WHERE workspace_id = ? AND timestamp >= ?
                   GROUP BY action""",
                (workspace_id, cutoff),
            ).fetchall()
            counts: dict[str, int] = {r["action"]: r["cnt"] for r in rows}
            setattr(result, key, counts)

        # total
        total_row = self._db.execute(
            "SELECT COUNT(*) as cnt FROM audit_logs WHERE workspace_id = ?",
            (workspace_id,),
        ).fetchone()
        result.total = total_row["cnt"] if total_row else 0
        return result

    def prune_old_logs(self, workspace_id: str, days: int) -> int:
        """清理超过 days 天的审计日志，返回删除行数。"""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        with self._write_lock, self._db.conn:
            cursor = self._db.execute(
                "DELETE FROM audit_logs WHERE workspace_id = ? AND timestamp < ?",
                (workspace_id, cutoff),
            )
            deleted = cursor.rowcount if cursor else 0
        return deleted

    def get_user_activity_timeline(self, user_id: str, workspace_id: str,
                                   days: int = 7) -> UserActivity:
        """获取用户在 workspace 中的操作时间线。"""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

        daily_rows = self._db.execute(
            """SELECT date(timestamp) as day, COUNT(*) as cnt
               FROM audit_logs
               WHERE user_id = ? AND workspace_id = ? AND timestamp >= ?
               GROUP BY day ORDER BY day DESC""",
            (user_id, workspace_id, cutoff),
        ).fetchall()
        daily_actions = [{"date": r["day"], "count": r["cnt"]} for r in daily_rows]

        top_rows = self._db.execute(
            """SELECT action, COUNT(*) as cnt
               FROM audit_logs
               WHERE user_id = ? AND workspace_id = ? AND timestamp >= ?
               GROUP BY action ORDER BY cnt DESC LIMIT 10""",
            (user_id, workspace_id, cutoff),
        ).fetchall()
        top_actions = [{"action": r["action"], "count": r["cnt"]} for r in top_rows]

        total_row = self._db.execute(
            """SELECT COUNT(*) as cnt FROM audit_logs
               WHERE user_id = ? AND workspace_id = ? AND timestamp >= ?""",
            (user_id, workspace_id, cutoff),
        ).fetchone()
        total = total_row["cnt"] if total_row else 0

        return UserActivity(
            user_id=user_id,
            workspace_id=workspace_id,
            daily_actions=daily_actions,
            top_actions=top_actions,
            total_actions=total,
        )

    # ── Notification Preferences ──

    def get_notification_preferences(self, user_id: str,
                                     workspace_id: str) -> NotificationPreferences:
        """读取通知偏好，不存在则返回默认值。"""
        row = self._db.execute(
            """SELECT * FROM notification_preferences
               WHERE user_id = ? AND workspace_id = ?""",
            (user_id, workspace_id),
        ).fetchone()
        if row is None:
            return NotificationPreferences(user_id=user_id, workspace_id=workspace_id)
        return NotificationPreferences(
            user_id=row["user_id"],
            workspace_id=row["workspace_id"],
            email_enabled=bool(row["email_enabled"]),
            push_enabled=bool(row["push_enabled"]),
            digest_frequency=row["digest_frequency"],
        )

    def update_notification_preferences(self, prefs: NotificationPreferences) -> None:
        """写入（INSERT OR REPLACE）通知偏好。"""
        with self._write_lock, self._db.conn:
            self._db.execute(
                """INSERT OR REPLACE INTO notification_preferences
                   (user_id, workspace_id, email_enabled, push_enabled, digest_frequency)
                   VALUES (?, ?, ?, ?, ?)""",
                (prefs.user_id, prefs.workspace_id,
                 int(prefs.email_enabled), int(prefs.push_enabled),
                 prefs.digest_frequency),
            )

    # ── Analytics ──

    def get_workspace_analytics(self, workspace_id: str, memory_store) -> "WorkspaceAnalytics":
        """聚合全部工作区分析指标。"""
        from src.core.analytics import WorkspaceAnalytics
        try:
            memory_by_type = self.get_memory_by_type(workspace_id, memory_store)
            growth = self.get_growth_trend(workspace_id, memory_store)
            contributors = self.get_top_contributors(workspace_id)
            media = self.get_media_breakdown(workspace_id, memory_store)

            # member_count
            member_row = self._db.execute(
                "SELECT COUNT(*) as cnt FROM memberships WHERE workspace_id = ?",
                [workspace_id],
            ).fetchone()
            member_count = member_row["cnt"] if member_row else 0

            # top_entities
            entity_rows = self._db.execute(
                """SELECT name, mention_count FROM entities
                   WHERE workspace_id = ? ORDER BY mention_count DESC LIMIT 10""",
                [workspace_id],
            ).fetchall()
            top_entities = [
                {"name": r["name"], "mention_count": r["mention_count"]}
                for r in entity_rows
            ]

            # action_completion_rate
            action_row = self._db.execute(
                """SELECT COUNT(*) as total,
                   SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) as completed
                   FROM action_plans WHERE workspace_id = ?""",
                [workspace_id],
            ).fetchone()
            total = action_row["total"] if action_row else 0
            completed = action_row["completed"] if action_row else 0
            completion_rate = (completed / total) if total > 0 else 0.0

            # weekly_active_users
            wau_row = self._db.execute(
                """SELECT COUNT(DISTINCT user_id) as cnt FROM audit_logs
                   WHERE workspace_id = ? AND timestamp >= datetime('now', '-7 days')""",
                [workspace_id],
            ).fetchone()
            wau = wau_row["cnt"] if wau_row else 0

            return WorkspaceAnalytics(
                member_count=member_count,
                memory_by_type=memory_by_type,
                memory_growth=growth,
                top_entities=top_entities,
                top_contributors=contributors,
                action_completion_rate=round(completion_rate, 4),
                media_breakdown=media,
                weekly_active_users=wau,
            )
        except Exception:
            logger.warning("workspace_analytics_failed", exc_info=True)
            return WorkspaceAnalytics()

    def get_memory_by_type(self, workspace_id: str, memory_store) -> dict[str, int]:
        """按 memory_type 分组的记忆计数。"""
        try:
            rows = self._db.execute(
                """SELECT memory_type, COUNT(*) as cnt FROM notes
                   WHERE workspace_id = ? AND status = 'active'
                   GROUP BY memory_type""",
                [workspace_id],
            ).fetchall()
            return {r["memory_type"]: r["cnt"] for r in rows}
        except Exception:
            logger.warning("memory_by_type_failed", exc_info=True)
            return {}

    def get_growth_trend(self, workspace_id: str, memory_store, days: int = 30) -> list[dict]:
        """每日新增记忆趋势。"""
        try:
            cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
            rows = self._db.execute(
                """SELECT date(timestamp) as day, COUNT(*) as cnt FROM notes
                   WHERE workspace_id = ?
                   GROUP BY day ORDER BY day""",
                [workspace_id],
            ).fetchall()
            return [
                {"date": r["day"], "count": r["cnt"]}
                for r in rows
                if r["day"] and r["day"] >= cutoff
            ]
        except Exception:
            logger.warning("growth_trend_failed", exc_info=True)
            return []

    def get_top_contributors(self, workspace_id: str, days: int = 30) -> list[dict]:
        """成员贡献排行 — 基于审计日志中 memory_* 操作计数。"""
        try:
            cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
            rows = self._db.execute(
                """SELECT user_id, COUNT(*) as cnt FROM audit_logs
                   WHERE workspace_id = ? AND action LIKE 'memory_%'
                   AND timestamp >= ?
                   GROUP BY user_id ORDER BY cnt DESC LIMIT 10""",
                [workspace_id, cutoff],
            ).fetchall()
            return [{"user_id": r["user_id"], "count": r["cnt"]} for r in rows]
        except Exception:
            logger.warning("top_contributors_failed", exc_info=True)
            return []

    def get_media_breakdown(self, workspace_id: str, memory_store) -> dict[str, int]:
        """文本/图片/音频/视频 占比。"""
        try:
            row = self._db.execute(
                """SELECT
                   SUM(CASE WHEN content LIKE '[图片%' THEN 1 ELSE 0 END) as image,
                   SUM(CASE WHEN content LIKE '[音频%' THEN 1 ELSE 0 END) as audio,
                   SUM(CASE WHEN content LIKE '[视频%' THEN 1 ELSE 0 END) as video,
                   SUM(CASE WHEN content NOT LIKE '[图片%'
                            AND content NOT LIKE '[音频%'
                            AND content NOT LIKE '[视频%' THEN 1 ELSE 0 END) as text
                   FROM notes WHERE workspace_id = ? AND status = 'active'""",
                [workspace_id],
            ).fetchone()
            if row is not None:
                return {
                    "text": row["text"] or 0,
                    "image": row["image"] or 0,
                    "audio": row["audio"] or 0,
                    "video": row["video"] or 0,
                }
            return {"text": 0, "image": 0, "audio": 0, "video": 0}
        except Exception:
            logger.warning("media_breakdown_failed", exc_info=True)
            return {}

    # ── Internal ──

    @staticmethod
    def _row_to_plan(row: dict) -> ActionPlan:
        return ActionPlan(
            id=row["id"], workspace_id=row["workspace_id"],
            title=row["title"], description=row.get("description", ""),
            assigned_to=row.get("assigned_to"), assigned_by=row.get("assigned_by"),
            priority=ActionPriority(row.get("priority", "medium")),
            status=ActionStatus(row.get("status", "pending")),
            due_date=datetime.fromisoformat(row["due_date"]) if row.get("due_date") else None,
            related_memory_ids=json.loads(row.get("related_memory_ids") or "[]"),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            completed_at=datetime.fromisoformat(row["completed_at"]) if row.get("completed_at") else None,
        )

    @staticmethod
    def _row_to_audit(row: dict) -> AuditLog:
        return AuditLog(
            id=row["id"], workspace_id=row["workspace_id"], user_id=row["user_id"],
            action=AuditAction(row["action"]),
            resource_type=row["resource_type"], resource_id=row["resource_id"],
            detail=row.get("detail", ""),
            timestamp=datetime.fromisoformat(row["timestamp"]),
        )

    @staticmethod
    def _row_to_notif(row: dict) -> Notification:
        return Notification(
            id=row["id"], user_id=row["user_id"], workspace_id=row["workspace_id"],
            title=row["title"], body=row.get("body", ""),
            read=bool(row.get("read", 0)),
            created_at=datetime.fromisoformat(row["created_at"]),
            link=row.get("link", ""),
        )

    def close(self):
        if hasattr(self._db, "conn") and self._db.conn:
            self._db.conn.close()


class CollaborationService:
    """协作门面 — 统一编排 ActionPlan + Audit + Notification。

    职责：协调多个 store 完成跨实体业务操作（如：assign_action 同时写 audit_log + notification）。
    """

    def __init__(self, collab_store: CollabStore, auth_store=None):
        self._store = collab_store
        self._auth = auth_store

    # ── Action Plan ──

    def create_action(self, plan: ActionPlan, actor_id: str, actor_name: str) -> ActionPlan:
        result = self._store.create_action_plan(plan)
        # Audit
        self._store.log_audit(AuditLog(
            workspace_id=plan.workspace_id, user_id=actor_id,
            action=AuditAction.ACTION_PLAN_CREATE,
            resource_type="action_plan", resource_id=plan.id,
            detail=f"创建行动计划: {plan.title}",
        ))
        # Activity
        self._store.log_activity(ActivityEvent(
            workspace_id=plan.workspace_id, user_id=actor_id, user_name=actor_name,
            event_type="action_plan_created",
            message=f"创建了行动计划「{plan.title}」",
        ))
        # Notify assignee
        if plan.assigned_to:
            self._store.send_notification(Notification(
                user_id=plan.assigned_to, workspace_id=plan.workspace_id,
                title="新任务分配", body=f"{actor_name} 分配了任务「{plan.title}」给你",
                link=f"/workspace/actions/{plan.id}",
            ))
        return result

    def complete_action(self, plan_id: str, workspace_id: str, user_id: str, user_name: str) -> ActionPlan | None:
        plan = self._store.get_action_plan(workspace_id, plan_id)
        if plan is None:
            return None
        plan.status = ActionStatus.COMPLETED
        plan.completed_at = datetime.now(timezone.utc)
        self._store.update_action_plan(plan)

        self._store.log_audit(AuditLog(
            workspace_id=workspace_id, user_id=user_id,
            action=AuditAction.ACTION_PLAN_COMPLETE,
            resource_type="action_plan", resource_id=plan_id,
            detail=f"完成: {plan.title}",
        ))
        self._store.log_activity(ActivityEvent(
            workspace_id=workspace_id, user_id=user_id, user_name=user_name,
            event_type="action_plan_completed",
            message=f"完成了任务「{plan.title}」",
        ))
        return plan

    # ── Memory Merge (跨用户) ──

    def merge_workspace_memories(self, workspace_id: str, primary_id: str,
                                  secondary_ids: list[str], user_id: str,
                                  user_name: str, memory_store) -> int:
        """合并工作区内记忆。"""
        merged = 0
        for sid in secondary_ids:
            sec = memory_store.get_by_id(sid)
            if sec is None:
                continue
            sec.status = "merged"
            memory_store.store(sec)
            merged += 1

            self._store.log_audit(AuditLog(
                workspace_id=workspace_id, user_id=user_id,
                action=AuditAction.MEMORY_MERGE,
                resource_type="memory", resource_id=sid,
                detail=f"合并到 {primary_id[:8]}",
            ))

        if merged > 0:
            self._store.log_activity(ActivityEvent(
                workspace_id=workspace_id, user_id=user_id, user_name=user_name,
                event_type="memory_merged", message=f"合并了 {merged} 条记忆",
                metadata={"primary_id": primary_id, "count": merged},
            ))
        return merged

    # ── Dashboard ──

    def get_dashboard(self, workspace_id: str, memory_store) -> TeamStats:
        return self._store.get_team_stats(workspace_id, memory_store)

    # ── Activity Log ──

    def get_activity_log(self, workspace_id: str, limit: int = 30) -> list[dict]:
        return self._store.recent_activity(workspace_id, limit)

    def get_audit_log(self, workspace_id: str, limit: int = 50,
                      action: str = "", user_id: str = "") -> list[AuditLog]:
        return self._store.list_audit_logs(workspace_id, limit, action, user_id)

    # ── Analytics ──

    def get_workspace_analytics(self, workspace_id: str, memory_store) -> "WorkspaceAnalytics":
        return self._store.get_workspace_analytics(workspace_id, memory_store)

    def get_analytics_growth(self, workspace_id: str, memory_store, days: int = 30) -> list[dict]:
        return self._store.get_growth_trend(workspace_id, memory_store, days)

    def get_analytics_contributors(self, workspace_id: str, days: int = 30) -> list[dict]:
        return self._store.get_top_contributors(workspace_id, days)

    def get_analytics_media(self, workspace_id: str, memory_store) -> dict[str, int]:
        return self._store.get_media_breakdown(workspace_id, memory_store)
