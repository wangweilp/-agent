"""pytest 共享 fixtures。"""
import pytest

from src.adapters.config import Settings


@pytest.fixture
def settings():
    """提供测试用 Settings 实例。"""
    return Settings(deepseek_api_key="sk-test")
