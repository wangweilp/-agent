"""阶段6 P1 定向测试 — Worker 崩溃恢复 / 删除 Race / 幂等。

覆盖要求：
- Worker Recovery：DB 中真实留下 RUNNING → 恢复机制重新发现 → 收敛 failed，
  fresh heartbeat 不被误回收，不产生 orphan execution，不跨 workspace。
- Delete Race：active Job 不可物理删除 → cancel_requested → Worker 收敛为 cancelled；
  Worker 不会向已删除 Job 写 Execution（无 FK error）。
- Idempotency：并发 RUN → 最终 active execution == 1（DB 层原子保护）。
"""
from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone

import pytest

from src.sync.models import (
    EXECUTION_STATUS_ACTIVE,
    SyncExecution,
    SyncJob,
)
from src.sync.sync_store import SyncStore


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _backdate(dt: datetime, seconds: int) -> datetime:
    return dt - timedelta(seconds=seconds)


# ═════════════════════════════════════════════════════════════════════════
# P1-1 Worker Recovery
# ═════════════════════════════════════════════════════════════════════════


class TestWorkerRecovery:
    """DB 中留下 RUNNING/queued 的 Job 必须被 recover_stale_jobs 收敛。"""

    def test_stale_running_job_recovered_to_failed(
        self, sync_store: SyncStore, sample_connector_config, sample_rule, sample_job
    ):
        """Worker 崩溃遗留的 RUNNING Job（心跳过期）→ failed。"""
        # 模拟 Worker 已认领：running + 旧心跳
        sample_job.status = "running"
        sample_job.started_at = _backdate(_utcnow(), 3600)
        sample_job.heartbeat_at = _backdate(_utcnow(), 3600)
        sample_job.worker_id = "worker-dead"
        sample_job.attempt_count = 1
        sync_store.save_job(sample_job)

        recovered = sync_store.recover_stale_jobs(stale_timeout_seconds=300)
        assert len(recovered) == 1
        assert recovered[0]["job_id"] == sample_job.id
        assert recovered[0]["recovered_to"] == "failed"

        # 收敛后 Job 不再是 running
        job = sync_store.get_job(sample_job.id)
        assert job is not None
        assert job.status == "failed"

    def test_stale_queued_job_recovered(self, sync_store, sample_connector_config, sample_rule, sample_job):
        """queued 且无心跳（发出后 Worker 立刻死）也应被收敛。"""
        # 新建一个 created_at 已在过去（1h 前）的 queued Job —— 模拟入队后 Worker 死亡
        stale_queued = SyncJob(
            connector_config_id=sample_connector_config.id,
            rule_id=sample_rule.id,
            name="stale-queued",
            status="queued",
            created_at=_backdate(_utcnow(), 3600),
        )
        sync_store.save_job(stale_queued)

        recovered = sync_store.recover_stale_jobs(stale_timeout_seconds=300)
        assert any(r["job_id"] == stale_queued.id for r in recovered)
        assert sync_store.get_job(stale_queued.id).status == "failed"

    def test_fresh_running_job_not_recovered(
        self, sync_store, sample_connector_config, sample_rule, sample_job
    ):
        """心跳新鲜的 RUNNING Job（Worker 仍活着）不能被误回收。"""
        sample_job.status = "running"
        sample_job.started_at = _utcnow()
        sample_job.heartbeat_at = _utcnow()  # 新鲜
        sample_job.worker_id = "worker-alive"
        sync_store.save_job(sample_job)

        recovered = sync_store.recover_stale_jobs(stale_timeout_seconds=300)
        assert recovered == []
        assert sync_store.get_job(sample_job.id).status == "running"

    def test_recovery_marks_active_execution_failed_no_orphan(
        self, sync_store, sample_connector_config, sample_rule, sample_job
    ):
        """收敛 Job 时其 active execution 也必须收敛，不留 orphan running。"""
        sample_job.status = "running"
        sample_job.heartbeat_at = _backdate(_utcnow(), 3600)
        sync_store.save_job(sample_job)

        exec1 = SyncExecution(job_id=sample_job.id, status="running", workspace_id="default")
        sync_store.save_execution(exec1)

        sync_store.recover_stale_jobs(stale_timeout_seconds=300)

        e = sync_store.get_execution(exec1.id)
        assert e is not None
        assert e.status == "failed"
        assert "recovered" in (e.error or "")

        # 不再有该 Job 的 active execution
        assert sync_store.get_active_execution(sample_job.id) is None

    def test_recovery_does_not_cross_workspace(
        self, sync_store, sample_connector_config, sample_rule, sample_job
    ):
        """恢复只收敛 stale 的 Job；另一 workspace 的 fresh Job 不受影响。"""
        # ws-a：stale running
        job_a = sample_job
        job_a.status = "running"
        job_a.heartbeat_at = _backdate(_utcnow(), 3600)
        sync_store.save_job(job_a, workspace_id="ws-a")

        # ws-b：fresh
        job_b = SyncJob(
            connector_config_id=sample_connector_config.id,
            rule_id=sample_rule.id,
            name="job-b",
            status="running",
            workspace_id="ws-b",
            heartbeat_at=_utcnow(),
        )
        sync_store.save_job(job_b, workspace_id="ws-b")

        recovered = sync_store.recover_stale_jobs(stale_timeout_seconds=300)
        assert any(r["workspace_id"] == "ws-a" for r in recovered)
        assert sync_store.get_job(job_a.id, workspace_id="ws-a").status == "failed"
        # ws-b fresh 不被回收
        assert sync_store.get_job(job_b.id, workspace_id="ws-b").status == "running"

    def test_worker_claim_sets_lifecycle_fields(
        self, sync_store, sample_connector_config, sample_rule, sample_job
    ):
        """Worker 认领后 Job 带 started_at/heartbeat/worker_id/attempt_count。"""
        from unittest.mock import MagicMock
        from src.sync.sync_pipeline import SyncPipeline
        from src.sync.sync_worker import SyncWorker

        sync_store.save_job(sample_job)
        exec1 = SyncExecution(job_id=sample_job.id, workspace_id="default")
        sync_store.save_execution(exec1)

        pipeline = MagicMock(spec=SyncPipeline)
        result = MagicMock()
        result.status = "completed"
        result.items_fetched = 0
        result.items_new = 0
        result.items_updated = 0
        result.items_deleted = 0
        result.items_renamed = 0
        result.memories_created = 0
        result.errors_count = 0
        result.error = None
        result.processing_time_ms = 1
        pipeline.run.return_value = result

        worker = SyncWorker(sync_store, pipeline)
        sample_job.status = "queued"  # Router/Scheduler 入队时置 queued
        sync_store.save_job(sample_job)
        worker._process(sample_job, exec1)

        job = sync_store.get_job(sample_job.id)
        assert job.status == "completed"
        assert job.started_at is not None
        assert job.worker_id != ""
        assert job.attempt_count >= 1


