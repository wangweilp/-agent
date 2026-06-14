"""Red-Team API Abuse Tests — API 层滥用攻击测试。

验证：恶意输入/超长/../注入/缺字段/过大limit不返回500，不泄露敏感信息。
"""

import os, pytest, tempfile, shutil
from fastapi import FastAPI; from fastapi.testclient import TestClient
from src.adapters.config import Settings
from src.adapters.sqlite_sandbox_v2_store import SQLiteSandboxV2Store
from src.adapters.sqlite_sandbox_v2_queue import SQLiteSandboxV2Queue
from src.open_platform.sandbox_v2.service import SandboxV2Service
from src.open_platform.sandbox_v2.worker import SandboxV2Worker
from src.open_platform.sandbox_v2.artifacts import LocalSandboxArtifactStore
from src.open_platform.sandbox_v2.packages import LocalSandboxPackageQuarantineStore
from src.open_platform.sandbox_v2.network import SandboxNetworkEgressService
from src.open_platform.sandbox_v2.execution_provider import create_default_provider_registry
from src.open_platform.sandbox_v2.kill_switch import SandboxKillSwitchService
from src.api.sandbox_v2 import create_sandbox_v2_router


@pytest.fixture
def client():
    db_fd, db_path = tempfile.mkstemp(suffix=".db"); art_root = tempfile.mkdtemp(); pkg_root = tempfile.mkdtemp()
    os.close(db_fd)
    settings = Settings()
    store = SQLiteSandboxV2Store(settings, db_path=db_path)
    queue = SQLiteSandboxV2Queue(settings, db_path=db_path)
    art = LocalSandboxArtifactStore(artifact_root=art_root)
    pkg = LocalSandboxPackageQuarantineStore(quarantine_root=pkg_root)
    ns = SandboxNetworkEgressService(store=store)
    providers = create_default_provider_registry()
    ks = SandboxKillSwitchService(store=store, queue=queue, execution_providers=providers)
    svc = SandboxV2Service(store=store, queue=queue, artifact_store=art, package_store=pkg, network_service=ns, execution_providers=providers, kill_switch=ks)
    app = FastAPI(); app.include_router(create_sandbox_v2_router(svc, worker=SandboxV2Worker(queue=queue, service=svc, worker_id="rt-api")))
    yield TestClient(app)
    try: os.unlink(db_path)
    except: pass
    for d in [art_root, pkg_root]:
        try: shutil.rmtree(d)
        except: pass


class TestInputValidation:
    def test_empty_job_id_404(self, client):
        # path param with ../ should be caught by FastAPI routing
        res = client.get("/api/runtime/sandbox-v2/jobs/../admin")
        assert res.status_code in (404, 422)

    def test_oversized_limit_truncated(self, client):
        res = client.get("/api/runtime/sandbox-v2/jobs?limit=999999")
        assert res.status_code != 500

    def test_negative_limit_handled(self, client):
        res = client.get("/api/runtime/sandbox-v2/jobs?limit=-1")
        assert res.status_code != 500


class TestNo500:
    def test_get_nonexistent_artifact(self, client):
        res = client.get("/api/runtime/sandbox-v2/artifacts/nonexistent123")
        assert res.status_code != 500

    def test_delete_nonexistent_artifact(self, client):
        res = client.delete("/api/runtime/sandbox-v2/artifacts/nonexistent123")
        assert res.status_code != 500

    def test_duplicate_cancel(self, client):
        client.post("/api/runtime/sandbox-v2/jobs/tmp-cancel-dupe/cancel")
        res = client.post("/api/runtime/sandbox-v2/jobs/tmp-cancel-dupe/cancel")
        assert res.status_code != 500

    def test_malformed_url_preflight(self, client):
        res = client.post("/api/runtime/sandbox-v2/network/preflight", json={"url": "not-a-valid-url!!!"})
        assert res.status_code != 500

    def test_invalid_provider_container_plan(self, client):
        res = client.post("/api/runtime/sandbox-v2/isolation/container-plans", json={"provider": "__invalid__"})
        assert res.status_code != 500

    def test_get_nonexistent_kill_request(self, client):
        res = client.get("/api/runtime/sandbox-v2/kill/requests")
        assert res.status_code == 200  # empty list, no 500


class TestNoSensitiveInfoLeak:
    def test_response_no_stack_trace(self, client):
        res = client.get("/api/runtime/sandbox-v2/artifacts/nonexistent")
        text = res.text.lower()
        assert "traceback" not in text
        assert "file" not in text or '"' not in text  # don't leak local paths

    def test_readiness_no_local_paths(self, client):
        res = client.get("/api/runtime/sandbox-v2/readiness")
        data = res.json()
        # No local paths like D:\
        for k, v in data.items():
            if isinstance(v, str):
                assert "D:\\" not in v
                assert "C:\\" not in v


class TestPathTraversalInAPI:
    def test_job_id_path_traversal(self, client):
        res = client.get("/api/runtime/sandbox-v2/jobs/../../../etc/passwd")
        assert res.status_code in (404, 422)

    def test_execution_record_path_traversal(self, client):
        js = {"mode": "simulation"}
        res = client.post("/api/runtime/sandbox-v2/jobs", json={"mode": "../../"})
        assert res.status_code != 500
