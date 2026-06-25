"""AnalyticsStore 单元测试 — 验证 async 写入 + 聚合 + 失败降级。

覆盖：
- 4 张表的写入（agent_runs / memory_events / user_activity / token_usage）
- UPSERT 语义（user_activity / token_usage）
- 幂等 schema 初始化
- 异常降级（不抛出）
"""
import asyncio
import os
import sqlite3
import tempfile
from datetime import datetime, timezone

import pytest
from unittest.mock import MagicMock

from src.adapters.config import Settings
from src.core.analytics.analytics_store import AnalyticsStore


@pytest.fixture
def settings(tmp_path):
    """创建测试 Settings（临时 DB 路径）。"""
    return Settings(
        deepseek_api_key="test",
        environment="test",
        sqlite_db_path=str(tmp_path / "test_analytics.db"),
    )


@pytest.fixture
def store(settings):
    """创建 AnalyticsStore。"""
    s = AnalyticsStore(settings)
    yield s
    s.close()


# ── Schema 初始化测试 ──────────────────────────────────


class TestAnalyticsStoreSchema:
    def test_creates_all_four_tables(self, store):
        """4 张 analytics 表都被创建。"""
        conn = store.conn
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()]
        assert "analytics_user_activity_daily" in tables
        assert "analytics_agent_runs" in tables
        assert "analytics_memory_events" in tables
        assert "analytics_token_usage_daily" in tables

    def test_idempotent_init(self, settings):
        """多次初始化不报错。"""
        s1 = AnalyticsStore(settings)
        s2 = AnalyticsStore(settings)
        s1.close()
        s2.close()

    def test_indexes_created(self, store):
        """索引被创建。"""
        conn = store.conn
        indexes = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        ).fetchall()]
        assert "idx_auad_tenant_date" in indexes
        assert "idx_aar_tenant_created" in indexes
        assert "idx_ame_tenant_type" in indexes
        assert "idx_atud_tenant_date" in indexes


# ── Agent Runs 写入测试 ────────────────────────────────


class TestRecordAgentRun:
    def test_records_success(self, store):
        run_id = asyncio.run(store.record_agent_run(
            tenant_id="t1", workspace_id="w1", agent_name="knowledge_agent",
            status="success", duration_ms=150.5, prompt_tokens=500,
            completion_tokens=200, cost_usd=0.05,
        ))
        assert run_id.startswith("ar_")

        rows = store.conn.execute(
            "SELECT * FROM analytics_agent_runs WHERE id = ?", (run_id,)
        ).fetchall()
        assert len(rows) == 1
        row = rows[0]
        assert row["status"] == "success"
        assert row["duration_ms"] == 150.5
        assert row["prompt_tokens"] == 500
        assert row["cost_usd"] == 0.05

    def test_records_failure(self, store):
        asyncio.run(store.record_agent_run(
            tenant_id="t1", workspace_id="w1", agent_name="research_agent",
            status="failed", duration_ms=50.0,
        ))
        rows = store.conn.execute(
            "SELECT * FROM analytics_agent_runs WHERE status = 'failed'"
        ).fetchall()
        assert len(rows) == 1

    def test_records_multiple_runs(self, store):
        for i in range(5):
            asyncio.run(store.record_agent_run(
                tenant_id="t1", workspace_id="w1", agent_name="agent",
                status="success" if i < 4 else "failed",
                duration_ms=100.0 + i,
            ))
        rows = store.conn.execute("SELECT * FROM analytics_agent_runs").fetchall()
        assert len(rows) == 5


# ── Memory Events 写入测试 ────────────────────────────


class TestRecordMemoryEvent:
    def test_records_insert(self, store):
        event_id = asyncio.run(store.record_memory_event(
            tenant_id="t1", workspace_id="w1", memory_type="episodic",
            event_type="INSERT", hit=False,
        ))
        assert event_id.startswith("me_")
        row = store.conn.execute(
            "SELECT * FROM analytics_memory_events WHERE id = ?", (event_id,)
        ).fetchone()
        assert row["event_type"] == "INSERT"
        assert row["hit"] == 0

    def test_records_hit(self, store):
        asyncio.run(store.record_memory_event(
            tenant_id="t1", workspace_id="w1", memory_type="semantic",
            event_type="HIT", hit=True,
        ))
        row = store.conn.execute(
            "SELECT * FROM analytics_memory_events WHERE event_type = 'HIT'"
        ).fetchone()
        assert row["hit"] == 1

    def test_records_delete(self, store):
        asyncio.run(store.record_memory_event(
            tenant_id="t1", workspace_id="w1", memory_type="episodic",
            event_type="DELETE", hit=False,
        ))
        row = store.conn.execute(
            "SELECT * FROM analytics_memory_events WHERE event_type = 'DELETE'"
        ).fetchone()
        assert row is not None


