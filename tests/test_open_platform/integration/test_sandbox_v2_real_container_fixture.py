"""Step 6C — Real Container Trusted Fixture 集成测试。

默认 skip。只在以下条件都满足时运行：
- SANDBOX_V2_CONTAINER_EXECUTION_ENABLED=true
- SANDBOX_V2_RUN_CONTAINER_INTEGRATION=true
- 平台是 Linux/WSL2
- Docker/Podman 可用
- 本地镜像存在
"""
import os, pytest, tempfile, shutil, shutil as _shutil
from src.adapters.config import Settings
from src.adapters.sqlite_sandbox_v2_store import SQLiteSandboxV2Store
from src.adapters.sqlite_sandbox_v2_queue import SQLiteSandboxV2Queue
from src.open_platform.sandbox_v2.service import SandboxV2Service
from src.open_platform.sandbox_v2.artifacts import LocalSandboxArtifactStore
from src.open_platform.sandbox_v2.packages import LocalSandboxPackageQuarantineStore
from src.open_platform.sandbox_v2.network import SandboxNetworkEgressService
from src.open_platform.sandbox_v2.execution_provider import create_default_provider_registry
from src.open_platform.sandbox_v2.kill_switch import SandboxKillSwitchService
from src.open_platform.sandbox_v2.container_provider import (
    RootlessContainerExecutionProvider, ContainerCommandBuilder,
)
from src.open_platform.sandbox_v2.models import (
    SandboxV2IsolationProvider, SandboxV2ContainerRuntime,
    SandboxContainerRuntimeConfig, SandboxV2ContainerExecutionStatus,
    TRUSTED_CONTAINER_FIXTURES, DEFAULT_ALLOWED_IMAGES,
)

# ── Skip conditions ──

_RUN_INTEGRATION = os.environ.get("SANDBOX_V2_CONTAINER_EXECUTION_ENABLED", "").lower() in ("true", "1", "yes") and \
                   os.environ.get("SANDBOX_V2_RUN_CONTAINER_INTEGRATION", "").lower() in ("true", "1", "yes")

_IS_LINUX = __import__("platform").system() == "Linux"
_HAS_DOCKER = _shutil.which("docker") is not None
_HAS_PODMAN = _shutil.which("podman") is not None
_HAS_RUNTIME = _HAS_DOCKER or _HAS_PODMAN

_RUNTIME = "docker" if _HAS_DOCKER else ("podman" if _HAS_PODMAN else "unavailable")
_IMAGE = sorted(DEFAULT_ALLOWED_IMAGES)[0]

if _HAS_RUNTIME and _IS_LINUX:
    import subprocess
    _r = subprocess.run([_RUNTIME, "image", "inspect", _IMAGE], capture_output=True, text=True, timeout=10)
    _HAS_IMAGE = _r.returncode == 0
else:
    _HAS_IMAGE = False

CAN_RUN_REAL = _RUN_INTEGRATION and _IS_LINUX and _HAS_RUNTIME and _HAS_IMAGE

skip_reason = ""
if not _RUN_INTEGRATION:
    skip_reason = "Env vars not set. Need SANDBOX_V2_CONTAINER_EXECUTION_ENABLED=true and SANDBOX_V2_RUN_CONTAINER_INTEGRATION=true"
elif not _IS_LINUX:
    skip_reason = f"Not Linux. Current: {__import__('platform').system()}"
elif not _HAS_RUNTIME:
    skip_reason = "No container runtime (docker/podman) found."
elif not _HAS_IMAGE:
    skip_reason = f"Image '{_IMAGE}' not found locally. Run: {_RUNTIME} pull {_IMAGE}"


