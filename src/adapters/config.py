import logging
import secrets
from typing import Literal

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


logger = logging.getLogger(__name__)
_GENERATED_DEV_JWT_SECRET: str | None = None


def _is_production(environment: str) -> bool:
    return environment.lower() in {"production", "prod"}


def _development_jwt_secret_key() -> str:
    global _GENERATED_DEV_JWT_SECRET
    if _GENERATED_DEV_JWT_SECRET is None:
        _GENERATED_DEV_JWT_SECRET = secrets.token_hex(32)
        logger.warning(
            "JWT_SECRET_KEY not set; generated temporary development key "
            "(set ENVIRONMENT=production to require explicit configuration)"
        )
    return _GENERATED_DEV_JWT_SECRET


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        frozen=True,
        extra="ignore",
        populate_by_name=True,
    )

    deepseek_api_key: str
    environment: str = "development"
    log_level: str = "INFO"
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    jwt_secret_key: str = ""
    chroma_persist_dir: str = "./data/chroma_db"
    sqlite_db_path: str = "./data/agent_memory.db"
    embedding_model: str = "BAAI/bge-small-zh-v1.5"
    upload_dir: str = "./data/uploads"
    upload_max_size_mb: int = 20
    database_backend: Literal["sqlite", "postgres"] = Field(
        default="sqlite",
        validation_alias=AliasChoices("DATABASE_BACKEND", "database_backend"),
    )
    cache_backend: Literal["memory", "redis"] = Field(
        default="memory",
        validation_alias=AliasChoices("CACHE_BACKEND", "cache_backend"),
    )
    object_storage_backend: Literal["local", "s3", "minio"] = Field(
        default="local",
        validation_alias=AliasChoices("OBJECT_STORAGE_BACKEND", "object_storage_backend"),
    )
    queue_backend: Literal["inline", "redis", "celery", "rq"] = Field(
        default="inline",
        validation_alias=AliasChoices("QUEUE_BACKEND", "queue_backend"),
    )
    postgres_dsn: str = Field(
        default="",
        validation_alias=AliasChoices("POSTGRES_DSN", "DATABASE_URL", "postgres_dsn"),
    )
    redis_url: str = Field(
        default="",
        validation_alias=AliasChoices("REDIS_URL", "redis_url"),
    )
    object_storage_endpoint: str = Field(
        default="",
        validation_alias=AliasChoices("OBJECT_STORAGE_ENDPOINT", "S3_ENDPOINT_URL", "MINIO_ENDPOINT", "object_storage_endpoint"),
    )
    object_storage_bucket: str = Field(
        default="cognitive-os",
        validation_alias=AliasChoices("OBJECT_STORAGE_BUCKET", "S3_BUCKET", "MINIO_BUCKET", "object_storage_bucket"),
    )
    queue_url: str = Field(
        default="",
        validation_alias=AliasChoices("QUEUE_URL", "CELERY_BROKER_URL", "RQ_REDIS_URL", "queue_url"),
    )
    cors_allowed_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ]
    )
    cors_allow_credentials: bool = True
    audio_upload_dir: str = "./data/audio_uploads"
    audio_max_size_mb: int = 50
    video_upload_dir: str = "./data/video_uploads"
    video_max_size_mb: int = 200
    video_keyframe_interval: int = 5
    agent_max_tool_rounds: int = 5
    agent_short_term_size: int = Field(
        default=20,
        validation_alias=AliasChoices(
            "AGENT_SHORT_TERM_SIZE",
            "AGENT_SHORT_TERM_MEMORY_SIZE",
        ),
    )
    agent_context_window: int = 6
    admin_email: str = ""
    admin_password: str = ""
    sync_local_folder_allowed_roots: list[str] = Field(default_factory=list)
    sync_local_folder_max_file_bytes: int = 10_485_760

    @model_validator(mode="after")
    def ensure_jwt_secret_key(self) -> "Settings":
        if self.jwt_secret_key:
            return self
        if _is_production(self.environment):
            raise ValueError(
                "JWT_SECRET_KEY is required when ENVIRONMENT=production. "
                "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
            )
        object.__setattr__(self, "jwt_secret_key", _development_jwt_secret_key())
        return self
