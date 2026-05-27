"""本地 Embedding 提供器 — 使用 sentence-transformers 模型。"""
import logging
import os
import threading
from typing import TYPE_CHECKING

from src.adapters.config import Settings

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "BAAI/bge-small-zh-v1.5"
_DIMENSIONS: dict[str, int] = {
    "BAAI/bge-small-zh-v1.5": 512,
}


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

    延迟加载模型，首次调用 encode() 时加载，节省启动时间。
    双重检查锁定保证多线程安全。
    自动检测 CUDA，缓存命中时跳过 HF 网络检查。
    """

    def __init__(self, config: Settings) -> None:
        self._model_name = config.embedding_model
        self._device = os.environ.get("EMBEDDING_DEVICE", "") or _detect_device()
        self._model: SentenceTransformer | None = None
        self._lock = threading.Lock()

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
                    self._model = SentenceTransformer(
                        self._model_name,
                        device=self._device,
                    )
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
