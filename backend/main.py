"""FastAPI application entry point.

Run from the project root (``d:\\dma\\day2``)::

    uvicorn backend.main:app --reload --port 8000

The memory engine and causal kernel lazily initialize themselves on first
request, so startup stays cheap. CORS is configured to allow the frontend
dev server at ``http://localhost:3000``.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routes import kernel, memory
from backend.core.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
)
logger = logging.getLogger("backend.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan hook.

    Components lazily initialize on first request. Add eager warm-up here
    if desired (e.g. pre-build the Chroma collections at boot).
    """
    logger.info(
        "Zhiwei Cognitive OS backend starting | api_prefix=%s cors=%s",
        settings.API_V1_PREFIX, settings.CORS_ORIGINS,
    )
    yield
    logger.info("Zhiwei Cognitive OS backend shutting down.")


app = FastAPI(
    title="Zhiwei Cognitive OS - Backend",
    description=(
        "Multi-layer memory engine (LlamaIndex + ChromaDB) and causal kernel "
        "(intent routing + sandboxed execution) for the Cognitive OS."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(memory.router, prefix=settings.API_V1_PREFIX)
app.include_router(kernel.router, prefix=settings.API_V1_PREFIX)


@app.get("/health", tags=["meta"])
async def health() -> dict:
    """Liveness probe."""
    return {"status": "ok", "service": "zhiwei-cognitive-os-backend"}


@app.get("/", tags=["meta"])
async def root() -> dict:
    """Service root with a link to the OpenAPI docs."""
    return {
        "service": "zhiwei-cognitive-os-backend",
        "version": "0.1.0",
        "docs": "/docs",
        "openapi": "/openapi.json",
    }
