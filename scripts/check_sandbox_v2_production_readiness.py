#!/usr/bin/env python
"""Sandbox v2 Production Readiness Check Script.

Step 10 --- 生产化 readiness 检查脚本。

功能：
1. 读取环境变量配置（通过 SandboxV2Settings）
2. 检查当前 OS
3. 检查 artifact root 是否存在或可创建
4. 检查 package quarantine root 是否存在或可创建
5. 检查 Docker/Podman 是否存在（不启动容器）
6. 检查容器执行 env 是否关闭或显式开启
7. 检查 network 是否 preflight-only
8. 检查 package download 是否关闭
9. 检查 arbitrary PID kill 是否关闭
10. 检查 red-team 测试文件是否存在
11. 输出 JSON 和人类可读 summary

安全约束：
- 不联网
- 不执行容器
- 不安装包
- 不执行用户代码
- 不杀系统进程
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import sys
from pathlib import Path
from typing import Any


# ── Project root detection ──────────────────────────────────────────────

def _find_project_root() -> Path:
    """查找项目根目录（包含 src/ 目录的目录）。"""
    current = Path(__file__).resolve().parent.parent
    if (current / "src").is_dir():
        return current
    # Fallback: search upward
    for p in [current] + list(current.parents):
        if (p / "src").is_dir():
            return p
    return current


PROJECT_ROOT = _find_project_root()


# ── Config loading ──────────────────────────────────────────────────────

def _load_settings() -> Any:
    """加载 SandboxV2Settings，如果模块不可用则从 os.environ 直接读取。"""
    try:
        sys.path.insert(0, str(PROJECT_ROOT))
        from src.open_platform.sandbox_v2.config import load_sandbox_v2_settings
        return load_sandbox_v2_settings()
    except ImportError:
        # Fallback: direct env reading
        return _load_settings_from_env()


def _env_bool(name: str, default: bool) -> bool:
    val = os.getenv(name, "").strip().lower()
    if val in ("true", "1", "yes"):
        return True
    if val in ("false", "0", "no"):
        return False
    return default


def _load_settings_from_env() -> dict[str, Any]:
    """Fallback: 直接从环境变量读取配置。"""
    return {
        "fail_closed": _env_bool("SANDBOX_V2_FAIL_CLOSED", True),
        "network_enabled": _env_bool("SANDBOX_V2_NETWORK_ENABLED", False),
        "network_preflight_only": _env_bool("SANDBOX_V2_NETWORK_PREFLIGHT_ONLY", True),
        "package_download_enabled": _env_bool("SANDBOX_V2_PACKAGE_DOWNLOAD_ENABLED", False),
        "package_installation_enabled": _env_bool("SANDBOX_V2_PACKAGE_INSTALLATION_ENABLED", False),
        "public_registry_enabled": _env_bool("SANDBOX_V2_PUBLIC_REGISTRY_ENABLED", False),
        "container_execution_enabled": _env_bool("SANDBOX_V2_CONTAINER_EXECUTION_ENABLED", False),
        "user_command_execution": _env_bool("SANDBOX_V2_USER_COMMAND_EXECUTION", False),
        "user_image_execution": _env_bool("SANDBOX_V2_USER_IMAGE_EXECUTION", False),
        "arbitrary_pid_kill": _env_bool("SANDBOX_V2_ARBITRARY_PID_KILL", False),
        "auto_pull_images": _env_bool("SANDBOX_V2_AUTO_PULL_IMAGES", False),
        "read_only_artifacts": _env_bool("SANDBOX_V2_READ_ONLY_ARTIFACTS", True),
        "kill_switch_enabled": _env_bool("SANDBOX_V2_KILL_SWITCH_ENABLED", True),
        "artifact_root": os.getenv("SANDBOX_V2_ARTIFACT_ROOT", ".sandbox_v2_artifacts"),
        "package_quarantine_root": os.getenv("SANDBOX_V2_PACKAGE_QUARANTINE_ROOT", ".sandbox_v2_package_quarantine"),
    }


# ── Check functions ─────────────────────────────────────────────────────

def _check_safe_defaults(settings: Any) -> tuple[bool, list[str]]:
    """检查安全默认值。"""
    issues: list[str] = []

    def get(k: str, default: Any) -> Any:
        if hasattr(settings, k):
            return getattr(settings, k)
        return settings.get(k, default) if isinstance(settings, dict) else default

    if not get("fail_closed", True):
        issues.append("SANDBOX_V2_FAIL_CLOSED is not true")
    if get("network_enabled", False):
        issues.append("SANDBOX_V2_NETWORK_ENABLED is true --- production must be false")
    if get("package_download_enabled", False):
        issues.append("SANDBOX_V2_PACKAGE_DOWNLOAD_ENABLED is true --- production must be false")
    if get("package_installation_enabled", False):
        issues.append("SANDBOX_V2_PACKAGE_INSTALLATION_ENABLED is true --- production must be false")
    if get("public_registry_enabled", False):
        issues.append("SANDBOX_V2_PUBLIC_REGISTRY_ENABLED is true --- production must be false")
    if get("container_execution_enabled", False):
        issues.append("SANDBOX_V2_CONTAINER_EXECUTION_ENABLED is true --- requires additional audit")
    if get("user_command_execution", False):
        issues.append("SANDBOX_V2_USER_COMMAND_EXECUTION is true --- MUST be false for production")
    if get("user_image_execution", False):
        issues.append("SANDBOX_V2_USER_IMAGE_EXECUTION is true --- MUST be false for production")
    if get("arbitrary_pid_kill", False):
        issues.append("SANDBOX_V2_ARBITRARY_PID_KILL is true --- MUST be false for production")
    if get("auto_pull_images", False):
        issues.append("SANDBOX_V2_AUTO_PULL_IMAGES is true --- must be false for production")
    if not get("read_only_artifacts", True):
        issues.append("SANDBOX_V2_READ_ONLY_ARTIFACTS is false --- must be true for production")

    return len(issues) == 0, issues


def _check_directory(root_key: str, default_path: str) -> tuple[bool, str]:
    """检查目录是否存在或可创建。"""
    env_val = os.getenv(root_key, default_path)
    target = Path(env_val)
    if not target.is_absolute():
        target = PROJECT_ROOT / target
    if target.exists():
        if target.is_dir():
            return True, f"exists at {target}"
        return False, f"exists but is not a directory: {target}"
    # 尝试创建
    try:
        target.mkdir(parents=True, exist_ok=True)
        return True, f"created at {target}"
    except OSError as e:
        return False, f"cannot create {target}: {e}"


def _check_container_runtime() -> tuple[bool, str]:
    """检查 Docker/Podman 是否存在（不启动容器）。"""
    docker_path = shutil.which("docker")
    podman_path = shutil.which("podman")
    if docker_path:
        return True, f"Docker found at {docker_path}"
    if podman_path:
        return True, f"Podman found at {podman_path}"
    return False, "Neither Docker nor Podman found in PATH"


def _check_red_team_suite() -> tuple[bool, str]:
    """检查 red-team 测试文件是否存在。"""
    red_team_dir = PROJECT_ROOT / "tests" / "test_open_platform" / "red_team"
    if not red_team_dir.is_dir():
        return False, f"Red-team directory not found: {red_team_dir}"
    test_files = sorted(red_team_dir.glob("test_sandbox_v2_red_team_*.py"))
    if not test_files:
        return False, "No red-team test files found"
    return True, f"Found {len(test_files)} red-team test files"


def _check_docs_present() -> dict[str, bool]:
    """检查 hardening 文档是否存在。"""
    docs_dir = PROJECT_ROOT / "docs"
    required = {
        "production_hardening": "sandbox-v2-production-hardening.md",
        "operations_runbook": "sandbox-v2-operations-runbook.md",
        "incident_response": "sandbox-v2-incident-response.md",
        "deployment_checklist": "sandbox-v2-deployment-checklist.md",
    }
    result: dict[str, bool] = {}
    for key, filename in required.items():
        result[key] = (docs_dir / filename).is_file()
    return result


def _check_env_template() -> bool:
    """检查 .env.sandbox-v2.example 是否存在。"""
    return (PROJECT_ROOT / ".env.sandbox-v2.example").is_file()


def _check_docker_compose_example() -> bool:
    """检查 docker-compose.sandbox-v2.example.yml 是否存在。"""
    return (PROJECT_ROOT / "docker-compose.sandbox-v2.example.yml").is_file()


def _check_os() -> dict[str, Any]:
    """返回当前 OS 信息。"""
    return {
        "system": platform.system(),
        "release": platform.release(),
        "version": platform.version(),
        "machine": platform.machine(),
        "is_windows": platform.system() == "Windows",
        "is_linux": platform.system() == "Linux",
    }


# ── Main check ──────────────────────────────────────────────────────────

def run_readiness_check() -> dict[str, Any]:
    """运行完整的 production readiness 检查，返回结构化结果。"""
    settings = _load_settings()

    safe_defaults_ok, safe_defaults_issues = _check_safe_defaults(settings)
    artifact_ok, artifact_msg = _check_directory("SANDBOX_V2_ARTIFACT_ROOT", ".sandbox_v2_artifacts")
    package_ok, package_msg = _check_directory("SANDBOX_V2_PACKAGE_QUARANTINE_ROOT", ".sandbox_v2_package_quarantine")
    container_runtime_ok, container_runtime_msg = _check_container_runtime()
    red_team_ok, red_team_msg = _check_red_team_suite()
    docs_present = _check_docs_present()
    env_template_ok = _check_env_template()
    compose_ok = _check_docker_compose_example()
    os_info = _check_os()

    # Determine container_execution_enabled from settings
    if hasattr(settings, "container_execution_enabled"):
        container_exec_enabled = settings.container_execution_enabled
    else:
        container_exec_enabled = settings.get("container_execution_enabled", False) if isinstance(settings, dict) else False

    # Build production blockers
    blockers: list[str] = []
    if not safe_defaults_ok:
        blockers.extend(safe_defaults_issues)
    if not artifact_ok:
        blockers.append(f"Artifact root issue: {artifact_msg}")
    if not package_ok:
        blockers.append(f"Package quarantine root issue: {package_msg}")
    if not red_team_ok:
        blockers.append(f"Red-team suite issue: {red_team_msg}")

    # Build warnings
    warns: list[str] = []
    if not container_runtime_ok:
        warns.append(f"Container runtime not available: {container_runtime_msg}")
    if not env_template_ok:
        warns.append(".env.sandbox-v2.example not found")
    if not compose_ok:
        warns.append("docker-compose.sandbox-v2.example.yml not found")
    missing_docs = [k for k, v in docs_present.items() if not v]
    if missing_docs:
        warns.append(f"Missing docs: {', '.join(missing_docs)}")

    # Recommended next steps
    next_steps: list[str] = []
    if hasattr(settings, 'recommended_next_steps'):
        next_steps = settings.recommended_next_steps()
    else:
        if os_info["is_windows"]:
            next_steps.append("Windows detected --- real container validation requires WSL2/Linux")
        next_steps.append("Run red-team tests: python -m pytest tests/test_open_platform/red_team -q")
        next_steps.append("Complete docs if missing")

    return {
        "timestamp": __import__("datetime").datetime.now().isoformat(),
        "project_root": str(PROJECT_ROOT),
        "os": os_info,
        "safe_defaults": safe_defaults_ok,
        "safe_defaults_issues": safe_defaults_issues,
        "artifact_ready": artifact_ok,
        "artifact_detail": artifact_msg,
        "package_quarantine_ready": package_ok,
        "package_quarantine_detail": package_msg,
        "network_locked_down": not (hasattr(settings, 'network_enabled') and settings.network_enabled if hasattr(settings, 'network_enabled') else False),
        "package_download_locked_down": not (hasattr(settings, 'package_download_enabled') and settings.package_download_enabled if hasattr(settings, 'package_download_enabled') else False),
        "container_execution_enabled": container_exec_enabled,
        "container_runtime_available": container_runtime_ok,
        "container_runtime_detail": container_runtime_msg,
        "red_team_suite_present": red_team_ok,
        "red_team_detail": red_team_msg,
        "docs_present": docs_present,
        "env_template_present": env_template_ok,
        "docker_compose_example_present": compose_ok,
        "production_blockers": blockers,
        "warnings": warns,
        "recommended_next_steps": next_steps,
    }


def print_human_summary(result: dict[str, Any]) -> None:
    """打印人类可读的 readiness summary。"""
    print("=" * 70)
    print("  Sandbox v2 Production Readiness Check")
    print("=" * 70)
    print(f"  Project root: {result['project_root']}")
    print(f"  OS: {result['os']['system']} {result['os']['release']} ({result['os']['machine']})")
    print()

    # Safe defaults
    status = "[OK] PASS" if result["safe_defaults"] else "[FAIL] FAIL"
    print(f"  [{status}] Safe defaults")
    for issue in result.get("safe_defaults_issues", []):
        print(f"         [WARN] {issue}")
    print()

    # Artifact
    status = "[OK] PASS" if result["artifact_ready"] else "[FAIL] FAIL"
    print(f"  [{status}] Artifact root: {result['artifact_detail']}")
    print()

    # Package quarantine
    status = "[OK] PASS" if result["package_quarantine_ready"] else "[FAIL] FAIL"
    print(f"  [{status}] Package quarantine root: {result['package_quarantine_detail']}")
    print()

    # Network
    status = "[OK] PASS" if result["network_locked_down"] else "[WARN]WARN"
    print(f"  [{status}] Network locked down: {'yes' if result['network_locked_down'] else 'NO --- network is open!'}")
    print()

    # Package download
    status = "[OK] PASS" if result["package_download_locked_down"] else "[WARN]WARN"
    print(f"  [{status}] Package download locked down: {'yes' if result['package_download_locked_down'] else 'NO --- download is open!'}")
    print()

    # Container execution
    ce = result["container_execution_enabled"]
    status = "[WARN]WARN" if ce else "[OK] PASS"
    print(f"  [{status}] Container execution: {'ENABLED' if ce else 'disabled (safe)'}")
    print()

    # Container runtime
    status = "[OK] INFO" if result["container_runtime_available"] else "[WARN]NOTE"
    print(f"  [{status}] Container runtime: {result['container_runtime_detail']}")
    print()

    # Red-team
    status = "[OK] PASS" if result["red_team_suite_present"] else "[FAIL] FAIL"
    print(f"  [{status}] Red-team suite: {result['red_team_detail']}")
    print()

    # Docs
    docs = result["docs_present"]
    for doc_key, doc_present in docs.items():
        status = "[OK]" if doc_present else "[FAIL]"
        print(f"  [{status}] Doc: {doc_key} --- {'present' if doc_present else 'MISSING'}")
    print()

    # Templates
    print(f"  [{'[OK]' if result['env_template_present'] else '[FAIL]'}] .env.sandbox-v2.example: {'present' if result['env_template_present'] else 'MISSING'}")
    print(f"  [{'[OK]' if result['docker_compose_example_present'] else '[FAIL]'}] docker-compose.sandbox-v2.example.yml: {'present' if result['docker_compose_example_present'] else 'MISSING'}")
    print()

    # Blockers
    blockers = result.get("production_blockers", [])
    if blockers:
        print(f"  [BLOCKER]PRODUCTION BLOCKERS ({len(blockers)}):")
        for b in blockers:
            print(f"       -{b}")
        print()

    # Warnings
    warns = result.get("warnings", [])
    if warns:
        print(f"  [WARN]WARNINGS ({len(warns)}):")
        for w in warns:
            print(f"       -{w}")
        print()

    # Next steps
    steps = result.get("recommended_next_steps", [])
    if steps:
        print("  ->Recommended next steps:")
        for i, s in enumerate(steps, 1):
            print(f"     {i}. {s}")
        print()

    # Summary
    total_blockers = len(blockers)
    total_warns = len(warns)
    if total_blockers == 0 and total_warns == 0:
        print("  [READY]Overall: READY FOR PRODUCTION")
    elif total_blockers == 0:
        print(f"  [WARN]Overall: READY with {total_warns} warning(s)")
    else:
        print(f"  [NOT READY]Overall: NOT READY --- {total_blockers} blocker(s), {total_warns} warning(s)")

    print()
    print("=" * 70)


def main() -> int:
    """运行 readiness 检查并输出结果。"""
    result = run_readiness_check()

    # 始终输出 JSON（到 stdout 或文件）
    output_json = os.getenv("SANDBOX_V2_READINESS_OUTPUT_JSON", "false").lower() in ("true", "1", "yes")

    if output_json or "--json" in sys.argv:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print_human_summary(result)

    # 返回 exit code: 0 = ready, 1 = has blockers
    return 1 if result.get("production_blockers") else 0


if __name__ == "__main__":
    sys.exit(main())
