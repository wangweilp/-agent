"""本地 Embedding 提供器 — 使用 sentence-transformers 模型。"""
import logging
import os
import threading
from typing import TYPE_CHECKING

# Keep Hugging Face progress output out of the application logs.  Do not set
# HF_HUB_OFFLINE/TRANSFORMERS_OFFLINE here: those flags are process-wide and
# would also prevent the first-run cache-miss fallback from downloading.
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")

from src.adapters.config import Settings

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "BAAI/bge-small-zh-v1.5"
_DIMENSIONS: dict[str, int] = {
    "BAAI/bge-small-zh-v1.5": 512,
}
_OFFLINE_ENV_VARS = ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE")
_TRUTHY_ENV_VALUES = {"1", "true", "yes", "on"}


def _offline_mode_enabled() -> bool:
    """Return whether Hugging Face access was explicitly disabled."""
    return any(
        os.environ.get(name, "").strip().lower() in _TRUTHY_ENV_VALUES
        for name in _OFFLINE_ENV_VARS
    )


def _detect_device() -> str:
    try:
        import torch  # type: ignore[import-untyped]
        if torch.cuda.is_available():
            return "cuda"
    except Exception:
        pass
    return "cpu"


class EmbeddingError(Exception):
    """Embedding 相关错误。"""


class LocalEmbeddingProvider:
    """使用本地 sentence-transformers 模型生成文本 Embedding。

    模型在 warmup() 或首次 encode() 时加载，全局单例。
    优先从本地缓存加载，避免 HF 网络检查。
    自动检测 CUDA。
    """

    def __init__(self, config: Settings) -> None:
        self._model_name = config.embedding_model
        self._device = os.environ.get("EMBEDDING_DEVICE", "") or _detect_device()
        self._model: SentenceTransformer | None = None
        self._lock = threading.Lock()
        self._loaded = False

    def warmup(self) -> None:
        """预加载模型，避免首次请求时阻塞。"""
        _ = self.model
        self._loaded = True
        logger.info("embedding 模型预热完成")

    @property
    def model(self) -> "SentenceTransformer":
        if self._model is None:
            with self._lock:
                if self._model is None:
                    from sentence_transformers import SentenceTransformer

                    logger.info(
                        "加载 embedding 模型: %s (device=%s)",
                        self._model_name,
                        self._device,
                    )
                    # Always probe the local cache first to avoid an unnecessary
                    # network check.  A cache miss falls back to Hugging Face
                    # unless the caller explicitly enabled offline mode.
                    try:
                        self._model = SentenceTransformer(
                            self._model_name,
                            device=self._device,
                            local_files_only=True,
                        )
                    except Exception as cache_error:
                        if _offline_mode_enabled():
                            raise EmbeddingError(
                                f"Embedding 模型 {self._model_name!r} 不在本地缓存，"
                                "且当前处于离线模式。请预先下载模型，或移除 "
                                "HF_HUB_OFFLINE/TRANSFORMERS_OFFLINE 后重试。"
                            ) from cache_error

                        logger.info("本地缓存未命中，从 HF 下载模型")
                        try:
                            self._model = SentenceTransformer(
                                self._model_name,
                                device=self._device,
                                local_files_only=False,
                            )
                        except Exception as download_error:
                            raise EmbeddingError(
                                f"无法加载 embedding 模型 {self._model_name!r}："
                                "本地缓存未命中且下载失败。请检查网络、代理和 "
                                "Hugging Face 访问权限。"
                            ) from download_error
        return self._model

    def encode(self, text: str) -> list[float]:
        text = text.strip()
        if not text:
            raise ValueError("输入文本不能为空")

        result = self.model.encode(
            text,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return result.tolist()

    @property
    def dimension(self) -> int:
        try:
            return self.model.get_sentence_embedding_dimension()
        except Exception:
            return _DIMENSIONS.get(self._model_name, 512)

    def close(self) -> None:
        self._model = None

    def __enter__(self) -> "LocalEmbeddingProvider":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
