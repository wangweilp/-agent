"""Tests for Sandbox v2 Production Configuration (Step 10).

验证 SandboxV2Settings 数据类和 load_sandbox_v2_settings()：
1. 默认配置 network=false
2. 默认 package_download=false
3. 默认 container_execution=false
4. 默认 user_command_execution=false
5. 默认 arbitrary_pid_kill=false
6. 默认 fail_closed=true
7. 读取环境变量 true/false 正确
8. is_safe_default() 返回正确
9. production_blockers() 检测危险配置
10. warnings() 检测非生产后端
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ── Import ───────────────────────────────────────────────────────────────

from src.open_platform.sandbox_v2.config import (
    SandboxV2Settings,
    load_sandbox_v2_settings,
    _env_bool,
    _env_int,
    _env_list,
    _env_str,
)


# ═══════════════════════════════════════════════════════════════════════════
# 1. 默认配置安全关闭
# ═══════════════════════════════════════════════════════════════════════════

class TestDefaultSafeConfig:
    """默认配置所有危险能力必须关闭。"""

    def test_default_fail_closed_true(self):
        settings = SandboxV2Settings()
        assert settings.fail_closed is True

    def test_default_network_disabled(self):
        settings = SandboxV2Settings()
        assert settings.network_enabled is False

    def test_default_package_download_disabled(self):
        settings = SandboxV2Settings()
        assert settings.package_download_enabled is False

    def test_default_package_installation_disabled(self):
        settings = SandboxV2Settings()
        assert settings.package_installation_enabled is False

    def test_default_public_registry_disabled(self):
        settings = SandboxV2Settings()
        assert settings.public_registry_enabled is False

    def test_default_container_execution_disabled(self):
        settings = SandboxV2Settings()
        assert settings.container_execution_enabled is False

    def test_default_user_command_execution_disabled(self):
        settings = SandboxV2Settings()
        assert settings.user_command_execution is False

    def test_default_user_image_execution_disabled(self):
        settings = SandboxV2Settings()
        assert settings.user_image_execution is False

    def test_default_arbitrary_pid_kill_disabled(self):
        settings = SandboxV2Settings()
        assert settings.arbitrary_pid_kill is False

    def test_default_auto_pull_images_disabled(self):
        settings = SandboxV2Settings()
        assert settings.auto_pull_images is False

    def test_default_read_only_artifacts_true(self):
        settings = SandboxV2Settings()
        assert settings.read_only_artifacts is True

    def test_default_kill_switch_enabled(self):
        settings = SandboxV2Settings()
        assert settings.kill_switch_enabled is True

    def test_default_container_kill_disabled(self):
        settings = SandboxV2Settings()
        assert settings.container_kill_enabled is False

    def test_default_network_preflight_only(self):
        settings = SandboxV2Settings()
        assert settings.network_preflight_only is True

    def test_default_mode_is_simulation(self):
        settings = SandboxV2Settings()
        assert settings.mode == "simulation"

    def test_default_action_is_deny(self):
        settings = SandboxV2Settings()
        assert settings.default_action == "deny"


# ═══════════════════════════════════════════════════════════════════════════
# 2. 安全默认值验证方法
# ═══════════════════════════════════════════════════════════════════════════

class TestIsSafeDefault:
    """is_safe_default() 方法正确检测安全状态。"""

    def test_default_is_safe(self):
        settings = SandboxV2Settings()
        assert settings.is_safe_default() is True

    def test_network_enabled_makes_unsafe(self):
        settings = SandboxV2Settings(network_enabled=True)
        assert settings.is_safe_default() is False

    def test_package_download_enabled_makes_unsafe(self):
        settings = SandboxV2Settings(package_download_enabled=True)
        assert settings.is_safe_default() is False

    def test_container_execution_enabled_makes_unsafe(self):
        settings = SandboxV2Settings(container_execution_enabled=True)
        assert settings.is_safe_default() is False

    def test_user_command_execution_makes_unsafe(self):
        settings = SandboxV2Settings(user_command_execution=True)
        assert settings.is_safe_default() is False

    def test_fail_closed_false_makes_unsafe(self):
        settings = SandboxV2Settings(fail_closed=False)
        assert settings.is_safe_default() is False


# ═══════════════════════════════════════════════════════════════════════════
# 3. production_blockers() 方法
# ═══════════════════════════════════════════════════════════════════════════

class TestProductionBlockers:
    """production_blockers() 正确检测生产阻塞项。"""

    def test_default_has_no_blockers(self):
        settings = SandboxV2Settings()
        assert settings.production_blockers() == []

    def test_fail_closed_false_is_blocker(self):
        settings = SandboxV2Settings(fail_closed=False)
        blockers = settings.production_blockers()
        assert any("fail_closed" in b for b in blockers)

    def test_network_enabled_is_blocker(self):
        settings = SandboxV2Settings(network_enabled=True)
        blockers = settings.production_blockers()
        assert any("network_enabled" in b for b in blockers)

    def test_container_execution_enabled_is_blocker(self):
        settings = SandboxV2Settings(container_execution_enabled=True)
        blockers = settings.production_blockers()
        assert any("container_execution" in b for b in blockers)

    def test_user_command_execution_is_blocker(self):
        settings = SandboxV2Settings(user_command_execution=True)
        blockers = settings.production_blockers()
        assert any("user_command_execution" in b for b in blockers)

    def test_user_image_execution_is_blocker(self):
        settings = SandboxV2Settings(user_image_execution=True)
        blockers = settings.production_blockers()
        assert any("user_image_execution" in b for b in blockers)

    def test_arbitrary_pid_kill_is_blocker(self):
        settings = SandboxV2Settings(arbitrary_pid_kill=True)
        blockers = settings.production_blockers()
        assert any("arbitrary_pid_kill" in b for b in blockers)

    def test_auto_pull_images_is_blocker(self):
        settings = SandboxV2Settings(auto_pull_images=True)
        blockers = settings.production_blockers()
        assert any("auto_pull_images" in b for b in blockers)

    def test_package_download_enabled_is_blocker(self):
        settings = SandboxV2Settings(package_download_enabled=True)
        blockers = settings.production_blockers()
        assert any("package_download" in b for b in blockers)

    def test_public_registry_enabled_is_blocker(self):
        settings = SandboxV2Settings(public_registry_enabled=True)
        blockers = settings.production_blockers()
        assert any("public_registry" in b for b in blockers)


# ═══════════════════════════════════════════════════════════════════════════
# 4. warnings() 方法
# ═══════════════════════════════════════════════════════════════════════════

class TestWarnings:
    """warnings() 正确处理非阻塞警告。"""

    def test_default_warns_about_sqlite_database(self):
        settings = SandboxV2Settings()
        warns = settings.warnings()
        assert any("Database" in w for w in warns)

    def test_default_warns_about_sqlite_queue(self):
        settings = SandboxV2Settings()
        warns = settings.warnings()
        assert any("Queue" in w for w in warns)

    def test_default_warns_about_local_object_storage(self):
        settings = SandboxV2Settings()
        warns = settings.warnings()
        assert any("local" in w.lower() for w in warns)

    def test_postgres_backend_no_warn_about_sqlite(self):
        settings = SandboxV2Settings(database_backend="postgres")
        warns = settings.warnings()
        assert not any("Database" in w for w in warns)

    def test_redis_backend_no_warn_about_sqlite_queue(self):
        settings = SandboxV2Settings(queue_backend="redis")
        warns = settings.warnings()
        assert not any("Queue" in w for w in warns)

    def test_redis_url_configured(self):
        settings = SandboxV2Settings(redis_url="redis://localhost:6379/0")
        warns = settings.warnings()
        assert not any("REDIS_URL" in w for w in warns)

    def test_hash_not_required_warns(self):
        settings = SandboxV2Settings(require_package_hash=False)
        warns = settings.warnings()
        assert any("require_package_hash" in w for w in warns)

    def test_signature_not_required_warns(self):
        settings = SandboxV2Settings(require_package_signature=False)
        warns = settings.warnings()
        assert any("require_package_signature" in w for w in warns)

    def test_sbom_not_required_warns(self):
        settings = SandboxV2Settings(require_sbom=False)
        warns = settings.warnings()
        assert any("require_sbom" in w for w in warns)


# ═══════════════════════════════════════════════════════════════════════════
# 5. 环境变量读取
# ═══════════════════════════════════════════════════════════════════════════

class TestEnvVarReading:
    """load_sandbox_v2_settings() 正确从环境变量读取。"""

    def test_env_bool_true(self, monkeypatch):
        monkeypatch.setenv("SANDBOX_V2_TEST_BOOL", "true")
        result = _env_bool("SANDBOX_V2_TEST_BOOL", False)
        assert result is True

    def test_env_bool_false(self, monkeypatch):
        monkeypatch.setenv("SANDBOX_V2_TEST_BOOL", "false")
        result = _env_bool("SANDBOX_V2_TEST_BOOL", True)
        assert result is False

    def test_env_bool_1(self, monkeypatch):
        monkeypatch.setenv("SANDBOX_V2_TEST_BOOL", "1")
        result = _env_bool("SANDBOX_V2_TEST_BOOL", False)
        assert result is True

    def test_env_bool_0(self, monkeypatch):
        monkeypatch.setenv("SANDBOX_V2_TEST_BOOL", "0")
        result = _env_bool("SANDBOX_V2_TEST_BOOL", True)
        assert result is False

    def test_env_bool_yes_no(self, monkeypatch):
        monkeypatch.setenv("SANDBOX_V2_TEST_BOOL", "yes")
        assert _env_bool("SANDBOX_V2_TEST_BOOL", False) is True
        monkeypatch.setenv("SANDBOX_V2_TEST_BOOL", "no")
        assert _env_bool("SANDBOX_V2_TEST_BOOL", True) is False

    def test_env_bool_missing_returns_default(self):
        result = _env_bool("SANDBOX_V2_NONEXISTENT_VAR_12345", True)
        assert result is True
        result = _env_bool("SANDBOX_V2_NONEXISTENT_VAR_12345", False)
        assert result is False

    def test_env_bool_invalid_returns_default(self, monkeypatch):
        monkeypatch.setenv("SANDBOX_V2_TEST_BOOL", "garbage")
        result = _env_bool("SANDBOX_V2_TEST_BOOL", False)
        assert result is False

    def test_env_int_valid(self, monkeypatch):
        monkeypatch.setenv("SANDBOX_V2_TEST_INT", "42")
        result = _env_int("SANDBOX_V2_TEST_INT", 0)
        assert result == 42

    def test_env_int_missing_returns_default(self):
        result = _env_int("SANDBOX_V2_NONEXISTENT_INT", 100)
        assert result == 100

    def test_env_int_invalid_returns_default(self, monkeypatch):
        monkeypatch.setenv("SANDBOX_V2_TEST_INT", "not_a_number")
        result = _env_int("SANDBOX_V2_TEST_INT", 100)
        assert result == 100

    def test_env_list_comma_separated(self, monkeypatch):
        monkeypatch.setenv("SANDBOX_V2_TEST_LIST", "a,b,c")
        result = _env_list("SANDBOX_V2_TEST_LIST")
        assert result == ["a", "b", "c"]

    def test_env_list_spaces(self, monkeypatch):
        monkeypatch.setenv("SANDBOX_V2_TEST_LIST", "a, b , c")
        result = _env_list("SANDBOX_V2_TEST_LIST")
        assert result == ["a", "b", "c"]

    def test_env_list_empty(self):
        result = _env_list("SANDBOX_V2_NONEXISTENT_LIST")
        assert result == []

    def test_env_list_with_default(self):
        result = _env_list("SANDBOX_V2_NONEXISTENT_LIST", default=["x"])
        assert result == ["x"]

    def test_env_str_valid(self, monkeypatch):
        monkeypatch.setenv("SANDBOX_V2_TEST_STR", "hello")
        result = _env_str("SANDBOX_V2_TEST_STR", "default")
        assert result == "hello"

    def test_env_str_missing_returns_default(self):
        result = _env_str("SANDBOX_V2_NONEXISTENT_STR", "default_val")
        assert result == "default_val"


# ═══════════════════════════════════════════════════════════════════════════
# 6. 配置对象字段访问
# ═══════════════════════════════════════════════════════════════════════════

class TestSettingsFields:
    """SandboxV2Settings 所有字段可正常访问。"""

    def test_all_core_fields_accessible(self):
        settings = SandboxV2Settings()
        assert settings.enabled is True
        assert settings.mode == "simulation"
        assert settings.default_action == "deny"
        assert settings.fail_closed is True

    def test_all_artifact_fields_accessible(self):
        settings = SandboxV2Settings()
        assert settings.artifact_root == ".sandbox_v2_artifacts"
        assert settings.max_artifact_bytes == 1_048_576
        assert settings.max_job_artifact_bytes == 10_485_760
        assert settings.read_only_artifacts is True

    def test_all_package_fields_accessible(self):
        settings = SandboxV2Settings()
        assert settings.package_quarantine_root == ".sandbox_v2_package_quarantine"
        assert settings.package_download_enabled is False
        assert settings.require_package_hash is True
        assert settings.require_package_signature is True
        assert settings.require_sbom is True

    def test_all_network_fields_accessible(self):
        settings = SandboxV2Settings()
        assert settings.network_enabled is False
        assert settings.network_preflight_only is True
        assert settings.block_private_networks is True
        assert settings.block_metadata_service is True
        assert "localhost" in settings.denied_domains
        assert "127.0.0.1" in settings.denied_domains
        assert "169.254.169.254" in settings.denied_domains

    def test_all_container_fields_accessible(self):
        settings = SandboxV2Settings()
        assert settings.container_execution_enabled is False
        assert settings.auto_pull_images is False
        assert settings.user_command_execution is False
        assert settings.user_image_execution is False
        assert "python:3.11-alpine" in settings.allowed_images
        assert "busybox:latest" in settings.allowed_images

    def test_all_queue_fields_accessible(self):
        settings = SandboxV2Settings()
        assert settings.queue_backend == "sqlite"
        assert settings.worker_enabled is True
        assert settings.worker_max_attempts == 3
        assert settings.worker_lease_seconds == 60

    def test_future_backend_fields_accessible(self):
        settings = SandboxV2Settings()
        assert settings.database_backend == "sqlite"
        assert settings.redis_url == ""
        assert settings.object_storage_backend == "local"
        assert settings.minio_endpoint == ""
        assert settings.s3_bucket == "sandbox-v2-artifacts"


# ═══════════════════════════════════════════════════════════════════════════
# 7. recommended_next_steps
# ═══════════════════════════════════════════════════════════════════════════

class TestRecommendedNextSteps:
    """recommended_next_steps() 输出合理的建议。"""

    def test_default_returns_steps(self):
        settings = SandboxV2Settings()
        steps = settings.recommended_next_steps()
        assert len(steps) > 0
        assert any("PostgreSQL" in s or "Redis" in s or "MinIO" in s for s in steps)

    def test_includes_readiness_script(self):
        settings = SandboxV2Settings()
        steps = settings.recommended_next_steps()
        assert any("readiness" in s.lower() for s in steps)


# ═══════════════════════════════════════════════════════════════════════════
# 8. load_sandbox_v2_settings() 返回正确类型
# ═══════════════════════════════════════════════════════════════════════════

class TestLoadSettings:
    """load_sandbox_v2_settings() 返回 SandboxV2Settings 实例。"""

    def test_returns_sandbox_v2_settings_instance(self):
        settings = load_sandbox_v2_settings()
        assert isinstance(settings, SandboxV2Settings)

    def test_has_is_safe_default_method(self):
        settings = load_sandbox_v2_settings()
        assert callable(settings.is_safe_default)
        result = settings.is_safe_default()
        assert isinstance(result, bool)
