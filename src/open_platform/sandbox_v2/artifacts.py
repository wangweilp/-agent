"""Sandbox v2 Local Artifact Store — 安全本地文件 artifact 存储。

所有 artifact 存储在 artifact root 目录内。
通过 pathlib.resolve() 验证所有路径在 root 内。
按 organization_id / workspace_id / job_id 分目录。

安全约束：
- 所有路径必须在 artifact root 内
- 不执行文件
- 不解压压缩包
- 不处理 symlink
- 不访问网络
- 用户原始文件名不用于真实路径
"""

from __future__ import annotations

import hashlib
import logging
import os
import pathlib
import stat
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from src.open_platform.sandbox_v2.models import (
    SandboxArtifact,
    SandboxArtifactManifest,
    SandboxV2ArtifactStatus,
    SandboxV2ArtifactType,
    SandboxV2RiskLevel,
)

logger = logging.getLogger(__name__)

_DEFAULT_ARTIFACT_ROOT = ".sandbox_v2_artifacts"


class LocalSandboxArtifactStore:
    """安全本地 artifact 存储。

    安全策略：
    - 所有路径验证在 artifact root 内
    - 文件名 sanizite
    - 写入后设只读
    - 写入后计算 sha256
    """

    def __init__(self, artifact_root: str = ""):
        self._root = artifact_root or _DEFAULT_ARTIFACT_ROOT
        self._root_path = pathlib.Path(self._root).resolve()
        self._ensure_root()

    @property
    def root_path(self) -> pathlib.Path:
        return self._root_path

    @property
    def root(self) -> str:
        return str(self._root_path)

    def _ensure_root(self):
        self._root_path.mkdir(parents=True, exist_ok=True)

    def _resolve_in_root(self, relative_path: str) -> pathlib.Path:
        """将相对路径 resolve 到 root 内，并验证。

        Raises:
            ValueError: 如果路径不在 root 内
        """
        # 先检查路径包含危险模式
        cleaned = relative_path.replace("\\", "/")
        if ".." in cleaned.split("/"):
            raise ValueError(f"Path traversal detected in '{relative_path}'.")
        if cleaned.startswith("/") or (len(cleaned) > 1 and cleaned[1] == ":"):
            raise ValueError(f"Absolute path not allowed: '{relative_path}'.")
        if cleaned.startswith("//"):
            raise ValueError(f"UNC path not allowed: '{relative_path}'.")

        safe = self._root_path / relative_path
        # Resolve and validate
        resolved = safe.resolve()
        try:
            r_root = self._root_path.resolve()
            common = pathlib.Path(os.path.commonpath([str(resolved), str(r_root)]))
            if common != r_root:
                raise ValueError(f"Path '{relative_path}' escapes artifact root.")
        except (ValueError, OSError) as e:
            raise ValueError(f"Path validation failed: {e}") from e
        return resolved

    def _storage_dir(
        self,
        organization_id: str,
        workspace_id: str,
        job_id: str,
        artifact_id: str,
    ) -> pathlib.Path:
        """构建 artifact 存储目录：{root}/{org}/{ws}/{job_id}/{artifact_id}/"""
        safe_org = _safe_path_segment(organization_id or "default")
        safe_ws = _safe_path_segment(workspace_id or "default")
        safe_job = _safe_path_segment(job_id or "default")
        safe_art = _safe_path_segment(artifact_id or uuid4().hex[:16])
        return self._resolve_in_root(f"{safe_org}/{safe_ws}/{safe_job}/{safe_art}")

    def create_artifact(
        self,
        *,
        job_id: str = "",
        organization_id: str = "",
        workspace_id: str = "",
        record_id: str = "",
        artifact_type: str = SandboxV2ArtifactType.UNKNOWN,
        name: str = "",
        original_filename: str = "",
        content: bytes = b"",
        content_text: str = "",
        mime_type: str = "text/plain",
        read_only: bool = True,
        retention_hours: int = 24,
        metadata: dict | None = None,
    ) -> SandboxArtifact:
        """创建并写入 artifact。

        安全流程：
        1. 生成 artifact_id 和 safe_filename
        2. 解析存储路径，确保在 root 内
        3. 创建目录
        4. 写入文件到 {storage_dir}/file
        5. 设置只读权限
        6. 计算 sha256
        7. 返回 SandboxArtifact metadata
        """
        if not content and content_text:
            content = content_text.encode("utf-8")

        artifact_id = f"sbxart_{uuid4().hex[:16]}"
        safe_name = _safe_filename(original_filename or name or f"{artifact_type}.txt")

        storage_dir = self._storage_dir(organization_id, workspace_id, job_id, artifact_id)
        storage_dir.mkdir(parents=True, exist_ok=True)

        file_path = storage_dir / "file"

        # Write
        file_path.write_bytes(content)

        # Set read-only
        if read_only:
            _set_read_only(str(file_path))

        # Compute sha256
        sha256 = hashlib.sha256(content).hexdigest()

        now = datetime.now(timezone.utc)
        retention = now if retention_hours > 0 else None
        if retention:
            from datetime import timedelta
            retention = now + timedelta(hours=retention_hours)

        artifact = SandboxArtifact(
            artifact_id=artifact_id,
            job_id=job_id,
            organization_id=organization_id,
            workspace_id=workspace_id,
            record_id=record_id,
            artifact_type=artifact_type,
            name=name or safe_name,
            original_filename=original_filename,
            safe_filename=safe_name,
            storage_key=f"{organization_id or 'default'}/{workspace_id or 'default'}/{job_id}/{artifact_id}/file",
            storage_backend="local",
            size_bytes=len(content),
            mime_type=mime_type,
            sha256=sha256,
            created_at=now,
            materialized_at=now,
            read_only=read_only,
            status=SandboxV2ArtifactStatus.MATERIALIZED,
            retention_until=retention,
            metadata=metadata or {},
        )
        logger.info("artifact_created",
                     extra={"artifact_id": artifact_id, "job_id": job_id, "size_bytes": len(content)})
        return artifact

    def read_artifact(self, storage_key: str) -> bytes:
        """读取 artifact 内容。只允许读 artifact root 内文件。"""
        file_path = self._resolve_in_root(storage_key)
        if not file_path.exists():
            raise FileNotFoundError(f"Artifact file not found: {storage_key}")
        if not file_path.is_file():
            raise ValueError(f"Storage key does not point to a file: {storage_key}")
        return file_path.read_bytes()

    def read_artifact_text(self, storage_key: str, max_bytes: int = 1_048_576) -> str:
        """以文本形式读取 artifact 内容。"""
        content = self.read_artifact(storage_key)
        if len(content) > max_bytes:
            truncated = content[:max_bytes]
            return truncated.decode("utf-8", errors="replace") + f"\n\n... [truncated at {max_bytes} bytes, total {len(content)} bytes]"
        return content.decode("utf-8", errors="replace")

    def delete_artifact_file(self, storage_key: str) -> bool:
        """删除 artifact 文件（及父目录）。只允许删除 root 内文件。"""
        try:
            file_path = self._resolve_in_root(storage_key)
            if file_path.exists() and file_path.is_file():
                # Make writable to delete
                _set_writable(str(file_path))
                file_path.unlink()
            # Remove parent dir if empty
            parent = file_path.parent
            if parent != self._root_path.resolve() and parent.exists():
                try:
                    parent.rmdir()
                except OSError:
                    pass  # dir not empty
            return True
        except (ValueError, OSError) as e:
            logger.warning("artifact_delete_failed", extra={"storage_key": storage_key, "error": str(e)})
            return False

    def create_manifest(
        self,
        job_id: str,
        record_id: str,
        artifacts: list[SandboxArtifact],
    ) -> SandboxArtifactManifest:
        """为 job/record 创建 artifact manifest。"""
        now = datetime.now(timezone.utc)
        artifact_ids = [a.artifact_id for a in artifacts]
        total_size = sum(a.size_bytes for a in artifacts)
        # sha256 of concatenated artifact SHA256s
        concat = "".join(a.sha256 for a in artifacts if a.sha256).encode()
        manifest_sha = hashlib.sha256(concat).hexdigest() if concat else ""

        return SandboxArtifactManifest(
            manifest_id=f"sbxmft_{uuid4().hex[:16]}",
            job_id=job_id,
            record_id=record_id,
            artifact_ids=artifact_ids,
            total_size_bytes=total_size,
            artifact_count=len(artifacts),
            created_at=now,
            sealed=True,
            sha256=manifest_sha,
        )

    def verify_sha256(self, storage_key: str, expected_sha256: str) -> bool:
        """验证 artifact 的 sha256。"""
        try:
            content = self.read_artifact(storage_key)
            actual = hashlib.sha256(content).hexdigest()
            return actual == expected_sha256
        except Exception:
            return False


# ═══════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════


def _safe_path_segment(name: str) -> str:
    """Sanitize 路径段——只保留字母数字和横杠。"""
    import re
    cleaned = re.sub(r'[^\w\-]', '_', name)[:64]
    return cleaned or "default"


def _safe_filename(name: str) -> str:
    """生成安全的文件名——只用字母数字、下划线和点。"""
    import re
    cleaned = name.replace("\\", "/").split("/")[-1]
    cleaned = cleaned.replace("\x00", "")
    cleaned = re.sub(r'[^\w\.\-]', '_', cleaned)
    cleaned = cleaned.strip(".")
    if not cleaned:
        return "_artifact"
    if len(cleaned) > 200:
        return cleaned[:195] + "." + cleaned.split(".")[-1][-4:] if "." in cleaned else cleaned[:195]
    return cleaned


def _set_read_only(path_str: str):
    """设置文件为只读（跨平台）。"""
    try:
        os.chmod(path_str, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
    except Exception:
        pass  # chmod 可能不可用，安全忽略


def _set_writable(path_str: str):
    """设置文件为可写（用于删除）。"""
    try:
        os.chmod(path_str, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)
    except Exception:
        pass
