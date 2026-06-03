"""Audio API 测试 — 覆盖 list/get/update/delete/archive 端点。"""
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.audio import create_audio_router
from src.adapters.config import Settings
from src.core.types import Memory


# ── Fixtures ──


@pytest.fixture
def settings():
    return Settings(deepseek_api_key="sk-test")


@pytest.fixture
def mock_llm():
    return MagicMock()


@pytest.fixture
def mock_writer():
    writer = MagicMock()
    writer.pending = 0
    writer.stats = {
        "worker": {"alive": True, "started_at": "2026-01-01T00:00:00", "uptime_seconds": 0},
        "queue": {"pending": 0, "total_stored": 0, "total_failed": 0},
        "dead_letter": {"count": 0, "dir": "./data/dead_letter"},
        "recent_tasks": [],
    }
    writer.alerts = []
    return writer


@pytest.fixture
def mock_agent():
    agent = MagicMock()
    agent._memory_store = MagicMock()
    agent._memory_store.get_recent.return_value = []
    agent._memory_store.get_by_id.return_value = None
    return agent


@pytest.fixture
def client(settings, mock_llm, mock_writer, mock_agent):
    app = FastAPI()
    app.include_router(create_audio_router(settings, mock_llm, mock_writer, mock_agent))
    return TestClient(app)


def _make_memory(
    id_: str = "m1", content: str = "[音频记忆·工作区] test.mp3",
    source: str = "user", memory_type: str = "working",
    status: str = "active", importance: int = 7,
    entities: list[str] | None = None,
) -> Memory:
    return Memory(
        id=id_, content=content, summary=None, source=source,
        timestamp=datetime.now(timezone.utc), importance=importance,
        entities=entities or ["AI", "音频"], memory_type=memory_type,
        status=status,
    )


# ── Test: Audio List ──


class TestAudioList:
    def test_returns_audio_memories(self, client, mock_agent):
        mock_agent._memory_store.get_recent.return_value = [
            _make_memory("a1", "[音频记忆·工作区] 会议.mp3", memory_type="working"),
            _make_memory("a2", "[音频记忆·情景] 学习笔记.m4a", memory_type="episodic"),
            _make_memory("a3", "普通记忆", memory_type="episodic"),  # 非音频
        ]

        res = client.get("/audio?limit=20")

        assert res.status_code == 200
        data = res.json()
        assert len(data) >= 2  # 至少 2 条音频记忆

    def test_filters_by_query(self, client, mock_agent):
        mock_agent._memory_store.get_recent.return_value = [
            _make_memory("a1", "[音频记忆·工作区] RAG讨论.mp3", entities=["RAG"]),
            _make_memory("a2", "[音频记忆·工作区] Python学习.mp3", entities=["Python"]),
        ]

        res = client.get("/audio?q=RAG&limit=20")

        assert res.status_code == 200
        data = res.json()
        assert len(data) == 1
        assert "RAG" in data[0]["content"]

    def test_empty_when_no_agent(self):
        """无 agent 时返回空列表。"""
        app = FastAPI()
        app.include_router(create_audio_router(
            Settings(deepseek_api_key="sk-test"),
            MagicMock(), MagicMock(), None,
        ))
        client = TestClient(app)

        res = client.get("/audio")
        assert res.status_code == 200
        assert res.json() == []

    def test_handles_store_error(self, client, mock_agent):
        mock_agent._memory_store.get_recent.side_effect = RuntimeError("DB down")

        res = client.get("/audio")

        assert res.status_code == 200
        assert res.json() == []


# ── Test: Audio Get By ID ──


class TestAudioGetById:
    def test_returns_audio_detail(self, client, mock_agent):
        mem = _make_memory("a1", "[音频记忆·工作区] 内容")
        mock_agent._memory_store.get_by_id.return_value = mem

        res = client.get("/audio/a1")

        assert res.status_code == 200
        data = res.json()
        assert data["id"] == "a1"
        assert data["status"] == "active"

    def test_404_for_nonexistent(self, client, mock_agent):
        mock_agent._memory_store.get_by_id.return_value = None

        res = client.get("/audio/nonexistent")

        assert res.status_code == 404


