"""Dashboard V2 Analytics Pipeline 集成测试。

覆盖：
- AnalyticsRepository 从 analytics_* 表聚合查询
- Retention 计算（D1/D7/D30）
- 真实 Percentile 计算（P50/P95/P99）
- Alert Trigger（3 条规则）
- Fallback Logic（analytics 表为空时降级 usage_events）
- Empty DB
- AnalyticsPipeline 集成层
"""
import asyncio
import os
import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlite_utils import Database as SqliteDB

from src.api.dashboard_v2_router import create_dashboard_v2_router
from src.api.middleware import TokenPayload, require_auth
from src.core.analytics.analytics_repository import AnalyticsRepository
from src.core.analytics.analytics_store import AnalyticsStore
from src.core.analytics.analytics_pipeline import AnalyticsPipeline
from src.core.analytics.dashboard_alert_evaluator import DashboardAlertEvaluator
from src.core.dashboard_v2_service import DashboardV2Service
from src.adapters.config import Settings


# ── Schema（含 analytics 表 + usage_events + notes + subscriptions）──

_FULL_SCHEMA = """
CREATE TABLE IF NOT EXISTS analytics_user_activity_daily (
    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, workspace_id TEXT NOT NULL DEFAULT '',
    user_id TEXT NOT NULL, event_date TEXT NOT NULL,
    sessions INTEGER NOT NULL DEFAULT 0, messages INTEGER NOT NULL DEFAULT 0,
    active_minutes INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_auad_unique ON analytics_user_activity_daily(tenant_id, user_id, event_date);
CREATE INDEX IF NOT EXISTS idx_auad_date ON analytics_user_activity_daily(event_date);

CREATE TABLE IF NOT EXISTS analytics_agent_runs (
    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, workspace_id TEXT NOT NULL DEFAULT '',
    agent_name TEXT NOT NULL DEFAULT '', status TEXT NOT NULL,
    duration_ms REAL NOT NULL DEFAULT 0, prompt_tokens INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL DEFAULT 0, cost_usd REAL NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_aar_tenant_created ON analytics_agent_runs(tenant_id, created_at);

CREATE TABLE IF NOT EXISTS analytics_memory_events (
    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, workspace_id TEXT NOT NULL DEFAULT '',
    memory_type TEXT NOT NULL DEFAULT '', event_type TEXT NOT NULL,
    hit INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_ame_tenant_type ON analytics_memory_events(tenant_id, event_type, created_at);

CREATE TABLE IF NOT EXISTS analytics_token_usage_daily (
    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, workspace_id TEXT NOT NULL DEFAULT '',
    event_date TEXT NOT NULL, prompt_tokens INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL DEFAULT 0, cost_usd REAL NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_atud_unique ON analytics_token_usage_daily(tenant_id, workspace_id, event_date);

CREATE TABLE IF NOT EXISTS usage_events (
    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, user_id TEXT NOT NULL,
    resource TEXT NOT NULL, quantity INTEGER NOT NULL DEFAULT 1,
    workspace_id TEXT NOT NULL DEFAULT '', unit TEXT NOT NULL DEFAULT 'count',
    metadata_json TEXT NOT NULL DEFAULT '{}', cost_cents INTEGER NOT NULL DEFAULT 0,
    timestamp TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_ue_ts ON usage_events(timestamp);

CREATE TABLE IF NOT EXISTS notes (
    id TEXT PRIMARY KEY, content TEXT NOT NULL, summary TEXT, source TEXT,
    timestamp TEXT NOT NULL, importance INTEGER NOT NULL DEFAULT 5,
    entities_json TEXT NOT NULL DEFAULT '[]', relations_json TEXT NOT NULL DEFAULT '[]',
    memory_type TEXT DEFAULT 'episodic', access_count INTEGER NOT NULL DEFAULT 0,
    last_accessed TEXT, status TEXT NOT NULL DEFAULT 'active', archived_at TEXT,
    workspace_id TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS subscriptions (
    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, plan_tier TEXT NOT NULL DEFAULT 'free',
    status TEXT NOT NULL DEFAULT 'trial', billing_cycle TEXT NOT NULL DEFAULT 'monthly'
);
"""


