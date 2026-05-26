"""LocalEmbeddingProvider 单元测试。"""
import pytest
import threading
from unittest.mock import MagicMock, patch

from src.adapters.config import Settings


@pytest.fixture
def settings():
    return Settings(
        deepseek_api_key="sk-test",
        embedding_model="BAAI/bge-small-zh-v1.5",
    )


def _make_mock_st():
    """创建 mock SentenceTransformer 实例。"""
    mock_instance = MagicMock()
    mock_instance.encode.return_value = MagicMock()
    mock_instance.encode.return_value.tolist.return_value = [0.1, 0.2, 0.3]
    mock_instance.get_sentence_embedding_dimension.return_value = 512
    return mock_instance


class TestInit:
    def test_model_is_none_at_init(self, settings):
        from src.adapters.embedding import LocalEmbeddingProvider
        provider = LocalEmbeddingProvider(settings)
        assert provider._model is None

    def test_stores_model_name(self, settings):
        from src.adapters.embedding import LocalEmbeddingProvider
        provider = LocalEmbeddingProvider(settings)
        assert provider._model_name == "BAAI/bge-small-zh-v1.5"

    def test_default_model_when_not_configured(self):
        settings = Settings(deepseek_api_key="sk-test")
        from src.adapters.embedding import LocalEmbeddingProvider
        provider = LocalEmbeddingProvider(settings)
        assert provider._model_name == "BAAI/bge-small-zh-v1.5"


class TestGetEmbedding:
    def test_lazy_loads_model_on_first_call(self, settings):
        mock_instance = _make_mock_st()
        with patch("sentence_transformers.SentenceTransformer", return_value=mock_instance) as mock_st:
            from src.adapters.embedding import LocalEmbeddingProvider
            provider = LocalEmbeddingProvider(settings)
            result = provider.get_embedding("测试文本")

            mock_st.assert_called_once_with("BAAI/bge-small-zh-v1.5")
            mock_instance.encode.assert_called_once_with(
                "测试文本", normalize_embeddings=True, show_progress_bar=False
            )
            assert result == [0.1, 0.2, 0.3]

    def test_loads_model_only_once(self, settings):
        mock_instance = _make_mock_st()
        with patch("sentence_transformers.SentenceTransformer", return_value=mock_instance) as mock_st:
            from src.adapters.embedding import LocalEmbeddingProvider
            provider = LocalEmbeddingProvider(settings)
            provider.get_embedding("第一次")
            provider.get_embedding("第二次")

            assert mock_st.call_count == 1

    def test_embedding_returns_list_of_float(self, settings):
        mock_instance = _make_mock_st()
        with patch("sentence_transformers.SentenceTransformer", return_value=mock_instance):
            from src.adapters.embedding import LocalEmbeddingProvider
            provider = LocalEmbeddingProvider(settings)
            result = provider.get_embedding("测试")

            assert isinstance(result, list)
            assert all(isinstance(x, float) for x in result)

    def test_empty_text_raises_value_error(self, settings):
        from src.adapters.embedding import LocalEmbeddingProvider
        provider = LocalEmbeddingProvider(settings)
        with pytest.raises(ValueError, match="不能为空"):
            provider.get_embedding("")


class TestThreadSafety:
    def test_concurrent_first_calls_load_once(self, settings):
        """多线程首次调用只加载一次模型。"""
        load_count = 0
        lock = threading.Lock()

        def mock_load(model_name):
            nonlocal load_count
            with lock:
                load_count += 1
            return _make_mock_st()

        with patch("sentence_transformers.SentenceTransformer", side_effect=mock_load):
            from src.adapters.embedding import LocalEmbeddingProvider
            provider = LocalEmbeddingProvider(settings)
            threads = [
                threading.Thread(target=provider.get_embedding, args=(f"文本{i}",))
                for i in range(10)
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            assert load_count == 1


class TestDimension:
    def test_returns_model_dimension(self, settings):
        mock_instance = _make_mock_st()
        with patch("sentence_transformers.SentenceTransformer", return_value=mock_instance):
            from src.adapters.embedding import LocalEmbeddingProvider
            provider = LocalEmbeddingProvider(settings)
            provider.get_embedding("触发加载")

            assert provider.dimension == 512
