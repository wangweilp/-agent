"""Causal kernel REST endpoints.

Exposes intent routing and sandboxed (mock) execution under
``/api/v1/kernel``. Request and response bodies are strictly typed via
Pydantic models so FastAPI generates a complete OpenAPI schema.
"""
from __future__ import annotations

from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, status

from backend.models.kernel import (
    ExecuteRequest,
    ExecuteResponse,
    RouteRequest,
    RouteResponse,
)
from backend.services.causal_kernel import CausalKernel

router = APIRouter(prefix="/kernel", tags=["causal-kernel"])


@lru_cache(maxsize=1)
def get_causal_kernel() -> CausalKernel:
    """Singleton causal kernel shared across requests."""
    return CausalKernel()


@router.post(
    "/route",
    response_model=RouteResponse,
    summary="Classify a user query into MEMORY_SEARCH or CODE_EXECUTION.",
)
async def route_query(
    req: RouteRequest,
    kernel: CausalKernel = Depends(get_causal_kernel),
) -> RouteResponse:
    try:
        intent = await kernel.route_query(req.query)
    except Exception as exc:  # pragma: no cover - defensive guard
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Intent routing failed: {exc}",
        ) from exc
    return RouteResponse(
        intent=intent,  # type: ignore[arg-type]
        confidence=1.0,
        raw_query=req.query,
    )


@router.post(
    "/execute",
    response_model=ExecuteResponse,
    summary="Run code through the security-gated mock sandbox.",
)
async def execute(
    req: ExecuteRequest,
    kernel: CausalKernel = Depends(get_causal_kernel),
) -> ExecuteResponse:
    try:
        result = await kernel.execute_in_sandbox(req.code_string)
    except Exception as exc:  # pragma: no cover - defensive guard
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Sandbox execution failed: {exc}",
        ) from exc
    return ExecuteResponse(**result)