@pytest.fixture
def db():
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    db = SqliteDB(conn)
    for stmt in _FULL_SCHEMA.strip().split(";"):
        s = stmt.strip()
        if s:
            db.execute(s)
    yield db
    conn.close()
    try:
        os.unlink(db_path)
    except OSError:
        pass


@pytest.fixture
def repo(db):
    return AnalyticsRepository(db)


@pytest.fixture
def mock_token():
    return TokenPayload(
        user_id="test-user", workspace_id="default",
        role="admin", email="test@example.com",
    )


@pytest.fixture
def client(repo, mock_token):
    service = DashboardV2Service(repo)
    app = FastAPI()
    app.include_router(create_dashboard_v2_router(service))
    app.dependency_overrides[require_auth] = lambda: mock_token
    return TestClient(app)


# ── 辅助函数 ───────────────────────────────────────────


def _insert_activity(db, tenant_id, user_id, event_date, sessions=1, messages=1):
    db.execute(
        """INSERT INTO analytics_user_activity_daily
           (id, tenant_id, workspace_id, user_id, event_date, sessions, messages, active_minutes)
           VALUES (?, ?, '', ?, ?, ?, ?, 1)""",
        [f"ua_{user_id}_{event_date}", tenant_id, user_id, event_date, sessions, messages],
    )


def _insert_agent_run(db, tenant_id, status, duration_ms, agent_name="agent", days_ago=0):
    ts = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
    db.execute(
        """INSERT INTO analytics_agent_runs
           (id, tenant_id, workspace_id, agent_name, status, duration_ms, created_at)
           VALUES (?, ?, '', ?, ?, ?, ?)""",
        [f"ar_{tenant_id}_{status}_{duration_ms}_{days_ago}", tenant_id, agent_name, status, duration_ms, ts],
    )


def _insert_memory_event(db, tenant_id, event_type, memory_type="episodic", hit=0, uid=None):
    import uuid
    eid = uid or f"me_{uuid.uuid4().hex[:8]}"
    db.execute(
        """INSERT INTO analytics_memory_events
           (id, tenant_id, workspace_id, memory_type, event_type, hit)
           VALUES (?, ?, '', ?, ?, ?)""",
        [eid, tenant_id, memory_type, event_type, hit],
    )


def _insert_token_usage(db, tenant_id, event_date, cost_usd, prompt_tokens=1000, uid=None):
    import uuid
    tid = uid or f"tu_{uuid.uuid4().hex[:8]}"
    db.execute(
        """INSERT INTO analytics_token_usage_daily
           (id, tenant_id, workspace_id, event_date, prompt_tokens, completion_tokens, cost_usd)
           VALUES (?, ?, '', ?, ?, 0, ?)""",
        [tid, tenant_id, event_date, prompt_tokens, cost_usd],
    )


# ═══════════════════════════════════════════════════════
# Repository 聚合查询测试（从 analytics 表）
# ═══════════════════════════════════════════════════════


