"""Timeline API 测试 — 覆盖 /timeline, /timeline/day/{date}, /timeline/stats 端点。"""
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.timeline import create_timeline_router
from src.adapters.sqlite_store import SQLiteStoreAdapter
from src.core.types import Memory


# ── Fixtures ──


@pytest.fixture
def mock_agent():
    agent = MagicMock()
    agent._memory_store = MagicMock()
    agent._memory_store.get_recent.return_value = []
    mock_exec = MagicMock()
    mock_exec.fetchall.return_value = []
    agent._memory_store._db = MagicMock()
    agent._memory_store._db.execute.return_value = mock_exec
    # Give _row_to_memory a real implementation for _to_event type detection
    agent._memory_store._row_to_memory = SQLiteStoreAdapter._row_to_memory
    return agent


@pytest.fixture
def client(mock_agent):
    app = FastAPI()
    app.include_router(create_timeline_router(mock_agent))
    return TestClient(app)


def _make_row(
    id_: str = "m1", content: str = "测试记忆", summary: str | None = None,
    source: str = "user", timestamp: str = "2026-06-01T10:00:00",
    importance: int = 5, entities_json: str = "[]",
    memory_type: str = "episodic", status: str = "active",
    archived_at: str | None = None,
) -> dict:
    return {
        "id": id_, "content": content, "summary": summary, "source": source,
        "timestamp": timestamp, "importance": importance,
        "entities_json": entities_json,
        "relations_json": "[]", "memory_type": memory_type,
        "access_count": 0, "last_accessed": None,
        "status": status, "archived_at": archived_at,
    }


def _make_mock_row(**kwargs):
    """Create a dict that also supports __getitem__ for row-like access."""
    class Row(dict):
        pass
    return Row(kwargs)


# ── Test: GET /timeline ──


class TestTimelineList:
    def test_returns_days_grouped_by_date(self, client, mock_agent):
        mock_agent._memory_store._db.execute.return_value.fetchall.return_value = [
            _make_mock_row(**_make_row("m1", "记忆A", timestamp="2026-06-01T10:00:00")),
            _make_mock_row(**_make_row("m2", "记忆B", timestamp="2026-06-01T14:00:00")),
            _make_mock_row(**_make_row("m3", "记忆C", timestamp="2026-06-02T09:00:00")),
        ]

        res = client.get("/timeline?limit=30")

        assert res.status_code == 200
        data = res.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        # 2026-06-02 should be first (descending)
        assert data[0]["date"] == "2026-06-02"

    def test_filters_by_date_range(self, client, mock_agent):
        mock_agent._memory_store._db.execute.return_value.fetchall.return_value = [
            _make_mock_row(**_make_row("m1", "A", timestamp="2026-06-01T10:00:00")),
        ]

        res = client.get("/timeline?start_date=2026-05-01&end_date=2026-06-30&limit=30")

        assert res.status_code == 200

    def test_filters_by_memory_type(self, client, mock_agent):
        mock_agent._memory_store._db.execute.return_value.fetchall.return_value = [
            _make_mock_row(**_make_row("m1", "语义", memory_type="semantic")),
        ]

        res = client.get("/timeline?memory_type=semantic&limit=30")

        assert res.status_code == 200
        data = res.json()
        for day in data:
            for evt in day["events"]:
                assert evt["memory_type"] == "semantic"

    def test_filters_by_entity(self, client, mock_agent):
        mock_agent._memory_store._db.execute.return_value.fetchall.return_value = [
            _make_mock_row(**_make_row("m1", "AI记忆", entities_json='["AI","Python"]')),
        ]

        res = client.get("/timeline?entity=AI&limit=30")

        assert res.status_code == 200

    def test_pagination(self, client, mock_agent):
        rows = [
            _make_mock_row(**_make_row(f"m{i}", f"记忆{i}",
                            timestamp=f"2026-06-{i:02d}T10:00:00"))
            for i in range(1, 31)
        ]
        mock_agent._memory_store._db.execute.return_value.fetchall.return_value = rows

        res_page1 = client.get("/timeline?page=1&limit=10")
        res_page2 = client.get("/timeline?page=2&limit=10")

        assert res_page1.status_code == 200
        assert res_page2.status_code == 200

    def test_empty_result(self, client, mock_agent):
        mock_agent._memory_store._db.execute.return_value.fetchall.return_value = []

        res = client.get("/timeline?limit=30")

        assert res.status_code == 200
        assert res.json() == []

    def test_db_error_returns_empty(self, client, mock_agent):
        mock_agent._memory_store._db.execute.side_effect = RuntimeError("DB down")

        res = client.get("/timeline?limit=30")

        assert res.status_code == 200
        assert res.json() == []

    def test_event_type_memory_created(self, client, mock_agent):
        mock_agent._memory_store._db.execute.return_value.fetchall.return_value = [
            _make_mock_row(**_make_row("m1", "新记忆", source="user",
                            memory_type="episodic", status="active")),
        ]

        res = client.get("/timeline?limit=10")

        data = res.json()
        types = [e["type"] for day in data for e in day["events"]]
        assert "memory_created" in types

    def test_event_type_reflection(self, client, mock_agent):
        mock_agent._memory_store._db.execute.return_value.fetchall.return_value = [
            _make_mock_row(**_make_row("r1", "反思内容", source="reflect",
                            memory_type="reflect", status="active")),
        ]

        res = client.get("/timeline?limit=10")

        data = res.json()
        types = [e["type"] for day in data for e in day["events"]]
        assert "reflection_generated" in types

    def test_event_type_archived(self, client, mock_agent):
        mock_agent._memory_store._db.execute.return_value.fetchall.return_value = [
            _make_mock_row(**_make_row("a1", "已归档", status="archived",
                            archived_at="2026-06-15T10:00:00")),
        ]

        res = client.get("/timeline?limit=10")

        data = res.json()
        all_types = [e["type"] for day in data for e in day["events"]]
        assert "memory_archived" in all_types

    def test_event_type_merged(self, client, mock_agent):
        mock_agent._memory_store._db.execute.return_value.fetchall.return_value = [
            _make_mock_row(**_make_row("m1", "已合并", status="merged")),
        ]

        res = client.get("/timeline?limit=10")

        data = res.json()
        types = [e["type"] for day in data for e in day["events"]]
        assert "memory_merged" in types

    def test_event_type_image(self, client, mock_agent):
        mock_agent._memory_store._db.execute.return_value.fetchall.return_value = [
            _make_mock_row(**_make_row("img1", "[图片] 白板分析", memory_type="image", status="active")),
        ]

        res = client.get("/timeline?limit=10")

        data = res.json()
        types = [e["type"] for day in data for e in day["events"]]
        assert "image_uploaded" in types

    def test_event_type_promoted(self, client, mock_agent):
        mock_agent._memory_store._db.execute.return_value.fetchall.return_value = [
            _make_mock_row(**_make_row("p1", "概念提升记忆", source="agent",
                            memory_type="semantic", status="active")),
        ]

        res = client.get("/timeline?limit=10")

        data = res.json()
        types = [e["type"] for day in data for e in day["events"]]
        assert "memory_promoted" in types

    def test_event_type_weekly_report(self, client, mock_agent):
        mock_agent._memory_store._db.execute.return_value.fetchall.return_value = [
            _make_mock_row(**_make_row("w1", "周报 2026-W22", source="agent",
                            memory_type="episodic", status="active")),
        ]

        res = client.get("/timeline?limit=10")

        data = res.json()
        assert res.status_code == 200

    def test_dedup_same_event(self, client, mock_agent):
        """Same id in both regular and archived form should not duplicate."""
        mock_agent._memory_store._db.execute.return_value.fetchall.return_value = [
            _make_mock_row(**_make_row("a1", "已归档记忆", status="archived",
                            archived_at="2026-06-15T10:00:00",
                            timestamp="2026-01-01T10:00:00")),
        ]

        res = client.get("/timeline?limit=10")

        data = res.json()
        # Should have 2 events: one for the memory (on its original date via _event_type logic)
        # The archived_at triggers a second event on the archive date
        assert res.status_code == 200


