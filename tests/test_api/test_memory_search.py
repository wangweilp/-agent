"""Memory Search & Management API 测试 — 覆盖 search/update/delete/merge/archive 端点。"""
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes import create_router
from src.core.types import Memory


# ── Fixtures ──


@pytest.fixture
def mock_agent():
    agent = MagicMock()
    agent._memory_store = MagicMock()
    agent._memory_store.get_recent.return_value = []
    agent._memory_store.search_by_entity.return_value = []
    # _row_to_memory: 使用真实的 Memory dataclass 序列化逻辑
    # mock _db.execute → fetchall return [] by default
    mock_exec = MagicMock()
    mock_exec.fetchall.return_value = []
    agent._memory_store._db = MagicMock()
    agent._memory_store._db.execute.return_value = mock_exec
    # vector store
    agent._vector_store = MagicMock()
    agent._vector_store._collection = MagicMock()
    agent._vector_store._collection.get.return_value = {"ids": ["dummy"]}
    # embedding
    agent._embedding = MagicMock()
    agent._embedding.encode.return_value = [0.1] * 512
    return agent


@pytest.fixture
def client(mock_agent):
    app = FastAPI()
    app.include_router(create_router(mock_agent))
    return TestClient(app)


def _make_memory(
    id_: str = "m1", content: str = "测试记忆", source: str = "user",
    memory_type: str = "episodic", status: str = "active",
    importance: int = 5, entities: list[str] | None = None,
    days_ago: int = 10,
) -> Memory:
    return Memory(
        id=id_, content=content, summary=None, source=source,
        timestamp=datetime.now(timezone.utc) - timedelta(days=days_ago),
        importance=importance, entities=entities or [], memory_type=memory_type,
        status=status,
    )


# ── Test: GET /memory/search ──

# 搜索端点使用 store._row_to_memory() 来转换 SQL 行 → Memory 对象。
# 在 mock 环境中，_row_to_memory 是 MagicMock，返回 MagicMock 而非真正的 Memory。
# 解决方案：用真实的 static method 替换 mock 的 _row_to_memory。


