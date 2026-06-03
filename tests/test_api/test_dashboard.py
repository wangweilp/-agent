"""Dashboard API 集成测试 — 覆盖所有 6 个新增端点 + 错误降级。"""
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI

from src.api.dashboard import create_dashboard_router
from src.core.types import Memory


# ── Fixtures ──


@pytest.fixture
def mock_agent():
    """创建一个带有 _memory_store mock 的 agent。"""
    agent = MagicMock()
    agent._memory_store = MagicMock()
    agent._memory_store.get_recent.return_value = []
    agent._memory_store._db = MagicMock()
    agent._memory_store._db.execute.return_value.fetchone.return_value = None
    agent._memory_store._db.execute.return_value.fetchall.return_value = []
    return agent


@pytest.fixture
def mock_writer():
    """创建一个带有 stats 和 pending 的 mock writer。"""
    writer = MagicMock()
    writer.pending = 0
    writer.stats = {
        "dead_letter": {"count": 0},
        "queue": {"pending": 0, "total_stored": 0, "total_failed": 0},
    }
    return writer


@pytest.fixture
def client(mock_agent, mock_writer):
    """创建一个测试用 FastAPI TestClient。"""
    app = FastAPI()
    router = create_dashboard_router(mock_agent, mock_writer)
    app.include_router(router)
    from fastapi.testclient import TestClient
    return TestClient(app)


def _make_memory_row(**kwargs):
    """模拟 sqlite3.Row — 返回 dict，支持 row['key'] 访问。"""
    return kwargs


# ── Test: GET /dashboard/summary ──


class TestDashboardSummary:
    def test_returns_all_status_counts(self, client, mock_agent):
        """summary 端点内部两次 _db().execute()，需要 fetchone 返回两个不同结果。"""
        mock_agent._memory_store._db.execute.return_value.fetchone.side_effect = [
            _make_memory_row(
                total=42, active=30, archived=5, merged=4, deleted=3,
                episodic=25, semantic=10, reflect=7,
            ),
            _make_memory_row(cnt=0),  # weekly_growth 的查询
        ]

        res = client.get("/dashboard/summary")

        assert res.status_code == 200
        data = res.json()
        assert data["total_memories"] == 42
        assert data["active_memories"] == 30
        assert data["archived_memories"] == 5
        assert data["merged_memories"] == 4
        assert data["deleted_memories"] == 3
        assert data["episodic_count"] == 25
        assert data["semantic_count"] == 10
        assert data["reflect_count"] == 7

    def test_includes_queue_and_dlq(self, client, mock_agent, mock_writer):
        mock_writer.pending = 5
        mock_writer.stats = {"dead_letter": {"count": 3}}
        mock_agent._memory_store._db.execute.return_value.fetchone.side_effect = [
            _make_memory_row(
                total=0, active=0, archived=0, merged=0, deleted=0,
                episodic=0, semantic=0, reflect=0,
            ),
            _make_memory_row(cnt=0),
        ]

        res = client.get("/dashboard/summary")

        data = res.json()
        assert data["queue_depth"] == 5
        assert data["dlq_count"] == 3

    def test_weekly_growth_count(self, client, mock_agent):
        mock_agent._memory_store._db.execute.return_value.fetchone.side_effect = [
            _make_memory_row(
                total=5, active=5, archived=0, merged=0, deleted=0,
                episodic=5, semantic=0, reflect=0,
            ),
            _make_memory_row(cnt=12),  # 本周新增 12 条
        ]

        res = client.get("/dashboard/summary")

        data = res.json()
        assert res.status_code == 200
        assert data["weekly_growth"] == 12

    def test_handles_database_error_gracefully(self, client, mock_agent):
        mock_agent._memory_store._db.execute.side_effect = RuntimeError("DB down")

        res = client.get("/dashboard/summary")

        assert res.status_code == 200
        data = res.json()
        assert data["total_memories"] == 0  # 默认值

    def test_handles_writer_none(self, mock_agent):
        """writer 为 None 时不崩溃。"""
        from fastapi.testclient import TestClient

        app = FastAPI()
        app.include_router(create_dashboard_router(mock_agent, None))
        client = TestClient(app)

        res = client.get("/dashboard/summary")
        assert res.status_code == 200


