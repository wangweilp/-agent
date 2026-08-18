"""pytest 共享 fixtures。"""
import pytest

from src.adapters.config import Settings

# smoke_test.py 是独立运行脚本（python tests/smoke_test.py），不是 pytest 用例。
# 且其函数名以 test_ 开头、文件名匹配 *_test.py，会被 pytest 默认收集。
# 排除：避免其加载 embedding 模型 / os.chdir / 写真实 Settings 污染测试进程
# 全局状态（Test Isolation）。
collect_ignore = ["smoke_test.py"]


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