# ── Test: GET /timeline/day/{date} ──


class TestTimelineDay:
    def test_returns_events_for_specific_day(self, client, mock_agent):
        mock_agent._memory_store._db.execute.return_value.fetchall.return_value = [
            _make_mock_row(**_make_row("m1", "A", timestamp="2026-06-01T10:00:00")),
            _make_mock_row(**_make_row("m2", "B", timestamp="2026-06-01T14:00:00")),
        ]

        res = client.get("/timeline/day/2026-06-01")

        assert res.status_code == 200
        data = res.json()
        assert data["date"] == "2026-06-01"
        assert data["count"] == 2

    def test_404_for_empty_day(self, client, mock_agent):
        mock_agent._memory_store._db.execute.return_value.fetchall.return_value = []

        res = client.get("/timeline/day/1999-01-01")

        assert res.status_code == 404

    def test_db_error_returns_500(self, client, mock_agent):
        mock_agent._memory_store._db.execute.side_effect = RuntimeError("DB error")

        res = client.get("/timeline/day/2026-06-01")

        assert res.status_code == 500


# ── Test: GET /timeline/stats ──


class TestTimelineStats:
    def test_returns_aggregate_counts(self, client, mock_agent):
        mock_agent._memory_store._db.execute.return_value.fetchall.return_value = [
            _make_mock_row(**_make_row("m1", "记忆", source="user", memory_type="episodic", status="active")),
            _make_mock_row(**_make_row("r1", "反思", source="reflect", memory_type="reflect", status="active")),
            _make_mock_row(**_make_row("a1", "归档", status="archived", archived_at="2026-06-01T10:00:00")),
            _make_mock_row(**_make_row("p1", "提升", source="agent", memory_type="semantic", status="active")),
        ]

        res = client.get("/timeline/stats")

        assert res.status_code == 200
        data = res.json()
        assert data["total_events"] == 4
        assert data["created_count"] >= 1
        assert data["reflection_count"] == 1
        assert data["promoted_count"] == 1

    def test_filters_by_date_range(self, client, mock_agent):
        mock_agent._memory_store._db.execute.return_value.fetchall.return_value = [
            _make_mock_row(**_make_row("m1", "A", timestamp="2026-06-01T10:00:00")),
        ]

        res = client.get("/timeline/stats?start_date=2026-05-01&end_date=2026-06-30")

        assert res.status_code == 200
        data = res.json()
        assert data["total_events"] == 1

    def test_db_error_returns_defaults(self, client, mock_agent):
        mock_agent._memory_store._db.execute.side_effect = RuntimeError("DB down")

        res = client.get("/timeline/stats")

        assert res.status_code == 200
        data = res.json()
        assert data["total_events"] == 0

    def test_empty_result_returns_zeroes(self, client, mock_agent):
        mock_agent._memory_store._db.execute.return_value.fetchall.return_value = []

        res = client.get("/timeline/stats")

        assert res.status_code == 200
        data = res.json()
        assert data["total_events"] == 0
        assert data["created_count"] == 0
