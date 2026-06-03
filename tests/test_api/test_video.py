"""Video API 测试 — 覆盖 list/get/update/delete/archive 端点 + analyzer 核心逻辑。"""
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.video import create_video_router
from src.adapters.config import Settings
from src.core.types import Memory
from src.core.video_analyzer import VideoAnalysisResult, VideoAnalyzer


# ── Fixtures ──


@pytest.fixture
def settings():
    return Settings(deepseek_api_key="sk-test")


@pytest.fixture
def mock_llm():
    llm = MagicMock()
    resp = MagicMock()
    resp.choices = [MagicMock()]
    resp.choices[0].message.content = '{"summary":"测试视频","topic":"教程","key_points":["点1"],"entities":["AI"],"concepts":["ML"],"suggested_use":"学习","importance_hint":7}'
    llm.chat.return_value = resp
    return llm


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
    app.include_router(create_video_router(settings, mock_llm, mock_writer, mock_agent))
    return TestClient(app)


def _make_memory(
    id_: str = "v1", content: str = "[视频记忆·工作区] test.mp4",
    source: str = "user", memory_type: str = "working",
    status: str = "active", importance: int = 7,
    entities: list[str] | None = None,
) -> Memory:
    return Memory(
        id=id_, content=content, summary=None, source=source,
        timestamp=datetime.now(timezone.utc), importance=importance,
        entities=entities or ["AI", "视频"], memory_type=memory_type,
        status=status,
    )


# ── Test: Video List ──


class TestVideoList:
    def test_returns_video_memories(self, client, mock_agent):
        mock_agent._memory_store.get_recent.return_value = [
            _make_memory("v1", "[视频记忆·工作区] 教程.mp4"),
            _make_memory("v2", "[视频记忆·情景] 会议.mov"),
            _make_memory("v3", "普通记忆"),
        ]

        res = client.get("/video?limit=20")

        assert res.status_code == 200
        data = res.json()
        assert len(data) >= 2

    def test_filters_by_query(self, client, mock_agent):
        mock_agent._memory_store.get_recent.return_value = [
            _make_memory("v1", "[视频记忆·工作区] RAG教程.mp4", entities=["RAG"]),
            _make_memory("v2", "[视频记忆·工作区] Python.mp4", entities=["Python"]),
        ]

        res = client.get("/video?q=RAG&limit=20")

        assert res.status_code == 200
        data = res.json()
        assert len(data) == 1

    def test_empty_when_no_agent(self):
        app = FastAPI()
        app.include_router(create_video_router(
            Settings(deepseek_api_key="sk-test"), MagicMock(), MagicMock(), None))
        c = TestClient(app)
        res = c.get("/video")
        assert res.status_code == 200
        assert res.json() == []

    def test_handles_store_error(self, client, mock_agent):
        mock_agent._memory_store.get_recent.side_effect = RuntimeError("DB down")
        res = client.get("/video")
        assert res.status_code == 200
        assert res.json() == []


# ── Test: Video Get By ID ──


class TestVideoGetById:
    def test_returns_detail(self, client, mock_agent):
        mock_agent._memory_store.get_by_id.return_value = _make_memory("v1")
        res = client.get("/video/v1")
        assert res.status_code == 200
        assert res.json()["id"] == "v1"

    def test_404(self, client, mock_agent):
        mock_agent._memory_store.get_by_id.return_value = None
        res = client.get("/video/nonexistent")
        assert res.status_code == 404


# ── Test: Video Update ──


class TestVideoUpdate:
    def test_updates(self, client, mock_agent):
        mock_agent._memory_store.get_by_id.return_value = _make_memory("v1")
        res = client.patch("/video/v1", json={"content": "[视频] 更新", "importance": 9})
        assert res.status_code == 200
        assert res.json()["importance"] == 9

    def test_404(self, client, mock_agent):
        mock_agent._memory_store.get_by_id.return_value = None
        assert client.patch("/video/nonexistent", json={"content": "新"}).status_code == 404

    def test_500_store_failure(self, client, mock_agent):
        mock_agent._memory_store.get_by_id.return_value = _make_memory("v1")
        mock_agent._memory_store.store.side_effect = RuntimeError("err")
        assert client.patch("/video/v1", json={"content": "新"}).status_code == 500


# ── Test: Video Delete ──