# ── Test: GET /dashboard/topics ──


class TestDashboardTopics:
    def test_returns_ranked_topics(self, client, mock_agent):
        mock_agent._memory_store._db.execute.return_value.fetchall.return_value = [
            _make_memory_row(name="AI", mention_count=15, memory_count=8),
            _make_memory_row(name="Python", mention_count=10, memory_count=5),
            _make_memory_row(name="RAG", mention_count=7, memory_count=4),
        ]

        res = client.get("/dashboard/topics?limit=3")

        assert res.status_code == 200
        data = res.json()
        assert len(data) == 3
        assert data[0]["name"] == "AI"
        assert data[0]["mention_count"] == 15
        assert data[0]["memory_count"] == 8

    def test_default_limit(self, client, mock_agent):
        res = client.get("/dashboard/topics")
        assert res.status_code == 200

    def test_handles_empty_result(self, client, mock_agent):
        mock_agent._memory_store._db.execute.return_value.fetchall.return_value = []

        res = client.get("/dashboard/topics")

        assert res.status_code == 200
        assert res.json() == []

    def test_handles_db_error(self, client, mock_agent):
        mock_agent._memory_store._db.execute.side_effect = RuntimeError("DB error")

        res = client.get("/dashboard/topics")

        assert res.status_code == 200
        assert res.json() == []


# ── Test: GET /dashboard/entities ──


class TestDashboardEntities:
    def test_returns_entity_list(self, client, mock_agent):
        mock_agent._memory_store._db.execute.return_value.fetchall.return_value = [
            _make_memory_row(name="张三", entity_type="person", mention_count=20, first_seen="2025-01-01"),
            _make_memory_row(name="Python", entity_type="tech", mention_count=15, first_seen="2025-01-02"),
        ]

        res = client.get("/dashboard/entities?limit=2")

        assert res.status_code == 200
        data = res.json()
        assert len(data) == 2
        assert data[0]["name"] == "张三"
        assert data[0]["mention_count"] == 20
        assert data[0]["entity_type"] == "person"

    def test_handles_empty(self, client, mock_agent):
        mock_agent._memory_store._db.execute.return_value.fetchall.return_value = []

        res = client.get("/dashboard/entities")

        assert res.status_code == 200
        assert res.json() == []


# ── Test: GET /dashboard/recent ──


class TestDashboardRecent:
    def test_returns_recent_memories(self, client, mock_agent):
        mock_agent._memory_store.get_recent.return_value = [
            Memory(
                id="m1", content="学习了RAG技术", summary="RAG学习",
                source="user", timestamp=datetime.now(timezone.utc),
                importance=7, entities=["RAG", "AI"],
                memory_type="episodic", status="active",
            ),
            Memory(
                id="m2", content="关于Python的反思", summary="Python反思",
                source="reflect", timestamp=datetime.now(timezone.utc),
                importance=8, entities=["Python"],
                memory_type="reflect", status="active",
            ),
        ]

        res = client.get("/dashboard/recent?limit=2")

        assert res.status_code == 200
        data = res.json()
        assert len(data) == 2
        assert data[0]["id"] == "m1"
        assert data[0]["source"] == "user"
        assert data[0]["memory_type"] == "episodic"
        assert data[0]["status"] == "active"
        assert "RAG" in data[0]["entities"]

    def test_content_preview_truncates(self, client, mock_agent):
        long_content = "A" * 200
        mock_agent._memory_store.get_recent.return_value = [
            Memory(
                id="m1", content=long_content, summary=None,
                source="user", timestamp=datetime.now(timezone.utc),
                importance=5, memory_type="episodic", status="active",
            ),
        ]

        res = client.get("/dashboard/recent?limit=1")

        data = res.json()
        assert len(data[0]["content_preview"]) <= 120

    def test_handles_store_error(self, client, mock_agent):
        mock_agent._memory_store.get_recent.side_effect = RuntimeError("store error")

        res = client.get("/dashboard/recent")

        assert res.status_code == 200
        assert res.json() == []


# ── Test: GET /dashboard/reflections ──


