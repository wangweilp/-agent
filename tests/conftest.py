"""pytest 共享 fixtures。"""
import pytest

from src.adapters.config import Settings


@pytest.fixture(autouse=True)
def _disable_dev_auth_for_tests(monkeypatch):
    """全局关闭 dev auth 注入。

    安全原因：测试环境不应自动注入 dev admin token。
    无 token 请求必须返回 401，这是安全测试的基础前提。
    需要 dev auth 的特定测试可以通过 monkeypatch.delenv 恢复。
    """
    monkeypatch.setenv("DISABLE_DEV_AUTH", "true")


@pytest.fixture
def settings():
    """提供测试用 Settings 实例。"""
    return Settings(deepseek_api_key="sk-test")
