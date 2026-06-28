"""Zhiwei Cognitive OS - Backend package.

Phase 18: Multi-layer Memory Engine & Causal Kernel initialization.

This package is strictly isolated from the frontend. All I/O is async-first;
LLM/vector operations are wrapped via asyncio.to_thread so the public API
surface stays fully awaitable.
"""
__version__ = "0.1.0"