class TestRepositoryAggregationFromAnalytics:
    def test_dau_from_analytics_table(self, db, repo):
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        _insert_activity(db, "t1", "u1", today)
        _insert_activity(db, "t1", "u2", today)
        _insert_activity(db, "t1", "u3", today)
        assert repo.get_dau() == 3

    def test_wau_from_analytics_table(self, db, repo):
        today = datetime.now(timezone.utc)
        for i in range(7):
            d = (today - timedelta(days=i)).strftime("%Y-%m-%d")
            _insert_activity(db, "t1", f"u{i}", d)
        assert repo.get_wau() == 7

    def test_mau_from_analytics_table(self, db, repo):
        today = datetime.now(timezone.utc)
        for i in range(30):
            d = (today - timedelta(days=i)).strftime("%Y-%m-%d")
            _insert_activity(db, "t1", f"u{i}", d)
        assert repo.get_mau() == 30

    def test_agent_success_rate_from_analytics(self, db, repo):
        _insert_agent_run(db, "t1", "success", 100)
        _insert_agent_run(db, "t1", "success", 200)
        _insert_agent_run(db, "t1", "success", 150)
        _insert_agent_run(db, "t1", "failed", 50)
        assert repo.get_agent_success_rate() == 75.0

    def test_memory_hit_rate_from_analytics(self, db, repo):
        _insert_memory_event(db, "t1", "INSERT", hit=0)
        _insert_memory_event(db, "t1", "INSERT", hit=0)
        _insert_memory_event(db, "t1", "HIT", hit=1)
        _insert_memory_event(db, "t1", "HIT", hit=1)
        # hits=2, total=4, rate=50%
        assert repo.get_memory_hit_rate() == 50.0

    def test_net_memory_growth_from_analytics(self, db, repo):
        _insert_memory_event(db, "t1", "INSERT")
        _insert_memory_event(db, "t1", "INSERT")
        _insert_memory_event(db, "t1", "INSERT")
        _insert_memory_event(db, "t1", "DELETE")
        # 3 inserts - 1 delete = 2
        assert repo.get_net_memory_growth() == 2

    def test_token_cost_from_analytics(self, db, repo):
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        # 使用 UPSERT 语义（同一天多次写入累加）
        _insert_token_usage(db, "t1", today, cost_usd=1.0)
        # 第二次插入用不同 tenant 避免触发 UPSERT 冲突
        _insert_token_usage(db, "t2", today, cost_usd=0.5)
        # 1.5 USD * 720 = 1080 cents
        assert repo.get_token_cost_cents() == 1080


# ═══════════════════════════════════════════════════════
# Retention 计算测试
# ═══════════════════════════════════════════════════════


class TestRetentionCalculation:
    def test_d1_retention_from_analytics(self, db, repo):
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
        # u1 昨日和今日都活跃
        _insert_activity(db, "t1", "u1", yesterday)
        _insert_activity(db, "t1", "u1", today)
        # u2 昨日活跃，今日不活跃
        _insert_activity(db, "t1", "u2", yesterday)
        # D1 = 1/2 * 100 = 50%
        assert repo.get_retention_d1() == 50.0

    def test_d7_retention_from_analytics(self, db, repo):
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        d7 = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
        _insert_activity(db, "t1", "u1", d7)
        _insert_activity(db, "t1", "u1", today)
        _insert_activity(db, "t1", "u2", d7)
        # D7 = 1/2 * 100 = 50%
        assert repo.get_retention_d7() == 50.0

    def test_d30_retention_from_analytics(self, db, repo):
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        d30 = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")
        _insert_activity(db, "t1", "u1", d30)
        _insert_activity(db, "t1", "u1", today)
        _insert_activity(db, "t1", "u2", d30)
        # D30 = 1/2 * 100 = 50%
        assert repo.get_retention_d30() == 50.0

    def test_d1_retention_zero_base(self, db, repo):
        """无昨日活跃用户时返回 0。"""
        assert repo.get_retention_d1() == 0.0

    def test_retention_cohort_from_analytics(self, db, repo):
        today = datetime.now(timezone.utc)
        d0 = today.strftime("%Y-%m-%d")
        d1 = (today - timedelta(days=1)).strftime("%Y-%m-%d")
        _insert_activity(db, "t1", "u1", d1)
        _insert_activity(db, "t1", "u2", d1)
        _insert_activity(db, "t1", "u1", d0)
        cohort = repo.get_retention_cohort(weeks=8)
        assert len(cohort) >= 1


# ═══════════════════════════════════════════════════════
# 真实 Percentile 计算测试
# ═══════════════════════════════════════════════════════