class TestMemorySearch:
    def test_keyword_search_returns_results(self, client, mock_agent):
        # 替换 _row_to_memory 为真实实现
        from src.adapters.sqlite_store import SQLiteStoreAdapter
        mock_agent._memory_store._row_to_memory = SQLiteStoreAdapter._row_to_memory
        mock_agent._memory_store._db.execute.return_value.fetchall.return_value = [
            {"id": "m1", "content": "学习RAG技术", "summary": None, "source": "user",
             "timestamp": "2026-01-01T00:00:00", "importance": 7, "entities_json": '["RAG"]',
             "relations_json": "[]", "memory_type": "episodic", "access_count": 0,
             "last_accessed": None, "status": "active", "archived_at": None},
        ]

        res = client.get("/memory/search?q=RAG&semantic=false&limit=10")

        assert res.status_code == 200
        data = res.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        assert data[0]["entities"] == ["RAG"]

    def test_entity_search_returns_results(self, client, mock_agent):
        mock_agent._memory_store.search_by_entity.return_value = [
            _make_memory("e1", "关于AI的记忆", entities=["AI"]),
        ]

        res = client.get("/memory/search?q=AI&limit=10")

        assert res.status_code == 200
        data = res.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_filter_by_memory_type(self, client, mock_agent):
        from src.adapters.sqlite_store import SQLiteStoreAdapter
        mock_agent._memory_store._row_to_memory = SQLiteStoreAdapter._row_to_memory
        mock_agent._memory_store._db.execute.return_value.fetchall.return_value = [
            {"id": "e1", "content": "情景", "summary": None, "source": "user",
             "timestamp": "2026-01-01T00:00:00", "importance": 7, "entities_json": "[]",
             "relations_json": "[]", "memory_type": "episodic", "access_count": 0,
             "last_accessed": None, "status": "active", "archived_at": None},
            {"id": "s1", "content": "语义", "summary": None, "source": "user",
             "timestamp": "2026-01-02T00:00:00", "importance": 5, "entities_json": "[]",
             "relations_json": "[]", "memory_type": "semantic", "access_count": 0,
             "last_accessed": None, "status": "active", "archived_at": None},
        ]

        res = client.get("/memory/search?q=test&type=episodic&limit=50")

        assert res.status_code == 200
        types = [m["memory_type"] for m in res.json()]
        assert all(t == "episodic" for t in types)

    def test_filter_by_status(self, client, mock_agent):
        from src.adapters.sqlite_store import SQLiteStoreAdapter
        mock_agent._memory_store._row_to_memory = SQLiteStoreAdapter._row_to_memory
        mock_agent._memory_store._db.execute.return_value.fetchall.return_value = [
            {"id": "a1", "content": "活跃", "summary": None, "source": "user",
             "timestamp": "2026-01-01T00:00:00", "importance": 5, "entities_json": "[]",
             "relations_json": "[]", "memory_type": "episodic", "access_count": 0,
             "last_accessed": None, "status": "active", "archived_at": None},
            {"id": "a2", "content": "归档", "summary": None, "source": "user",
             "timestamp": "2026-01-02T00:00:00", "importance": 5, "entities_json": "[]",
             "relations_json": "[]", "memory_type": "episodic", "access_count": 0,
             "last_accessed": None, "status": "archived", "archived_at": "2026-03-01T00:00:00"},
        ]

        res = client.get("/memory/search?q=test&status=archived&limit=50")

        assert res.status_code == 200
        data = res.json()
        assert isinstance(data, list)
        assert all(m["status"] == "archived" for m in data)

    def test_default_excludes_deleted_merged(self, client, mock_agent):
        from src.adapters.sqlite_store import SQLiteStoreAdapter
        mock_agent._memory_store._row_to_memory = SQLiteStoreAdapter._row_to_memory
        mock_agent._memory_store._db.execute.return_value.fetchall.return_value = [
            {"id": "a1", "content": "活跃", "summary": None, "source": "user",
             "timestamp": "2026-01-01T00:00:00", "importance": 5, "entities_json": "[]",
             "relations_json": "[]", "memory_type": "episodic", "access_count": 0,
             "last_accessed": None, "status": "active", "archived_at": None},
            {"id": "d1", "content": "已删除", "summary": None, "source": "user",
             "timestamp": "2026-01-02T00:00:00", "importance": 5, "entities_json": "[]",
             "relations_json": "[]", "memory_type": "episodic", "access_count": 0,
             "last_accessed": None, "status": "deleted", "archived_at": None},
        ]

        res = client.get("/memory/search?q=test&limit=50")

        data = res.json()
        assert isinstance(data, list)
        ids = {m["id"] for m in data}
        assert "a1" in ids
        assert "d1" not in ids

    def test_date_filter(self, client, mock_agent):
        from src.adapters.sqlite_store import SQLiteStoreAdapter
        mock_agent._memory_store._row_to_memory = SQLiteStoreAdapter._row_to_memory
        mock_agent._memory_store._db.execute.return_value.fetchall.return_value = []

        res = client.get("/memory/search?date_from=2026-05-01&limit=50")

        assert res.status_code == 200

    def test_empty_result(self, client, mock_agent):
        from src.adapters.sqlite_store import SQLiteStoreAdapter
        mock_agent._memory_store._row_to_memory = SQLiteStoreAdapter._row_to_memory
        mock_agent._memory_store._db.execute.return_value.fetchall.return_value = []

        res = client.get("/memory/search?q=nonexistent&limit=10")

        assert res.status_code == 200
        data = res.json()
        assert data == []

    def test_semantic_search_flag(self, client, mock_agent):
        mock_agent._vector_store.search.return_value = []

        res = client.get("/memory/search?q=机器学习&semantic=true&limit=10")

        assert res.status_code == 200
        assert isinstance(res.json(), list)


# ── Test: PATCH /memory/{id} ──


class TestMemoryUpdate:
    def test_updates_content(self, client, mock_agent):
        mem = _make_memory("m1", "原始内容")
        mock_agent._memory_store.get_by_id.return_value = mem

        res = client.patch("/memory/m1", json={"content": "更新后的内容"})

        assert res.status_code == 200
        data = res.json()
        assert data["content"] == "更新后的内容"
        mock_agent._memory_store.store.assert_called_once()

    def test_updates_importance(self, client, mock_agent):
        mem = _make_memory("m1", "内容", importance=5)
        mock_agent._memory_store.get_by_id.return_value = mem

        res = client.patch("/memory/m1", json={"importance": 9})

        assert res.status_code == 200
        data = res.json()
        assert data["importance"] == 9

    def test_updates_entities(self, client, mock_agent):
        mem = _make_memory("m1", "内容", entities=["旧实体"])
        mock_agent._memory_store.get_by_id.return_value = mem

        res = client.patch("/memory/m1", json={"entities": ["新实体1", "新实体2"]})

        assert res.status_code == 200
        assert "新实体1" in res.json()["entities"]

    def test_404_for_nonexistent(self, client, mock_agent):
        mock_agent._memory_store.get_by_id.return_value = None

        res = client.patch("/memory/nonexistent", json={"content": "新"})

        assert res.status_code == 404

    def test_store_failure_returns_500(self, client, mock_agent):
        mem = _make_memory("m1", "内容")
        mock_agent._memory_store.get_by_id.return_value = mem
        mock_agent._memory_store.store.side_effect = RuntimeError("DB write failed")

        res = client.patch("/memory/m1", json={"content": "新"})

        assert res.status_code == 500


# ── Test: DELETE /memory/{id} ──


