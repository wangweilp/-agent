"""Sandbox v2 Object Storage Adapter — MinIO / S3 兼容对象存储。

Step 12 — Production Backend Migration.

设计原则:
1. 为 Artifact 和 Package Quarantine 提供可插拔的对象存储后端。
2. 默认使用 local file storage (无变化)。
3. MinIO / S3 通过 boto3 连接。
4. Object key 必须 sanitize，防止路径穿越。
5. 不泄露 access key / secret key。
6. 测试不依赖真实 MinIO/S3。
7. 缺依赖或缺配置时 fail closed。

安全约束:
- 所有 object key 经过 sanitize
- 路径穿越防护
- 不在日志中输出密钥
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
from pathlib import Path
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# Module dependency check
# ═══════════════════════════════════════════════════════════════════════════

_BOTO3_AVAILABLE = False
try:
    import boto3 as _boto3_module
    from botocore.exceptions import ClientError as _BotoClientError
    _BOTO3_AVAILABLE = True
except ImportError:
    _BotoClientError = Exception

_BOTO3_UNAVAILABLE_MSG = (
    "boto3 is not installed. Install with: pip install boto3"
)


def _require_boto3():
    """检查 boto3 是否可用。"""
    if not _BOTO3_AVAILABLE:
        raise ImportError(_BOTO3_UNAVAILABLE_MSG)


# ═══════════════════════════════════════════════════════════════════════════
# Key Sanitization
# ═══════════════════════════════════════════════════════════════════════════

_SAFE_KEY_RE = re.compile(r"[^a-zA-Z0-9._\-/]")
_DANGEROUS_PATTERNS = [
    "..",          # 路径穿越
    "~",           # home dir
    "\x00",        # null byte
]


def sanitize_object_key(key: str) -> str:
    """Sanitize object key。

    规则:
    1. 移除危险字符 (只保留 a-z A-Z 0-9 . _ - /)
    2. 移除连续的 .. 防止路径穿越
    3. 移除空段
    4. 限制长度
    """
    # 移除 null bytes
    key = key.replace("\x00", "")

    # 替换危险模式
    for pattern in _DANGEROUS_PATTERNS:
        key = key.replace(pattern, "")

    # 只保留安全字符
    key = _SAFE_KEY_RE.sub("", key)

    # 移除连续斜杠
    while "//" in key:
        key = key.replace("//", "/")

    # 移除首尾斜杠
    key = key.strip("/")

    # 限制长度
    if len(key) > 1024:
        key = key[:1024]

    # 空 key 用 uuid 填充
    if not key:
        key = uuid4().hex[:12]

    return key


def build_object_key(prefix: str, organization_id: str, workspace_id: str,
                     category: str, filename: str) -> str:
    """构建 sanitized object key。

    格式: {prefix}/{org}/{ws}/{category}/{filename}
    如果 prefix 为空，省略前缀。
    """
    parts = []
    if prefix:
        parts.append(sanitize_object_key(prefix))
    if organization_id:
        parts.append(sanitize_object_key(organization_id))
    if workspace_id:
        parts.append(sanitize_object_key(workspace_id))
    parts.append(sanitize_object_key(category))
    parts.append(sanitize_object_key(filename))
    return "/".join(parts)


# ═══════════════════════════════════════════════════════════════════════════
# Fake In-Memory Object Storage (for testing)
# ═══════════════════════════════════════════════════════════════════════════

class FakeS3Client:
    """Memory-backed fake S3 client for unit testing."""

    def __init__(self):
        self._objects: dict[str, bytes] = {}
        self._metadata: dict[str, dict[str, str]] = {}

    def put_object(self, Bucket: str, Key: str, Body: bytes, **kwargs) -> dict[str, Any]:
        self._objects[Key] = Body if isinstance(Body, bytes) else Body.encode("utf-8")
        self._metadata[Key] = {"Bucket": Bucket, "Key": Key}
        return {"ResponseMetadata": {"HTTPStatusCode": 200}}

    def get_object(self, Bucket: str, Key: str) -> dict[str, Any]:
        if Key not in self._objects:
            raise _BotoClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")
        from io import BytesIO
        return {"Body": BytesIO(self._objects[Key]), "ContentLength": len(self._objects[Key])}

    def delete_object(self, Bucket: str, Key: str) -> dict[str, Any]:
        self._objects.pop(Key, None)
        self._metadata.pop(Key, None)
        return {"ResponseMetadata": {"HTTPStatusCode": 204}}

    def head_object(self, Bucket: str, Key: str) -> dict[str, Any]:
        if Key not in self._objects:
            raise _BotoClientError({"Error": {"Code": "404"}}, "HeadObject")
        return {"ContentLength": len(self._objects[Key])}

    def list_objects_v2(self, Bucket: str, Prefix: str = "", MaxKeys: int = 1000) -> dict[str, Any]:
        contents = []
        for key in self._objects:
            if key.startswith(Prefix):
                contents.append({"Key": key, "Size": len(self._objects[key])})
        contents.sort(key=lambda x: x["Key"])
        return {"Contents": contents[:MaxKeys], "KeyCount": len(contents[:MaxKeys])}


# ═══════════════════════════════════════════════════════════════════════════
# S3SandboxV2Storage
# ═══════════════════════════════════════════════════════════════════════════

class S3SandboxV2Storage:
    """S3-compatible object storage adapter。

    支持:
    - AWS S3
    - MinIO (设置 endpoint_url)
    - 任何 S3-compatible 存储

    参数:
        endpoint_url: MinIO endpoint URL (S3 留空)
        access_key: Access key
        secret_key: Secret key
        bucket: Bucket name
        region: AWS region
        prefix: Object key prefix
        connect: 是否立即连接 (测试中为 False)
    """

    def __init__(self, endpoint_url: str = "", access_key: str = "",
                 secret_key: str = "", bucket: str = "sandbox-v2-artifacts",
                 region: str = "us-east-1", prefix: str = "",
                 connect: bool = False):
        self._endpoint_url = endpoint_url
        self._access_key = access_key
        self._secret_key = secret_key
        self._bucket = bucket
        self._region = region
        self._prefix = prefix
        self._client: Any = None
        self._connected = False
        if connect:
            self._connect()

    def _connect(self) -> None:
        """连接 S3/MinIO。"""
        _require_boto3()
        if not self._access_key or not self._secret_key:
            raise ValueError("Access key and secret key are required.")
        if not self._bucket:
            raise ValueError("Bucket name is required.")
        try:
            kwargs: dict[str, Any] = {
                "aws_access_key_id": self._access_key,
                "aws_secret_access_key": self._secret_key,
                "region_name": self._region,
            }
            if self._endpoint_url:
                kwargs["endpoint_url"] = self._endpoint_url
                kwargs["use_ssl"] = self._endpoint_url.startswith("https")
                kwargs["verify"] = True
            self._client = _boto3_module.client("s3", **kwargs)
            self._connected = True
        except Exception as e:
            raise ConnectionError(f"Failed to create S3 client: {e}") from e

    def health_check(self) -> dict[str, Any]:
        """对象存储连接健康检查。"""
        if not _BOTO3_AVAILABLE:
            return {"ok": False, "reason": _BOTO3_UNAVAILABLE_MSG}
        if not self._access_key or not self._secret_key:
            return {"ok": False, "reason": "Access key or secret key not configured"}
        if not self._bucket:
            return {"ok": False, "reason": "Bucket not configured"}
        try:
            s3 = self._s3()
            s3.head_bucket(Bucket=self._bucket)
            return {"ok": True, "reason": f"Object storage healthy (bucket={self._bucket})"}
        except Exception as e:
            return {"ok": False, "reason": f"Object storage connection failed: {e}"}

    def ensure_bucket_exists(self) -> dict[str, Any]:
        """检查或创建 bucket。只在显式集成模式下调用。"""
        if not _BOTO3_AVAILABLE:
            return {"ok": False, "reason": _BOTO3_UNAVAILABLE_MSG}
        try:
            s3 = self._s3()
            s3.head_bucket(Bucket=self._bucket)
            return {"ok": True, "created": False, "reason": f"Bucket '{self._bucket}' already exists"}
        except Exception:
            try:
                s3.create_bucket(Bucket=self._bucket)
                return {"ok": True, "created": True, "reason": f"Created bucket '{self._bucket}'"}
            except Exception as e:
                return {"ok": False, "reason": f"Failed to ensure bucket: {e}"}

    def _s3(self) -> Any:
        """获取 S3 client。"""
        if self._client is None:
            self._connect()
        return self._client

    def _build_key(self, organization_id: str, workspace_id: str,
                   category: str, filename: str) -> str:
        return build_object_key(self._prefix, organization_id, workspace_id, category, filename)

    @property
    def is_available(self) -> bool:
        """检查依赖是否可用。"""
        return _BOTO3_AVAILABLE

    @property
    def availability_message(self) -> str:
        """返回可用性描述。"""
        if not _BOTO3_AVAILABLE:
            return _BOTO3_UNAVAILABLE_MSG
        has_creds = bool(self._access_key and self._secret_key and self._bucket)
        return f"boto3 available. {'Credentials configured.' if has_creds else 'Credentials not configured.'}"

    # ── Core Operations ──

    def put_object(self, key: str, body: bytes, content_type: str = "application/octet-stream",
                   metadata: dict[str, str] | None = None) -> dict[str, Any]:
        """上传对象。key 已 sanitize。"""
        key = sanitize_object_key(key)
        s3 = self._s3()
        kwargs: dict[str, Any] = {
            "Bucket": self._bucket,
            "Key": key,
            "Body": body,
            "ContentType": content_type,
        }
        if metadata:
            kwargs["Metadata"] = {k: str(v) for k, v in metadata.items()}
        return s3.put_object(**kwargs)

    def put_object_safe(self, organization_id: str, workspace_id: str,
                        category: str, filename: str, body: bytes,
                        content_type: str = "application/octet-stream") -> dict[str, Any]:
        """安全上传对象（自动构建 key 并 sanitize）。"""
        key = self._build_key(organization_id, workspace_id, category, filename)
        return self.put_object(key, body, content_type)

    def get_object(self, key: str) -> bytes | None:
        """下载对象。key 已 sanitize。"""
        key = sanitize_object_key(key)
        s3 = self._s3()
        try:
            resp = s3.get_object(Bucket=self._bucket, Key=key)
            return resp["Body"].read()
        except Exception:
            # NoSuchKey 或其他任何异常 → 返回 None
            return None

    def get_object_safe(self, organization_id: str, workspace_id: str,
                        category: str, filename: str) -> bytes | None:
        """安全下载对象。"""
        key = self._build_key(organization_id, workspace_id, category, filename)
        return self.get_object(key)

    def delete_object(self, key: str) -> bool:
        """删除对象。"""
        key = sanitize_object_key(key)
        s3 = self._s3()
        try:
            s3.delete_object(Bucket=self._bucket, Key=key)
            return True
        except _BotoClientError:
            return False

    def delete_object_safe(self, organization_id: str, workspace_id: str,
                           category: str, filename: str) -> bool:
        """安全删除对象。"""
        key = self._build_key(organization_id, workspace_id, category, filename)
        return self.delete_object(key)

    def object_exists(self, key: str) -> bool:
        """检查对象是否存在。"""
        key = sanitize_object_key(key)
        s3 = self._s3()
        try:
            s3.head_object(Bucket=self._bucket, Key=key)
            return True
        except _BotoClientError:
            return False

    def list_objects(self, prefix: str = "", max_keys: int = 100) -> list[dict[str, Any]]:
        """列出对象。"""
        prefix = sanitize_object_key(prefix)
        s3 = self._s3()
        try:
            resp = s3.list_objects_v2(Bucket=self._bucket, Prefix=prefix, MaxKeys=max_keys)
            return resp.get("Contents", [])
        except _BotoClientError:
            return []

    def presign_read_url(self, key: str, expires_in: int = 3600) -> str:
        """生成预签名读取 URL（暂返回 disabled）。"""
        return "disabled"

    # ── 用于测试的 fake client 注入 ──
    def _set_client(self, client: Any) -> None:
        """注入 fake S3 client (仅供测试使用)。"""
        self._client = client
        self._connected = True


# ═══════════════════════════════════════════════════════════════════════════
# Factory helpers
# ═══════════════════════════════════════════════════════════════════════════

def create_fake_s3_storage(bucket: str = "test-bucket") -> S3SandboxV2Storage:
    """创建使用 FakeS3Client 的 S3SandboxV2Storage，用于测试。"""
    storage = S3SandboxV2Storage.__new__(S3SandboxV2Storage)
    storage._endpoint_url = ""
    storage._access_key = "fake-access-key"
    storage._secret_key = "fake-secret-key"
    storage._bucket = bucket
    storage._region = "us-east-1"
    storage._prefix = ""
    storage._client = FakeS3Client()
    storage._connected = True
    return storage