class TestPercentileCalculation:
    def test_real_p50_p95_p99(self, db, repo):
        """插入 10 个 duration，验证真实分位数（线性插值法，与 numpy 一致）。"""
        durations = [100, 200, 300, 400, 500, 600, 700, 800, 900, 1000]
        for d in durations:
            _insert_agent_run(db, "t1", "success", d)
        percentiles = repo.get_latency_percentiles()
        # 线性插值法: rank = p/100 * (n-1), n=10
        # P50: rank=4.5 → 500*0.5 + 600*0.5 = 550
        assert percentiles["p50_ms"] == 550.0
        # P95: rank=8.55 → 900*0.45 + 1000*0.55 = 955
        assert percentiles["p95_ms"] == 955.0
        # P99: rank=8.91 → 900*0.09 + 1000*0.91 = 991
        assert percentiles["p99_ms"] == 991.0

    def test_percentile_single_value(self, db, repo):
        """单个数据点时 P50=P95=P99。"""
        _insert_agent_run(db, "t1", "success", 500.0)
        percentiles = repo.get_latency_percentiles()
        assert percentiles["p50_ms"] == 500.0
        assert percentiles["p95_ms"] == 500.0
        assert percentiles["p99_ms"] == 500.0

    def test_percentile_empty(self, db, repo):
        """无数据时返回 0。"""
        percentiles = repo.get_latency_percentiles()
        assert percentiles["p50_ms"] == 0.0
        assert percentiles["p95_ms"] == 0.0
        assert percentiles["p99_ms"] == 0.0

    def test_p95_backward_compatible(self, db, repo):
        _insert_agent_run(db, "t1", "success", 100)
        _insert_agent_run(db, "t1", "success", 200)
        _insert_agent_run(db, "t1", "success", 300)
        # P95 of [100,200,300]: rank=0.95*2=1.9, 介于 200 和 300 = 290
        assert repo.get_p95_latency_ms() == 290.0


# ═══════════════════════════════════════════════════════
# Fallback Logic 测试（analytics 表为空时降级 usage_events）
# ═══════════════════════════════════════════════════════


class TestFallbackLogic:
    def test_dau_fallback_to_usage_events(self, db, repo):
        """analytics 表为空时，DAU 从 usage_events 查询。"""
        now = datetime.now(timezone.utc).isoformat()
        db.execute(
            """INSERT INTO usage_events (id, tenant_id, user_id, resource, quantity, timestamp)
               VALUES ('e1', 't1', 'u1', 'llm_call', 1, ?)""",
            [now],
        )
        db.execute(
            """INSERT INTO usage_events (id, tenant_id, user_id, resource, quantity, timestamp)
               VALUES ('e2', 't1', 'u2', 'search', 1, ?)""",
            [now],
        )
        assert repo.get_dau() == 2

    def test_agent_success_rate_fallback(self, db, repo):
        """analytics 表为空时，从 usage_events + metadata_json 查询。"""
        import json
        now = datetime.now(timezone.utc).isoformat()
        db.execute(
            """INSERT INTO usage_events (id, tenant_id, user_id, resource, quantity, metadata_json, timestamp)
               VALUES ('a1', 't1', 'u1', 'agent_run', 1, ?, ?)""",
            [json.dumps({"status": "success", "duration_ms": 100}), now],
        )
        db.execute(
            """INSERT INTO usage_events (id, tenant_id, user_id, resource, quantity, metadata_json, timestamp)
               VALUES ('a2', 't1', 'u1', 'agent_run', 1, ?, ?)""",
            [json.dumps({"status": "failed", "duration_ms": 50}), now],
        )
        assert repo.get_agent_success_rate() == 50.0

    def test_memory_hit_rate_fallback_to_notes(self, db, repo):
        """analytics 表为空时，从 notes 表 access_count 查询。"""
        now = datetime.now(timezone.utc).isoformat()
        db.execute(
            "INSERT INTO notes (id, content, timestamp, access_count, status) VALUES ('m1', 'c', ?, 5, 'active')",
            [now],
        )
        db.execute(
            "INSERT INTO notes (id, content, timestamp, access_count, status) VALUES ('m2', 'c', ?, 0, 'active')",
            [now],
        )
        assert repo.get_memory_hit_rate() == 50.0

    def test_d30_retention_no_fallback(self, db, repo):
        """analytics 表为空时，D30 不支持 fallback，返回 0。"""
        assert repo.get_retention_d30() == 0.0


# ═══════════════════════════════════════════════════════
# Alert Trigger 测试
# ═══════════════════════════════════════════════════════


