"""MemoryLifecycleManager 单元测试。

覆盖：
    - archive: 规则 1 (importance<4 + age>90d) 和规则 2 (365d 未被 recall)
    - merge: 规则 4 (重复记忆 → MERGED)
    - purge: 物理删除 deleted 记忆
    - recall_filter: include_archived 参数控制检索范围
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, create_autospec, patch

import pytest

from src.core.memory_lifecycle import (
    ARCHIVE_AGE_DAYS,
    ARCHIVE_IMPORTANCE_THRESHOLD,
    ARCHIVE_UNACCESSED_DAYS,
    MemoryLifecycleManager,
    LifecycleStore,
)
from src.core.types import Memory, SearchResult


# ── Fixtures ──


@pytest.fixture
def mock_store():
    """创建一个支持 LifecycleStore 协议的 mock。"""
    store = create_autospec(LifecycleStore, instance=True)
    store.list_by_status.return_value = []
    store.list_all.return_value = []
    return store


@pytest.fixture
def lifecycle(mock_store):
    return MemoryLifecycleManager(mock_store)


def _make_memory(
    id_: str = "m1",
    content: str = "测试记忆",
    source: str = "user",
    days_ago: int = 10,
    importance: int = 5,
    entities: list[str] | None = None,
    memory_type: str = "episodic",
    status: str = "active",
    last_accessed_days_ago: int | None = None,
    *,
    now: datetime | None = None,
) -> Memory:
    """创建测试用 Memory。

    Args:
        last_accessed_days_ago: None 表示从未被访问（last_accessed=None）。
        now: 指定参考时间，用于确定性边界测试。默认 datetime.now(timezone.utc)。
    """
    now = now or datetime.now(timezone.utc)
    return Memory(
        id=id_,
        content=content,
        summary=None,
        source=source,
        timestamp=now - timedelta(days=days_ago),
        importance=importance,
        entities=entities or [],
        memory_type=memory_type,
        status=status,
        last_accessed=(
            now - timedelta(days=last_accessed_days_ago)
            if last_accessed_days_ago is not None
            else None
        ),
    )


# ── Archive 测试 ──


class TestArchiveOldMemories:
    def test_rule1_archives_low_importance_old_memory(self, lifecycle, mock_store):
        """规则 1: importance < 4 且 age > 90 天 → ARCHIVED"""
        old_low = _make_memory("old", "旧的低价值信息", days_ago=100, importance=3)
        mock_store.list_by_status.return_value = [old_low]

        count = lifecycle.archive_old_memories()

        assert count == 1
        assert old_low.status == "archived"
        assert old_low.archived_at is not None
        mock_store.store.assert_called_once()

    def test_rule1_ignores_recent_low_importance(self, lifecycle, mock_store):
        """age ≤ 90 天，即使 importance < 4 也不归档"""
        recent_low = _make_memory("r", "最近的低价值", days_ago=30, importance=3)
        mock_store.list_by_status.return_value = [recent_low]

        count = lifecycle.archive_old_memories()

        assert count == 0
        assert recent_low.status == "active"

    def test_rule1_ignores_old_high_importance(self, lifecycle, mock_store):
        """importance ≥ 4，即使 age > 90 天也不归档"""
        old_high = _make_memory("vip", "重要的旧信息", days_ago=100, importance=7)
        mock_store.list_by_status.return_value = [old_high]

        count = lifecycle.archive_old_memories()

        assert count == 0
        assert old_high.status == "active"

    def test_rule1_boundary_importance(self, lifecycle, mock_store):
        """边界值: importance=4 不归档, importance=3 归档"""
        # importance=4 → 不归档
        m4 = _make_memory("m4", "importance=4", days_ago=100, importance=4)
        # importance=3 → 归档
        m3 = _make_memory("m3", "importance=3", days_ago=100, importance=3)
        mock_store.list_by_status.return_value = [m4, m3]

        count = lifecycle.archive_old_memories()

        assert count == 1
        assert m4.status == "active"
        assert m3.status == "archived"

    def test_rule1_boundary_age(self, lifecycle, mock_store):
        """边界值: age=90 天不归档, age=91 天归档"""
        m90 = _make_memory("m90", "刚好90天", days_ago=90, importance=3)
        m91 = _make_memory("m91", "91天", days_ago=91, importance=3)
        mock_store.list_by_status.return_value = [m90, m91]

        count = lifecycle.archive_old_memories()

        assert count == 1
        assert m90.status == "active"
        assert m91.status == "archived"

    def test_rule2_archives_long_unaccessed(self, lifecycle, mock_store):
        """规则 2: 连续 365 天未被 Recall → ARCHIVED"""
        # last_accessed = 400 天前
        unaccessed = _make_memory(
            "ua", "长期未访问", days_ago=400, importance=7,
            last_accessed_days_ago=400,
        )
        mock_store.list_by_status.return_value = [unaccessed]

        count = lifecycle.archive_old_memories()

        assert count == 1
        assert unaccessed.status == "archived"

    def test_rule2_never_accessed_uses_timestamp(self, lifecycle, mock_store):
        """从未被访问的记忆，以 timestamp 计算 access 间隔"""
        # 400 天前创建，从未被访问
        never_accessed = _make_memory(
            "na", "从未被访问", days_ago=400, importance=8,
            last_accessed_days_ago=None,  # last_accessed = None
        )
        mock_store.list_by_status.return_value = [never_accessed]

        count = lifecycle.archive_old_memories()

        assert count == 1
        assert never_accessed.status == "archived"

    def test_rule2_ignores_recently_accessed(self, lifecycle, mock_store):
        """最近被访问过的记忆不归档"""
        accessed = _make_memory(
            "acc", "最近访问过", days_ago=400, importance=7,
            last_accessed_days_ago=30,  # 30 天前访问过
        )
        mock_store.list_by_status.return_value = [accessed]

        count = lifecycle.archive_old_memories()

        assert count == 0
        assert accessed.status == "active"

    def test_rule2_boundary_accessed(self, lifecycle, mock_store):
        """边界值: 365 天未访问归档, 364 天不归档"""
        now = datetime.now(timezone.utc)
        m365 = _make_memory(
            "m365", "365天", days_ago=400, importance=7,
            last_accessed_days_ago=365, now=now,
        )
        m364 = _make_memory(
            "m364", "364天", days_ago=400, importance=7,
            last_accessed_days_ago=364, now=now,
        )
        mock_store.list_by_status.return_value = [m365, m364]

        count = lifecycle.archive_old_memories()

        assert count == 1
        assert m364.status == "active"
        assert m365.status == "archived"

    def test_rule2_boundary_accessed_366(self, lifecycle, mock_store):
        """366 天未访问 → 归档"""
        now = datetime.now(timezone.utc)
        m366 = _make_memory(
            "m366", "366天", days_ago=400, importance=7,
            last_accessed_days_ago=366, now=now,
        )
        m364 = _make_memory(
            "m364", "364天", days_ago=400, importance=7,
            last_accessed_days_ago=364, now=now,
        )
        mock_store.list_by_status.return_value = [m366, m364]

        count = lifecycle.archive_old_memories()

        assert count == 1
        assert m364.status == "active"
        assert m366.status == "archived"

    def test_skips_already_archived(self, lifecycle, mock_store):
        """已归档的记忆不重复处理"""
        archived = _make_memory("arch", "已归档", days_ago=100, importance=3, status="archived")
        mock_store.list_by_status.return_value = []

        # 只查 active，archived 不出现在候选集中
        count = lifecycle.archive_old_memories()

        assert count == 0

    def test_empty_list_returns_zero(self, lifecycle, mock_store):
        mock_store.list_by_status.return_value = []

        count = lifecycle.archive_old_memories()

        assert count == 0

    def test_store_error_is_handled_gracefully(self, lifecycle, mock_store):
        """单条写入失败不影响其他记忆"""
        m1 = _make_memory("m1", "记忆1", days_ago=100, importance=3)
        m2 = _make_memory("m2", "记忆2", days_ago=100, importance=3)
        mock_store.list_by_status.return_value = [m1, m2]
        mock_store.store.side_effect = [Exception("DB error"), None]

        count = lifecycle.archive_old_memories()

        assert count == 1  # m1 失败, m2 成功

    def test_list_error_returns_zero(self, lifecycle, mock_store):
        mock_store.list_by_status.side_effect = RuntimeError("DB down")

        count = lifecycle.archive_old_memories()

        assert count == 0


# ── Merge 测试 ──


class TestMergeDuplicateMemories:
    def test_merges_exact_content_duplicates(self, lifecycle, mock_store):
        """完全相同的 content → MERGED，保留最早的那条"""
        old = _make_memory("old", "完全相同的记忆内容", days_ago=50)
        new_dup = _make_memory("new", "完全相同的记忆内容", days_ago=10)
        mock_store.list_by_status.return_value = [new_dup, old]

        count = lifecycle.merge_duplicate_memories()

        assert count == 1
        assert new_dup.status == "merged"  # 较新的被标记 merged (old 更早)
        assert old.status == "active"       # primary 保持 active

    def test_preserves_earliest_by_timestamp(self, lifecycle, mock_store):
        """保留 timestamp 最早的那条"""
        earliest = _make_memory("e1", "重复内容", days_ago=200)
        middle = _make_memory("m1", "重复内容", days_ago=100)
        latest = _make_memory("l1", "重复内容", days_ago=10)
        mock_store.list_by_status.return_value = [latest, middle, earliest]

        count = lifecycle.merge_duplicate_memories()

        assert count == 2  # middle + latest → merged
        assert earliest.status == "active"
        assert middle.status == "merged"
        assert latest.status == "merged"

    def test_no_merge_for_unique_content(self, lifecycle, mock_store):
        """内容不同不合并"""
        m1 = _make_memory("a", "记忆A")
        m2 = _make_memory("b", "记忆B")
        mock_store.list_by_status.return_value = [m1, m2]

        count = lifecycle.merge_duplicate_memories()

        assert count == 0
        assert m1.status == "active"
        assert m2.status == "active"

    def test_empty_list_returns_zero(self, lifecycle, mock_store):
        mock_store.list_by_status.return_value = []

        count = lifecycle.merge_duplicate_memories()

        assert count == 0

    def test_merge_updates_primary_stats(self, lifecycle, mock_store):
        """合并后 primary 累积 access_count 和 importance"""
        primary = _make_memory("p", "重复", days_ago=100, importance=5)
        primary.access_count = 10
        dup = _make_memory("d", "重复", days_ago=50, importance=8)
        dup.access_count = 5
        mock_store.list_by_status.return_value = [dup, primary]

        lifecycle.merge_duplicate_memories()

        assert primary.access_count == 15  # 10 + 5
        assert primary.importance == 8     # max(5, 8)

    def test_multiple_duplicate_groups(self, lifecycle, mock_store):
        """多组重复各自独立处理"""
        g1_old = _make_memory("g1a", "组1内容", days_ago=100)
        g1_new = _make_memory("g1b", "组1内容", days_ago=50)
        g2_old = _make_memory("g2a", "组2内容", days_ago=100)
        g2_new = _make_memory("g2b", "组2内容", days_ago=50)
        mock_store.list_by_status.return_value = [g1_new, g1_old, g2_new, g2_old]

        count = lifecycle.merge_duplicate_memories()

        assert count == 2  # 每组各标记 1 个为 merged

    def test_list_error_returns_zero(self, lifecycle, mock_store):
        mock_store.list_by_status.side_effect = RuntimeError("DB down")

        count = lifecycle.merge_duplicate_memories()

        assert count == 0


# ── Purge 测试 ──


class TestPurgeDeletedMemories:
    def test_purges_all_deleted(self, lifecycle, mock_store):
        """物理删除所有 status=deleted 的记忆"""
        d1 = _make_memory("d1", "已删除1", status="deleted")
        d2 = _make_memory("d2", "已删除2", status="deleted")
        mock_store.list_by_status.return_value = [d1, d2]

        count = lifecycle.purge_deleted_memories()

        assert count == 2
        assert mock_store.delete.call_count == 2
        mock_store.delete.assert_any_call("d1")
        mock_store.delete.assert_any_call("d2")

    def test_empty_list_returns_zero(self, lifecycle, mock_store):
        mock_store.list_by_status.return_value = []

        count = lifecycle.purge_deleted_memories()

        assert count == 0
        mock_store.delete.assert_not_called()

    def test_delete_error_is_handled(self, lifecycle, mock_store):
        """单条删除失败不影响其他"""
        d1 = _make_memory("d1", "删除失败", status="deleted")
        d2 = _make_memory("d2", "删除成功", status="deleted")
        mock_store.list_by_status.return_value = [d1, d2]
        mock_store.delete.side_effect = [RuntimeError("gone"), None]

        count = lifecycle.purge_deleted_memories()

        assert count == 1  # d1 失败, d2 成功

    def test_list_error_returns_zero(self, lifecycle, mock_store):
        mock_store.list_by_status.side_effect = RuntimeError("DB down")

        count = lifecycle.purge_deleted_memories()

        assert count == 0


# ── Recall Filter 测试（retrieval 层 status 过滤）──


class TestRecallStatusFilter:
    """验证 MemoryRetrievalService 的 status 过滤行为。

    注: 这是 integration-style 测试，需要使用真实 Memory 对象和 mock 适配器。
    """

    def test_default_excludes_archived(self):
        """默认 include_archived=False → 不返回 archived 记忆"""
        from src.core.retrieval import MemoryRetrievalService

        store = _FakeLifecycleStore()
        store._memories["active1"] = _make_memory(
            "active1", "关于机器学习的记忆", status="active",
        )
        store._memories["archived1"] = _make_memory(
            "archived1", "关于机器学习的旧记忆", status="archived", days_ago=200,
        )

        vs = _FakeVectorStore()
        vs._search_returns = [
            SearchResult(doc_id="active1", score=0.9, metadata={}),
            SearchResult(doc_id="archived1", score=0.85, metadata={}),
        ]

        emb = _FakeEmbedding()
        service = MemoryRetrievalService(store, vs, emb)

        results = service.retrieve("机器学习", top_k=5)

        ids = [m.id for m in results]
        assert "active1" in ids
        assert "archived1" not in ids

    def test_include_archived_true_includes_archived(self):
        """include_archived=True → 返回 archived 记忆"""
        from src.core.retrieval import MemoryRetrievalService

        store = _FakeLifecycleStore()
        store._memories["active1"] = _make_memory(
            "active1", "关于机器学习的记忆", status="active",
        )
        store._memories["archived1"] = _make_memory(
            "archived1", "关于机器学习的旧记忆", status="archived", days_ago=200,
        )

        vs = _FakeVectorStore()
        vs._search_returns = [
            SearchResult(doc_id="active1", score=0.9, metadata={}),
            SearchResult(doc_id="archived1", score=0.85, metadata={}),
        ]

        emb = _FakeEmbedding()
        service = MemoryRetrievalService(store, vs, emb)

        results = service.retrieve("机器学习", top_k=5, include_archived=True)

        ids = [m.id for m in results]
        assert "active1" in ids
        assert "archived1" in ids

    def test_excludes_merged_and_deleted_always(self):
        """merged 和 deleted 状态始终被排除"""
        from src.core.retrieval import MemoryRetrievalService

        store = _FakeLifecycleStore()
        store._memories["active1"] = _make_memory("active1", "测试", status="active")
        store._memories["merged1"] = _make_memory("merged1", "测试", status="merged")
        store._memories["deleted1"] = _make_memory("deleted1", "测试", status="deleted")

        vs = _FakeVectorStore()
        vs._search_returns = [
            SearchResult(doc_id="active1", score=0.9, metadata={}),
            SearchResult(doc_id="merged1", score=0.8, metadata={}),
            SearchResult(doc_id="deleted1", score=0.7, metadata={}),
        ]

        emb = _FakeEmbedding()
        service = MemoryRetrievalService(store, vs, emb)

        # 即使 include_archived=True，merged/deleted 也不返回
        results = service.retrieve("测试", top_k=5, include_archived=True)

        ids = [m.id for m in results]
        assert "active1" in ids
        assert "merged1" not in ids
        assert "deleted1" not in ids


# ── _should_archive 单元测试 ──


class TestShouldArchive:
    def test_rule1_boundaries(self):
        """测试规则 1 各边界条件"""
        now = datetime.now(timezone.utc)

        # importance < 4, age > 90 → True (92天确保跨过边界)
        m = _make_memory("t", "test", days_ago=92, importance=3, now=now)
        assert MemoryLifecycleManager._should_archive(m, now) is True

        # importance < 4, age = 90 → False (不大于90)
        m = _make_memory("t", "test", days_ago=90, importance=3, now=now)
        assert MemoryLifecycleManager._should_archive(m, now) is False

        # importance = 4, age > 90 → False (不小于4)
        m = _make_memory("t", "test", days_ago=92, importance=4, now=now)
        assert MemoryLifecycleManager._should_archive(m, now) is False

    def test_rule2_boundaries(self):
        """测试规则 2 各边界条件"""
        now = datetime.now(timezone.utc)

        # 从未访问, age >= 365 → True
        m = _make_memory("t", "test", days_ago=366, importance=8, last_accessed_days_ago=None, now=now)
        assert MemoryLifecycleManager._should_archive(m, now) is True

        # 从未访问, age = 364 → False (< 365)
        m = _make_memory("t", "test", days_ago=364, importance=8, last_accessed_days_ago=None, now=now)
        assert MemoryLifecycleManager._should_archive(m, now) is False

        # 有访问记录, 365 天前访问 → True (>= 365)
        m = _make_memory("t", "test", days_ago=400, importance=8, last_accessed_days_ago=365, now=now)
        assert MemoryLifecycleManager._should_archive(m, now) is True

    def test_both_rules_false(self):
        """两个规则都不满足 → False"""
        now = datetime.now(timezone.utc)
        m = _make_memory(
            "t", "test", days_ago=10, importance=8, last_accessed_days_ago=5,
        )
        assert MemoryLifecycleManager._should_archive(m, now) is False


# ── Fake 适配器 ──


class _FakeLifecycleStore:
    """最小 LifecycleStore 实现 — 用于 retrieval filter 测试。"""

    def __init__(self):
        self._memories: dict[str, Memory] = {}

    def store(self, memory: Memory) -> str:
        self._memories[memory.id] = memory
        return memory.id

    def delete(self, memory_id: str) -> None:
        self._memories.pop(memory_id, None)

    def search_by_entity(self, entity_name: str) -> list[Memory]:
        return [m for m in self._memories.values() if entity_name in m.entities]

    def get_by_id(self, memory_id: str) -> Memory | None:
        mem = self._memories.get(memory_id)
        if mem is not None:
            mem.access_count += 1
            mem.last_accessed = datetime.now(timezone.utc)
        return mem

    def get_recent(self, limit: int) -> list[Memory]:
        sorted_mems = sorted(
            self._memories.values(), key=lambda m: m.timestamp, reverse=True,
        )
        return sorted_mems[:limit]

    def list_all(self) -> list[Memory]:
        return list(self._memories.values())

    def list_by_status(self, status: str) -> list[Memory]:
        return [m for m in self._memories.values() if m.status == status]

    def update_status(self, memory_id: str, status: str) -> None:
        if memory_id in self._memories:
            self._memories[memory_id].status = status


class _FakeVectorStore:
    def __init__(self):
        self._search_returns: list[SearchResult] = []

    def store(self, doc_id: str, embedding, metadata) -> str:
        return doc_id

    def search(self, embedding, k: int) -> list[SearchResult]:
        return self._search_returns


class _FakeEmbedding:
    def encode(self, text: str) -> list[float]:
        return [0.1] * 512


# ── Protocol 合规测试 ──


class TestProtocolCompliance:
    def test_manager_accepts_lifecycle_store(self, mock_store):
        manager = MemoryLifecycleManager(mock_store)
        assert isinstance(manager, MemoryLifecycleManager)

    def test_fake_store_satisfies_protocol(self):
        store = _FakeLifecycleStore()
        assert isinstance(store, LifecycleStore)
