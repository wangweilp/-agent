"""Health Config Router — exposes config dispatch status for observability.

P4: Simplified to use ConfigDispatch.get_readiness_summary().
Does NOT expose secrets (DSN/URL).
"""
from __future__ import annotations

from fastapi import APIRouter

from src.adapters.config import Settings
from src.bootstrap.config_dispatch import ConfigDispatch


def create_config_health_router(
    settings: Settings,
    config_dispatch: ConfigDispatch,
) -> APIRouter:
    """Create router exposing config dispatch status at /health/config.

    All adapters are metadata-only (no active connection).
    """
    router = APIRouter(tags=["health"])

    @router.get("/health/config")
    async def health_config() -> dict:
        """Report config dispatch status. All adapters are metadata-only."""
        return {
            "database_backend": settings.database_backend,
            "cache_backend": settings.cache_backend,
            "queue_backend": settings.queue_backend,
            "active_store": "sqlite",  # SQLite always remains the active store
            "dispatch": config_dispatch.get_readiness_summary(),
        }

    return router
