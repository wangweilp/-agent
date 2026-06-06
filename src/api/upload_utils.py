"""Upload utilities — chunked file reading with size enforcement.

All upload endpoints MUST use these helpers instead of raw ``await f.read()``
to prevent unbounded memory consumption and enable early rejection of
oversized files.
"""

from __future__ import annotations

import logging
from fastapi import HTTPException, UploadFile

logger = logging.getLogger(__name__)

# ── Default chunk size (1 MiB) ──
_DEFAULT_CHUNK_SIZE: int = 1024 * 1024


async def read_upload_chunked(
    file: UploadFile,
    max_bytes: int,
    chunk_size: int = _DEFAULT_CHUNK_SIZE,
    filename: str = "",
) -> bytes:
    """Read an upload file in bounded chunks, rejecting oversized files early.

    Unlike ``await f.read()`` which buffers the entire file in memory before
    any size check, this incrementally reads chunks and aborts as soon as the
    total exceeds *max_bytes*.

    Args:
        file: The Starlette UploadFile.
        max_bytes: Maximum allowed size in bytes.
        chunk_size: Read buffer size (default 1 MiB).
        filename: Optional display name for error messages.

    Returns:
        The complete file content as bytes.

    Raises:
        HTTPException 413: If the content exceeds *max_bytes*.
    """
    chunks: list[bytes] = []
    total = 0
    name = filename or file.filename or "unknown"

    while True:
        try:
            chunk = await file.read(chunk_size)
        except Exception as exc:
            logger.warning("upload_read_error", extra={"file": name, "error": str(exc)})
            raise HTTPException(status_code=400, detail="文件读取失败")

        if not chunk:
            break

        total += len(chunk)
        if total > max_bytes:
            max_mb = max_bytes / (1024 * 1024)
            logger.info(
                "upload_size_exceeded",
                extra={"file": name, "size_bytes": total, "max_mb": round(max_mb, 1)},
            )
            raise HTTPException(
                status_code=413,
                detail=f"文件大小超过上限 ({max_mb:.0f} MB)",
            )

        chunks.append(chunk)

    return b"".join(chunks)


async def save_upload_chunked(
    file: UploadFile,
    dest_path: str,
    max_bytes: int,
    chunk_size: int = _DEFAULT_CHUNK_SIZE,
) -> int:
    """Read an upload in chunks and stream it directly to disk.

    This avoids ever holding the full file content in memory — the maximum
    resident memory is *chunk_size* plus OS buffers.

    Args:
        file: The Starlette UploadFile.
        dest_path: Absolute filesystem path to write to.
        max_bytes: Maximum allowed size in bytes.
        chunk_size: Write buffer size (default 1 MiB).

    Returns:
        Total bytes written.

    Raises:
        HTTPException 413: Content exceeds *max_bytes*.
        HTTPException 400: Read or write I/O error.
    """
    name = file.filename or "unknown"
    total = 0

    try:
        with open(dest_path, "wb") as out:
            while True:
                try:
                    chunk = await file.read(chunk_size)
                except Exception as exc:
                    logger.warning("upload_read_error", extra={"file": name, "error": str(exc)})
                    raise HTTPException(status_code=400, detail="文件读取失败")

                if not chunk:
                    break

                total += len(chunk)
                if total > max_bytes:
                    max_mb = max_bytes / (1024 * 1024)
                    logger.info(
                        "upload_size_exceeded",
                        extra={"file": name, "size_bytes": total, "max_mb": round(max_mb, 1)},
                    )
                    raise HTTPException(
                        status_code=413,
                        detail=f"文件大小超过上限 ({max_mb:.0f} MB)",
                    )

                try:
                    out.write(chunk)
                except OSError as exc:
                    logger.exception("upload_write_error", extra={"file": name, "path": dest_path})
                    raise HTTPException(status_code=400, detail="文件保存失败")

        return total

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("upload_unexpected_error", extra={"file": name})
        raise HTTPException(status_code=400, detail="文件处理失败")
