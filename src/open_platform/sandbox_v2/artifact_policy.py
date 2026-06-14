"""Sandbox v2 Artifact Policy — 文件 artifact 安全策略评估。

安全策略：
1. 默认 fail closed
2. 未知 artifact_type 默认拒绝
3. 大小限制（单文件 + job 总大小）
4. MIME 类型白名单
5. 危险文件扩展名拦截
6. 文件名 sanitize
7. 路径穿越防护
8. 默认 read_only_required=true
9. 策略字段缺失 → fail closed
10. 输出 SandboxArtifactPolicyDecision

不执行代码，不访问网络，不写真实文件系统。
"""

from __future__ import annotations

import logging
import re
from typing import Any

from src.open_platform.sandbox_v2.models import (
    SandboxV2ArtifactType,
    SandboxV2RiskLevel,
    SandboxArtifactMaterializationRequest,
    SandboxArtifactPolicyDecision,
    BLOCKED_FILE_EXTENSIONS,
    ALLOWED_ARTIFACT_MIME_TYPES,
    DEFAULT_ARTIFACT_MAX_BYTES,
    DEFAULT_JOB_TOTAL_ARTIFACT_BYTES,
)

logger = logging.getLogger(__name__)

# 路径穿越模式
_PATH_TRAVERSAL_PATTERNS: list[re.Pattern] = [
    re.compile(r"\.\./"),
    re.compile(r"\.\.\\"),
    re.compile(r"^[A-Za-z]:\\"),   # Windows drive path
    re.compile(r"^/"),               # Absolute Unix path
    re.compile(r"^\\\\"),           # UNC path
    re.compile(r"~"),               # Home dir expansion
]


def evaluate_artifact_policy(
    request: SandboxArtifactMaterializationRequest,
    *,
    max_size_bytes: int = DEFAULT_ARTIFACT_MAX_BYTES,
    job_total_bytes: int = DEFAULT_JOB_TOTAL_ARTIFACT_BYTES,
    current_job_total: int = 0,
    allowed_mime_types: frozenset[str] | None = None,
    force_read_only: bool = True,
) -> SandboxArtifactPolicyDecision:
    """评估 artifact 物化请求，返回决策。

    Args:
        request: 物化请求
        max_size_bytes: 单个 artifact 最大字节数
        job_total_bytes: job 所有 artifact 最大总字节数
        current_job_total: 当前 job 已用字节数
        allowed_mime_types: 允许的 MIME 类型（None 则使用默认白名单）
        force_read_only: 强制只读
    """
    try:
        return _evaluate_impl(
            request=request,
            max_size_bytes=max_size_bytes,
            job_total_bytes=job_total_bytes,
            current_job_total=current_job_total,
            allowed_mime_types=allowed_mime_types or ALLOWED_ARTIFACT_MIME_TYPES,
            force_read_only=force_read_only,
        )
    except Exception:
        logger.exception("artifact_policy_evaluation_failed")
        return SandboxArtifactPolicyDecision(
            allowed=False,
            reason="Artifact policy evaluation raised an exception — fail closed.",
            risk_level=SandboxV2RiskLevel.CRITICAL,
            max_size_bytes=max_size_bytes,
            read_only_required=True,
            fail_closed=True,
            matched_rules=["exception_fail_closed"],
        )


