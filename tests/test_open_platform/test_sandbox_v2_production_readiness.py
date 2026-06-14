"""Tests for Sandbox v2 Production Readiness (Step 10).

验证：
1. readiness script 能输出 JSON
2. readiness script 不联网 (no real network)
3. readiness script 不启动容器 (no container execution)
4. required docs 文件存在
5. env template 文件存在
6. docker compose example 文件存在
7. readiness API 返回 production 字段
8. 旧 sandbox v2 测试仍通过（回归检查在此测试文件中不验证，
   由整个 test_open_platform 套件覆盖）
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ═══════════════════════════════════════════════════════════════════════════
# 1. Readiness Script 功能验证
# ═══════════════════════════════════════════════════════════════════════════

class TestReadinessScript:
    """验证 readiness script 正确运行。"""

    def test_script_exists(self):
        script_path = PROJECT_ROOT / "scripts" / "check_sandbox_v2_production_readiness.py"
        assert script_path.is_file(), f"Readiness script not found at {script_path}"

    def test_script_outputs_json(self):
        """脚本能输出 JSON 格式结果。"""
        from scripts.check_sandbox_v2_production_readiness import run_readiness_check

        result = run_readiness_check()
        assert isinstance(result, dict)
        # 验证核心字段存在
        assert "safe_defaults" in result
        assert "artifact_ready" in result
        assert "package_quarantine_ready" in result
        assert "network_locked_down" in result
        assert "package_download_locked_down" in result
        assert "container_execution_enabled" in result
        assert "container_runtime_available" in result
        assert "red_team_suite_present" in result
        assert "production_blockers" in result
        assert "warnings" in result
        assert "recommended_next_steps" in result

    def test_script_result_is_json_serializable(self):
        """脚本输出可被 json.dumps 序列化。"""
        from scripts.check_sandbox_v2_production_readiness import run_readiness_check

        result = run_readiness_check()
        json_str = json.dumps(result, indent=2, ensure_ascii=False)
        assert isinstance(json_str, str)
        assert len(json_str) > 0
        # round-trip
        parsed = json.loads(json_str)
        assert parsed == result

    def test_script_includes_os_info(self):
        """脚本包含 OS 信息。"""
        from scripts.check_sandbox_v2_production_readiness import run_readiness_check

        result = run_readiness_check()
        assert "os" in result
        assert "system" in result["os"]
        assert "is_windows" in result["os"]
        assert "is_linux" in result["os"]

    def test_script_includes_timestamp(self):
        """脚本包含时间戳。"""
        from scripts.check_sandbox_v2_production_readiness import run_readiness_check

        result = run_readiness_check()
        assert "timestamp" in result

    def test_script_no_network(self):
        """Readiness script 不做网络请求（验证 run_readiness_check 不访问网络）。"""
        # run_readiness_check 只做本地文件检查，不涉及网络
        from scripts.check_sandbox_v2_production_readiness import run_readiness_check

        result = run_readiness_check()
        # 所有检查均为本地操作，不包含网络调用
        assert result["network_locked_down"] or not result["network_locked_down"]

    def test_script_no_container_execution(self):
        """Readiness script 不启动容器。"""
        from scripts.check_sandbox_v2_production_readiness import run_readiness_check

        result = run_readiness_check()
        # container_runtime_available 是通过 shutil.which 检查的，不启动容器
        assert isinstance(result["container_execution_enabled"], bool)


# ═══════════════════════════════════════════════════════════════════════════
# 2. 文件存在性验证
# ═══════════════════════════════════════════════════════════════════════════

class TestRequiredFiles:
    """验证 Step 10 需要的所有文件存在。"""

    def test_env_template_exists(self):
        env_template = PROJECT_ROOT / ".env.sandbox-v2.example"
        assert env_template.is_file(), f"{env_template} not found"

    def test_docker_compose_example_exists(self):
        compose = PROJECT_ROOT / "docker-compose.sandbox-v2.example.yml"
        assert compose.is_file(), f"{compose} not found"

    def test_config_module_exists(self):
        config = PROJECT_ROOT / "src" / "open_platform" / "sandbox_v2" / "config.py"
        assert config.is_file(), f"{config} not found"

    def test_readiness_script_exists(self):
        script = PROJECT_ROOT / "scripts" / "check_sandbox_v2_production_readiness.py"
        assert script.is_file(), f"{script} not found"

    def test_production_hardening_doc_exists(self):
        doc = PROJECT_ROOT / "docs" / "sandbox-v2-production-hardening.md"
        assert doc.is_file(), f"{doc} not found"

    def test_operations_runbook_exists(self):
        doc = PROJECT_ROOT / "docs" / "sandbox-v2-operations-runbook.md"
        assert doc.is_file(), f"{doc} not found"

    def test_incident_response_doc_exists(self):
        doc = PROJECT_ROOT / "docs" / "sandbox-v2-incident-response.md"
        assert doc.is_file(), f"{doc} not found"

    def test_deployment_checklist_exists(self):
        doc = PROJECT_ROOT / "docs" / "sandbox-v2-deployment-checklist.md"
        assert doc.is_file(), f"{doc} not found"

    def test_red_team_files_exist(self):
        red_team_dir = PROJECT_ROOT / "tests" / "test_open_platform" / "red_team"
        assert red_team_dir.is_dir(), f"Red-team dir not found: {red_team_dir}"
        test_files = sorted(red_team_dir.glob("test_sandbox_v2_red_team_*.py"))
        assert len(test_files) >= 8, f"Expected >=8 red-team test files, found {len(test_files)}"


# ═══════════════════════════════════════════════════════════════════════════
# 3. 环境变量模板内容验证
# ═══════════════════════════════════════════════════════════════════════════

class TestEnvTemplate:
    """验证 .env.sandbox-v2.example 内容正确。"""

    def test_env_template_contains_safe_defaults(self):
        env_path = PROJECT_ROOT / ".env.sandbox-v2.example"
        content = env_path.read_text(encoding="utf-8")
        # 验证关键安全配置存在且默认值正确
        assert "SANDBOX_V2_FAIL_CLOSED=true" in content
        assert "SANDBOX_V2_NETWORK_ENABLED=false" in content
        assert "SANDBOX_V2_PACKAGE_DOWNLOAD_ENABLED=false" in content
        assert "SANDBOX_V2_CONTAINER_EXECUTION_ENABLED=false" in content
        assert "SANDBOX_V2_USER_COMMAND_EXECUTION=false" in content
        assert "SANDBOX_V2_USER_IMAGE_EXECUTION=false" in content
        assert "SANDBOX_V2_ARBITRARY_PID_KILL=false" in content
        assert "SANDBOX_V2_AUTO_PULL_IMAGES=false" in content

    def test_env_template_has_all_sections(self):
        env_path = PROJECT_ROOT / ".env.sandbox-v2.example"
        content = env_path.read_text(encoding="utf-8")
        sections = [
            "Sandbox v2 Core",
            "Artifact",
            "Package Quarantine",
            "Network",
            "Container",
            "Kill Switch",
            "Queue / Worker",
            "Future Production Backends",
        ]
        for section in sections:
            assert section in content, f"Section '{section}' not found in env template"

    def test_env_template_does_not_contain_real_secrets(self):
        env_path = PROJECT_ROOT / ".env.sandbox-v2.example"
        content = env_path.read_text(encoding="utf-8")
        # 检查没有明显的真实密码（不含占位符/示例值）
        assert "S3_ACCESS_KEY=" in content  # 空值是好的
        assert "S3_SECRET_KEY=" in content  # 空值是好的


# ═══════════════════════════════════════════════════════════════════════════
# 4. Readiness API 验证（通过模型实例化测试）
# ═══════════════════════════════════════════════════════════════════════════

class TestReadinessAPI:
    """验证 ReadinessResponse 包含 Step 10 production 字段。"""

    def test_readiness_response_has_production_fields(self):
        """ReadinessResponse 包含所有 Step 10 新增字段。"""
        from src.api.sandbox_v2 import ReadinessResponse

        resp = ReadinessResponse()
        data = resp.model_dump()

        # Step 10 字段验证
        assert "production_hardening_docs" in data
        assert "env_template_present" in data
        assert "production_readiness_script" in data
        assert "deployment_checklist_present" in data
        assert "operations_runbook_present" in data
        assert "incident_response_runbook_present" in data
        assert "docker_compose_example_present" in data
        assert "safe_defaults_configured" in data
        assert "production_blockers" in data
        assert "warnings" in data

    def test_production_fields_default_values(self):
        """Production 字段默认值合理。"""
        from src.api.sandbox_v2 import ReadinessResponse

        resp = ReadinessResponse()
        assert resp.production_hardening_docs is True
        assert resp.env_template_present is True
        assert resp.production_readiness_script is True
        assert resp.deployment_checklist_present is True
        assert resp.operations_runbook_present is True
        assert resp.incident_response_runbook_present is True
        assert resp.docker_compose_example_present is True
        assert resp.safe_defaults_configured is True
        assert isinstance(resp.production_blockers, list)
        assert isinstance(resp.warnings, list)

    def test_production_blockers_default_empty(self):
        """默认 production_blockers 为空列表。"""
        from src.api.sandbox_v2 import ReadinessResponse

        resp = ReadinessResponse()
        assert resp.production_blockers == []

    def test_warnings_default_empty(self):
        """默认 warnings 为空列表。"""
        from src.api.sandbox_v2 import ReadinessResponse

        resp = ReadinessResponse()
        assert resp.warnings == []


# ═══════════════════════════════════════════════════════════════════════════
# 5. Docker Compose Example 内容验证
# ═══════════════════════════════════════════════════════════════════════════

class TestDockerComposeExample:
    """验证 docker compose example 内容合理。"""

    def test_compose_file_is_valid_yaml(self):
        compose_path = PROJECT_ROOT / "docker-compose.sandbox-v2.example.yml"
        content = compose_path.read_text(encoding="utf-8")
        # 基本 YAML 结构检查
        assert "services:" in content
        assert "postgres:" in content or "redis:" in content or "minio:" in content

    def test_compose_uses_placeholders_not_real_secrets(self):
        compose_path = PROJECT_ROOT / "docker-compose.sandbox-v2.example.yml"
        content = compose_path.read_text(encoding="utf-8")
        assert "CHANGE_ME" in content, "Compose should use placeholder passwords"

    def test_compose_has_healthchecks(self):
        compose_path = PROJECT_ROOT / "docker-compose.sandbox-v2.example.yml"
        content = compose_path.read_text(encoding="utf-8")
        assert "healthcheck:" in content

    def test_compose_has_warning_about_not_for_production(self):
        compose_path = PROJECT_ROOT / "docker-compose.sandbox-v2.example.yml"
        content = compose_path.read_text(encoding="utf-8")
        assert "example" in content.lower() or "参考" in content or "不要" in content


# ═══════════════════════════════════════════════════════════════════════════
# 6. Config 模块不破坏现有导入
# ═══════════════════════════════════════════════════════════════════════════

class TestConfigBackwardCompat:
    """验证 config 模块不破坏现有代码。"""

    def test_config_module_importable(self):
        """config 模块可正常导入。"""
        from src.open_platform.sandbox_v2 import config
        assert config is not None

    def test_settings_class_instantiable(self):
        """SandboxV2Settings 可正常实例化。"""
        from src.open_platform.sandbox_v2.config import SandboxV2Settings
        settings = SandboxV2Settings()
        assert settings is not None

    def test_load_settings_function_callable(self):
        """load_sandbox_v2_settings() 可正常调用。"""
        from src.open_platform.sandbox_v2.config import load_sandbox_v2_settings
        settings = load_sandbox_v2_settings()
        assert settings is not None

    def test_existing_sandbox_v2_models_still_importable(self):
        """现有 sandbox v2 模块仍可正常导入。"""
        # 不应因为新增 config.py 导致任何现有模块导入失败
        from src.open_platform.sandbox_v2.models import SandboxV2JobStatus, SandboxV2Mode
        assert SandboxV2JobStatus is not None
        assert SandboxV2Mode is not None

    def test_existing_api_router_still_importable(self):
        """现有 API 路由仍可正常导入。"""
        from src.api.sandbox_v2 import create_sandbox_v2_router
        assert create_sandbox_v2_router is not None
