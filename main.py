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
from src.adapters.org_store import OrganizationStoreAdapter
from src.adapters.rbac_store import RBACStoreAdapter
from src.adapters.compliance_store import ComplianceStoreAdapter
from src.api.audio import create_audio_router
from src.api.auth_router import create_auth_router
from src.api.dashboard import create_dashboard_router
from src.api.graph import create_graph_router
from src.api.middleware import JWTTokenService, init_auth, AuthMiddleware
from src.api.rate_limit import RateLimitMiddleware
from src.api.routes import create_router
from src.api.timeline import create_timeline_router
from src.api.upload import create_upload_router
from src.api.video import create_video_router
from src.api.workspace_router import create_workspace_router
from src.api.analytics_router import create_analytics_router
from src.api.agent_collab_router import create_agent_collab_router
from src.api.import_router import create_import_router
from src.api.org_router import create_org_router
from src.api.rbac_router import create_rbac_router
from src.api.audit_router import create_audit_router
from src.api.compliance_router import create_compliance_router
from src.adapters.billing_store import BillingStoreAdapter
from src.adapters.growth_store import GrowthStoreAdapter
from src.adapters.payment_gateway import PaymentGatewayRegistry
from src.adapters.subscription_store import SubscriptionStoreAdapter
from src.adapters.tenant_store import TenantStoreAdapter
from src.adapters.usage_store import UsageStoreAdapter
from src.adapters.collab_adapter import DefaultMultiAgentCoordinator
from src.adapters.alert_store import AlertStoreAdapter
from src.adapters.report_store import ReportStoreAdapter
from src.adapters.usage_collector import UsageCollector
from src.api.alert_router import create_alert_router
from src.api.admin_router import create_admin_router
from src.api.billing_router import create_billing_router
from src.api.growth_router import create_growth_router
from src.api.report_router import create_report_router
from src.api.subscription_router import create_subscription_router
from src.api.tenant_router import create_tenant_router
from src.api.usage_router import create_usage_router
from src.api.growth_analytics_router import create_growth_analytics_router
from src.core.agent import CognitiveAgent
from src.core.import_worker import ImportWorker
from src.core.import_pipeline import ImportMemoryPipeline
from src.core.consolidation import DefaultMemoryConsolidator
from src.core.memory_lifecycle import MemoryLifecycleManager
from src.core.memory_queue import MemoryWriteWorker
from src.core.retrieval import MemoryRetrievalService
from src.tools.registry import ToolRegistry

# ── Step 20: Enterprise AI Agent Platform ──
from src.agents.registry import AgentRegistry
from src.agents.workflow import (
    WorkflowEngine,
    create_meeting_to_training_workflow,
    create_research_to_report_workflow,
)
from src.agents.builtin.knowledge_agent import create_knowledge_agent
from src.agents.builtin.meeting_agent import create_meeting_agent
from src.agents.builtin.research_agent import create_research_agent
from src.agents.builtin.sales_agent import create_sales_agent
from src.agents.builtin.support_agent import create_support_agent
from src.agents.builtin.training_agent import create_training_agent
from src.agents.department import (
    RDAgent, ProductAgent, OperationsAgent,
    SalesDeptAgent, HRAgent, CustomerServiceAgent,
)
from src.api.agent_router import create_agent_router

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
    logging.getLogger().setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
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
    usage_collector.shutdown()
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

# 中间件层：RateLimit → CORS → Auth（从外到内）
# Starlette add_middleware 使用 insert(0)，先添加的在底层，后添加的在外层
app.add_middleware(AuthMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RateLimitMiddleware, max_requests=30, window_seconds=60.0)

# ── SaaS Multi-Tenant + Team Collaboration Bootstrap ──
auth_store = SQLiteAuthStore(settings)
token_service = JWTTokenService(secret_key=settings.jwt_secret_key, auth_store=auth_store)
init_auth(token_service, auth_store)

