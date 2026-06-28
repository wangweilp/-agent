"""Memory engine REST endpoints.

Exposes the multi-layer memory engine (write / search) under
``/api/v1/memory``. Request and response bodies are strictly typed via
Pydantic models so FastAPI generates a complete OpenAPI schema.
"""
from __future__ import annotations

from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, status

from backend.models.memory import (
    MemorySearchHit,
    MemorySearchRequest,
    MemorySearchResponse,
    MemoryWriteRequest,
    MemoryWriteResponse,
)
from backend.services.memory_engine import ZhiweiMemoryEngine

router = APIRouter(prefix="/memory", tags=["memory"])


@lru_cache(maxsize=1)
def get_memory_engine() -> ZhiweiMemoryEngine:
    """Singleton memory engine shared across requests."""
    return ZhiweiMemoryEngine()


@router.post(
    "/write",
    response_model=MemoryWriteResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Write a memory to the multi-layer engine.",
)
async def write_memory(
    req: MemoryWriteRequest,
    engine: ZhiweiMemoryEngine = Depends(get_memory_engine),
) -> MemoryWriteResponse:
    try:
        result = await engine.write_memory(
            content=req.content,
            scope=req.scope,
            importance=req.importance,
        )
    except Exception as exc:  # pragma: no cover - defensive guard
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Memory write failed: {exc}",
        ) from exc
    return MemoryWriteResponse(**result)


@router.post(
    "/search",
    response_model=MemorySearchResponse,
    summary="Search memories by vector similarity (optional mock rerank).",
)
async def search_memory(
    req: MemorySearchRequest,
    engine: ZhiweiMemoryEngine = Depends(get_memory_engine),
) -> MemorySearchResponse:
    try:
        result = await engine.search_memory(
            query=req.query,
            top_k=req.top_k,
            rerank=req.rerank,
            scope=req.scope,
        )
    except Exception as exc:  # pragma: no cover - defensive guard
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Memory search failed: {exc}",
        ) from exc
    hits = [MemorySearchHit(**hit) for hit in result["hits"]]
    return MemorySearchResponse(
        query=result["query"],
        hits=hits,
        total=result["total"],
        reranked=result["reranked"],
    )
