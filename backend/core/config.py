"""Application settings managed via pydantic-settings.

Reads from environment variables and an optional ``.env`` file at the project
root. All settings carry strict types so FastAPI / OpenAPI generation stays
deterministic.
"""
from __future__ import annotations

from pathlib import Path
from typing import List

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Strongly-typed application configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---- OpenAI / LLM ----
    OPENAI_API_KEY: SecretStr = Field(
        default=SecretStr(""),
        description="OpenAI API key. When empty, the memory engine falls back "
        "to a deterministic mock embedder for local development.",
    )
    OPENAI_BASE_URL: str | None = Field(
        default=None,
        description="Optional OpenAI-compatible base URL (Azure, proxy, etc.).",
    )
    OPENAI_EMBEDDING_MODEL: str = Field(
        default="text-embedding-3-small",
        description="Embedding model used by the memory engine.",
    )
    OPENAI_CHAT_MODEL: str = Field(
        default="gpt-4o-mini",
        description="Chat model used by the causal kernel for intent routing.",
    )

    # ---- ChromaDB ----
    CHROMA_DB_DIR: Path = Field(
        default=Path("./.chroma_db"),
        description="Local filesystem path for the persistent Chroma vector store.",
    )
    CHROMA_COLLECTION_EPISODIC: str = Field(
        default="episodic_memory",
        description="Chroma collection name for episodic (event-based) memories.",
    )
    CHROMA_COLLECTION_SEMANTIC: str = Field(
        default="semantic_memory",
        description="Chroma collection name for semantic (fact-based) memories.",
    )

    # ---- Memory Engine ----
    MEMORY_DEFAULT_TOP_K: int = Field(
        default=5, ge=1, le=100,
        description="Default number of memories returned by search_memory.",
    )
    MEMORY_RERANK_CANDIDATE_MULTIPLIER: int = Field(
        default=3, ge=1, le=10,
        description="Over-fetch multiplier applied before mock reranking.",
    )

    # ---- Causal Kernel / Sandbox ----
    SANDBOX_ENABLED: bool = Field(
        default=True,
        description="Master switch for the sandbox executor. When enabled, "
        "LOCAL_PROCESS mode performs real isolated Python execution via subprocess; "
        "SIMULATION mode remains metadata-only as a fallback.",
    )
    SANDBOX_FORBIDDEN_PATTERNS: List[str] = Field(
        default_factory=lambda: [
            "os.system", "subprocess", "rm -rf", "shutil.rmtree",
            "os.popen", "os.exec", "os.spawn", "os.remove", "os.unlink",
            "__import__", "eval(", "exec(", "open('/etc", "open(\"/etc",
        ],
        description="Substring blocklist for the sandbox security gate (second layer after AST scan).",
    )
    SANDBOX_EXECUTION_TIMEOUT_SECONDS: int = Field(
        default=10,
        ge=1,
        le=300,
        description="Hard wall-clock timeout for a single real Python execution in LOCAL_PROCESS mode.",
    )
    SANDBOX_MAX_OUTPUT_CHARACTERS: int = Field(
        default=65_536,
        ge=256,
        description="Maximum characters of stdout/stderr retained per execution (truncation guard against memory blowup).",
    )

    # ---- API ----
    API_V1_PREFIX: str = Field(
        default="/api/v1",
        description="Prefix applied to all registered routers.",
    )
    CORS_ORIGINS: List[str] = Field(
        default_factory=lambda: ["http://localhost:3000"],
        description="Allowed CORS origins. The frontend dev server runs on :3000.",
    )

    @property
    def openai_api_key_value(self) -> str:
        """Return the raw API key string (empty when unset)."""
        return self.OPENAI_API_KEY.get_secret_value()


settings = Settings()