# ── Test: Audio Update ──


class TestAudioUpdate:
    def test_updates_content(self, client, mock_agent):
        mem = _make_memory("a1", "[音频记忆·工作区] 原始")
        mock_agent._memory_store.get_by_id.return_value = mem

        res = client.patch("/audio/a1", json={"content": "[音频记忆·工作区] 更新后"})

        assert res.status_code == 200
        assert "更新后" in res.json()["content"]

    def test_updates_importance(self, client, mock_agent):
        mem = _make_memory("a1", importance=5)
        mock_agent._memory_store.get_by_id.return_value = mem

        res = client.patch("/audio/a1", json={"importance": 9})

        assert res.status_code == 200
        assert res.json()["importance"] == 9

    def test_404_for_nonexistent(self, client, mock_agent):
        mock_agent._memory_store.get_by_id.return_value = None

        res = client.patch("/audio/nonexistent", json={"content": "新"})

        assert res.status_code == 404

    def test_store_failure_500(self, client, mock_agent):
        mem = _make_memory("a1")
        mock_agent._memory_store.get_by_id.return_value = mem
        mock_agent._memory_store.store.side_effect = RuntimeError("write error")

        res = client.patch("/audio/a1", json={"content": "新"})

        assert res.status_code == 500


# ── Test: Audio Delete ──


class TestAudioDelete:
    def test_soft_deletes(self, client, mock_agent):
        mem = _make_memory("a1")
        mock_agent._memory_store.get_by_id.return_value = mem

        res = client.delete("/audio/a1")

        assert res.status_code == 200
        assert res.json()["status"] == "deleted"
        mock_agent._memory_store.update_status.assert_called_with("a1", "deleted")

    def test_404_for_nonexistent(self, client, mock_agent):
        mock_agent._memory_store.get_by_id.return_value = None

        res = client.delete("/audio/nonexistent")

        assert res.status_code == 404

    def test_delete_failure_500(self, client, mock_agent):
        mem = _make_memory("a1")
        mock_agent._memory_store.get_by_id.return_value = mem
        mock_agent._memory_store.update_status.side_effect = RuntimeError("error")

        res = client.delete("/audio/a1")

        assert res.status_code == 500


# ── Test: Audio Archive ──


class TestAudioArchive:
    def test_archives_memory(self, client, mock_agent):
        mem = _make_memory("a1", status="active")
        mock_agent._memory_store.get_by_id.return_value = mem

        res = client.post("/audio/a1/archive")

        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "archived"
        assert data["archived_at"] is not None

    def test_404_for_nonexistent(self, client, mock_agent):
        mock_agent._memory_store.get_by_id.return_value = None

        res = client.post("/audio/nonexistent/archive")

        assert res.status_code == 404

    def test_archive_failure_500(self, client, mock_agent):
        mem = _make_memory("a1")
        mock_agent._memory_store.get_by_id.return_value = mem
        mock_agent._memory_store.store.side_effect = RuntimeError("error")

        res = client.post("/audio/a1/archive")

        assert res.status_code == 500


# ── Test: Audio Upload ──


class TestAudioUpload:
    def test_upload_rejects_no_files(self, client):
        res = client.post("/audio/upload")
        # FastAPI returns 422 for missing required form field
        assert res.status_code in (400, 422)

    def test_upload_empty_file_list(self, client):
        res = client.post("/audio/upload", files=[])
        assert res.status_code in (400, 422)

    def test_upload_rejects_invalid_format(self, client):
        """非音频格式应被拒绝。"""
        fake_file = ("fake.txt", b"not audio", "text/plain")
        res = client.post("/audio/upload", files=[("files", fake_file)])
        assert res.status_code == 400  # 不支持的扩展名