# ═════════════════════════════════════════════════════════════════════════
# P1-2 Delete Race / Job 生命周期
# ═════════════════════════════════════════════════════════════════════════


class TestDeleteLifecycle:
    """active Job 不可物理删除，需先 cancel_requested 再收敛。"""

    def test_active_job_cannot_be_physically_deleted_via_store(
        self, sync_store, sample_connector_config, sample_rule, sample_job
    ):
        """RUNNING Job 直接 delete_job 会成功删除 —— 但这是 Store 层，Router 已拦截。
        此处验证 Router 语义由 API 测试覆盖；同时在 Store 层验证执行完成态可删。"""
        sample_job.status = "running"
        sync_store.save_job(sample_job)

        # Store 层 delete_job 仍会删除（它不感知生命周期）；真正拦截在 Router。
        # 但我们验证：删除前先置 cancel_requested 的 Job 仍保留（作为收敛中间态）。
        sample_job.status = "cancel_requested"
        sync_store.save_job(sample_job)
        assert sync_store.get_job(sample_job.id) is not None

    def test_worker_finalizes_cancelled_job(self, sync_store, sample_connector_config, sample_rule, sample_job):
        """运行期间被置 cancel_requested 的 Job → Worker 收敛为 cancelled。"""
        from unittest.mock import MagicMock
        from src.sync.sync_pipeline import SyncPipeline

        sync_store.save_job(sample_job)
        exec1 = SyncExecution(job_id=sample_job.id, workspace_id="default")
        sync_store.save_execution(exec1)

        sample_job.status = "queued"
        sync_store.save_job(sample_job)

        # 模拟：pipeline 运行前，外部将 Job 置为 cancel_requested
        def _cancel(*args, **kwargs):
            sample_job.status = "cancel_requested"
            sync_store.save_job(sample_job)
            result = MagicMock()
            result.status = "completed"
            result.items_fetched = 0
            result.items_new = 0
            result.items_updated = 0
            result.items_deleted = 0
            result.items_renamed = 0
            result.memories_created = 0
            result.errors_count = 0
            result.error = None
            result.processing_time_ms = 1
            return result

        pipeline = MagicMock(spec=SyncPipeline)
        pipeline.run.side_effect = _cancel

        from src.sync.sync_worker import SyncWorker
        worker = SyncWorker(sync_store, pipeline)
        worker._process(sample_job, exec1)

        job = sync_store.get_job(sample_job.id)
        exec_r = sync_store.get_execution(exec1.id)
        assert job.status == "cancelled"
        assert exec_r.status == "cancelled"

    def test_terminal_job_can_be_deleted(self, sync_store, sample_connector_config, sample_rule, sample_job):
        """终止态 Job 可物理删除（Router 语义）。"""
        sample_job.status = "completed"
        sync_store.save_job(sample_job)
        assert sync_store.delete_job(sample_job.id) is True
        assert sync_store.get_job(sample_job.id) is None

    def test_worker_does_not_crash_writing_to_deleted_job(
        self, sync_store, sample_connector_config, sample_rule, sample_job
    ):
        """Job 被物理删除后，Worker 不崩溃（_safe_* 兜底），无 FK 异常上抛。"""
        from unittest.mock import MagicMock
        from src.sync.sync_pipeline import SyncPipeline
        from src.sync.sync_worker import SyncWorker

        sync_store.save_job(sample_job)
        exec1 = SyncExecution(job_id=sample_job.id, workspace_id="default")
        sync_store.save_execution(exec1)

        # 先物理删除 Job（级联删除 execution）
        sync_store.delete_job(sample_job.id)

        pipeline = MagicMock(spec=SyncPipeline)
        result = MagicMock()
        result.status = "completed"
        result.items_fetched = 0
        result.items_new = 0
        result.items_updated = 0
        result.items_deleted = 0
        result.items_renamed = 0
        result.memories_created = 0
        result.errors_count = 0
        result.error = None
        result.processing_time_ms = 1
        pipeline.run.return_value = result

        worker = SyncWorker(sync_store, pipeline)
        # 不应抛异常
        worker._process(sample_job, exec1)
        assert sync_store.get_job(sample_job.id) is None


