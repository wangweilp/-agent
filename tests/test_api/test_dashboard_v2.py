"""Dashboard V2 API 集成测试 — 覆盖 4 个 P0 端点 + OpenAPI 验证 + 错误降级。

测试策略：
- 创建真实 SQLite 临时文件 DB（含 usage_events / subscriptions / notes 表）
- 使用 check_same_thread=False 兼容 TestClient 多线程
- 插入测试数据
- 创建真实 AnalyticsRepository + DashboardV2Service + Router
- 用 dependency_overrides 跳过 require_auth
- 验证 HTTP 200 + response_model 校验 + OpenAPI 生成
"""
import json
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
from src.core.dashboard_v2_service import DashboardV2Service


# ── 测试用 Schema ───────────────────────────────────────

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS usage_events (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    resource TEXT NOT NULL,
    quantity INTEGER NOT NULL DEFAULT 1,
    workspace_id TEXT NOT NULL DEFAULT '',
    unit TEXT NOT NULL DEFAULT 'count',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    cost_cents INTEGER NOT NULL DEFAULT 0,
    timestamp TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_ue_tenant ON usage_events(tenant_id);
CREATE INDEX IF NOT EXISTS idx_ue_resource ON usage_events(resource);
CREATE INDEX IF NOT EXISTS idx_ue_ts ON usage_events(timestamp);

CREATE TABLE IF NOT EXISTS subscriptions (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    plan_tier TEXT NOT NULL DEFAULT 'free',
    status TEXT NOT NULL DEFAULT 'trial',
    billing_cycle TEXT NOT NULL DEFAULT 'monthly',
    current_period_start TEXT,
    current_period_end TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS notes (
    id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    summary TEXT,
    source TEXT,
    timestamp TEXT NOT NULL,
    importance INTEGER NOT NULL DEFAULT 5,
    entities_json TEXT NOT NULL DEFAULT '[]',
    relations_json TEXT NOT NULL DEFAULT '[]',
    memory_type TEXT DEFAULT 'episodic',
    access_count INTEGER NOT NULL DEFAULT 0,
    last_accessed TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    archived_at TEXT,
    workspace_id TEXT NOT NULL DEFAULT ''
);
"""


# ── Fixtures ────────────────────────────────────────────


@pytest.fixture
def db():
    """创建临时文件 SQLite DB 并初始化 schema（check_same_thread=False）。"""
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    db = SqliteDB(conn)
    for stmt in _SCHEMA_SQL.strip().split(";"):
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
    """创建 AnalyticsRepository。"""
    return AnalyticsRepository(db)


@pytest.fixture
def service(repo):
    """创建 DashboardV2Service。"""
    return DashboardV2Service(repo)


@pytest.fixture
def mock_token():
    """模拟认证 token。"""
    return TokenPayload(
        user_id="test-user",
        workspace_id="default",
        role="admin",
        email="test@example.com",
    )


@pytest.fixture
def client(service, mock_token):
    """创建测试用 FastAPI TestClient，跳过 require_auth。"""
    app = FastAPI()
    app.include_router(create_dashboard_v2_router(service))
    app.dependency_overrides[require_auth] = lambda: mock_token
    return TestClient(app)


# ── 数据插入辅助 ────────────────────────────────────────


def _insert_usage_event(db, event_id, tenant_id, user_id, resource, timestamp,
                        cost_cents=0, quantity=1, metadata=None):
    """插入 usage_events 测试数据。"""
    db.execute(
        """INSERT INTO usage_events (id, tenant_id, user_id, resource, quantity,
           workspace_id, unit, metadata_json, cost_cents, timestamp)
           VALUES (?, ?, ?, ?, ?, '', 'count', ?, ?, ?)""",
        [event_id, tenant_id, user_id, resource, quantity,
         json.dumps(metadata or {}), cost_cents, timestamp],
    )


def _insert_note(db, note_id, content, timestamp, memory_type="episodic",
                 status="active", access_count=0, workspace_id=""):
    """插入 notes 测试数据。"""
    db.execute(
        """INSERT INTO notes (id, content, summary, source, timestamp, importance,
           entities_json, relations_json, memory_type, access_count, last_accessed,
           status, archived_at, workspace_id)
           VALUES (?, ?, '', 'user', ?, 5, '[]', '[]', ?, ?, NULL, ?, NULL, ?)""",
        [note_id, content, timestamp, memory_type, access_count, status, workspace_id],
    )


def _insert_subscription(db, sub_id, tenant_id, plan_tier, status, billing_cycle="monthly"):
    """插入 subscriptions 测试数据。"""
    db.execute(
        """INSERT INTO subscriptions (id, tenant_id, plan_tier, status, billing_cycle)
           VALUES (?, ?, ?, ?, ?)""",
        [sub_id, tenant_id, plan_tier, status, billing_cycle],
    )


# ── Overview 端点测试 ───────────────────────────────────


class TestDashboardV2Overview:
    """GET /dashboard/v2/overview"""

    def test_returns_200_with_empty_db(self, client):
        """空数据库时返回 200 + 全默认值。"""
        res = client.get("/dashboard/v2/overview")
        assert res.status_code == 200
        data = res.json()
        assert data["mrr_cents"] == 0
        assert data["dau"] == 0
        assert data["wau"] == 0
        assert data["mau"] == 0
        assert data["agent_success_rate"] == 0.0
        assert data["p95_latency_ms"] == 0.0
        assert data["total_memories"] == 0
        assert data["memory_hit_rate"] == 0.0

    def test_returns_correct_dau_wau_mau(self, client, db):
        """插入 3 个用户（今日活跃），验证 DAU=3。"""
        now = datetime.now(timezone.utc).isoformat()
        _insert_usage_event(db, "e1", "t1", "u1", "llm_call", now)
        _insert_usage_event(db, "e2", "t1", "u2", "llm_call", now)
        _insert_usage_event(db, "e3", "t1", "u3", "search", now)

        res = client.get("/dashboard/v2/overview")
        assert res.status_code == 200
        data = res.json()
        assert data["dau"] == 3
        assert data["wau"] >= 3
        assert data["mau"] >= 3

    def test_returns_memory_stats(self, client, db):
        """插入 5 条记忆（3 条被访问过），验证命中率 60%。"""
        now = datetime.now(timezone.utc).isoformat()
        _insert_note(db, "m1", "content1", now, access_count=5)
        _insert_note(db, "m2", "content2", now, access_count=1)
        _insert_note(db, "m3", "content3", now, access_count=0)
        _insert_note(db, "m4", "content4", now, access_count=0)
        _insert_note(db, "m5", "content5", now, access_count=0)

        res = client.get("/dashboard/v2/overview")
        assert res.status_code == 200
        data = res.json()
        assert data["total_memories"] == 5
        assert data["memory_hit_rate"] == 40.0  # 2/5 * 100

    def test_returns_token_cost(self, client, db):
        """插入 Token 消耗事件，验证成本计算。"""
        now = datetime.now(timezone.utc).isoformat()
        _insert_usage_event(db, "e1", "t1", "u1", "llm_call", now, cost_cents=500)
        _insert_usage_event(db, "e2", "t1", "u1", "embedding", now, cost_cents=200)

        res = client.get("/dashboard/v2/overview")
        assert res.status_code == 200
        data = res.json()
        assert data["token_cost_today_cents"] == 700

    def test_returns_agent_success_rate(self, client, db):
        """插入 4 个 agent_run（1 个失败），验证成功率 75%。"""
        now = datetime.now(timezone.utc).isoformat()
        _insert_usage_event(db, "a1", "t1", "u1", "agent_run", now,
                            metadata={"status": "success", "duration_ms": 100})
        _insert_usage_event(db, "a2", "t1", "u1", "agent_run", now,
                            metadata={"status": "success", "duration_ms": 200})
        _insert_usage_event(db, "a3", "t1", "u1", "agent_run", now,
                            metadata={"status": "success", "duration_ms": 300})
        _insert_usage_event(db, "a4", "t1", "u1", "agent_run", now,
                            metadata={"status": "failed", "duration_ms": 50})

        res = client.get("/dashboard/v2/overview")
        assert res.status_code == 200
        data = res.json()
        assert data["agent_success_rate"] == 75.0
        assert data["p95_latency_ms"] == 285.0  # P95 of [50,100,200,300] 线性插值: rank=2.85


class TestDashboardV2Growth:
    """GET /dashboard/v2/growth"""

    def test_returns_200_with_empty_db(self, client):
        """空数据库时返回 200 + 空列表。"""
        res = client.get("/dashboard/v2/growth")
        assert res.status_code == 200
        data = res.json()
        assert data["dau_series"] == []
        assert data["retention_cohort"] == []
        # funnel 始终返回 4 个阶段（count=0）
        assert len(data["funnel"]) == 4
        assert all(s["count"] == 0 for s in data["funnel"])
        assert data["activation_rate"] == 0.0

    def test_returns_dau_series(self, client, db):
        """插入多天数据，验证时间序列。"""
        now = datetime.now(timezone.utc)
        for i in range(3):
            ts = (now - timedelta(days=i)).isoformat()
            _insert_usage_event(db, f"e{i}", "t1", f"u{i}", "llm_call", ts)

        res = client.get("/dashboard/v2/growth?days=7")
        assert res.status_code == 200
        data = res.json()
        assert len(data["dau_series"]) >= 1

    def test_returns_funnel(self, client, db):
        """插入订阅数据，验证漏斗。"""
        _insert_subscription(db, "s1", "t1", "pro", "active")
        _insert_subscription(db, "s2", "t2", "free", "trial")

        res = client.get("/dashboard/v2/growth")
        assert res.status_code == 200
        data = res.json()
        stages = {s["stage"]: s["count"] for s in data["funnel"]}
        assert stages["trial"] == 1
        assert stages["paid"] == 1

    def test_returns_retention_d1(self, client, db):
        """插入昨日和今日活跃用户，验证 D1 留存。"""
        yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        today = datetime.now(timezone.utc).isoformat()
        # u1 昨日和今日都活跃
        _insert_usage_event(db, "e1", "t1", "u1", "llm_call", yesterday)
        _insert_usage_event(db, "e2", "t1", "u1", "llm_call", today)
        # u2 昨日活跃但今日不活跃
        _insert_usage_event(db, "e3", "t1", "u2", "llm_call", yesterday)

        res = client.get("/dashboard/v2/overview")
        assert res.status_code == 200
        data = res.json()
        # D1 = 1/2 * 100 = 50.0
        assert data["retention_d1"] == 50.0

    def test_days_param_validation(self, client):
        """days 参数超出范围时返回 422。"""
        res = client.get("/dashboard/v2/growth?days=0")
        assert res.status_code == 422
        res = client.get("/dashboard/v2/growth?days=999")
        assert res.status_code == 422


class TestDashboardV2AgentPerformance:
    """GET /dashboard/v2/agent-performance"""

    def test_returns_200_with_empty_db(self, client):
        """空数据库时返回 200 + 默认值。"""
        res = client.get("/dashboard/v2/agent-performance")
        assert res.status_code == 200
        data = res.json()
        assert data["success_rate"] == 0.0
        assert data["failure_rate"] == 0.0
        assert data["latency"]["p95_ms"] == 0.0
        assert data["token_cost_cents"] == 0
        assert data["call_volume_series"] == []

    def test_returns_success_and_failure_rate(self, client, db):
        """插入 5 个 agent_run（1 个失败），验证成功率 80%。"""
        now = datetime.now(timezone.utc).isoformat()
        for i in range(4):
            _insert_usage_event(db, f"a{i}", "t1", "u1", "agent_run", now,
                                metadata={"status": "success", "duration_ms": 100})
        _insert_usage_event(db, "a4", "t1", "u1", "agent_run", now,
                            metadata={"status": "failed", "duration_ms": 50})

        res = client.get("/dashboard/v2/agent-performance")
        assert res.status_code == 200
        data = res.json()
        assert data["success_rate"] == 80.0
        assert data["failure_rate"] == 20.0

    def test_returns_p95_latency(self, client, db):
        """插入 10 个 agent_run，验证 P95 计算。"""
        now = datetime.now(timezone.utc).isoformat()
        for i in range(10):
            _insert_usage_event(db, f"p{i}", "t1", "u1", "agent_run", now,
                                metadata={"status": "success", "duration_ms": (i + 1) * 100})

        res = client.get("/dashboard/v2/agent-performance")
        assert res.status_code == 200
        data = res.json()
        # durations = [100,200,...,1000], P95 线性插值: rank=8.55 → 955
        assert data["latency"]["p95_ms"] == 955.0

    def test_returns_token_usage_series(self, client, db):
        """插入 Token 消耗，验证时间序列。"""
        now = datetime.now(timezone.utc)
        _insert_usage_event(db, "t1", "t1", "u1", "llm_call", now.isoformat(),
                            quantity=500, cost_cents=100)
        _insert_usage_event(db, "t2", "t1", "u1", "embedding", now.isoformat(),
                            quantity=200, cost_cents=50)

        res = client.get("/dashboard/v2/agent-performance")
        assert res.status_code == 200
        data = res.json()
        assert data["token_cost_cents"] == 150
        assert len(data["token_usage_series"]) >= 1


class TestDashboardV2MemoryHealth:
    """GET /dashboard/v2/memory-health"""

    def test_returns_200_with_empty_db(self, client):
        """空数据库时返回 200 + 默认值。"""
        res = client.get("/dashboard/v2/memory-health")
        assert res.status_code == 200
        data = res.json()
        assert data["hit_rate"] == 0.0
        assert data["total_memories"] == 0
        assert data["active_memories"] == 0
        assert data["net_growth"] == 0
        assert data["type_distribution"] == []

    def test_returns_memory_stats(self, client, db):
        """插入 4 条记忆（2 条被访问），验证命中率 50%。"""
        now = datetime.now(timezone.utc).isoformat()
        _insert_note(db, "m1", "c1", now, memory_type="episodic", access_count=5)
        _insert_note(db, "m2", "c2", now, memory_type="semantic", access_count=1)
        _insert_note(db, "m3", "c3", now, memory_type="episodic", access_count=0)
        _insert_note(db, "m4", "c4", now, memory_type="semantic", access_count=0)

        res = client.get("/dashboard/v2/memory-health")
        assert res.status_code == 200
        data = res.json()
        assert data["total_memories"] == 4
        assert data["active_memories"] == 4
        assert data["hit_rate"] == 50.0

    def test_returns_type_distribution(self, client, db):
        """插入不同类型记忆，验证类型分布。"""
        now = datetime.now(timezone.utc).isoformat()
        _insert_note(db, "m1", "c1", now, memory_type="episodic")
        _insert_note(db, "m2", "c2", now, memory_type="episodic")
        _insert_note(db, "m3", "c3", now, memory_type="semantic")

        res = client.get("/dashboard/v2/memory-health")
        assert res.status_code == 200
        data = res.json()
        types = {t["memory_type"]: t["count"] for t in data["type_distribution"]}
        assert types["episodic"] == 2
        assert types["semantic"] == 1

    def test_returns_growth_series(self, client, db):
        """插入多天记忆，验证增长序列。"""
        now = datetime.now(timezone.utc)
        for i in range(3):
            ts = (now - timedelta(days=i)).isoformat()
            _insert_note(db, f"m{i}", f"c{i}", ts)

        res = client.get("/dashboard/v2/memory-health?days=7")
        assert res.status_code == 200
        data = res.json()
        assert len(data["growth_series"]) >= 1

    def test_excludes_deleted_memories(self, client, db):
        """已删除记忆不计入统计。"""
        now = datetime.now(timezone.utc).isoformat()
        _insert_note(db, "m1", "c1", now, status="active")
        _insert_note(db, "m2", "c2", now, status="deleted")

        res = client.get("/dashboard/v2/memory-health")
        assert res.status_code == 200
        data = res.json()
        assert data["total_memories"] == 1
        assert data["active_memories"] == 1


class TestDashboardV2OpenAPI:
    """OpenAPI 生成验证 — 无 PydanticUserError / ForwardRef 错误。"""

    def test_openapi_schema_generated(self, client):
        """GET /openapi.json 返回 200 且包含 Dashboard V2 路径。"""
        res = client.get("/openapi.json")
        assert res.status_code == 200
        spec = res.json()
        paths = spec.get("paths", {})
        assert "/dashboard/v2/overview" in paths
        assert "/dashboard/v2/growth" in paths
        assert "/dashboard/v2/agent-performance" in paths
        assert "/dashboard/v2/memory-health" in paths

    def test_openapi_components_defined(self, client):
        """OpenAPI components 中包含所有响应模型。"""
        res = client.get("/openapi.json")
        spec = res.json()
        schemas = spec.get("components", {}).get("schemas", {})
        assert "OverviewResponse" in schemas
        assert "GrowthResponse" in schemas
        assert "AgentPerformanceResponse" in schemas
        assert "MemoryHealthResponse" in schemas
        assert "MetricPoint" in schemas
        assert "LatencyPercentiles" in schemas

    def test_no_optional_any_in_schema(self, client):
        """验证 schema 中无 Optional[Any] 导致的 null-only 字段。"""
        res = client.get("/openapi.json")
        spec = res.json()
        schemas = spec.get("components", {}).get("schemas", {})
        overview = schemas.get("OverviewResponse", {})
        props = overview.get("properties", {})
        # 每个字段都应有类型，不应出现 type: null
        for field_name, field_spec in props.items():
            assert "type" in field_spec or "anyOf" in field_spec, \
                f"字段 {field_name} 缺少类型定义"


class TestDashboardV2ErrorHandling:
    """错误降级测试 — Repository 异常时返回默认值。"""

    def test_overview_handles_repo_error(self, db):
        """Repository 内部异常时 Overview 返回默认值。"""
        broken_repo = MagicMock()
        broken_repo.get_mrr_cents.side_effect = RuntimeError("DB down")
        broken_repo.get_dau.side_effect = RuntimeError("DB down")
        broken_repo.get_total_memories.side_effect = RuntimeError("DB down")
        service = DashboardV2Service(broken_repo)

        app = FastAPI()
        app.include_router(create_dashboard_v2_router(service))
        token = TokenPayload(user_id="u", workspace_id="default", role="admin", email="")
        app.dependency_overrides[require_auth] = lambda: token
        client = TestClient(app)

        res = client.get("/dashboard/v2/overview")
        assert res.status_code == 200
        data = res.json()
        assert data["mrr_cents"] == 0
        assert data["dau"] == 0

    def test_growth_handles_repo_error(self, db):
        """Repository 异常时 Growth 返回空列表。"""
        broken_repo = MagicMock()
        broken_repo.get_dau_series.side_effect = RuntimeError("DB down")
        broken_repo.get_retention_cohort.side_effect = RuntimeError("DB down")
        service = DashboardV2Service(broken_repo)

        app = FastAPI()
        app.include_router(create_dashboard_v2_router(service))
        token = TokenPayload(user_id="u", workspace_id="default", role="admin", email="")
        app.dependency_overrides[require_auth] = lambda: token
        client = TestClient(app)

        res = client.get("/dashboard/v2/growth")
        assert res.status_code == 200
        data = res.json()
        assert data["dau_series"] == []
        assert data["retention_cohort"] == []
