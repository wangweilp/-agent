"""Test Sandbox v2 Artifact Store — 本地 artifact 存储测试。

覆盖：
1. 物化后文件为 read_only
2. artifact 写入后 sha256 正确
3. 读和写/删除路径在 root 内
4. manifest 生成包含 artifact_ids
5. 路径穿越防护
"""
import pytest
import tempfile
import os
import hashlib
import pathlib

from src.open_platform.sandbox_v2.artifacts import LocalSandboxArtifactStore
from src.open_platform.sandbox_v2.models import (
    SandboxV2ArtifactType,
    SandboxV2ArtifactStatus,
)


@pytest.fixture
def store():
    """创建临时 artifact store。"""
    root = tempfile.mkdtemp(prefix="sbx_art_test_")
    s = LocalSandboxArtifactStore(artifact_root=root)
    yield s
    import shutil
    try:
        shutil.rmtree(root)
    except Exception:
        pass


class TestCreateArtifact:
    def test_basic_text_artifact(self, store):
        """正常 text artifact 可以物化。"""
        art = store.create_artifact(
            job_id="job-test-1",
            artifact_type=SandboxV2ArtifactType.TEXT,
            name="test.txt",
            content_text="hello sandbox artifact",
        )
        assert art.status == SandboxV2ArtifactStatus.MATERIALIZED
        assert art.size_bytes > 0
        assert art.sha256
        assert art.read_only is True

    def test_artifact_write_and_read(self, store):
        """写入后读取内容一致。"""
        content = b"binary test data 12345"
        art = store.create_artifact(
            job_id="job-rw",
            artifact_type=SandboxV2ArtifactType.OUTPUT,
            name="data.bin",
            content=content,
            mime_type="application/octet-stream",
        )
        read_bytes = store.read_artifact(art.storage_key)
        assert read_bytes == content

    def test_sha256_correct(self, store):
        """sha256 计算正确。"""
        content = b"verify sha256 hash"
        art = store.create_artifact(
            job_id="job-hash",
            artifact_type=SandboxV2ArtifactType.TEXT,
            name="hash.txt",
            content=content,
        )
        expected = hashlib.sha256(content).hexdigest()
        assert art.sha256 == expected
        assert store.verify_sha256(art.storage_key, expected) is True

    def test_json_artifact(self, store):
        """JSON artifact 可以物化。"""
        art = store.create_artifact(
            job_id="job-json",
            artifact_type=SandboxV2ArtifactType.JSON,
            name="data.json",
            content_text='{"key": "value"}',
            mime_type="application/json",
        )
        assert art.status == SandboxV2ArtifactStatus.MATERIALIZED
        assert art.mime_type == "application/json"

    def test_read_text(self, store):
        """read_artifact_text 返回文本。"""
        art = store.create_artifact(
            job_id="job-txt",
            artifact_type=SandboxV2ArtifactType.LOG,
            name="simulation.log",
            content_text="line1\nline2\nline3",
        )
        text = store.read_artifact_text(art.storage_key)
        assert "line1" in text

    def test_truncation(self, store):
        """大内容截断显示。"""
        content = "a" * 5000
        art = store.create_artifact(
            job_id="job-trunc",
            artifact_type=SandboxV2ArtifactType.TEXT,
            name="large.txt",
            content_text=content,
        )
        text = store.read_artifact_text(art.storage_key, max_bytes=100)
        assert len(text) < 5000
        assert "[truncated" in text.lower() or len(text) <= 200


class TestDeleteArtifact:
    def test_delete_removes_file(self, store):
        """删除 artifact 后文件不存在。"""
        art = store.create_artifact(
            job_id="job-del",
            artifact_type=SandboxV2ArtifactType.TEXT,
            name="to_delete.txt",
            content_text="delete me",
        )
        deleted = store.delete_artifact_file(art.storage_key)
        assert deleted is True

    def test_delete_resolves_in_root(self, store):
        """路径穿越的 storage_key 不会被删除。"""
        with pytest.raises(ValueError):
            store._resolve_in_root("../../../outside.txt")


class TestPathIsolation:
    def test_resolve_inside_root(self, store):
        """resolve 确保在 root 内。"""
        # Normal path should work
        p = store._resolve_in_root("org-1/ws-1/job-1/art-1/file")
        assert str(store.root_path) in str(p)

    def test_path_traversal_rejected(self, store):
        """路径穿越被 resolve 拒绝。"""
        with pytest.raises(ValueError):
            store._resolve_in_root("../../../etc/passwd")


class TestManifest:
    def test_manifest_creation(self, store):
        """manifest 包含 artifact_ids。"""
        art1 = store.create_artifact(
            job_id="job-mft", artifact_type=SandboxV2ArtifactType.LOG,
            name="log1.txt", content_text="log data",
        )
        art2 = store.create_artifact(
            job_id="job-mft", artifact_type=SandboxV2ArtifactType.JSON,
            name="result.json", content_text='{"ok":true}',
        )
        manifest = store.create_manifest("job-mft", "rec-mft", [art1, art2])
        assert manifest.artifact_count == 2
        assert art1.artifact_id in manifest.artifact_ids
        assert art2.artifact_id in manifest.artifact_ids
        assert manifest.sealed is True
        assert len(manifest.sha256) == 64
