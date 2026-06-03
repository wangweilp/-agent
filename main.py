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
from src.adapters.auth_store import SQLiteAuthStore, WorkspaceContext
from src.adapters.collab_store import CollabStore, CollaborationService
from src.api.audio import create_audio_router
from src.api.auth_router import create_auth_router
from src.api.dashboard import create_dashboard_router
from src.api.graph import create_graph_router
from src.api.middleware import JWTTokenService, init_auth
from src.api.routes import create_router
from src.api.timeline import create_timeline_router
from src.api.upload import create_upload_router
from src.api.video import create_video_router
from src.api.workspace_router import create_workspace_router
from src.api.analytics_router import create_analytics_router
from src.api.agent_collab_router import create_agent_collab_router
from src.api.import_router import create_import_router
from src.adapters.collab_adapter import DefaultMultiAgentCoordinator
from src.core.agent import CognitiveAgent
from src.core.import_worker import ImportWorker
from src.core.memory_queue import MemoryWriteWorker
from src.core.retrieval import MemoryRetrievalService
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


def create_agent(settings: Settings) -> tuple[CognitiveAgent, MemoryWriteWorker, DeepSeekAdapter]:
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

    memory_writer = MemoryWriteWorker(settings, embedding_provider=embedding)
    agent = CognitiveAgent(
        llm=llm,
        memory_store=memory_store,
        vector_store=vector_store,
        embedding_provider=embedding,
        tool_executor=tool_registry,
        memory_writer=memory_writer,
    )
    memory_writer.start()
    logger.info("memory_writer 线程已启动")
    return agent, memory_writer, llm


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("服务启动")
    yield
    logger.info("服务关闭，等待后台任务刷盘...")
    import_worker.shutdown()
    agent.shutdown()


settings = bootstrap()
agent, memory_writer, llm = create_agent(settings)

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

# ── SaaS Multi-Tenant + Team Collaboration Bootstrap ──
auth_store = SQLiteAuthStore(settings)
token_service = JWTTokenService()
init_auth(token_service, auth_store)
collab_store = CollabStore(settings)
collab_service = CollaborationService(collab_store, auth_store)

app.include_router(create_router(agent))
app.include_router(create_dashboard_router(agent, memory_writer))
app.include_router(create_timeline_router(agent))
app.include_router(create_graph_router(agent))
app.include_router(create_audio_router(settings, llm, memory_writer, agent))
app.include_router(create_video_router(settings, llm, memory_writer, agent))
app.include_router(create_upload_router(settings, llm, memory_writer, agent))
app.include_router(create_auth_router(token_service, auth_store))
app.include_router(create_workspace_router(collab_service, auth_store, agent))
app.include_router(create_analytics_router(collab_service, agent))

# ── Multi-Agent Collaboration Router ──
retrieval_service = MemoryRetrievalService(
    agent._memory_store, agent._vector_store, agent._embedding,
)
agent_collab_coordinator = DefaultMultiAgentCoordinator(
    collab_service=collab_service,
    auth_store=auth_store,
    retrieval_service=retrieval_service,
    tool_registry=ToolRegistry(
        memory_store=agent._memory_store,
        vector_store=agent._vector_store,
        embedding_provider=agent._embedding,
        llm=llm,
    ),
)
app.include_router(create_agent_collab_router(agent_collab_coordinator))

# ── Import Hub ──
import_worker = ImportWorker(settings, memory_writer=memory_writer, embedding_provider=agent._embedding)
import_worker.start()
logger.info("import_worker 线程已启动")

app.include_router(create_import_router(settings, llm, memory_writer, import_worker, agent))


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