class TestMemoryDelete:
    def test_soft_deletes_memory(self, client, mock_agent):
        mem = _make_memory("m1", "内容")
        mock_agent._memory_store.get_by_id.return_value = mem

        res = client.delete("/memory/m1")

        assert res.status_code == 200
        data = res.json()
        assert data["id"] == "m1"
        assert data["status"] == "deleted"
        mock_agent._memory_store.update_status.assert_called_with("m1", "deleted")

    def test_404_for_nonexistent(self, client, mock_agent):
        mock_agent._memory_store.get_by_id.return_value = None

        res = client.delete("/memory/nonexistent")

        assert res.status_code == 404

    def test_delete_failure_returns_500(self, client, mock_agent):
        mem = _make_memory("m1", "内容")
        mock_agent._memory_store.get_by_id.return_value = mem
        mock_agent._memory_store.update_status.side_effect = RuntimeError("DB error")

        res = client.delete("/memory/m1")

        assert res.status_code == 500


# ── Test: POST /memory/merge ──


class TestMemoryMerge:
    def test_merges_secondary_into_primary(self, client, mock_agent):
        primary = _make_memory("p1", "主记忆", importance=5, entities=["AI"])
        secondary = _make_memory("s1", "从记忆", importance=8, entities=["RAG"])
        mock_agent._memory_store.get_by_id.side_effect = [primary, secondary]

        res = client.post("/memory/merge", json={
            "primary_id": "p1",
            "secondary_ids": ["s1"],
        })

        assert res.status_code == 200
        data = res.json()
        assert data["primary_id"] == "p1"
        assert data["merged_count"] == 1
        assert "s1" in data["merged_ids"]
        assert secondary.status == "merged"

    def test_merges_entities(self, client, mock_agent):
        primary = _make_memory("p1", "主记忆", entities=["AI"])
        secondary = _make_memory("s1", "从记忆", entities=["RAG", "ChromaDB"])
        mock_agent._memory_store.get_by_id.side_effect = [primary, secondary]

        client.post("/memory/merge", json={"primary_id": "p1", "secondary_ids": ["s1"]})

        assert "AI" in primary.entities
        assert "RAG" in primary.entities
        assert "ChromaDB" in primary.entities

    def test_takes_max_importance(self, client, mock_agent):
        primary = _make_memory("p1", "主记忆", importance=3)
        secondary = _make_memory("s1", "从记忆", importance=9)
        mock_agent._memory_store.get_by_id.side_effect = [primary, secondary]

        client.post("/memory/merge", json={"primary_id": "p1", "secondary_ids": ["s1"]})

        assert primary.importance == 9

    def test_404_for_nonexistent_primary(self, client, mock_agent):
        mock_agent._memory_store.get_by_id.return_value = None

        res = client.post("/memory/merge", json={"primary_id": "bad", "secondary_ids": ["s1"]})

        assert res.status_code == 404

    def test_skips_nonexistent_secondaries(self, client, mock_agent):
        primary = _make_memory("p1", "主记忆")
        mock_agent._memory_store.get_by_id.side_effect = [primary, None]

        res = client.post("/memory/merge", json={"primary_id": "p1", "secondary_ids": ["bad"]})

        assert res.status_code == 400  # no valid secondaries → 400

    def test_empty_secondary_ids_rejected(self, client):
        res = client.post("/memory/merge", json={"primary_id": "p1", "secondary_ids": []})

        assert res.status_code == 422  # Pydantic validation error


# ── Test: POST /memory/{id}/archive ──


class TestMemoryArchive:
    def test_archives_memory(self, client, mock_agent):
        mem = _make_memory("m1", "内容", status="active")
        mock_agent._memory_store.get_by_id.return_value = mem

        res = client.post("/memory/m1/archive")

        assert res.status_code == 200
        data = res.json()
        assert data["id"] == "m1"
        assert data["status"] == "archived"
        assert data["archived_at"] is not None
        assert mem.archived_at is not None

    def test_404_for_nonexistent(self, client, mock_agent):
        mock_agent._memory_store.get_by_id.return_value = None

        res = client.post("/memory/nonexistent/archive")

        assert res.status_code == 404

    def test_archive_failure_returns_500(self, client, mock_agent):
        mem = _make_memory("m1", "内容")
        mock_agent._memory_store.get_by_id.return_value = mem
        mock_agent._memory_store.store.side_effect = RuntimeError("DB error")

        res = client.post("/memory/m1/archive")

        assert res.status_code == 500


# ── Test: GET /memory/{id} ──


class TestMemoryGetById:
    def test_returns_full_memory_with_status(self, client, mock_agent):
        mem = _make_memory("m1", "完整记忆", status="active", entities=["AI", "Python"])
        mock_agent._memory_store.get_by_id.return_value = mem

        res = client.get("/memory/m1")

        assert res.status_code == 200
        data = res.json()
        assert data["id"] == "m1"
        assert data["status"] == "active"
        assert "relations" in data
        assert "archived_at" in data
        assert "embedding_status" in data

    def test_404_for_nonexistent(self, client, mock_agent):
        mock_agent._memory_store.get_by_id.return_value = None

        res = client.get("/memory/nonexistent")

        assert res.status_code == 404
