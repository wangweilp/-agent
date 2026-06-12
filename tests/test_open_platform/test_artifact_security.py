"""Artifact Sandbox 安全测试。

验证：
1. 禁止 execution / subprocess / docker / container / microVM
2. 禁止 runtime
3. 禁止 network
4. 禁止 filesystem write
5. execution_allowed 永远 False
6. runtime_enabled 永远 False
7. metadata_only 永远 True
8. 所有通过 store/service 的 artifact 都无法执行

这是 Artifact Sandbox，不是 Runtime Sandbox。
"""

from __future__ import annotations

import os
import tempfile

import pytest

os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")

from src.adapters.config import Settings
from src.adapters.artifact_store import SQLiteArtifactStore
from src.open_platform.artifact_service import ArtifactService
from src.open_platform.artifact import (
    Artifact,
    ArtifactStatus,
    ArtifactType,
)


@pytest.fixture
def settings():
    return Settings(deepseek_api_key="sk-test")


@pytest.fixture
def tmp_db_path():
    d = tempfile.mkdtemp()
    path = os.path.join(d, "test_security.db")
    yield path
    import shutil
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def store(settings, tmp_db_path):
    return SQLiteArtifactStore(settings, db_path=tmp_db_path)


@pytest.fixture
def service(store):
    return ArtifactService(store)


# ═══════════════════════════════════════════
# 禁止执行
# ═══════════════════════════════════════════


class TestNoExecution:
    """禁止 execution。"""

    def test_domain_no_execution_method(self):
        """Artifact domain 不应包含执行方法。"""
        forbidden = [
            "execute", "run", "exec", "spawn", "launch",
            "start", "stop", "restart", "kill", "subprocess",
            "call", "invoke", "shell",
        ]
        for name in forbidden:
            assert not hasattr(Artifact, name), f"Artifact 不应有 {name} 方法"

    def test_service_no_execution_method(self):
        """ArtifactService 不应包含执行方法。"""
        forbidden = [
            "execute", "run", "exec", "spawn", "launch",
            "start_container", "create_container", "start_microvm",
            "subprocess", "shell",
        ]
        for name in forbidden:
            assert not hasattr(ArtifactService, name), \
                f"ArtifactService 不应有 {name} 方法"

    def test_store_no_execution_method(self):
        """ArtifactStore 不应包含执行方法。"""
        forbidden = [
            "execute", "run", "exec", "spawn", "launch",
            "start_container", "create_container", "start_microvm",
            "subprocess", "shell",
        ]
        for name in forbidden:
            assert not hasattr(SQLiteArtifactStore, name), \
                f"SQLiteArtifactStore 不应有 {name} 方法"

    def test_store_no_runtime_import(self):
        """Store 不应导入 runtime/container/microVM 相关模块。"""
        import inspect
        source = inspect.getsource(SQLiteArtifactStore)
        forbidden_patterns = [
            "subprocess", "docker", "container", "microvm",
            "podman", "kubernetes", "lxc", "firecracker",
            "os.system", "os.popen", "shell=True",
        ]
        for pattern in forbidden_patterns:
            assert pattern not in source.lower(), \
                f"SQLiteArtifactStore 源码不应包含 {pattern}"


# ═══════════════════════════════════════════
# 安全约束
# ═══════════════════════════════════════════


