"""Sandbox v2 Container Fixture 环境预检与验证脚本。

不 pull 镜像，不联网，不执行用户代码。
输出当前环境状态和建议。

用法: python scripts/run_sandbox_v2_container_fixture_check.py
"""

import os, sys, platform, shutil, subprocess, json

def check():
    print("=" * 60)
    print("Sandbox v2 — Container Trusted Fixture Environment Check")
    print("=" * 60)

    p = {"platform": platform.system(), "release": platform.release(),
         "is_linux": platform.system() == "Linux"}

    has_docker = shutil.which("docker") is not None
    has_podman = shutil.which("podman") is not None
    runtime = "docker" if has_docker else ("podman" if has_podman else "unavailable")

    env_enabled = os.environ.get("SANDBOX_V2_CONTAINER_EXECUTION_ENABLED", "").lower() in ("true", "1", "yes")
    integration_enabled = os.environ.get("SANDBOX_V2_RUN_CONTAINER_INTEGRATION", "").lower() in ("true", "1", "yes")

    image = "python:3.11-alpine"
    has_image = False
    if has_docker or has_podman:
        try:
            r = subprocess.run([runtime, "image", "inspect", image], capture_output=True, text=True, timeout=10)
            has_image = r.returncode == 0
        except Exception:
            has_image = False

    can_run = all([p["is_linux"], (has_docker or has_podman), env_enabled, integration_enabled, has_image])

    print(f"\n  Platform:           {p['platform']} {p['release']}")
    print(f"  Is Linux:           {p['is_linux']}")
    print(f"  Docker available:   {has_docker}")
    print(f"  Podman available:   {has_podman}")
    print(f"  Runtime:            {runtime}")
    print(f"  Image ({image}):     {'present' if has_image else 'NOT FOUND'}")
    print(f"  CONTAINER_EXECUTION_ENABLED: {env_enabled}")
    print(f"  RUN_CONTAINER_INTEGRATION:   {integration_enabled}")
    print(f"  CAN RUN REAL FIXTURE: {'YES' if can_run else 'NO'}")

    print()
    if not can_run:
        print("  Reasons:")
        if not p["is_linux"]:
            print("    - Not Linux/WSL2. Real container execution requires Linux.")
        if not (has_docker or has_podman):
            print("    - No Docker/Podman found. Install Docker or Podman.")
        if not env_enabled:
            print("    - Set: export SANDBOX_V2_CONTAINER_EXECUTION_ENABLED=true")
        if not integration_enabled:
            print("    - Set: export SANDBOX_V2_RUN_CONTAINER_INTEGRATION=true")
        if not has_image:
            print(f"    - Pull image: {runtime} pull {image}")
        print()
        print("  On Windows: real container execution is NOT available.")
        print("  Use WSL2 or a Linux VM.")
        print("  See docs/sandbox-v2-real-container-fixture.md for setup guide.")

    if can_run:
        print("  All preconditions satisfied. Running real container fixture...")
        print()
        # Run via API or direct provider call
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        from src.adapters.config import Settings
        from src.adapters.sqlite_sandbox_v2_store import SQLiteSandboxV2Store
        from src.open_platform.sandbox_v2.container_provider import RootlessContainerExecutionProvider
        from src.open_platform.sandbox_v2.models import SandboxContainerRuntimeConfig, SandboxV2IsolationProvider, SandboxV2ContainerRuntime

        settings = Settings()
        store = SQLiteSandboxV2Store(settings)
        rt_enum = SandboxV2ContainerRuntime.DOCKER if has_docker else SandboxV2ContainerRuntime.PODMAN
        config = SandboxContainerRuntimeConfig(
            provider=SandboxV2IsolationProvider.DOCKER_ROOTLESS_FUTURE,
            runtime=rt_enum, enabled=True,
        )
        provider = RootlessContainerExecutionProvider(config=config)
        result = provider.run_real_trusted_fixture(job_id="preflight-check", fixture_id="hello-container-fixture", image=image)

        print(f"  Executed:  {result.get('executed')}")
        print(f"  Status:    {result.get('status')}")
        print(f"  Exit code: {result.get('exit_code')}")
        print(f"  Duration:  {result.get('duration_ms')}ms")
        print(f"  Stdout:    {result.get('stdout', '')[:200]}")
        print(f"  Container: {result.get('container_name', '')}")

    print()
    print("=" * 60)
    print("Check complete. No user code executed. No network accessed.")

if __name__ == "__main__":
    check()