# ── Super Admin Auto-Create（从环境变量） ──
if settings.admin_email and settings.admin_password:
    admin_user = auth_store.ensure_super_admin(
        email=settings.admin_email,
        password=settings.admin_password,
    )
    if admin_user:
        logger.info("super_admin_ready",
                    extra={"user_id": admin_user.id, "email": admin_user.email})
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
import_worker = ImportWorker(settings, memory_writer=memory_writer)
import_worker.start()
logger.info("import_worker 线程已启动")

app.include_router(create_import_router(settings, llm, memory_writer, import_worker, agent))

# ── Sync Hub ──
from src.sync.sync_store import SyncStore
from src.sync.sync_worker import SyncWorker
from src.sync.scheduler import SyncScheduler
from src.sync.sync_pipeline import SyncPipeline
from src.api.sync_router import create_sync_router

# Build the ImportMemoryPipeline that SyncPipeline reuses
lifecycle_manager = MemoryLifecycleManager(agent._memory_store)
consolidator = DefaultMemoryConsolidator(
    memory_store=agent._memory_store,
    vector_store=agent._vector_store,
    embedding_provider=agent._embedding,
    llm=llm,
)
import_pipeline = ImportMemoryPipeline(
    memory_store=agent._memory_store,
    vector_store=agent._vector_store,
    embedding_provider=agent._embedding,
    memory_writer=memory_writer,
    lifecycle_manager=lifecycle_manager,
    consolidator=consolidator,
    llm=llm,
)

sync_store = SyncStore(settings)
sync_pipeline = SyncPipeline(import_pipeline)

# ── Local folder allowlist (security boundary) ──
from src.sync.connectors.local_folder_connector import configure_local_folder_allowlist
configure_local_folder_allowlist(
    allowed_roots=settings.sync_local_folder_allowed_roots,
    max_file_bytes=settings.sync_local_folder_max_file_bytes,
)
logger.info(
    "sync_local_folder_allowlist_configured",
    extra={"roots": settings.sync_local_folder_allowed_roots},
)

sync_worker = SyncWorker(sync_store, sync_pipeline)
sync_scheduler = SyncScheduler(sync_store, sync_worker)

sync_worker.start()
sync_scheduler.start()
logger.info("sync_worker + sync_scheduler 线程已启动")

app.include_router(create_sync_router(sync_store, sync_worker, sync_scheduler))

# ── Step 18: Enterprise Brain ──
org_store = OrganizationStoreAdapter(settings)
rbac_store = RBACStoreAdapter(settings)
compliance_store = ComplianceStoreAdapter(settings)

app.include_router(create_org_router(org_store, auth_store, rbac_store))
app.include_router(create_rbac_router(rbac_store, org_store, auth_store))
app.include_router(create_audit_router(collab_store))
app.include_router(create_compliance_router(compliance_store, org_store))
app.include_router(create_admin_router(settings, org_store, auth_store, collab_store, agent._memory_store))

# ── Step 19: SaaS Platform ──
billing_store = BillingStoreAdapter(settings)
subscription_store = SubscriptionStoreAdapter(settings)
usage_store = UsageStoreAdapter(settings)
tenant_store = TenantStoreAdapter(settings)
growth_store = GrowthStoreAdapter(settings)
payment_gateway = PaymentGatewayRegistry()

app.include_router(create_billing_router(billing_store, payment_gateway))
app.include_router(create_subscription_router(subscription_store, usage_store, billing_store))
app.include_router(create_usage_router(usage_store, subscription_store, billing_store))
app.include_router(create_tenant_router(tenant_store, billing_store, subscription_store, growth_store))
app.include_router(create_growth_router(growth_store, subscription_store, billing_store))

logger.info("saas platform routers registered",
            extra={"event": "saas_platform_bootstrap_complete"})

# ── Step 19.5: Growth & Analytics Center ──
alert_store = AlertStoreAdapter(settings)
report_store = ReportStoreAdapter(settings)

usage_collector = UsageCollector(
    usage_store=usage_store,
    alert_store=alert_store,
    subscription_store=subscription_store,
    memory_store=agent._memory_store,
)
usage_collector.start()
logger.info("usage_collector 后台线程已启动",
            extra={"event": "usage_collector_started"})

