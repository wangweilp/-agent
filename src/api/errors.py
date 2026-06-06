"""Safe error helper — log full exception details server-side, return sanitised messages.

Every ``HTTPException`` in the API layer must use sanitised messages.
Internal implementation details (tracebacks, file paths, SQL errors,
library names) must never leak to the client.
"""

from __future__ import annotations

import logging

from fastapi import HTTPException

logger = logging.getLogger(__name__)

# ── Public safe messages (no internal detail) ──

MSG_INTERNAL_ERROR = "服务内部错误，请稍后重试"
MSG_NOT_FOUND = "请求的资源不存在"
MSG_VALIDATION_ERROR = "请求参数无效"
MSG_UNAUTHORIZED = "需要登录"
MSG_FORBIDDEN = "权限不足"
MSG_UPLOAD_FAILED = "文件上传失败，请检查文件格式和大小"
MSG_ANALYSIS_FAILED = "文件分析失败"


def safe_error(
    status_code: int,
    public_message: str = MSG_INTERNAL_ERROR,
    exc: Exception | None = None,
    *,
    log_message: str = "",
    extra: dict | None = None,
) -> HTTPException:
    """Return an HTTPException with a sanitised message while logging the full error.

    Usage::

        try:
            ...
        except SomeLibraryError as e:
            raise safe_error(500, exc=e, log_message="db_write_failed") from e
    """
    ctx = dict(extra or {})
    if exc is not None:
        ctx["error_type"] = type(exc).__name__
        ctx["error"] = str(exc)[:500]

    if log_message:
        logger.error(log_message, extra=ctx, exc_info=exc if exc else False)
    elif exc:
        logger.error("safe_error", extra=ctx, exc_info=True)

    public = public_message or MSG_INTERNAL_ERROR
    return HTTPException(status_code=status_code, detail=public)
