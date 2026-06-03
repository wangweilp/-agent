"""Memory Lifecycle Manager — 记忆生命周期管理系统。

四状态：
    ACTIVE   — 正常可检索
    ARCHIVED — 低价值/长期未访问，默认不参与检索
    MERGED   — 被合并吸收，不再独立存在
    DELETED  — 标记删除，待 purge 物理清理

四规则：
    规则 1: importance < 4 且 age > 90 天 → ARCHIVED
    规则 2: 连续 365 天未被 Recall → ARCHIVED
    规则 3: Consolidation 后被吸收 → MERGED（由 consolidation 引擎设置）
    规则 4: 重复记忆 → MERGED

三个操作：
    archive_old_memories()   — 执行规则 1 + 2
    merge_duplicate_memories() — 执行规则 4
    purge_deleted_memories()  — 物理清理标记为 deleted 的记忆
"""

import hashlib
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from src.adapters.sqlite_store import SQLiteStoreAdapter

from src.core.types import Memory

logger = logging.getLogger(__name__)

# ── 阈值 ──

ARCHIVE_IMPORTANCE_THRESHOLD = 4        # importance < 此值考虑归档
ARCHIVE_AGE_DAYS = 90                   # timestamp 距今超过此天数考虑归档
ARCHIVE_UNACCESSED_DAYS = 365           # 未被 recall 超过此天数考虑归档

# ── 协议 ──


@runtime_checkable
class LifecycleStore(Protocol):
    """MemoryStore 的超集 — lifecycle manager 需要的额外方法。

    SQLiteStoreAdapter 实现了此协议的所有方法。
    """

    def store(self, memory: Memory) -> str: ...
    def delete(self, memory_id: str) -> None: ...
    def get_by_id(self, memory_id: str) -> Memory | None: ...
    def get_recent(self, limit: int) -> list[Memory]: ...
    def list_all(self) -> list[Memory]: ...
    def list_by_status(self, status: str) -> list[Memory]: ...
    def update_status(self, memory_id: str, status: str) -> None: ...


# ── 实现 ──


class MemoryLifecycleManager:
    """记忆生命周期管理器。

    职责：
    - 定时扫描记忆，执行归档/合并/清理规则
    - 不参与实时检索路径（Recall 在 retrieval 层做 status 过滤）
    - 所有操作幂等 — 重复执行不产生不同结果
    """

    def __init__(self, memory_store: LifecycleStore) -> None:
        self._store = memory_store

    # ── 公共 API ──

    def archive_old_memories(self) -> int:
        """执行规则 1 + 规则 2：归档老旧/长期未访问的记忆。

        只处理 status="active" 的记忆，将其标记为 "archived"。

        Returns:
            本次归档的记忆数量。
        """
        try:
            memories = self._store.list_by_status("active")
        except Exception:
            logger.warning("lifecycle_archive_list_failed", exc_info=True)
            return 0

        now = datetime.now(timezone.utc)
        count = 0

        for mem in memories:
            if self._should_archive(mem, now):
                mem.status = "archived"
                mem.archived_at = now
                try:
                    self._store.store(mem)
                    count += 1
                    logger.debug(
                        "lifecycle_archived",
                        extra={
                            "memory_id": mem.id,
                            "importance": mem.importance,
                            "age_days": (now - mem.timestamp).days,
                        },
                    )
                except Exception:
                    logger.debug(
                        "lifecycle_archive_store_failed",
                        extra={"id": mem.id},
                        exc_info=True,
                    )

        if count > 0:
            logger.info("lifecycle_archive_complete", extra={"archived_count": count})
        return count

    def merge_duplicate_memories(self) -> int:
        """执行规则 4：检测并合并重复记忆。

        仅检测 status="active" 的记忆，两层策略：
        1. 内容 MD5 完全相同 → 保留最早的，其余标记为 "merged"
        2. （未来）embedding 相似度 ≥ 阈值 → 合并

        Returns:
            本次标记为 merged 的记忆数量。
        """
        try:
            memories = self._store.list_by_status("active")
        except Exception:
            logger.warning("lifecycle_merge_list_failed", exc_info=True)
            return 0

        # 按内容 hash 分组
        content_groups: dict[str, list[Memory]] = {}
        for mem in memories:
            key = hashlib.md5(mem.content.encode("utf-8")).hexdigest()
            content_groups.setdefault(key, []).append(mem)

        count = 0
        for group in content_groups.values():
            if len(group) < 2:
                continue
            # 保留最早的（按 timestamp 排序），其余标记 merged
            group.sort(key=lambda m: m.timestamp)
            primary = group[0]

            for dup in group[1:]:
                # 将重复内容合并到 primary
                primary.access_count += dup.access_count
                primary.importance = max(primary.importance, dup.importance)
                primary.entities = list(set(primary.entities + dup.entities))

                # 标记重复为 merged
                dup.status = "merged"
                try:
                    self._store.store(dup)
                    count += 1
                    logger.debug(
                        "lifecycle_merged_duplicate",
                        extra={
                            "primary_id": primary.id,
                            "duplicate_id": dup.id,
                            "hash": key[:8],
                        },
                    )
                except Exception:
                    logger.debug(
                        "lifecycle_merge_store_failed",
                        extra={"id": dup.id},
                        exc_info=True,
                    )

            # 更新 primary
            try:
                self._store.store(primary)
            except Exception:
                logger.debug(
                    "lifecycle_merge_primary_store_failed",
                    extra={"id": primary.id},
                    exc_info=True,
                )

        if count > 0:
            logger.info("lifecycle_merge_complete", extra={"merged_count": count})
        return count

    def purge_deleted_memories(self) -> int:
        """物理删除 status="deleted" 的记忆。

        此操作不可逆。建议在执行前做备份或二次确认。

        Returns:
            物理删除的记忆数量。
        """
        try:
            deleted = self._store.list_by_status("deleted")
        except Exception:
            logger.warning("lifecycle_purge_list_failed", exc_info=True)
            return 0

        count = 0
        for mem in deleted:
            try:
                self._store.delete(mem.id)
                count += 1
                logger.debug("lifecycle_purged", extra={"memory_id": mem.id})
            except Exception:
                logger.debug(
                    "lifecycle_purge_failed",
                    extra={"id": mem.id},
                    exc_info=True,
                )

        if count > 0:
            logger.info("lifecycle_purge_complete", extra={"purged_count": count})
        return count

    # ── 内部方法 ──

    @staticmethod
    def _should_archive(memory: Memory, now: datetime) -> bool:
        """判断单条记忆是否应归档（规则 1 + 规则 2）。"""
        age_days = (now - memory.timestamp).days

        # 规则 1: importance < 4 且 age > 90 天
        if memory.importance < ARCHIVE_IMPORTANCE_THRESHOLD and age_days > ARCHIVE_AGE_DAYS:
            return True

        # 规则 2: 连续 365 天未被 Recall
        last_access = memory.last_accessed or memory.timestamp
        days_since_access = (now - last_access).days
        if days_since_access >= ARCHIVE_UNACCESSED_DAYS:
            return True

        return False