class TestAlertTrigger:
    @pytest.fixture
    def mock_alert_store(self):
        store = MagicMock()
        store.record_event.return_value = "ale_test"
        store.create_rule.return_value = "alr_test"
        return store

    @pytest.fixture
    def evaluator(self, repo, mock_alert_store):
        return DashboardAlertEvaluator(repo, mock_alert_store, token_cost_threshold_cents=1000)

    def test_agent_success_rate_alert_triggered(self, db, repo, evaluator, mock_alert_store):
        """成功率 < 95% 触发 HIGH 告警。"""
        _insert_agent_run(db, "t1", "success", 100)
        _insert_agent_run(db, "t1", "failed", 50)
        # 成功率 50% < 95%
        events = evaluator.evaluate_all()
        triggered_names = [e.rule_name for e in events]
        assert "agent_success_rate_low" in triggered_names
        mock_alert_store.record_event.assert_called()

    def test_agent_latency_alert_triggered(self, db, repo, evaluator):
        """P95 > 2000ms 触发 MEDIUM 告警。"""
        _insert_agent_run(db, "t1", "success", 3000)
        _insert_agent_run(db, "t1", "success", 2500)
        events = evaluator.evaluate_all()
        triggered_names = [e.rule_name for e in events]
        assert "agent_p95_latency_high" in triggered_names

    def test_token_cost_alert_triggered(self, db, repo, evaluator):
        """日成本 > 阈值触发 HIGH 告警。"""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        _insert_token_usage(db, "t1", today, cost_usd=10.0)  # 10 USD = 7200 cents > 1000
        events = evaluator.evaluate_all()
        triggered_names = [e.rule_name for e in events]
        assert "token_daily_cost_high" in triggered_names

    def test_no_alert_when_healthy(self, db, repo, evaluator):
        """指标健康时不触发告警。"""
        _insert_agent_run(db, "t1", "success", 100)
        _insert_agent_run(db, "t1", "success", 200)
        events = evaluator.evaluate_all()
        assert len(events) == 0

    def test_seed_dashboard_rules(self, repo, mock_alert_store):
        evaluator = DashboardAlertEvaluator(repo, mock_alert_store)
        rule_ids = evaluator.seed_dashboard_rules("t1")
        assert len(rule_ids) == 3
        assert mock_alert_store.create_rule.call_count == 3


# ═══════════════════════════════════════════════════════
# Empty DB 测试
# ═══════════════════════════════════════════════════════


class TestEmptyDB:
    def test_dau_zero(self, repo):
        assert repo.get_dau() == 0

    def test_agent_success_rate_zero(self, repo):
        assert repo.get_agent_success_rate() == 0.0

    def test_percentiles_zero(self, repo):
        p = repo.get_latency_percentiles()
        assert p["p50_ms"] == 0.0
        assert p["p95_ms"] == 0.0
        assert p["p99_ms"] == 0.0

    def test_memory_hit_rate_zero(self, repo):
        assert repo.get_memory_hit_rate() == 0.0

    def test_retention_zero(self, repo):
        assert repo.get_retention_d1() == 0.0
        assert repo.get_retention_d7() == 0.0
        assert repo.get_retention_d30() == 0.0


# ═══════════════════════════════════════════════════════
# AnalyticsPipeline 集成层测试
# ═══════════════════════════════════════════════════════


