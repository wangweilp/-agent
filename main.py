"""Agent Memory 应用入口。

启动方式：
    uvicorn main:app --reload --host 0.0.0.0 --port 8000
    python main.py --cli          # CLI 交互模式
"""
import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.adapters.config import Settings
from src.adapters.embedding import LocalEmbeddingProvider
from src.adapters.llm import DeepSeekAdapter
from src.adapters.sqlite_store import SQLiteStoreAdapter
from src.adapters.vector_store import ChromaDBAdapter
from src.api.dashboard import create_dashboard_router
from src.api.routes import create_router
from src.core.agent import CognitiveAgent
from src.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


def bootstrap() -> Settings:
    logging.basicConfig(
        level=logging.INFO,
        format=(
            "%(asctime)s.%(msecs)03d "
            "%(levelname)s "
            "[%(name)s] "
            "%(message)s"
        ),
        datefmt="%Y-%m-%dT%H:%M:%S",
        stream=sys.stderr,
    )
    settings = Settings()  # type: ignore[call-arg]
    logger.info("服务启动完成", extra={"event": "bootstrap_complete"})
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


settings = bootstrap()
agent = create_agent(settings)

# 预加载 embedding 模型，避免首次请求阻塞
agent._embedding.warmup()

app = FastAPI(
    title="Agent Memory API",
    description="个人知识助手 — AI Second Brain",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(create_router(agent))
app.include_router(create_dashboard_router(agent))


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Agent Memory — AI Second Brain")
    parser.add_argument("--cli", action="store_true", help="以 CLI 交互模式运行")
    args = parser.parse_args()

    if args.cli:
        from src.tools.cli import run_cli

        run_cli(agent)
    else:
        import uvicorn

        uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