# ── User Activity 写入测试（UPSERT）────────────────────


class TestRecordUserActivity:
    def test_records_new_activity(self, store):
        asyncio.run(store.record_user_activity(
            tenant_id="t1", workspace_id="w1", user_id="u1",
            event_date="2026-06-23", sessions=1, messages=5, active_minutes=10,
        ))
        row = store.conn.execute(
            "SELECT * FROM analytics_user_activity_daily WHERE user_id = 'u1'"
        ).fetchone()
        assert row["sessions"] == 1
        assert row["messages"] == 5
        assert row["active_minutes"] == 10

    def test_upsert_aggregates(self, store):
        """同一 tenant+user+date 多次写入，累加 sessions/messages。"""
        asyncio.run(store.record_user_activity(
            tenant_id="t1", workspace_id="w1", user_id="u1",
            event_date="2026-06-23", sessions=1, messages=5, active_minutes=10,
        ))
        asyncio.run(store.record_user_activity(
            tenant_id="t1", workspace_id="w1", user_id="u1",
            event_date="2026-06-23", sessions=1, messages=3, active_minutes=5,
        ))
        row = store.conn.execute(
            "SELECT * FROM analytics_user_activity_daily WHERE user_id = 'u1'"
        ).fetchone()
        assert row["sessions"] == 2
        assert row["messages"] == 8
        assert row["active_minutes"] == 15

    def test_different_dates_separate(self, store):
        asyncio.run(store.record_user_activity(
            tenant_id="t1", workspace_id="w1", user_id="u1",
            event_date="2026-06-22", sessions=1,
        ))
        asyncio.run(store.record_user_activity(
            tenant_id="t1", workspace_id="w1", user_id="u1",
            event_date="2026-06-23", sessions=1,
        ))
        rows = store.conn.execute(
            "SELECT * FROM analytics_user_activity_daily WHERE user_id = 'u1'"
        ).fetchall()
        assert len(rows) == 2


# ── Token Usage 写入测试（UPSERT）──────────────────────


class TestRecordTokenUsage:
    def test_records_new_usage(self, store):
        asyncio.run(store.record_token_usage(
            tenant_id="t1", workspace_id="w1", event_date="2026-06-23",
            prompt_tokens=1000, completion_tokens=500, cost_usd=0.02,
        ))
        row = store.conn.execute(
            "SELECT * FROM analytics_token_usage_daily WHERE event_date = '2026-06-23'"
        ).fetchone()
        assert row["prompt_tokens"] == 1000
        assert row["cost_usd"] == 0.02

    def test_upsert_aggregates(self, store):
        asyncio.run(store.record_token_usage(
            tenant_id="t1", workspace_id="w1", event_date="2026-06-23",
            prompt_tokens=1000, completion_tokens=500, cost_usd=0.02,
        ))
        asyncio.run(store.record_token_usage(
            tenant_id="t1", workspace_id="w1", event_date="2026-06-23",
            prompt_tokens=500, completion_tokens=200, cost_usd=0.01,
        ))
        row = store.conn.execute(
            "SELECT * FROM analytics_token_usage_daily WHERE event_date = '2026-06-23'"
        ).fetchone()
        assert row["prompt_tokens"] == 1500
        assert row["completion_tokens"] == 700
        assert row["cost_usd"] == 0.03


# ── 失败降级测试 ───────────────────────────────────────


class TestAnalyticsStoreFailure:
    def test_write_failure_does_not_raise(self, settings):
        """写入失败时仅记录日志，不抛出。"""
        store = AnalyticsStore(settings)
        # 关闭连接模拟故障
        store._conn.close()
        # 不应抛出
        run_id = asyncio.run(store.record_agent_run(
            tenant_id="t1", workspace_id="w1", agent_name="a",
            status="success", duration_ms=100,
        ))
        assert run_id.startswith("ar_")  # ID 仍生成
        store.close()