@pytest.fixture
def service():
    db_fd, db_path = tempfile.mkstemp(suffix=".db"); art_root = tempfile.mkdtemp(); pkg_root = tempfile.mkdtemp()
    os.close(db_fd)
    settings = Settings()
    store = SQLiteSandboxV2Store(settings, db_path=db_path)
    queue = SQLiteSandboxV2Queue(settings, db_path=db_path)
    art = LocalSandboxArtifactStore(artifact_root=art_root)
    pkg = LocalSandboxPackageQuarantineStore(quarantine_root=pkg_root)
    ns = SandboxNetworkEgressService(store=store)
    providers = create_default_provider_registry()
    rt = SandboxV2ContainerRuntime.DOCKER if _HAS_DOCKER else (SandboxV2ContainerRuntime.PODMAN if _HAS_PODMAN else SandboxV2ContainerRuntime.UNAVAILABLE)
    config = SandboxContainerRuntimeConfig(
        provider=SandboxV2IsolationProvider.DOCKER_ROOTLESS_FUTURE,
        runtime=rt, enabled=_RUN_INTEGRATION,
    )
    providers[SandboxV2IsolationProvider.DOCKER_ROOTLESS_FUTURE] = RootlessContainerExecutionProvider(config=config)
    ks = SandboxKillSwitchService(store=store, queue=queue, execution_providers=providers)
    svc = SandboxV2Service(store=store, queue=queue, artifact_store=art, package_store=pkg, network_service=ns, execution_providers=providers, kill_switch=ks)
    yield svc
    try: os.unlink(db_path)
    except: pass
    for d in [art_root, pkg_root]:
        try: shutil.rmtree(d)
        except: pass


class TestPreflight:
    def test_preflight_no_500(self, service):
        pf = service.get_container_runtime_preflight()
        assert "runnable" in pf
        assert "reason" in pf

    def test_preflight_auto_pull_false(self, service):
        pf = service.get_container_runtime_preflight()
        assert pf["auto_pull_images"] is False


class TestRealContainerFixture:
    @pytest.mark.skipif(not CAN_RUN_REAL, reason=skip_reason)
    def test_run_hello_container(self, service):
        plan = service.create_container_execution_plan(
            provider=SandboxV2IsolationProvider.DOCKER_ROOTLESS_FUTURE,
            runtime=_RUNTIME, fixture_id="hello-container-fixture", image=_IMAGE,
        )
        cpid = plan["container_plan"]["container_plan_id"]
        result = service.run_real_container_trusted_fixture(cpid)
        assert result["executed"] is True
        assert result["status"] == "completed"
        assert "sandbox-v2" in result.get("stdout", "").lower()
        if "execution_record" in result:
            assert result["execution_record"]["no_real_execution"] is False
            assert result["execution_record"]["metadata"]["real_container_fixture"] is True

    @pytest.mark.skipif(not CAN_RUN_REAL, reason=skip_reason)
    def test_container_command_has_security_flags(self, service):
        plan = service.create_container_execution_plan(
            provider=SandboxV2IsolationProvider.DOCKER_ROOTLESS_FUTURE,
            runtime=_RUNTIME, fixture_id="hello-container-fixture", image=_IMAGE,
        )
        cpid = plan["container_plan"]["container_plan_id"]
        result = service.run_real_container_trusted_fixture(cpid)
        if "command" in result:
            cmd_str = " ".join(result["command"])
            for flag in ["--network=none", "--read-only", "--cap-drop=ALL", "no-new-privileges", "--user=65532:65532"]:
                assert flag in cmd_str, f"Missing security flag: {flag}"


class TestDisabledWithoutEnv:
    def test_run_without_env_returns_disabled(self, service):
        if CAN_RUN_REAL:
            pytest.skip("Env is enabled — can't test disabled path.")
        plan = service.create_container_execution_plan(
            provider=SandboxV2IsolationProvider.DOCKER_ROOTLESS_FUTURE,
            fixture_id="hello-container-fixture",
        )
        cpid = plan["container_plan"]["container_plan_id"]
        result = service.run_real_container_trusted_fixture(cpid)
        assert result["executed"] is False
        assert result.get("status") in ("disabled", "unavailable", "image_not_found")


class TestCommandSafety:
    def test_build_safe_docker_command(self):
        cmd = ContainerCommandBuilder.build_docker_command("alpine", ["echo", "hi"])
        assert "--network=none" in cmd
        assert "--read-only" in cmd
        assert "--cap-drop=ALL" in cmd
        assert "--user=65532:65532" in cmd
        assert "--security-opt=no-new-privileges" in cmd
        assert "--privileged" not in cmd
        assert "--network=host" not in cmd