class TestVideoDelete:
    def test_soft_delete(self, client, mock_agent):
        mock_agent._memory_store.get_by_id.return_value = _make_memory("v1")
        res = client.delete("/video/v1")
        assert res.status_code == 200
        assert res.json()["status"] == "deleted"

    def test_404(self, client, mock_agent):
        mock_agent._memory_store.get_by_id.return_value = None
        assert client.delete("/video/nonexistent").status_code == 404

    def test_500(self, client, mock_agent):
        mock_agent._memory_store.get_by_id.return_value = _make_memory("v1")
        mock_agent._memory_store.update_status.side_effect = RuntimeError("e")
        assert client.delete("/video/v1").status_code == 500


# ── Test: Video Archive ──


class TestVideoArchive:
    def test_archive(self, client, mock_agent):
        mock_agent._memory_store.get_by_id.return_value = _make_memory("v1", status="active")
        res = client.post("/video/v1/archive")
        assert res.status_code == 200
        assert res.json()["status"] == "archived"

    def test_404(self, client, mock_agent):
        mock_agent._memory_store.get_by_id.return_value = None
        assert client.post("/video/nonexistent/archive").status_code == 404

    def test_500(self, client, mock_agent):
        mock_agent._memory_store.get_by_id.return_value = _make_memory("v1")
        mock_agent._memory_store.store.side_effect = RuntimeError("e")
        assert client.post("/video/v1/archive").status_code == 500


# ── Test: Video Upload ──


class TestVideoUpload:
    def test_rejects_no_files(self, client):
        assert client.post("/video/upload").status_code in (400, 422)

    def test_rejects_invalid_format(self, client):
        res = client.post("/video/upload", files=[("files", ("bad.txt", b"x", "text/plain"))])
        assert res.status_code == 400

    def test_rejects_empty_file_list(self, client):
        assert client.post("/video/upload", files=[]).status_code in (400, 422)


# ── Test: VideoAnalyzer (unit, no ffmpeg needed) ──


class TestVideoAnalyzer:
    def test_result_dataclass_defaults(self):
        r = VideoAnalysisResult()
        assert r.summary == ""
        assert r.topic == ""
        assert r.importance_hint == 5

    def test_parse_response_valid_json(self):
        raw = '{"summary":"视频摘要","topic":"教程","entities":["AI"],"concepts":["ML"],"key_points":["p1"],"suggested_use":"学习","importance_hint":8}'
        r = VideoAnalyzer._parse_response(raw)
        assert r.summary == "视频摘要"
        assert r.topic == "教程"
        assert r.entities == ["AI"]
        assert r.concepts == ["ML"]
        assert r.importance_hint == 8

    def test_parse_response_invalid_json(self):
        r = VideoAnalyzer._parse_response("不是JSON，纯文本")
        assert r.summary == "不是JSON，纯文本"
        assert r.topic == "未知"

    def test_parse_response_with_code_fence(self):
        raw = '```json\n{"summary":"视频","topic":"教程","key_points":[],"entities":[],"concepts":[],"suggested_use":"","importance_hint":5}\n```'
        r = VideoAnalyzer._parse_response(raw)
        assert r.summary == "视频"

    def test_ocr_parse_valid(self):
        raw = '{"text_in_frame":"Hello World","scene_description":"代码屏幕"}'
        text = VideoAnalyzer._parse_ocr_response(raw)
        assert text == "Hello World"

    def test_ocr_parse_plain_text(self):
        text = VideoAnalyzer._parse_ocr_response("屏幕上显示: def hello()")
        assert "def hello()" in text

    def test_validate_bad_extension(self, tmp_path):
        bad = tmp_path / "test.exe"
        bad.write_bytes(b"fake video content with enough bytes")
        with pytest.raises(ValueError, match="不支持的视频格式"):
            VideoAnalyzer._validate(str(bad))

    def test_validate_empty_file(self, tmp_path):
        emp = tmp_path / "empty.mp4"
        emp.write_text("")
        with pytest.raises(ValueError, match="视频文件为空"):
            VideoAnalyzer._validate(str(emp))

    def test_validate_missing_file(self):
        with pytest.raises(FileNotFoundError):
            VideoAnalyzer._validate("/nonexistent/file.mp4")

    def test_parse_markdown_code_block(self):
        raw = '```\n{"summary":"MD视频","topic":"教程","key_points":[],"entities":[],"concepts":[],"suggested_use":"","importance_hint":5}\n```'
        r = VideoAnalyzer._parse_response(raw)
        assert r.summary == "MD视频"

    def test_placeholder_analysis(self, mock_llm, tmp_path):
        """回退分析——ffmpeg 不可用时使用 LLM 基于文件名推断。"""
        analyzer = VideoAnalyzer(mock_llm)
        result = analyzer._analyze_placeholder("AI学习笔记.mp4", 10 * 1024 * 1024)
        assert result.summary == "测试视频"  # from mock_llm
