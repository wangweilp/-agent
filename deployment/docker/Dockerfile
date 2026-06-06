# ============================================================
# Enterprise Knowledge OS — Backend Dockerfile
# Multi-stage build: builder → runtime
# ============================================================

# ── Stage 1: Builder ───────────────────────────────────────
FROM python:3.12-slim AS builder

# 离线安装模式：将 wheels 目录复制到 /wheels 后设置 PIP_NO_INDEX
# COPY wheels/ /wheels/
# ENV PIP_NO_INDEX=1 PIP_FIND_LINKS=/wheels/

WORKDIR /build

# 安装编译依赖（sentence-transformers 需要）
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ make cmake libffi-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# 在 builder 阶段安装全部依赖到 /install 前缀，用于后续复制
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Stage 2: Runtime ───────────────────────────────────────
FROM python:3.12-slim AS runtime

LABEL org.opencontainers.image.title="Enterprise Knowledge OS"
LABEL org.opencontainers.image.description="AI Second Brain — 个人知识助手后端"
LABEL org.opencontainers.image.version="0.1.0"

# 安装运行时系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# 创建非 root 用户
RUN groupadd --system app && useradd --system --gid app --create-home app

WORKDIR /app

# 从 builder 复制已安装的依赖
COPY --from=builder /install /usr/local

# 复制应用代码
COPY main.py .
COPY src/ ./src/

# 创建数据目录并设置权限
RUN mkdir -p /app/data && chown -R app:app /app

# 切换到非 root 用户
USER app

# 默认环境变量（可通过 docker run -e 覆盖）
ENV ENVIRONMENT=production \
    PYTHONUNBUFFERED=1

EXPOSE 8000

# 健康检查 — 通过 /health 端点验证服务可用
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/health', timeout=5).raise_for_status()" || exit 1

# 启动 uvicorn，绑定所有接口
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--log-level", "info"]
