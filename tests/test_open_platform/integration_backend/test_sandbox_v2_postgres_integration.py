"""PostgreSQL integration tests (Step 13). Default SKIP.

Only run when:
  SANDBOX_V2_RUN_BACKEND_INTEGRATION=true
  SANDBOX_V2_DATABASE_BACKEND=postgres
  SANDBOX_V2_POSTGRES_DSN configured
"""

import os
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

_RUNNING = os.environ.get("SANDBOX_V2_RUN_BACKEND_INTEGRATION", "").lower() in ("true", "1", "yes")
_DB_BACKEND = os.environ.get("SANDBOX_V2_DATABASE_BACKEND", "sqlite")
_DSN = os.environ.get("SANDBOX_V2_POSTGRES_DSN", "")

pytestmark = pytest.mark.skipif(
    not (_RUNNING and _DB_BACKEND == "postgres" and _DSN),
    reason="Requires SANDBOX_V2_RUN_BACKEND_INTEGRATION=true + database_backend=postgres + DSN configured",
)

_TEST_RUN_ID = f"step13-test-{__import__('uuid').uuid4().hex[:8]}"


@pytest.fixture(scope="module")
def store():
    from src.adapters.postgres_sandbox_v2_store import PostgresSandboxV2Store
    s = PostgresSandboxV2Store(dsn=_DSN, connect=True)
    # 初始化 schema
    sch = s.get_schema_sql_path()
    if sch:
        s.initialize_schema(str(sch))
    yield s
    # 清理测试数据
    try:
        s._execute("DELETE FROM sandbox_v2_jobs WHERE organization_id LIKE 'step13%'", ())
        s._execute("DELETE FROM sandbox_v2_artifacts WHERE organization_id LIKE 'step13%'", ())
    except Exception:
        pass


class TestPostgresHealth:
    def test_health_check(self, store):
        hc = store.health_check()
        assert hc["ok"], f"Health check failed: {hc}"

    def test_schema_initialized(self, store):
        rows = store._fetchall("SELECT tablename FROM pg_catalog.pg_tables WHERE schemaname='public' AND tablename LIKE 'sandbox_v2%'")
        tables = [r.get("tablename", "") for r in rows]
        assert "sandbox_v2_jobs" in tables


class TestPostgresJobCRUD:
    def test_create_job(self, store):
        from src.open_platform.sandbox_v2.models import SandboxJob
        job = SandboxJob(
            job_id=f"job-{_TEST_RUN_ID}-1", organization_id=f"step13-{_TEST_RUN_ID}",
            mode="simulation", status="created",
        )
        created = store.create_job(job)
        assert created.job_id == job.job_id

    def test_get_job(self, store):
        job_id = f"job-{_TEST_RUN_ID}-2"
        from src.open_platform.sandbox_v2.models import SandboxJob
        store.create_job(SandboxJob(job_id=job_id, organization_id=f"step13-{_TEST_RUN_ID}"))
        fetched = store.get_job(job_id)
        assert fetched is not None

    def test_list_jobs_org_filter(self, store):
        jobs = store.list_jobs(organization_id=f"step13-{_TEST_RUN_ID}")
        assert isinstance(jobs, list)


class TestPostgresExecutionRecords:
    def test_create_list_record(self, store):
        from src.open_platform.sandbox_v2.models import SandboxV2ExecutionRecord
        store.create_execution_record(SandboxV2ExecutionRecord(
            record_id=f"rec-{_TEST_RUN_ID}-1", job_id=f"job-{_TEST_RUN_ID}-2",
        ))
        records = store.list_execution_records(job_id=f"job-{_TEST_RUN_ID}-2")
        assert len(records) >= 1


class TestPostgresArtifacts:
    def test_create_artifact_metadata(self, store):
        from src.open_platform.sandbox_v2.models import SandboxArtifact
        art = SandboxArtifact(
            artifact_id=f"art-{_TEST_RUN_ID}-a", job_id=f"job-{_TEST_RUN_ID}-2",
            artifact_type="text", name="test.txt", organization_id=f"step13-{_TEST_RUN_ID}",
        )
        store.create_artifact(art)
        fetched = store.get_artifact(f"art-{_TEST_RUN_ID}-a")
        assert fetched is not None


class TestPostgresPackageRequests:
    def test_create_package_request(self, store):
        from src.open_platform.sandbox_v2.models import SandboxPackageRequest
        req = SandboxPackageRequest(
            package_request_id=f"pkg-{_TEST_RUN_ID}-1", package_name="test-pkg",
            job_id=f"job-{_TEST_RUN_ID}-2",
        )
        store.create_package_request(req)
        fetched = store.get_package_request(f"pkg-{_TEST_RUN_ID}-1")
        assert fetched is not None


class TestPostgresNetworkRequests:
    def test_create_network_request(self, store):
        from src.open_platform.sandbox_v2.models import SandboxNetworkEgressRequest
        req = SandboxNetworkEgressRequest(
            egress_request_id=f"egr-{_TEST_RUN_ID}-1", url="https://example.com",
            job_id=f"job-{_TEST_RUN_ID}-2",
        )
        store.create_network_egress_request(req)
        fetched = store.get_network_egress_request(f"egr-{_TEST_RUN_ID}-1")
        assert fetched is not None
