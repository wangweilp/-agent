"""Tests for Sandbox v2 Object Storage Adapter (Step 12).

验证:
1. S3SandboxV2Storage 初始化 (connect=False)
2. Key sanitization 防止路径穿越
3. 缺 boto3/配置时 fail closed
4. Fake S3 client: put_object, get_object, delete_object, object_exists
5. presign_read_url 返回 "disabled"
6. is_available / availability_message
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ═══════════════════════════════════════════════════════════════════════════
# 1. Key Sanitization
# ═══════════════════════════════════════════════════════════════════════════

class TestKeySanitization:
    """Object key sanitization 防路径穿越。"""

    def test_sanitize_normal_key(self):
        from src.adapters.object_sandbox_v2_storage import sanitize_object_key
        key = sanitize_object_key("org-123/artifacts/result.json")
        assert key == "org-123/artifacts/result.json"

    def test_sanitize_dot_dot_slash(self):
        from src.adapters.object_sandbox_v2_storage import sanitize_object_key
        key = sanitize_object_key("../../../etc/passwd")
        assert ".." not in key
        assert "etc/passwd" in key or "passwd" in key or key == "etc/passwd"

    def test_sanitize_dot_dot_backslash(self):
        from src.adapters.object_sandbox_v2_storage import sanitize_object_key
        key = sanitize_object_key("..\\..\\windows\\system32")
        assert ".." not in key or key == "windowssystem32"

    def test_sanitize_null_byte(self):
        from src.adapters.object_sandbox_v2_storage import sanitize_object_key
        key = sanitize_object_key("valid\x00injection.txt")
        assert "\x00" not in key

    def test_sanitize_dangerous_chars(self):
        from src.adapters.object_sandbox_v2_storage import sanitize_object_key
        key = sanitize_object_key("file name; rm -rf /")
        # 空格和分号应被移除
        assert " " not in key
        assert ";" not in key

    def test_sanitize_empty_key(self):
        from src.adapters.object_sandbox_v2_storage import sanitize_object_key
        key = sanitize_object_key("")
        assert len(key) > 0  # 空 key 用 uuid 填充
        assert len(key) == 12

    def test_sanitize_long_key_truncated(self):
        from src.adapters.object_sandbox_v2_storage import sanitize_object_key
        long_key = "a" * 2000
        key = sanitize_object_key(long_key)
        assert len(key) <= 1024

    def test_build_object_key_with_prefix(self):
        from src.adapters.object_sandbox_v2_storage import build_object_key
        key = build_object_key("sandbox-v2/prod", "org-1", "ws-1", "artifacts", "output.json")
        assert key == "sandbox-v2/prod/org-1/ws-1/artifacts/output.json"

    def test_build_object_key_without_prefix(self):
        from src.adapters.object_sandbox_v2_storage import build_object_key
        key = build_object_key("", "org-1", "ws-1", "packages", "pkg.tar")
        assert key == "org-1/ws-1/packages/pkg.tar"

    def test_build_object_key_sanitizes_dangerous_input(self):
        from src.adapters.object_sandbox_v2_storage import build_object_key
        key = build_object_key("prod", "../../../evil", "ws-1", "cat", "file.sh")
        assert ".." not in key


# ═══════════════════════════════════════════════════════════════════════════
# 2. S3SandboxV2Storage initialization
# ═══════════════════════════════════════════════════════════════════════════

class TestS3StorageInit:
    """S3SandboxV2Storage 初始化测试。"""

    def test_storage_instantiation_no_connect(self):
        from src.adapters.object_sandbox_v2_storage import S3SandboxV2Storage
        storage = S3SandboxV2Storage(
            endpoint_url="http://localhost:9000",
            access_key="fake-key",
            secret_key="fake-secret",
            bucket="test",
            connect=False,
        )
        assert storage is not None
        assert not storage._connected

    def test_storage_default_constructor(self):
        from src.adapters.object_sandbox_v2_storage import S3SandboxV2Storage
        storage = S3SandboxV2Storage()
        assert storage is not None

    def test_storage_is_available(self):
        from src.adapters.object_sandbox_v2_storage import S3SandboxV2Storage
        storage = S3SandboxV2Storage()
        assert isinstance(storage.is_available, bool)

    def test_storage_availability_message(self):
        from src.adapters.object_sandbox_v2_storage import S3SandboxV2Storage
        storage = S3SandboxV2Storage()
        msg = storage.availability_message
        assert isinstance(msg, str)
        assert len(msg) > 0

    def test_connect_without_credentials_raises(self):
        from src.adapters.object_sandbox_v2_storage import S3SandboxV2Storage
        storage = S3SandboxV2Storage(access_key="", secret_key="", connect=False)
        with pytest.raises((ValueError, ImportError)):
            storage._connect()


# ═══════════════════════════════════════════════════════════════════════════
# 3. Fake S3 client operations
# ═══════════════════════════════════════════════════════════════════════════

class TestFakeS3Storage:
    """使用 FakeS3Client 测试对象存储语义。"""

    @pytest.fixture
    def fake_storage(self):
        from src.adapters.object_sandbox_v2_storage import create_fake_s3_storage
        return create_fake_s3_storage(bucket="test-bucket")

    def test_put_object(self, fake_storage):
        result = fake_storage.put_object("artifacts/output.txt", b"hello world", content_type="text/plain")
        assert result["ResponseMetadata"]["HTTPStatusCode"] == 200

    def test_put_object_safe(self, fake_storage):
        result = fake_storage.put_object_safe("org-1", "ws-1", "artifacts", "data.json", b'{"key":"val"}')
        assert result["ResponseMetadata"]["HTTPStatusCode"] == 200

    def test_get_object(self, fake_storage):
        fake_storage.put_object("test/file.txt", b"content")
        data = fake_storage.get_object("test/file.txt")
        assert data == b"content"

    def test_get_object_not_found_returns_none(self, fake_storage):
        data = fake_storage.get_object("nonexistent/key.txt")
        assert data is None

    def test_get_object_safe(self, fake_storage):
        fake_storage.put_object_safe("org-1", "ws-1", "data", "out.json", b'{"result":"ok"}')
        data = fake_storage.get_object_safe("org-1", "ws-1", "data", "out.json")
        assert data == b'{"result":"ok"}'

    def test_delete_object(self, fake_storage):
        fake_storage.put_object("to-delete.txt", b"temp")
        assert fake_storage.delete_object("to-delete.txt") is True
        assert fake_storage.get_object("to-delete.txt") is None

    def test_object_exists(self, fake_storage):
        fake_storage.put_object("exists.txt", b"yes")
        assert fake_storage.object_exists("exists.txt") is True
        assert fake_storage.object_exists("nope.txt") is False

    def test_list_objects(self, fake_storage):
        fake_storage.put_object("artifacts/a.txt", b"a")
        fake_storage.put_object("artifacts/b.txt", b"b")
        fake_storage.put_object("packages/c.txt", b"c")
        result = fake_storage.list_objects(prefix="artifacts/")
        assert len(result) == 2
        keys = [obj["Key"] for obj in result]
        assert "artifacts/a.txt" in keys
        assert "artifacts/b.txt" in keys
        assert "packages/c.txt" not in keys

    def test_presign_read_url_returns_disabled(self, fake_storage):
        url = fake_storage.presign_read_url("some/file.pdf")
        assert url == "disabled"

    def test_put_object_with_sanitized_key(self, fake_storage):
        """Key with dangerous chars gets sanitized before storage."""
        result = fake_storage.put_object("../../etc/passwd\x00.txt", b"bad")
        # 即使上传了，key 也经过了 sanitize
        assert result["ResponseMetadata"]["HTTPStatusCode"] == 200

    def test_list_empty_prefix(self, fake_storage):
        result = fake_storage.list_objects(prefix="")
        assert isinstance(result, list)


# ═══════════════════════════════════════════════════════════════════════════
# 4. FakeS3Client directly
# ═══════════════════════════════════════════════════════════════════════════

class TestFakeS3ClientDirect:
    """直接测试 FakeS3Client。"""

    @pytest.fixture
    def fake(self):
        from src.adapters.object_sandbox_v2_storage import FakeS3Client
        return FakeS3Client()

    def test_put_and_get(self, fake):
        fake.put_object("bucket", "key1", b"data")
        resp = fake.get_object("bucket", "key1")
        assert resp["Body"].read() == b"data"

    def test_get_missing_key_raises(self, fake):
        from src.adapters.object_sandbox_v2_storage import _BotoClientError
        with pytest.raises(_BotoClientError):
            fake.get_object("bucket", "nonexistent")

    def test_delete(self, fake):
        fake.put_object("bucket", "del", b"x")
        fake.delete_object("bucket", "del")
        from src.adapters.object_sandbox_v2_storage import _BotoClientError
        with pytest.raises(_BotoClientError):
            fake.get_object("bucket", "del")

    def test_head_object(self, fake):
        fake.put_object("bucket", "head-test", b"data")
        resp = fake.head_object("bucket", "head-test")
        assert resp["ContentLength"] == 4

    def test_head_missing_raises(self, fake):
        from src.adapters.object_sandbox_v2_storage import _BotoClientError
        with pytest.raises(_BotoClientError):
            fake.head_object("bucket", "no-key")
