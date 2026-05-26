"""Agent Memory 应用入口 — 加载配置、组装依赖、启动 API/CLI。"""
import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.adapters.config import Settings
from src.adapters.embedding import LocalEmbeddingProvider
from src.adapters.llm import DeepSeekAdapter
from src.adapters.sqlite_store import SQLiteStoreAdapter
from src.adapters.vector_store import ChromaDBAdapter
from src.api.routes import create_router
from src.core.agent import CognitiveAgent
from src.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


def bootstrap() -> Settings:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stderr,
    )
    settings = Settings()  # type: ignore[call-arg]
    logger.info("Agent Memory 启动完成")
    return settings


def create_agent(settings: Settings) -> CognitiveAgent:
    llm = DeepSeekAdapter(settings)
    memory_store = SQLiteStoreAdapter(settings)
    vector_store = ChromaDBAdapter(settings)
    embedding = LocalEmbeddingProvider(settings)

    tool_registry = ToolRegistry(
        memory_store=memory_store,
        vector_store=vector_store,
        embedding_provider=embedding,
        llm=llm,
    )

    return CognitiveAgent(
        llm=llm,
        memory_store=memory_store,
        vector_store=vector_store,
        embedding_provider=embedding,
        tool_executor=tool_registry,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("服务启动")
    yield
    logger.info("服务关闭")


def create_app(settings: Settings | None = None) -> FastAPI:
    if settings is None:
        settings = bootstrap()

    agent = create_agent(settings)
    router = create_router(agent)

    app = FastAPI(
        title="Agent Memory API",
        description="个人知识助手 — AI Second Brain",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.include_router(router)
    return app


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Agent Memory — AI Second Brain")
    parser.add_argument("--cli", action="store_true", help="以 CLI 交互模式运行")
    parser.add_argument("--host", default="127.0.0.1", help="API 服务器地址")
    parser.add_argument("--port", type=int, default=8000, help="API 服务器端口")
    args = parser.parse_args()

    settings = bootstrap()

    if args.cli:
        from src.tools.cli import run_cli

        agent = create_agent(settings)
        run_cli(agent)
    else:
        import uvicorn

        app = create_app(settings)
        uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