class TestSafetyConstraints:
    """安全硬约束。"""

    def test_execution_allowed_always_false(self, store):
        """所有 artifact 的 execution_allowed 永远是 False。"""
        for at in ArtifactType:
            a = Artifact(workspace_id="ws", agent_id="a", title="T",
                         artifact_type=at.value)
            created = store.create(a)
            for status in [ArtifactStatus.REVIEW, ArtifactStatus.APPROVED,
                           ArtifactStatus.PUBLISHED, ArtifactStatus.REJECTED]:
                if can_migrate(created.status, status):
                    store.update_status(created.id, status)
                    created = store.get(created.id)

            fetched = store.get(created.id)
            assert fetched.execution_allowed is False, \
                f"artifact_type={at.value} 的 execution_allowed 应为 False"

    def test_runtime_enabled_always_false(self, store):
        """所有 artifact 的 runtime_enabled 永远是 False。"""
        for at in ArtifactType:
            a = Artifact(workspace_id="ws", agent_id="a", title="T",
                         artifact_type=at.value)
            created = store.create(a)
            for status in [ArtifactStatus.REVIEW, ArtifactStatus.APPROVED,
                           ArtifactStatus.PUBLISHED, ArtifactStatus.REJECTED]:
                if can_migrate(created.status, status):
                    store.update_status(created.id, status)
                    created = store.get(created.id)

            fetched = store.get(created.id)
            assert fetched.runtime_enabled is False

    def test_metadata_only_always_true(self, store):
        """所有 artifact 的 metadata_only 永远是 True。"""
        for at in ArtifactType:
            a = Artifact(workspace_id="ws", agent_id="a", title="T",
                         artifact_type=at.value)
            created = store.create(a)
            assert created.metadata_only is True

            fetched = store.get(created.id)
            assert fetched.metadata_only is True

    def test_validate_enforces_safety(self):
        """validate() 强制校验安全约束。"""
        a = Artifact(workspace_id="ws", agent_id="a", title="T")
        a.execution_allowed = True
        errors = a.validate()
        assert any("execution_allowed" in e for e in errors)

        a.execution_allowed = False
        a.runtime_enabled = True
        errors = a.validate()
        assert any("runtime_enabled" in e for e in errors)

        a.runtime_enabled = False
        a.metadata_only = False
        errors = a.validate()
        assert any("metadata_only" in e for e in errors)

    def test_create_always_resets_safety(self, store):
        """即使传入时为 True，create 也会强制重置。"""
        a = Artifact(workspace_id="ws", agent_id="a", title="T")
        a.execution_allowed = True
        a.runtime_enabled = True
        a.metadata_only = False
        created = store.create(a)
        assert created.execution_allowed is False
        assert created.runtime_enabled is False
        assert created.metadata_only is True

    def test_from_dict_always_resets_safety(self):
        """from_dict 强制 safety constraints。"""
        d = {
            "workspace_id": "ws",
            "agent_id": "a",
            "title": "T",
            "execution_allowed": True,
            "runtime_enabled": True,
            "metadata_only": False,
        }
        a = Artifact.from_dict(d)
        assert a.execution_allowed is False
        assert a.runtime_enabled is False
        assert a.metadata_only is True


# ═══════════════════════════════════════════
# 禁止网络
# ═══════════════════════════════════════════


class TestNoNetwork:
    """禁止网络访问。"""

    def test_domain_no_network(self):
        """Artifact domain 不包含任何网络相关方法/字段。"""
        import inspect
        source = inspect.getsource(Artifact)
        forbidden = ["requests", "urllib", "http", "socket", "urllib3"]
        for pattern in forbidden:
            # 放宽：artifact_type 是 domain 字段，不涉及网络 import
            assert f"import {pattern}" not in source, \
                f"Artifact domain 不应 import {pattern}"

    def test_service_no_network(self):
        """Service 不包含网络相关代码。"""
        import inspect
        source = inspect.getsource(ArtifactService)
        forbidden = ["requests", "urllib", "http.client"]
        for pattern in forbidden:
            assert f"import {pattern}" not in source, \
                f"ArtifactService 不应 import {pattern}"

    def test_store_no_network(self):
        """Store 不包含网络相关代码。"""
        import inspect
        source = inspect.getsource(SQLiteArtifactStore)
        forbidden = ["requests", "urllib", "http.client", "socket"]
        for pattern in forbidden:
            assert f"import {pattern}" not in source, \
                f"SQLiteArtifactStore 不应 import {pattern}"


# ═══════════════════════════════════════════
# 禁止 filesystem write
# ═══════════════════════════════════════════


class TestNoFilesystemWrite:
    """禁止文件系统写入（除了 SQLite 正常的 DB 写入）。"""

    def test_domain_no_file_write(self):
        """Artifact domain 不写文件。"""
        import inspect
        source = inspect.getsource(Artifact)
        forbidden = ["open(", "write(", "writelines", "shutil"]
        for pattern in forbidden:
            assert pattern not in source, \
                f"Artifact domain 不应包含 {pattern}"

    def test_service_no_file_write(self):
        """Service 不写文件。"""
        import inspect
        source = inspect.getsource(ArtifactService)
        assert "open(" not in source
        assert "write(" not in source

    def test_store_only_uses_db(self):
        """Store 只通过 SQLite 写入，不直接操作文件系统。"""
        import inspect
        source = inspect.getsource(SQLiteArtifactStore)

        # 允许 JSON（序列化用途）和 sqlite3/db 相关
        # 但不应有 open() 直接写文件
        lines = source.split("\n")
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            # 只检查不是 json.loads/json.dumps 的写入操作
            if "open(" in stripped and "sqlite" not in stripped.lower():
                pytest.fail(f"SQLiteArtifactStore 不应直接 open() 文件: {stripped}")


# ═══════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════


def can_migrate(from_status: str, to_status: str) -> bool:
    """检查状态迁移是否可能（用于测试中构建流水线）。"""
    from src.open_platform.artifact import is_valid_transition
    return is_valid_transition(from_status, to_status)
