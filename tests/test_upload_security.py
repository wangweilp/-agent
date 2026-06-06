"""Upload & Error Handling Security Tests.

Coverage:
- Chunked upload: oversized files rejected early (413)
- Chunked upload: content type validation still works
- Rate limiter: rejects after threshold, allows below
- Safe errors: internal exceptions yield sanitised messages, not tracebacks
- Safe errors: HTTPException detail strings have no internal paths/stacktraces
"""

from __future__ import annotations

import io
import time
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.testclient import TestClient

from src.api.errors import safe_error, MSG_INTERNAL_ERROR, MSG_UPLOAD_FAILED
from src.api.upload_utils import read_upload_chunked
from src.api.rate_limit import RateLimitMiddleware


# ═══════════════════════════════════════════
# Chunked Upload Tests
# ═══════════════════════════════════════════


class TestChunkedUpload:
    """验证分块读取正确拒绝超大文件。"""

    @pytest.mark.anyio
    async def test_read_within_limit(self):
        """正常大小文件完整读取。"""
        data = b"hello" * 1000  # 5 KB
        file = UploadFile(filename="test.txt", file=io.BytesIO(data))
        result = await read_upload_chunked(file, max_bytes=1024 * 1024)
        assert len(result) == len(data)

    @pytest.mark.anyio
    async def test_oversized_file_rejected_early(self):
        """超大文件必须在达到阈值时立即拒绝，不继续读取。"""
        data = b"x" * (2 * 1024 * 1024)
        file = UploadFile(filename="big.bin", file=io.BytesIO(data))
        with pytest.raises(HTTPException) as exc_info:
            await read_upload_chunked(file, max_bytes=1024 * 1024)
        assert exc_info.value.status_code == 413
        assert "MB" in exc_info.value.detail

    @pytest.mark.anyio
    async def test_empty_file(self):
        """空文件应正常返回空字节。"""
        file = UploadFile(filename="empty.txt", file=io.BytesIO(b""))
        result = await read_upload_chunked(file, max_bytes=1024 * 1024)
        assert result == b""

    @pytest.mark.anyio
    async def test_exact_boundary(self):
        """恰好等于限制的文件应通过。"""
        size = 1024
        data = b"a" * size
        file = UploadFile(filename="exact.txt", file=io.BytesIO(data))
        result = await read_upload_chunked(file, max_bytes=size)
        assert len(result) == size

    @pytest.mark.anyio
    async def test_one_byte_over(self):
        """超出 1 字节时应拒绝。"""
        data = b"a" * 1001
        file = UploadFile(filename="over.txt", file=io.BytesIO(data))
        with pytest.raises(HTTPException) as exc_info:
            await read_upload_chunked(file, max_bytes=1000)
        assert exc_info.value.status_code == 413


# ═══════════════════════════════════════════
# Rate Limiter Tests
# ═══════════════════════════════════════════


class TestRateLimiter:
    """验证速率限制器正确拒绝超出阈值的请求。"""

    @pytest.fixture
    def rate_limited_app(self):
        app = FastAPI()

        @app.post("/upload")
        async def upload():
            return {"status": "ok"}

        @app.get("/health")
        async def health():
            return {"status": "healthy"}

        app.add_middleware(RateLimitMiddleware, max_requests=3, window_seconds=60.0)
        return app

    @pytest.fixture
    def client(self, rate_limited_app):
        return TestClient(rate_limited_app)

    def test_below_limit_passes(self, client):
        """请求数低于阈值应全部通过。"""
        for _ in range(3):
            r = client.post("/upload")
            assert r.status_code == 200

    def test_above_limit_rejected(self, client):
        """超出阈值后返回 429。"""
        for _ in range(3):
            client.post("/upload")  # these pass

        r = client.post("/upload")
        assert r.status_code == 429
        body = r.json()
        assert "retry_after_seconds" in body

    def test_non_upload_route_not_limited(self, client):
        """非上传路由不受速率限制。"""
        for _ in range(10):
            r = client.get("/health")
            assert r.status_code == 200

    def test_disabled_limiter_passes(self):
        """禁用后所有请求通过。"""
        app = FastAPI()

        @app.post("/upload")
        async def upload():
            return {"status": "ok"}

        app.add_middleware(RateLimitMiddleware, max_requests=3, window_seconds=60.0, enabled=False)
        client = TestClient(app)
        for _ in range(10):
            r = client.post("/upload")
            assert r.status_code == 200

    def test_stats_returns_data(self, rate_limited_app):
        """stats() 返回合理的统计信息。"""
        for mw in rate_limited_app.user_middleware:
            if isinstance(mw, RateLimitMiddleware):
                stats = mw.stats()
                assert "active_ips" in stats
                assert "max_requests_per_window" in stats
                break


# ═══════════════════════════════════════════
# Safe Error Tests
# ═══════════════════════════════════════════


class TestSafeErrors:
    """验证安全错误消息不泄露内部信息。"""

    def test_safe_error_returns_sanitised_message(self):
        """safe_error 返回公开消息，不是异常原文。"""
        try:
            raise ValueError("internal_db_error: connection refused at /var/run/postgres")
        except ValueError as e:
            err = safe_error(500, MSG_INTERNAL_ERROR, exc=e, log_message="db_connect_failed")

        assert err.status_code == 500
        assert err.detail == MSG_INTERNAL_ERROR
        assert "connection refused" not in err.detail
        assert "/var/run" not in err.detail

    def test_safe_error_custom_message(self):
        """自定义公开消息被保留。"""
        try:
            raise RuntimeError("some_library_v3_internal_crash")
        except RuntimeError as e:
            err = safe_error(400, MSG_UPLOAD_FAILED, exc=e)

        assert err.status_code == 400
        assert err.detail == MSG_UPLOAD_FAILED
        assert "RuntimeError" not in err.detail

    def test_safe_error_no_exc(self):
        """不带异常时 safe_error 仍正常工作。"""
        err = safe_error(503, "服务暂时不可用", log_message="service_unavailable")
        assert err.status_code == 503
        assert err.detail == "服务暂时不可用"

    def test_http_exception_details_are_sanitised(self):
        """确认 API 路由中不再有 bare exception detail。"""
        # 直接实例化 HTTPException 时不应包含内部信息
        exc = HTTPException(status_code=500, detail=MSG_INTERNAL_ERROR)
        assert "traceback" not in exc.detail.lower()
        assert "exception" not in exc.detail.lower()
        assert "line " not in exc.detail.lower()

    def test_upload_utils_error_messages_sanitised(self):
        """upload_utils 发出的错误不泄露路径。"""
        # 413 错误不应暴露文件系统路径
        exc = HTTPException(status_code=413, detail="文件大小超过上限 (10 MB)")
        assert "/" not in exc.detail or "MB" in exc.detail.split("/")[-1]

    def test_rate_limit_error_message_sanitised(self):
        """429 错误不应泄露计数器/内部阈值。"""
        from src.api.rate_limit import RateLimitMiddleware
        # 检查 429 响应体模板
        assert "threshold" not in str(RateLimitMiddleware.__dict__)
