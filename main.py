"""Agent Memory 应用入口。"""
import logging
import sys

from src.adapters.config import Settings


def bootstrap() -> Settings:
    """初始化日志、加载配置，返回冻结的 Settings 实例。

    应在应用启动时最先调用。
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stderr,
    )
    settings = Settings()  # type: ignore[call-arg]
    logging.getLogger(__name__).info("Agent Memory 启动完成")
    return settings


def create_app(settings: Settings | None = None):
    """创建并返回 FastAPI 应用实例（预留）。"""
    if settings is None:
        settings = bootstrap()
    # TODO: 后续阶段在此组装路由和中间件
    return settings