app.include_router(create_alert_router(alert_store, usage_store))
app.include_router(create_report_router(report_store, usage_store, subscription_store))
app.include_router(create_growth_analytics_router(usage_store, subscription_store))

logger.info("growth & analytics center routers registered",
            extra={"event": "growth_analytics_bootstrap_complete"})

logger.info("enterprise brain routers registered",
            extra={"event": "enterprise_brain_bootstrap_complete"})

# ═══════════════════════════════════════════
# Step 20: Enterprise AI Agent Platform
# ═══════════════════════════════════════════

# Runtime memory adapter — 将 agent._memory_store 等包装为 Agent Runtime 可用的协议
from src.agents.runtime import MemoryProvider, KnowledgeGraphProvider, MemoryResult, GraphEntity, GraphRelation

class _AgentMemoryProvider:
    """将现有 CognitiveAgent 的记忆能力适配为 Agent Runtime MemoryProvider。"""
    def __init__(self, memory_store, vector_store, embedding):
        self._ms = memory_store
        self._vs = vector_store
        self._emb = embedding

    def search(self, query: str, top_k: int = 5) -> list[MemoryResult]:
        from src.core.retrieval import MemoryRetrievalService
        svc = MemoryRetrievalService(self._ms, self._vs, self._emb)
        memories = svc.retrieve(query, top_k=top_k)
        return [
            MemoryResult(memory_id=m.id, content=m.content, score=1.0, metadata={"source": m.source})
            for m in memories
        ]

    def remember(self, content: str, metadata: dict | None = None) -> str:
        from src.core.types import Memory
        from datetime import datetime, timezone
        m = Memory(content=content, source=metadata.get("source", "agent") if metadata else "agent")
        self._ms.save(m)
        try:
            emb = self._emb.encode(content)
            self._vs.add(m.id, emb, {"memory_id": m.id})
        except Exception:
            pass
        return m.id


class _AgentKGProvider:
    """知识图谱提供者适配。"""
    def __init__(self, memory_store):
        self._ms = memory_store

    def query_entities(self, query: str, top_k: int = 10) -> list[GraphEntity]:
        try:
            rows = self._ms.db.query(
                "SELECT * FROM entities WHERE name LIKE ? LIMIT ?",
                [f"%{query}%", top_k],
            )
            return [GraphEntity(id=str(r["id"]), name=r["name"], entity_type=r.get("entity_type", "")) for r in rows]
        except Exception:
            return []

    def query_relations(self, entity_id: str) -> list[GraphRelation]:
        try:
            rows = self._ms.db.query(
                "SELECT * FROM relations WHERE subject_id = ? OR object_id = ? LIMIT 20",
                [entity_id, entity_id],
            )
            return [GraphRelation(source=str(r["subject_id"]), target=str(r["object_id"]), predicate=r.get("predicate", "related")) for r in rows]
        except Exception:
            return []

    def traverse(self, start_id: str, depth: int = 2) -> dict:
        entities = set()
        relations = []
        frontier = {start_id}
        for _ in range(depth):
            if not frontier:
                break
            for eid in list(frontier):
                rels = self.query_relations(eid)
                relations.extend(rels)
                for r in rels:
                    frontier.add(r.target)
                    entities.add(r.target)
        return {"entities": list(entities), "relations": [{"source": r.source, "target": r.target, "predicate": r.predicate} for r in relations]}


agent_memory_provider = _AgentMemoryProvider(
    agent._memory_store, agent._vector_store, agent._embedding
)
agent_kg_provider = _AgentKGProvider(agent._memory_store)

# 创建 AgentRegistry
agent_registry = AgentRegistry()
agent_registry.set_providers(
    memory=agent_memory_provider,
    kg=agent_kg_provider,
)

