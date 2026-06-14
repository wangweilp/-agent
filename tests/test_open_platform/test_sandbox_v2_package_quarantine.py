"""Test Sandbox v2 Package Quarantine — 包隔离存储测试。"""
import pytest
import tempfile
import os
import shutil
import hashlib
from src.open_platform.sandbox_v2.packages import LocalSandboxPackageQuarantineStore
from src.open_platform.sandbox_v2.models import SandboxV2PackageQuarantineStatus


@pytest.fixture
def store():
    root = tempfile.mkdtemp(prefix="sbx_pkg_test_")
    s = LocalSandboxPackageQuarantineStore(quarantine_root=root)
    yield s
    try: shutil.rmtree(root)
    except: pass


class TestQuarantine:
    def test_quarantine_bytes_success(self, store):
        content = b"package content 12345"
        record, err = store.quarantine_package_bytes(
            content=content, original_filename="test.pkg",
            package_name="test-pkg", package_manager="pip",
        )
        assert err == ""
        assert record is not None
        assert record.status == SandboxV2PackageQuarantineStatus.QUARANTINED
        assert record.size_bytes == len(content)

    def test_sha256_correct(self, store):
        content = b"hash test content"
        record, _ = store.quarantine_package_bytes(content=content, original_filename="hash.pkg")
        expected = hashlib.sha256(content).hexdigest()
        assert record.sha256 == expected

    def test_expected_hash_mismatch(self, store):
        record, err = store.quarantine_package_bytes(
            content=b"data", original_filename="p.pkg", expected_sha256="deadbeef" * 8,
        )
        assert record is None
        assert "mismatch" in err.lower()

    def test_expected_hash_match(self, store):
        content = b"match data"
        expected = hashlib.sha256(content).hexdigest()
        record, err = store.quarantine_package_bytes(
            content=content, original_filename="m.pkg", expected_sha256=expected,
        )
        assert record is not None
        assert record.sha256 == expected

    def test_read_back(self, store):
        content = b"read back test"
        record, _ = store.quarantine_package_bytes(content=content, original_filename="rb.pkg")
        read_bytes = store.read_quarantined_bytes(record.storage_key)
        assert read_bytes == content

    def test_path_traversal_rejected(self, store):
        with pytest.raises(ValueError):
            store._resolve_in_root("../../../etc/passwd")

    def test_absolute_path_rejected(self, store):
        with pytest.raises(ValueError):
            store._resolve_in_root("/etc/passwd")

    def test_delete_file(self, store):
        content = b"to delete"
        record, _ = store.quarantine_package_bytes(content=content, original_filename="del.pkg")
        assert store.delete_quarantined_file(record.storage_key) is True

    def test_size_limit_exceeded(self, store):
        big = b"x" * 11_000_000  # 11 MB > 10 MB default
        record, err = store.quarantine_package_bytes(content=big, original_filename="big.pkg")
        assert record is None
        assert "exceeds" in err.lower()