def _evaluate_impl(
    request: SandboxArtifactMaterializationRequest,
    max_size_bytes: int,
    job_total_bytes: int,
    current_job_total: int,
    allowed_mime_types: frozenset[str],
    force_read_only: bool,
) -> SandboxArtifactPolicyDecision:
    matched_rules: list[str] = []

    # ── Rule 1: Validate artifact_type ──
    if not request.artifact_type:
        return SandboxArtifactPolicyDecision(
            allowed=False,
            reason="Artifact type is missing — fail closed.",
            risk_level=SandboxV2RiskLevel.HIGH,
            max_size_bytes=max_size_bytes,
            read_only_required=force_read_only,
            fail_closed=True,
            matched_rules=["artifact_type_missing"],
        )

    if request.artifact_type not in [e.value for e in SandboxV2ArtifactType]:
        return SandboxArtifactPolicyDecision(
            allowed=False,
            reason=f"Unknown artifact_type '{request.artifact_type}' — fail closed.",
            risk_level=SandboxV2RiskLevel.HIGH,
            max_size_bytes=max_size_bytes,
            read_only_required=force_read_only,
            fail_closed=True,
            matched_rules=["artifact_type_unknown"],
        )

    matched_rules.append("artifact_type_valid")

    # ── Rule 2: Check path traversal (on raw name, before sanitize) ──
    if _has_path_traversal(request.artifact_name):
        return SandboxArtifactPolicyDecision(
            allowed=False,
            reason=f"Artifact name '{request.artifact_name}' contains path traversal patterns.",
            risk_level=SandboxV2RiskLevel.CRITICAL,
            max_size_bytes=max_size_bytes,
            read_only_required=force_read_only,
            fail_closed=True,
            matched_rules=["path_traversal_blocked"],
        )

    # Also check source_ref for path traversal if non-empty
    if request.source_ref and _has_path_traversal(request.source_ref):
        return SandboxArtifactPolicyDecision(
            allowed=False,
            reason=f"Source ref contains path traversal patterns.",
            risk_level=SandboxV2RiskLevel.CRITICAL,
            max_size_bytes=max_size_bytes,
            read_only_required=force_read_only,
            fail_closed=True,
            matched_rules=["path_traversal_blocked_source"],
        )

    matched_rules.append("path_traversal_ok")

    # ── Rule 3: Validate artifact_name (sanitize + extension check) ──
    if not request.artifact_name:
        return SandboxArtifactPolicyDecision(
            allowed=False,
            reason="Artifact name is missing — fail closed.",
            risk_level=SandboxV2RiskLevel.HIGH,
            max_size_bytes=max_size_bytes,
            read_only_required=force_read_only,
            fail_closed=True,
            matched_rules=["artifact_name_missing"],
        )

    sanitized = sanitize_filename(request.artifact_name)
    if sanitized != request.artifact_name:
        return SandboxArtifactPolicyDecision(
            allowed=False,
            reason=f"Artifact name '{request.artifact_name}' contains unsafe characters. Sanitized name: '{sanitized}'.",
            risk_level=SandboxV2RiskLevel.MEDIUM,
            max_size_bytes=max_size_bytes,
            read_only_required=force_read_only,
            fail_closed=True,
            matched_rules=["artifact_name_unsafe"],
        )

    # ── Rule 4: Check dangerous extensions ──
    if _has_dangerous_extension(request.artifact_name):
        return SandboxArtifactPolicyDecision(
            allowed=False,
            reason=f"Artifact name '{request.artifact_name}' has a dangerous file extension.",
            risk_level=SandboxV2RiskLevel.CRITICAL,
            max_size_bytes=max_size_bytes,
            read_only_required=force_read_only,
            fail_closed=True,
            matched_rules=["dangerous_extension"],
        )

    matched_rules.append("extension_ok")

    # ── Rule 5: Read-only check ──
    if force_read_only and not request.read_only:
        return SandboxArtifactPolicyDecision(
            allowed=False,
            reason="Artifact must be read-only. Write requests are not allowed.",
            risk_level=SandboxV2RiskLevel.MEDIUM,
            max_size_bytes=max_size_bytes,
            read_only_required=True,
            fail_closed=True,
            matched_rules=["read_only_required"],
        )

    matched_rules.append("read_only_ok")

    # ── Rule 6: Size check ──
    actual_size = request.get_size()
    if actual_size > max_size_bytes:
        return SandboxArtifactPolicyDecision(
            allowed=False,
            reason=f"Artifact size {actual_size} bytes exceeds limit {max_size_bytes} bytes.",
            risk_level=SandboxV2RiskLevel.MEDIUM,
            max_size_bytes=max_size_bytes,
            read_only_required=force_read_only,
            fail_closed=True,
            matched_rules=["size_limit_exceeded"],
        )

    if current_job_total + actual_size > job_total_bytes:
        return SandboxArtifactPolicyDecision(
            allowed=False,
            reason=f"Job total artifact size {current_job_total + actual_size} exceeds limit {job_total_bytes} bytes.",
            risk_level=SandboxV2RiskLevel.MEDIUM,
            max_size_bytes=max_size_bytes,
            read_only_required=force_read_only,
            fail_closed=True,
            matched_rules=["job_total_size_exceeded"],
        )

    matched_rules.append("size_ok")

    # ── Rule 7: MIME type check ──
    mime = request.mime_type or _guess_mime_from_name(request.artifact_name)
    if mime not in allowed_mime_types:
        return SandboxArtifactPolicyDecision(
            allowed=False,
            reason=f"MIME type '{mime}' is not in allowed list.",
            risk_level=SandboxV2RiskLevel.MEDIUM,
            max_size_bytes=max_size_bytes,
            allowed_mime_types=sorted(allowed_mime_types),
            read_only_required=force_read_only,
            fail_closed=True,
            matched_rules=["mime_type_denied"],
        )

    matched_rules.append("mime_type_ok")

    # ── All checks passed ──
    matched_rules.append("all_checks_passed")
    return SandboxArtifactPolicyDecision(
        allowed=True,
        reason="All artifact policy checks passed.",
        risk_level=SandboxV2RiskLevel.LOW,
        max_size_bytes=max_size_bytes,
        allowed_mime_types=sorted(allowed_mime_types),
        read_only_required=force_read_only,
        fail_closed=False,
        matched_rules=matched_rules,
    )