# 注册内置 Agent
agent_registry.register(create_knowledge_agent(
    memory=agent_memory_provider,
    knowledge_graph=agent_kg_provider,
))
agent_registry.register(create_meeting_agent(
    memory=agent_memory_provider,
    knowledge_graph=agent_kg_provider,
))
agent_registry.register(create_research_agent(
    memory=agent_memory_provider,
    knowledge_graph=agent_kg_provider,
))
agent_registry.register(create_sales_agent(
    memory=agent_memory_provider,
    knowledge_graph=agent_kg_provider,
))
agent_registry.register(create_support_agent(
    memory=agent_memory_provider,
    knowledge_graph=agent_kg_provider,
))
agent_registry.register(create_training_agent(
    memory=agent_memory_provider,
    knowledge_graph=agent_kg_provider,
))

# 注册部门 Agent
for dept_cls in [RDAgent, ProductAgent, OperationsAgent, SalesDeptAgent, HRAgent, CustomerServiceAgent]:
    agent_registry.register(dept_cls(
        memory=agent_memory_provider,
        knowledge_graph=agent_kg_provider,
    ))

# 创建 WorkflowEngine 并注册预置工作流
workflow_engine = WorkflowEngine(agent_registry)
try:
    workflow_engine.register_workflow(create_meeting_to_training_workflow())
    logger.info("preset_workflow_registered", extra={"workflow_name": "meeting_to_training"})
except Exception as e:
    logger.warning("preset_workflow_register_failed", extra={"error": str(e)})

try:
    workflow_engine.register_workflow(create_research_to_report_workflow())
    logger.info("preset_workflow_registered", extra={"workflow_name": "research_to_report"})
except Exception as e:
    logger.warning("preset_workflow_register_failed", extra={"error": str(e)})

# 注册 Agent API 路由
app.include_router(create_agent_router(agent_registry, workflow_engine))

logger.info("enterprise_agent_platform_bootstrap_complete",
            extra={"event": "agent_platform_ready",
                   "builtin_agents": len(agent_registry)})


def main() -> None:
    import argparse
    import getpass

    parser = argparse.ArgumentParser(description="Agent Memory — AI Second Brain")
    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # 子命令: create-admin
    create_admin_parser = subparsers.add_parser(
        "create-admin", help="交互式创建超级管理员账号"
    )
    create_admin_parser.add_argument(
        "--email", type=str, default=None,
        help="管理员邮箱（不提供则交互输入）"
    )
    create_admin_parser.add_argument(
        "--name", type=str, default="Super Admin",
        help="管理员显示名称"
    )
    create_admin_parser.add_argument(
        "--password", type=str, default=None,
        help="管理员密码（不提供则交互输入）"
    )

    # 兼容旧用法: --cli
    parser.add_argument("--cli", action="store_true", help="以 CLI 交互模式运行")

    args = parser.parse_args()

    if args.command == "create-admin":
        _cmd_create_admin(args)
    elif args.cli:
        from src.tools.cli import run_cli

        run_cli(agent)
    else:
        import uvicorn

        uvicorn.run(app, host="0.0.0.0", port=8000)


def _cmd_create_admin(args) -> None:
    """CLI: python main.py create-admin — 交互式创建超级管理员账号。"""
    import getpass

    email: str = args.email or ""
    while not email or "@" not in email:
        if not args.email:
            email = input("管理员邮箱: ").strip()
        else:
            break

    name: str = args.name or "Super Admin"

    # 密码：优先用 --password 参数，否则交互式输入
    password: str = args.password or ""
    if not password:
        while len(password) < 6:
            password = getpass.getpass("管理员密码 (最少6位): ")
            if len(password) < 6:
                print("密码长度不足 6 位，请重新输入")

        password_confirm: str = getpass.getpass("确认密码: ")
        if password != password_confirm:
            print("错误: 两次密码不一致")
            return

    # 创建/更新超级管理员
    auth_store = SQLiteAuthStore(settings)
    try:
        user = auth_store.ensure_super_admin(email=email, password=password, name=name)
        if user is None:
            print("错误: 创建失败")
            return
        print(f"\n✓ 超级管理员已就绪")
        print(f"  用户ID: {user.id}")
        print(f"  邮箱:   {user.email}")
        print(f"  名称:   {user.name}")
        print(f"  角色:   super_admin (拥有所有权限)")
    finally:
        auth_store.close()


if __name__ == "__main__":
    main()