class TestAnalyticsPipeline:
    @pytest.fixture
    def settings(self, tmp_path):
        return Settings(
            deepseek_api_key="test", environment="test",
            sqlite_db_path=str(tmp_path / "pipeline.db"),
        )

    @pytest.fixture
    def pipeline(self, settings):
        store = AnalyticsStore(settings)
        yield AnalyticsPipeline(store)
        store.close()

    def test_record_agent_run_from_result(self, pipeline, settings):
        """从 AgentResult 记录到 analytics 表。"""
        result = MagicMock()
        result.success = True
        result.duration_ms = 150.0
        result.tokens_used = 500
        result.agent_name = "test_agent"
        asyncio.run(pipeline.record_agent_run_from_result(result, "t1", "w1"))

        store = AnalyticsStore(settings)
        rows = store.conn.execute("SELECT * FROM analytics_agent_runs").fetchall()
        assert len(rows) == 1
        assert rows[0]["status"] == "success"
        assert rows[0]["duration_ms"] == 150.0
        store.close()

    def test_record_memory_insert(self, pipeline, settings):
        asyncio.run(pipeline.record_memory_insert("t1", "w1", "episodic"))
        store = AnalyticsStore(settings)
        rows = store.conn.execute("SELECT * FROM analytics_memory_events").fetchall()
        assert len(rows) == 1
        assert rows[0]["event_type"] == "INSERT"
        store.close()

    def test_record_chat_activity(self, pipeline, settings):
        asyncio.run(pipeline.record_chat_activity("t1", "w1", "u1", messages=5))
        store = AnalyticsStore(settings)
        rows = store.conn.execute("SELECT * FROM analytics_user_activity_daily").fetchall()
        assert len(rows) == 1
        assert rows[0]["messages"] == 5
        store.close()

    def test_record_chat_token_usage(self, pipeline, settings):
        asyncio.run(pipeline.record_chat_token_usage("t1", "w1", prompt_tokens=1000, cost_usd=0.05))
        store = AnalyticsStore(settings)
        rows = store.conn.execute("SELECT * FROM analytics_token_usage_daily").fetchall()
        assert len(rows) == 1
        assert rows[0]["prompt_tokens"] == 1000
        store.close()

    def test_failure_does_not_raise(self, pipeline):
        """AnalyticsStore 故障时不抛出。"""
        pipeline._store._conn.close()
        result = MagicMock()
        result.success = True
        result.duration_ms = 100
        result.tokens_used = 0
        result.agent_name = "a"
        asyncio.run(pipeline.record_agent_run_from_result(result, "t1", "w1"))


# ═══════════════════════════════════════════════════════
# Dashboard V2 API 端到端测试（从 analytics 表）
# ═══════════════════════════════════════════════════════


class TestDashboardV2EndToEndFromAnalytics:
    def test_overview_returns_analytics_data(self, client, db):
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        _insert_activity(db, "t1", "u1", today)
        _insert_activity(db, "t1", "u2", today)
        _insert_agent_run(db, "t1", "success", 100)
        _insert_agent_run(db, "t1", "failed", 50)
        _insert_memory_event(db, "t1", "INSERT")
        _insert_memory_event(db, "t1", "HIT", hit=1)
        _insert_token_usage(db, "t1", today, cost_usd=1.0)

        res = client.get("/dashboard/v2/overview")
        assert res.status_code == 200
        data = res.json()
        assert data["dau"] == 2
        assert data["agent_success_rate"] == 50.0
        assert data["memory_hit_rate"] == 50.0
        assert data["token_cost_today_cents"] == 720

    def test_agent_performance_returns_real_percentiles(self, client, db):
        for d in [100, 200, 300, 400, 500, 600, 700, 800, 900, 1000]:
            _insert_agent_run(db, "t1", "success", d)
        res = client.get("/dashboard/v2/agent-performance")
        assert res.status_code == 200
        data = res.json()
        # 线性插值法（与 numpy.percentile 一致）
        assert data["latency"]["p50_ms"] == 550.0
        assert data["latency"]["p95_ms"] == 955.0
        assert data["success_rate"] == 100.0

    def test_memory_health_from_analytics(self, client, db):
        _insert_memory_event(db, "t1", "INSERT", "episodic")
        _insert_memory_event(db, "t1", "INSERT", "semantic")
        _insert_memory_event(db, "t1", "INSERT", "episodic")
        _insert_memory_event(db, "t1", "DELETE")
        res = client.get("/dashboard/v2/memory-health")
        assert res.status_code == 200
        data = res.json()
        assert data["net_growth"] == 2  # 3 inserts - 1 delete
        types = {t["memory_type"]: t["count"] for t in data["type_distribution"]}
        assert types["episodic"] == 2
        assert types["semantic"] == 1