# ═══════════════════════════════════════════
# Helper functions
# ═══════════════════════════════════════════


def sanitize_filename(filename: str) -> str:
    """Sanitize 文件名：移除危险字符，只保留安全字符。

    返回一个安全可用的文件名，或与原始相同（如果本来安全）。
    """
    if not filename:
        return "_artifact"
    # 移除路径穿越
    cleaned = filename.replace("\\", "/").split("/")[-1]
    # 移除 NULL 字节
    cleaned = cleaned.replace("\x00", "")
    # 移除不可打印字符（保留常见安全字符）
    cleaned = re.sub(r'[^\w\.\-_ ]', '_', cleaned)
    # 移除开头和结尾的点（防止隐藏文件）
    cleaned = cleaned.strip(".")
    if not cleaned:
        return "_artifact"
    # 限制长度
    if len(cleaned) > 200:
        base, ext = _split_ext(cleaned)
        cleaned = base[:195] + ext[-5:]
    return cleaned


def _split_ext(filename: str) -> tuple[str, str]:
    """分离文件名和扩展名。"""
    idx = filename.rfind(".")
    if idx <= 0:
        return filename, ""
    return filename[:idx], filename[idx:]


def _has_dangerous_extension(filename: str) -> bool:
    """检查文件名是否有危险扩展名。"""
    lower = filename.lower()
    for ext in BLOCKED_FILE_EXTENSIONS:
        if lower.endswith(ext):
            return True
    return False


def _has_path_traversal(value: str) -> bool:
    """检查值是否包含路径穿越模式。"""
    # 替换反斜杠用于检查
    normalized = value.replace("\\", "/")
    for pattern in _PATH_TRAVERSAL_PATTERNS:
        if pattern.search(value) or pattern.search(normalized):
            return True
    # 直接检查 ../ 模式
    if ".." in normalized.split("/"):
        return True
    return False


def _guess_mime_from_name(filename: str) -> str:
    """从文件名推断 MIME 类型。"""
    lower = filename.lower()
    if lower.endswith(".json"):
        return "application/json"
    if lower.endswith((".md", ".markdown")):
        return "text/markdown"
    if lower.endswith(".csv"):
        return "text/csv"
    if lower.endswith((".htm", ".html")):
        return "text/html"
    if lower.endswith(".xml"):
        return "application/xml"
    if lower.endswith((".png",)):
        return "image/png"
    if lower.endswith((".jpg", ".jpeg")):
        return "image/jpeg"
    if lower.endswith((".svg",)):
        return "image/svg+xml"
    if lower.endswith(".pdf"):
        return "application/pdf"
    if lower.endswith((".log", ".txt")):
        return "text/plain"
    if lower.endswith((".bin", ".dat")):
        return "application/octet-stream"
    return "text/plain"


def is_path_within_root(target: str, root: str) -> bool:
    """校验 target 路径是否在 root 目录内。"""
    import os
    try:
        real_target = os.path.realpath(target)
        real_root = os.path.realpath(root)
        common = os.path.commonpath([real_target, real_root])
        return common == real_root
    except (ValueError, OSError):
        return False
