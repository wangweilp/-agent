"""Causal kernel domain models (intent routing + sandbox execution)."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

# LLM-routed intent labels.
IntentLiteral = Literal["MEMORY_SEARCH", "CODE_EXECUTION"]


class RouteRequest(BaseModel):
    """Request body for POST /kernel/route."""

    query: str = Field(..., min_length=1, description="User input to classify.")


class RouteResponse(BaseModel):
    """Response body for POST /kernel/route."""

    intent: IntentLiteral = Field(..., description="Classified intent label.")
    confidence: float = Field(
        default=1.0, ge=0.0, le=1.0,
        description="Mock classifier confidence (placeholder).",
    )
    raw_query: str = Field(..., description="Echo of the original query.")


class ExecuteRequest(BaseModel):
    """Request body for POST /kernel/execute."""

    code_string: str = Field(
        ..., min_length=1,
        description="Code to be evaluated inside the (mock) sandbox.",
    )


class ExecuteResponse(BaseModel):
    """Response body for POST /kernel/execute.

    status:
        - SUCCESS      : code passed the security gate and was mock-executed.
        - INTERCEPTED  : code matched a forbidden pattern.
        - ERROR        : runtime failure inside the sandbox.
    """

    status: Literal["SUCCESS", "INTERCEPTED", "ERROR"]
    reason: Optional[str] = Field(
        default=None, description="Human-readable explanation (esp. on intercept).",
    )
    result: Optional[dict] = Field(
        default=None,
        description="Mock execution result payload (stdout/stderr/exit_code).",
    )
    execution_time_ms: Optional[int] = Field(
        default=None, ge=0, description="Simulated wall-clock cost in ms.",
    )
