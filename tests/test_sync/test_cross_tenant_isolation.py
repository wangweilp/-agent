"""跨租户攻击测试 — 验证 Sync + Memory 数据访问层的 workspace 隔离。

组织方式（对应阶段5的“跨租户攻击测试”目标）：
    Workspace A: Connector A / Rule A / Job A / Execution A / Memory A
    Workspace B: Connector B / Rule B / Job B / Execution B / Memory B

攻击场景（A Token 尝试访问 B 的资源）：
    A → GET B Connector      → None / 404
    A → DELETE B Connector   → False / 404
    A → GET B Job            → None / 404
    A → DELETE B Job         → False / 404
    A → RUN B Job            → 404
    A → GET B Result         → None / 404
    A → 查询 B Memory        → 0 results
    A → Search B Entity      → 0 results
    A → 修改 B Rule          → False / 404

隔离在数据访问层（store）实现，而非仅 Router 层 — 因此测试直接打 store，
再补一层 API 攻击验证（A Token 打 B 资源 → 404）。
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import MagicMock

from src.adapters.auth_store import SQLiteAuthStore, WorkspaceAwareStore, WorkspaceContext
from src.adapters.sqlite_store import SQLiteStoreAdapter
from src.api.middleware import JWTTokenService, init_auth
from src.api.sync_router import create_sync_router
from src.core.auth import User, WorkspaceRole
from src.sync.models import (
    ChangeRecord,
    SyncConnectorConfig,
    SyncExecution,
    SyncJob,
    SyncRule,
)
from src.sync.sync_worker import SyncWorker
from src.sync.scheduler import SyncScheduler
from src.sync.sync_pipeline import SyncPipeline


WS_A = "ws-a"
WS_B = "ws-b"


@pytest.fixture(autouse=True)
def _reset_workspace_context():
    """每个用例后清空 WorkspaceContext（thread-local），避免污染后续测试。"""
    yield
    WorkspaceContext.set(None)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ═══════════════════════════════════════════
# Sync 层 — 数据访问层隔离
# ═══════════════════════════════════════════


class TestSyncStoreIsolation:
    """SyncStore 直接打点 — 隔离必须发生在数据访问层。"""

    def test_connector_created_in_own_workspace(
        self, sync_store, settings, tmp_path
    ):
        """A 的 connector 只能按 ws-a 取到，A 取 B 的 connector 为 None。"""
        conn_a = SyncConnectorConfig(name="Conn A", connector_type="feishu", credentials={})
        sync_store.save_connector(conn_a, workspace_id=WS_A)

        # 同 workspace 可见
        assert sync_store.get_connector(conn_a.id, workspace_id=WS_A) is not None
        # 跨 workspace 不可见（B Token 取 A 的 connector → None → API 层 404）
        assert sync_store.get_connector(conn_a.id, workspace_id=WS_B) is None

    def test_connector_list_scoped(self, sync_store):
        """list_connectors 只返回本 workspace 的 connector。"""
        for ws in (WS_A, WS_B):
            sync_store.save_connector(
                SyncConnectorConfig(name=f"Conn {ws}", connector_type="feishu", credentials={}),
                workspace_id=ws,
            )

        assert {c.name for c in sync_store.list_connectors(workspace_id=WS_A)} == {"Conn ws-a"}
        assert {c.name for c in sync_store.list_connectors(workspace_id=WS_B)} == {"Conn ws-b"}

    def test_delete_connector_cross_workspace_denied(self, sync_store):
        """A Token 删除 B 的 connector → False，且 B 的 connector 仍在。"""
        conn_b = SyncConnectorConfig(name="Conn B", connector_type="feishu", credentials={})
        sync_store.save_connector(conn_b, workspace_id=WS_B)

        deleted = sync_store.delete_connector(conn_b.id, workspace_id=WS_A)
        assert deleted is False
        # B 的 connector 仍然存在
        assert sync_store.get_connector(conn_b.id, workspace_id=WS_B) is not None

    def _seed_job_pair(self, sync_store) -> tuple[SyncJob, SyncJob]:
        """创建 A 与 B 各一对 connector+rule+job。"""
        conn_a = SyncConnectorConfig(name="Conn A", connector_type="feishu", credentials={})
        conn_b = SyncConnectorConfig(name="Conn B", connector_type="feishu", credentials={})
        sync_store.save_connector(conn_a, workspace_id=WS_A)
        sync_store.save_connector(conn_b, workspace_id=WS_B)

        rule_a = SyncRule(rule_type="manual")
        rule_b = SyncRule(rule_type="manual")
        sync_store.save_rule(rule_a, workspace_id=WS_A)
        sync_store.save_rule(rule_b, workspace_id=WS_B)

        job_a = SyncJob(connector_config_id=conn_a.id, rule_id=rule_a.id, name="Job A")
        job_b = SyncJob(connector_config_id=conn_b.id, rule_id=rule_b.id, name="Job B")
        sync_store.save_job(job_a, workspace_id=WS_A)
        sync_store.save_job(job_b, workspace_id=WS_B)
        return job_a, job_b

    def test_get_job_cross_workspace_denied(self, sync_store):
        """A Token 取 B 的 job → None（API 层 404）。"""
        job_a, job_b = self._seed_job_pair(sync_store)
        assert sync_store.get_job(job_a.id, workspace_id=WS_A) is not None
        assert sync_store.get_job(job_b.id, workspace_id=WS_A) is None
        assert sync_store.get_job(job_a.id, workspace_id=WS_B) is None

    def test_list_jobs_scoped(self, sync_store):
        """list_jobs 只返回本 workspace 的 job。"""
        self._seed_job_pair(sync_store)
        assert {j.name for j in sync_store.list_jobs(workspace_id=WS_A)} == {"Job A"}
        assert {j.name for j in sync_store.list_jobs(workspace_id=WS_B)} == {"Job B"}

    def test_delete_job_cross_workspace_denied(self, sync_store):
        """A Token 删除 B 的 job → False，且 B 的 job 仍在。"""
        job_a, job_b = self._seed_job_pair(sync_store)
        deleted = sync_store.delete_job(job_b.id, workspace_id=WS_A)
        assert deleted is False
        assert sync_store.get_job(job_b.id, workspace_id=WS_B) is not None
        # B 的 rule 也不受影响
        assert sync_store.get_rule(job_b.rule_id, workspace_id=WS_B) is not None

    def test_rule_cross_workspace_denied(self, sync_store):
        """A Token 改/取 B 的 rule → 取不到 / 删不掉。"""
        job_a, job_b = self._seed_job_pair(sync_store)
        assert sync_store.get_rule(job_b.rule_id, workspace_id=WS_A) is None
        assert sync_store.delete_rule(job_b.rule_id, workspace_id=WS_A) is False
        assert sync_store.get_rule(job_b.rule_id, workspace_id=WS_B) is not None

    def test_execution_cross_workspace_denied(self, sync_store):
        """A Token 取 B 的 execution → None。"""
        job_a, job_b = self._seed_job_pair(sync_store)
        exec_b = SyncExecution(job_id=job_b.id, status="completed", workspace_id=WS_B)
        sync_store.save_execution(exec_b, workspace_id=WS_B)

        assert sync_store.get_execution(exec_b.id, workspace_id=WS_B) is not None
        assert sync_store.get_execution(exec_b.id, workspace_id=WS_A) is None
        # 按 job 过滤的 history 也不跨租户
        assert sync_store.list_executions(job_id=job_b.id, workspace_id=WS_A) == []

    def test_changes_cross_workspace_denied(self, sync_store):
        """A Token 取 B 的 change 记录 → 空。"""
        job_a, job_b = self._seed_job_pair(sync_store)
        exec_b = SyncExecution(job_id=job_b.id, status="completed", workspace_id=WS_B)
        sync_store.save_execution(exec_b, workspace_id=WS_B)
        change = ChangeRecord(
            execution_id=exec_b.id,
            connector_type="feishu",
            resource_id="res-1",
            change_type="created",
            detected_at=_utcnow(),
            workspace_id=WS_B,
        )
        sync_store.save_change(change, workspace_id=WS_B)

        assert sync_store.list_changes(exec_b.id, workspace_id=WS_B) != []
        assert sync_store.list_changes(exec_b.id, workspace_id=WS_A) == []


# ═══════════════════════════════════════════
# Sync 层 — API 攻击测试（A Token 打 B 资源 → 404）
# ═══════════════════════════════════════════


class TestSyncApiCrossTenantAttack:
    """A 的 token 尝试访问 B 的 connector/job → 404。"""

    @pytest.fixture
    def auth_store(self, settings):
        store = SQLiteAuthStore(settings, db_path=":memory:")
        yield store
        store.close()

    @pytest.fixture
    def token_service(self):
        return JWTTokenService()

    @pytest.fixture
    def client(self, sync_store, auth_store, token_service, tmp_path):
        init_auth(token_service, auth_store)

        pipeline = MagicMock(spec=SyncPipeline)
        worker = SyncWorker(sync_store, pipeline)
        scheduler = MagicMock(spec=SyncScheduler)

        router = create_sync_router(sync_store, worker, scheduler)
        app = FastAPI()
        app.include_router(router)
        return TestClient(app)

    def _headers(self, token_service, ws_id: str) -> dict:
        user = User(id=f"u-{ws_id}", email=f"{ws_id}@x.test", name=ws_id)
        tokens = token_service.create_tokens(user, ws_id, WorkspaceRole.ADMIN)
        return {"Authorization": f"Bearer {tokens.access_token}"}

    def test_a_cannot_get_b_connector(self, client, sync_store, token_service):
        """A Token GET B 的 connector → 404。"""
        conn_b = SyncConnectorConfig(name="Conn B", connector_type="feishu", credentials={})
        sync_store.save_connector(conn_b, workspace_id=WS_B)

        r = client.get(f"/sync/connectors", headers=self._headers(token_service, WS_A))
        assert r.status_code == 200
        assert r.json()["connectors"] == []
        # 无论如何不能通过任何路径拿到 B 的 connector 详情（无详情端点，用列表验证隔离）

    def test_a_cannot_delete_b_connector(self, client, sync_store, token_service):
        """A Token DELETE B 的 connector → 404，B 的 connector 保留。"""
        conn_b = SyncConnectorConfig(name="Conn B", connector_type="feishu", credentials={})
        sync_store.save_connector(conn_b, workspace_id=WS_B)

        r = client.delete(f"/sync/connectors/{conn_b.id}", headers=self._headers(token_service, WS_A))
        assert r.status_code == 404
        assert sync_store.get_connector(conn_b.id, workspace_id=WS_B) is not None

    def test_a_cannot_get_b_job(self, client, sync_store, token_service):
        """A Token GET B 的 job → 404。"""
        conn_b = SyncConnectorConfig(name="Conn B", connector_type="feishu", credentials={})
        sync_store.save_connector(conn_b, workspace_id=WS_B)
        rule_b = SyncRule(rule_type="manual")
        sync_store.save_rule(rule_b, workspace_id=WS_B)
        job_b = SyncJob(connector_config_id=conn_b.id, rule_id=rule_b.id, name="Job B")
        sync_store.save_job(job_b, workspace_id=WS_B)

        r = client.get(f"/sync/jobs/{job_b.id}", headers=self._headers(token_service, WS_A))
        assert r.status_code == 404

        # 列表也不泄露 B 的 job
        r2 = client.get("/sync/jobs", headers=self._headers(token_service, WS_A))
        assert r2.status_code == 200
        assert r2.json()["jobs"] == []

    def test_a_cannot_delete_b_job(self, client, sync_store, token_service):
        """A Token DELETE B 的 job → 404，B 的 job 保留。"""
        conn_b = SyncConnectorConfig(name="Conn B", connector_type="feishu", credentials={})
        sync_store.save_connector(conn_b, workspace_id=WS_B)
        rule_b = SyncRule(rule_type="manual")
        sync_store.save_rule(rule_b, workspace_id=WS_B)
        job_b = SyncJob(connector_config_id=conn_b.id, rule_id=rule_b.id, name="Job B")
        sync_store.save_job(job_b, workspace_id=WS_B)

        r = client.delete(f"/sync/jobs/{job_b.id}", headers=self._headers(token_service, WS_A))
        assert r.status_code == 404
        assert sync_store.get_job(job_b.id, workspace_id=WS_B) is not None

    def test_a_cannot_run_b_job(self, client, sync_store, token_service):
        """A Token RUN B 的 job → 404，不产生 execution。"""
        conn_b = SyncConnectorConfig(name="Conn B", connector_type="feishu", credentials={})
        sync_store.save_connector(conn_b, workspace_id=WS_B)
        rule_b = SyncRule(rule_type="manual")
        sync_store.save_rule(rule_b, workspace_id=WS_B)
        job_b = SyncJob(connector_config_id=conn_b.id, rule_id=rule_b.id, name="Job B")
        sync_store.save_job(job_b, workspace_id=WS_B)

        r = client.post(f"/sync/jobs/{job_b.id}/run", headers=self._headers(token_service, WS_A))
        assert r.status_code == 404
        # 不应产生任何 execution
        assert sync_store.list_executions(workspace_id=WS_B) == []

    def test_a_cannot_see_b_history(self, client, sync_store, token_service):
        """A Token 查 history 不包含 B 的 execution。"""
        conn_b = SyncConnectorConfig(name="Conn B", connector_type="feishu", credentials={})
        sync_store.save_connector(conn_b, workspace_id=WS_B)
        rule_b = SyncRule(rule_type="manual")
        sync_store.save_rule(rule_b, workspace_id=WS_B)
        job_b = SyncJob(connector_config_id=conn_b.id, rule_id=rule_b.id, name="Job B")
        sync_store.save_job(job_b, workspace_id=WS_B)
        exec_b = SyncExecution(job_id=job_b.id, status="completed", workspace_id=WS_B)
        sync_store.save_execution(exec_b, workspace_id=WS_B)

        r = client.get("/sync/history", headers=self._headers(token_service, WS_A))
        assert r.status_code == 200
        assert r.json()["executions"] == []


# ═══════════════════════════════════════════
# Memory 层 — WorkspaceAwareStore 隔离
# ═══════════════════════════════════════════


class TestMemoryTenantIsolation:
    """WorkspaceAwareStore：写入盖章 + 查询按 workspace 过滤。"""

    @pytest.fixture
    def settings(self):
        from src.adapters.config import Settings
        return Settings(deepseek_api_key="sk-test")

    @pytest.fixture
    def inner_store(self, settings):
        store = SQLiteStoreAdapter(settings, db_path=":memory:")
        yield store
        store.close()

    @pytest.fixture
    def store(self, inner_store):
        return WorkspaceAwareStore(inner_store)

    def _store_memory(self, store, ws_id: str, content: str, entity: str):
        from src.core.types import Memory
        # 在指定 workspace 上下文下写入
        payload = _make_payload(ws_id)
        WorkspaceContext.set(payload)
        m = Memory(
            content=content,
            summary=None,
            source="user",
            timestamp=_utcnow(),
            entities=[entity],
        )
        mid = store.store(m)
        # 校验盖章
        saved = store.get_by_id(mid)
        assert saved is not None and saved.workspace_id == ws_id
        return mid

    def test_memory_list_scoped(self, store):
        """A 读不到 B 的 memory。"""
        mem_a = self._store_memory(store, WS_A, "memory of A", "EntityA")
        mem_b = self._store_memory(store, WS_B, "memory of B", "EntityB")

        # A 上下文
        WorkspaceContext.set(_make_payload(WS_A))
        ids_a = {m.id for m in store.list_all()}
        assert mem_a in ids_a
        assert mem_b not in ids_a

        # B 上下文
        WorkspaceContext.set(_make_payload(WS_B))
        ids_b = {m.id for m in store.list_all()}
        assert mem_b in ids_b
        assert mem_a not in ids_b

    def test_get_by_id_cross_workspace_denied(self, store):
        """A 上下文 get B 的 memory → None。"""
        mem_a = self._store_memory(store, WS_A, "memory of A", "EntityA")
        mem_b = self._store_memory(store, WS_B, "memory of B", "EntityB")

        WorkspaceContext.set(_make_payload(WS_A))
        assert store.get_by_id(mem_a) is not None
        assert store.get_by_id(mem_b) is None

        WorkspaceContext.set(_make_payload(WS_B))
        assert store.get_by_id(mem_b) is not None
        assert store.get_by_id(mem_a) is None

    def test_search_by_entity_cross_workspace_denied(self, store):
        """A Search B 的 Entity → 0 results。"""
        self._store_memory(store, WS_A, "memory of A", "SharedEntity")
        self._store_memory(store, WS_B, "memory of B", "SharedEntity")

        WorkspaceContext.set(_make_payload(WS_A))
        a_results = store.search_by_entity("SharedEntity")
        assert len(a_results) == 1
        assert a_results[0].content == "memory of A"

        WorkspaceContext.set(_make_payload(WS_B))
        b_results = store.search_by_entity("SharedEntity")
        assert len(b_results) == 1
        assert b_results[0].content == "memory of B"

    def test_delete_cross_workspace_denied(self, store, inner_store):
        """A 上下文 delete B 的 memory → 不影响 B 数据。"""
        mem_b = self._store_memory(store, WS_B, "memory of B", "EntityB")

        WorkspaceContext.set(_make_payload(WS_A))
        store.delete(mem_b)
        # B 的数据仍在
        WorkspaceContext.set(_make_payload(WS_B))
        assert store.get_by_id(mem_b) is not None

        # A 上下文确实删不掉任何 B 记录
        WorkspaceContext.set(_make_payload(WS_A))
        raw = inner_store._db.execute(
            "SELECT 1 FROM notes WHERE id = ? AND workspace_id = ?", (mem_b, WS_B)
        ).fetchone()
        assert raw is not None

    def test_update_status_cross_workspace_denied(self, store):
        """A 上下文更新 B 的 memory 状态 → 不影响 B。"""
        mem_b = self._store_memory(store, WS_B, "memory of B", "EntityB")

        WorkspaceContext.set(_make_payload(WS_A))
        store.update_status(mem_b, "archived")

        WorkspaceContext.set(_make_payload(WS_B))
        b = store.get_by_id(mem_b)
        assert b is not None
        assert b.status == "active"


def _make_payload(ws_id: str):
    from src.core.auth import TokenPayload
    return TokenPayload(
        user_id=f"u-{ws_id}",
        workspace_id=ws_id,
        role=WorkspaceRole.ADMIN,
        email=f"{ws_id}@x.test",
    )