class TestDashboardReflections:
    def test_filters_only_reflect_source(self, client, mock_agent):
        mock_agent._memory_store.get_recent.return_value = [
            Memory(id="r1", content="反思：AI学习", summary="AI学习反思",
                   source="reflect", timestamp=datetime.now(timezone.utc),
                   importance=7, entities=["AI"], memory_type="reflect", status="active"),
            Memory(id="m1", content="普通记忆", summary=None,
                   source="user", timestamp=datetime.now(timezone.utc),
                   importance=5, entities=[], memory_type="episodic", status="active"),
            Memory(id="r2", content="反思：Python", summary="Python反思",
                   source="reflect", timestamp=datetime.now(timezone.utc),
                   importance=6, entities=["Python"], memory_type="reflect", status="active"),
        ]

        res = client.get("/dashboard/reflections?limit=5")

        data = res.json()
        assert len(data) == 2
        assert all(r["id"].startswith("r") for r in data)

    def test_topic_uses_first_entity(self, client, mock_agent):
        mock_agent._memory_store.get_recent.return_value = [
            Memory(id="r1", content="反思", summary="反思摘要",
                   source="reflect", timestamp=datetime.now(timezone.utc),
                   importance=7, entities=["机器学习", "AI"],
                   memory_type="reflect", status="active"),
        ]

        res = client.get("/dashboard/reflections?limit=1")

        data = res.json()
        assert data[0]["topic"] == "机器学习"

    def test_topic_default_when_no_entities(self, client, mock_agent):
        mock_agent._memory_store.get_recent.return_value = [
            Memory(id="r1", content="反思", summary="反思摘要",
                   source="reflect", timestamp=datetime.now(timezone.utc),
                   importance=7, entities=[],
                   memory_type="reflect", status="active"),
        ]

        res = client.get("/dashboard/reflections?limit=1")

        data = res.json()
        assert data[0]["topic"] == "未分类"

    def test_handles_store_error(self, client, mock_agent):
        mock_agent._memory_store.get_recent.side_effect = RuntimeError("store error")

        res = client.get("/dashboard/reflections")

        assert res.status_code == 200
        assert res.json() == []


# ── Test: GET /dashboard/weekly-report ──


class TestDashboardWeeklyReport:
    def test_returns_not_implemented_status(self, client, mock_agent):
        mock_agent._memory_store._db.execute.return_value.fetchone.return_value = _make_memory_row(cnt=0)
        mock_agent._memory_store._db.execute.return_value.fetchall.return_value = []

        res = client.get("/dashboard/weekly-report")

        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "not_implemented"
        assert "v0.4" in data["message"]

    def test_includes_basic_stats(self, client, mock_agent):
        """mock 返回本周新增 12 条，反思 3 条。"""
        fetchone_returns = [
            _make_memory_row(cnt=12),   # week_new query
            _make_memory_row(cnt=3),    # week_reflect query
        ]
        mock_agent._memory_store._db.execute.return_value.fetchone.side_effect = fetchone_returns
        mock_agent._memory_store._db.execute.return_value.fetchall.return_value = [
            _make_memory_row(name="AI"),
            _make_memory_row(name="Python"),
            _make_memory_row(name="RAG"),
        ]

        res = client.get("/dashboard/weekly-report")

        data = res.json()
        assert data["stats"]["week_new_memories"] == 12
        assert data["stats"]["week_reflections"] == 3
        assert data["stats"]["week_top_entities"] == ["AI", "Python", "RAG"]

    def test_handles_db_error(self, client, mock_agent):
        mock_agent._memory_store._db.execute.side_effect = RuntimeError("DB error")

        res = client.get("/dashboard/weekly-report")

        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "not_implemented"


# ── Test: 现有端点仍然正常 ──


class TestExistingEndpoints:
    def test_metrics_returns_data(self, client, mock_agent):
        mock_agent._memory_store.get_recent.return_value = []

        res = client.get("/dashboard/metrics")

        assert res.status_code == 200
        data = res.json()
        assert "memory_count" in data
        assert "reflection_count" in data

    def test_runtime_returns_stats(self, client):
        res = client.get("/dashboard/runtime")

        assert res.status_code == 200

    def test_traces_return_empty(self, client):
        res = client.get("/dashboard/traces")

        assert res.status_code == 200
        assert res.json() == []
