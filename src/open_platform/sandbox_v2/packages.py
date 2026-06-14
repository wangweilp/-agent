"""Sandbox v2 Package Quarantine Store — 包隔离存储。

所有包文件进入 quarantine，不允许直接进入可执行路径。
只接受 offline bytes 或测试 fixture，不联网下载。

安全约束：
- 不解压 zip/tar
- 不执行包
- 不安装包（不运行 pip/npm install）
- 路径隔离在 quarantine root 内
- 写入后只读
"""

from __future__ import annotations

import hashlib
import logging
import os
import pathlib
import re
import stat
from datetime import datetime, timezone
from uuid import uuid4

from src.open_platform.sandbox_v2.models import (
    SandboxPackageQuarantineRecord,
    SandboxV2PackageQuarantineStatus,
    SandboxV2PackageManager,
    SandboxV2SignatureStatus,
    SandboxV2SBOMStatus,
    SandboxV2VulnerabilityStatus,
    SandboxV2RiskLevel,
    DEFAULT_PACKAGE_MAX_BYTES,
)

logger = logging.getLogger(__name__)

_DEFAULT_QUARANTINE_ROOT = ".sandbox_v2_package_quarantine"


class LocalSandboxPackageQuarantineStore:
    """安全本地包隔离存储。"""

    def __init__(self, quarantine_root: str = ""):
        self._root = quarantine_root or _DEFAULT_QUARANTINE_ROOT
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
        cleaned = relative_path.replace("\\", "/")
        if ".." in cleaned.split("/"):
            raise ValueError(f"Path traversal detected: '{relative_path}'")
        if cleaned.startswith("/") or (len(cleaned) > 1 and cleaned[1] == ":"):
            raise ValueError(f"Absolute path not allowed: '{relative_path}'")
        safe = self._root_path / relative_path
        resolved = safe.resolve()
        r_root = self._root_path.resolve()
        common = pathlib.Path(os.path.commonpath([str(resolved), str(r_root)]))
        if common != r_root:
            raise ValueError(f"Path '{relative_path}' escapes quarantine root.")
        return resolved

    def _storage_dir(self, org_id: str, ws_id: str, pkg_req_id: str) -> pathlib.Path:
        so = _safe_seg(org_id or "default")
        sw = _safe_seg(ws_id or "default")
        sp = _safe_seg(pkg_req_id or uuid4().hex[:16])
        return self._resolve_in_root(f"{so}/{sw}/{sp}")

    def quarantine_package_bytes(
        self,
        content: bytes,
        original_filename: str,
        package_request_id: str = "",
        job_id: str = "",
        organization_id: str = "",
        workspace_id: str = "",
        package_name: str = "",
        package_version: str = "",
        package_manager: str = SandboxV2PackageManager.UNKNOWN,
        expected_sha256: str = "",
    ) -> tuple[SandboxPackageQuarantineRecord | None, str]:
        """将离线字节内容放入 quarantine。

        返回 (record, error_reason)。
        """
        if not content:
            return None, "Content is empty."
        if len(content) > DEFAULT_PACKAGE_MAX_BYTES:
            return None, f"Content size {len(content)} exceeds max {DEFAULT_PACKAGE_MAX_BYTES} bytes."

        req_id = package_request_id or f"sbxpkg_{uuid4().hex[:16]}"
        quarantine_id = f"sbxqrp_{uuid4().hex[:16]}"
        safe_name = _safe_filename(original_filename or f"{package_name}.{package_manager}")

        # Write to quarantine
        storage_dir = self._storage_dir(organization_id, workspace_id, req_id)
        storage_dir.mkdir(parents=True, exist_ok=True)
        file_path = storage_dir / safe_name
        file_path.write_bytes(content)
        _set_read_only(str(file_path))

        # Compute hash
        actual_sha256 = hashlib.sha256(content).hexdigest()

        # Verify expected hash
        if expected_sha256 and actual_sha256 != expected_sha256:
            return None, f"SHA256 mismatch: expected {expected_sha256[:16]}... got {actual_sha256[:16]}..."

        record = SandboxPackageQuarantineRecord(
            quarantine_id=quarantine_id,
            package_request_id=req_id,
            job_id=job_id,
            organization_id=organization_id,
            workspace_id=workspace_id,
            package_name=package_name,
            package_version=package_version,
            package_manager=package_manager,
            storage_key=f"{_safe_seg(organization_id or 'default')}/{_safe_seg(workspace_id or 'default')}/{_safe_seg(req_id)}/{safe_name}",
            size_bytes=len(content),
            sha256=actual_sha256,
            status=SandboxV2PackageQuarantineStatus.QUARANTINED,
            created_at=datetime.now(timezone.utc),
        )
        logger.info("package_quarantined", extra={"quarantine_id": quarantine_id, "sha256": actual_sha256[:16]})
        return record, ""

    def read_quarantined_bytes(self, storage_key: str) -> bytes:
        file_path = self._resolve_in_root(storage_key)
        if not file_path.exists() or not file_path.is_file():
            raise FileNotFoundError(f"Quarantine file not found: {storage_key}")
        return file_path.read_bytes()

    def verify_hash(self, expected_sha256: str, actual_sha256: str) -> bool:
        return expected_sha256 and actual_sha256 and expected_sha256 == actual_sha256

    def delete_quarantined_file(self, storage_key: str) -> bool:
        try:
            file_path = self._resolve_in_root(storage_key)
            if file_path.exists() and file_path.is_file():
                _set_writable(str(file_path))
                file_path.unlink()
            parent = file_path.parent
            if parent != self._root_path.resolve() and parent.exists():
                try:
                    parent.rmdir()
                except OSError:
                    pass
            return True
        except (ValueError, OSError) as e:
            logger.warning("quarantine_delete_failed", extra={"key": storage_key, "error": str(e)})
            return False


def _safe_seg(name: str) -> str:
    return re.sub(r'[^\w\-]', '_', name)[:64] or "default"


def _safe_filename(name: str) -> str:
    cleaned = name.replace("\\", "/").split("/")[-1].replace("\x00", "")
    cleaned = re.sub(r'[^\w\.\-_]', '_', cleaned).strip(".")
    return cleaned[:200] or "_package"


def _set_read_only(path_str: str):
    try:
        os.chmod(path_str, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
    except Exception:
        pass


def _set_writable(path_str: str):
    try:
        os.chmod(path_str, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)
    except Exception:
        pass