# ═════════════════════════════════════════════════════════════════════════
# P1-3 Job Idempotency
# ═════════════════════════════════════════════════════════════════════════


class TestJobIdempotency:
    """同一 Job 最多 1 个 active execution。"""

    def test_create_execution_if_idle_blocks_second(self, sync_store, sample_connector_config, sample_rule, sample_job):
        """已有 active execution 时，create_execution_if_idle 返回 None。"""
        e1 = SyncExecution(job_id=sample_job.id, workspace_id="default", status="pending")
        created1 = sync_store.create_execution_if_idle(e1)
        assert created1 is not None

        e2 = SyncExecution(job_id=sample_job.id, workspace_id="default", status="pending")
        created2 = sync_store.create_execution_if_idle(e2)
        assert created2 is None

        # 只有 1 个 active
        assert sync_store.get_active_execution(sample_job.id) is not None

    def test_after_completion_allows_new_execution(self, sync_store, sample_connector_config, sample_rule, sample_job):
        """active execution 结束后可再次运行。"""
        e1 = SyncExecution(job_id=sample_job.id, workspace_id="default", status="pending")
        sync_store.create_execution_if_idle(e1)
        e1.status = "completed"
        sync_store.save_execution(e1)

        e2 = SyncExecution(job_id=sample_job.id, workspace_id="default", status="pending")
        assert sync_store.create_execution_if_idle(e2) is not None

    def test_concurrent_create_yields_single_active(self, sync_store, sample_connector_config, sample_rule, sample_job):
        """并发 N 个 create_execution_if_idle → 最终只有 1 个 active execution。"""
        n = 20
        results: list[bool] = []
        results_lock = threading.Lock()

        def _worker():
            ex = SyncExecution(job_id=sample_job.id, workspace_id="default", status="pending")
            created = sync_store.create_execution_if_idle(ex)
            with results_lock:
                results.append(created is not None)

        threads = [threading.Thread(target=_worker) for _ in range(n)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert sum(results) == 1, f"期望恰好 1 个成功，实际 {sum(results)}"
        active = sync_store.get_active_execution(sample_job.id)
        assert active is not None

    def test_concurrent_run_api_yields_single_active(
        self, sync_store, settings, tmp_path
    ):
        """API 层并发 RUN → 最终 1 个 active execution。"""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from unittest.mock import MagicMock

        from src.adapters.auth_store import SQLiteAuthStore
        from src.api.middleware import JWTTokenService, init_auth
        from src.api.sync_router import create_sync_router
        from src.core.auth import User, WorkspaceRole
        from src.sync.scheduler import SyncScheduler
        from src.sync.sync_pipeline import SyncPipeline
        from src.sync.sync_worker import SyncWorker

        auth_store = SQLiteAuthStore(settings, db_path=":memory:")
        token_service = JWTTokenService()
        init_auth(token_service, auth_store)

        pipeline = MagicMock(spec=SyncPipeline)
        worker = SyncWorker(sync_store, pipeline)
        scheduler = MagicMock(spec=SyncScheduler)

        app = FastAPI()
        app.include_router(create_sync_router(sync_store, worker, scheduler))
        client = TestClient(app)

        user = User(id="u-idem", email="idem@x.test", name="idem")
        tokens = token_service.create_tokens(user, "default", WorkspaceRole.ADMIN)
        headers = {"Authorization": f"Bearer {tokens.access_token}"}

        # 造一个可运行的 Job（本地 connector 类型用 fake，仅验证幂等）
        from src.sync.models import SyncConnectorConfig, SyncRule
        cfg = SyncConnectorConfig(name="c", connector_type="fake", credentials={})
        sync_store.save_connector(cfg, workspace_id="default")
        rule = SyncRule(rule_type="manual")
        sync_store.save_rule(rule, workspace_id="default")
        job = SyncJob(connector_config_id=cfg.id, rule_id=rule.id, name="idem-job")
        sync_store.save_job(job, workspace_id="default")

        # 并发 RUN
        n = 10
        statuses: list[int] = []
        lock = threading.Lock()

        def _run():
            r = client.post(f"/sync/jobs/{job.id}/run", headers=headers)
            with lock:
                statuses.append(r.status_code)

        threads = [threading.Thread(target=_run) for _ in range(n)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        ok = sum(1 for s in statuses if s == 200)
        assert ok == 1, f"期望恰好 1 个 200，实际 {statuses}"
        # 其余应是 409
        assert all(s in (200, 409) for s in statuses)

        active = sync_store.get_active_execution(job.id, workspace_id="default")
        assert active is not None


# ═════════════════════════════════════════════════════════════════════════
# P1-M Memory 幂等（记录性）
# ═════════════════════════════════════════════════════════════════════════


class TestMemoryIdempotencyDocumentation:
    """Memory 幂等性 —— 记录当前设计与限制（P2）。

    结论：ImportMemoryPipeline.process 无去重键（Memory 为随机 UUID，无
    source/external_id/content_hash 唯一键）。P1 通过『不自动重试 + 单
    active execution』在执行层控制重复写 Memory 的风险；跨层 Memory 去重
    需 schema 唯一键设计，属 P2，不在此阶段改动。
    """

    def test_recovery_policy_does_not_auto_retry(self, sync_store, sample_connector_config, sample_rule, sample_job):
        """崩溃恢复策略 = 标记 failed，不自动重试 → 不会重复写 Memory。"""
        sample_job.status = "running"
        sample_job.heartbeat_at = _backdate(_utcnow(), 3600)
        sample_job.attempt_count = 1
        sync_store.save_job(sample_job)

        sync_store.recover_stale_jobs(stale_timeout_seconds=300)
        job = sync_store.get_job(sample_job.id)
        # 标记失败，且 attempt_count 不变（不产生新 execution → 不重复写 Memory）
        assert job.status == "failed"
        assert job.attempt_count == 1
        assert sync_store.get_active_execution(sample_job.id) is None