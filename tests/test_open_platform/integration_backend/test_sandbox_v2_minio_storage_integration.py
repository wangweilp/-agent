"""MinIO / S3 storage integration tests (Step 13). Default SKIP.

Only run when:
  SANDBOX_V2_RUN_BACKEND_INTEGRATION=true
  SANDBOX_V2_OBJECT_STORAGE_BACKEND=minio or s3
  Credentials configured
"""

import os
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

_RUNNING = os.environ.get("SANDBOX_V2_RUN_BACKEND_INTEGRATION", "").lower() in ("true", "1", "yes")
_OS_BACKEND = os.environ.get("SANDBOX_V2_OBJECT_STORAGE_BACKEND", "local")
_AK = os.environ.get("SANDBOX_V2_MINIO_ACCESS_KEY", "") or os.environ.get("SANDBOX_V2_S3_ACCESS_KEY", "")

pytestmark = pytest.mark.skipif(
    not (_RUNNING and _OS_BACKEND in ("minio", "s3") and _AK),
    reason="Requires SANDBOX_V2_RUN_BACKEND_INTEGRATION=true + object_storage_backend=minio/s3 + credentials",
)

_PREFIX = f"sandbox-v2-integration-tests/{__import__('uuid').uuid4().hex[:8]}"


@pytest.fixture(scope="module")
def storage():
    from src.adapters.object_sandbox_v2_storage import S3SandboxV2Storage
    endpoint = os.environ.get("SANDBOX_V2_MINIO_ENDPOINT", "")
    ak = os.environ.get("SANDBOX_V2_MINIO_ACCESS_KEY", "") or os.environ.get("SANDBOX_V2_S3_ACCESS_KEY", "")
    sk = os.environ.get("SANDBOX_V2_MINIO_SECRET_KEY", "") or os.environ.get("SANDBOX_V2_S3_SECRET_KEY", "")
    bucket = os.environ.get("SANDBOX_V2_MINIO_BUCKET", "") or os.environ.get("SANDBOX_V2_S3_BUCKET", "sandbox-v2-artifacts")
    region = os.environ.get("SANDBOX_V2_S3_REGION", "us-east-1")

    s = S3SandboxV2Storage(
        endpoint_url=endpoint, access_key=ak, secret_key=sk,
        bucket=bucket, region=region, prefix=_PREFIX, connect=True,
    )

    # Ensure bucket
    s.ensure_bucket_exists()

    yield s

    # Cleanup test objects
    try:
        objs = s.list_objects(prefix=_PREFIX, max_keys=100)
        for obj in objs:
            s.delete_object(obj.get("Key", ""))
    except Exception:
        pass


class TestMinIOHealth:
    def test_health_check(self, storage):
        hc = storage.health_check()
        assert hc["ok"], f"Health check failed: {hc}"


class TestMinIOBasicOps:
    def test_put_object(self, storage):
        key = f"{_PREFIX}/test-put.txt"
        result = storage.put_object(key, b"integration test", content_type="text/plain")
        assert result["ResponseMetadata"]["HTTPStatusCode"] == 200

    def test_get_object(self, storage):
        key = f"{_PREFIX}/test-get.txt"
        storage.put_object(key, b"hello integration")
        data = storage.get_object(key)
        assert data == b"hello integration"

    def test_object_exists(self, storage):
        key = f"{_PREFIX}/test-exists.txt"
        storage.put_object(key, b"data")
        assert storage.object_exists(key) is True
        assert storage.object_exists(f"{_PREFIX}/no-exist.txt") is False

    def test_list_objects(self, storage):
        storage.put_object(f"{_PREFIX}/list/a.txt", b"a")
        storage.put_object(f"{_PREFIX}/list/b.txt", b"b")
        result = storage.list_objects(prefix=f"{_PREFIX}/list/")
        assert len(result) >= 2

    def test_delete_object(self, storage):
        key = f"{_PREFIX}/test-del.txt"
        storage.put_object(key, b"temp")
        assert storage.delete_object(key) is True
        assert storage.get_object(key) is None


class TestMinIOSecurity:
    def test_path_traversal_key_sanitized(self, storage):
        result = storage.put_object("../../../etc/passwd\x00.txt", b"bad")
        assert result["ResponseMetadata"]["HTTPStatusCode"] == 200
        # 获取时应经过 sanitize，不应访问到 etc
        data = storage.get_object("../../../etc/passwd.txt")
        assert data is None

    def test_access_key_not_in_error(self):
        from src.adapters.object_sandbox_v2_storage import S3SandboxV2Storage
        ak = os.environ.get("SANDBOX_V2_MINIO_ACCESS_KEY", "") or os.environ.get("SANDBOX_V2_S3_ACCESS_KEY", "")
        st = S3SandboxV2Storage(access_key="secret-key-123", secret_key="pw", bucket="test", connect=False)
        hc = st.health_check()
        assert "secret-key-123" not in str(hc)

    def test_get_nonexistent_returns_none(self, storage):
        data = storage.get_object(f"{_PREFIX}/definitely-not-exist-99999.txt")
        assert data is None
