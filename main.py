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
from src.core.account_entitlements import ensure_workspace_account_entitlements
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
auth_store.flush()
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
entitlement_result = ensure_workspace_account_entitlements(
    auth_store=auth_store,
    tenant_store=tenant_store,
    subscription_store=subscription_store,
    billing_store=billing_store,
)
logger.info(
    "workspace_account_entitlements_ready",
    extra={"event": "workspace_account_entitlements_ready", **entitlement_result.__dict__},
)

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

# 注入 Agent Metrics Store（对接 UsageStore 持久化）
from src.agents.metrics import InMemoryAgentMetricsStore
agent_metrics_store = InMemoryAgentMetricsStore(usage_store=usage_store)
agent_registry.set_metrics_store(agent_metrics_store)

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

# 注册 Agent API 路由（含 Scenario Engine）
from src.agents.scenarios import ScenarioEngine
scenario_engine = ScenarioEngine(agent_registry, workflow_engine)
app.include_router(create_agent_router(agent_registry, workflow_engine, scenario_engine))

logger.info("enterprise_agent_platform_bootstrap_complete",
            extra={"event": "agent_platform_ready",
                   "builtin_agents": len(agent_registry)})

# ═══════════════════════════════════════════
# Step 21-C: Agent Marketplace API
# ═══════════════════════════════════════════

# 初始化 MarketplaceStore
from src.adapters.marketplace_store import SQLiteMarketplaceStore
from src.agents.marketplace import seed_builtin_marketplace_agents

marketplace_store = SQLiteMarketplaceStore(settings)
logger.info("marketplace_store_initialized")

# Seed 内置 Marketplace Agent catalog（幂等）
try:
    created = seed_builtin_marketplace_agents(marketplace_store)
    logger.info("marketplace_seed_complete", extra={"created_count": created})
except Exception:
    logger.exception("marketplace_seed_failed")

# 确保 seed 事务提交，释放写锁，避免阻塞后续 store 初始化
marketplace_store.flush()
logger.debug("marketplace_store_flushed")

# 注册 Marketplace API 路由
from src.api.marketplace_router import create_marketplace_router
app.include_router(create_marketplace_router(marketplace_store, usage_store, subscription_store))

logger.info("marketplace_api_registered",
            extra={"event": "marketplace_api_ready"})

# ═══════════════════════════════════════════
# Step 22: Open Platform — Developer API
# ═══════════════════════════════════════════

# 初始化 Open Platform Stores
from src.adapters.developer_store import SQLiteDeveloperStore
from src.adapters.submission_store import SQLiteSubmissionStore

developer_store = SQLiteDeveloperStore(settings)
logger.info("developer_store_initialized")

submission_store = SQLiteSubmissionStore(settings)
logger.info("submission_store_initialized")

# ═══════════════════════════════════════════
# Step 23-C: Runtime Store Bootstrap
# ═══════════════════════════════════════════

from src.adapters.runtime_store import SQLiteRuntimeStore

runtime_store = SQLiteRuntimeStore(settings)
logger.info("runtime_store_initialized")

# Seed 内置 Runtime Adapters（幂等）
try:
    created = runtime_store.seed_builtin_adapters()
    logger.info("runtime_adapters_seeded", extra={"created_count": created})
except Exception:
    logger.exception("runtime_adapters_seed_failed")

runtime_store.flush()
logger.debug("runtime_store_flushed")

# ═══════════════════════════════════════════
# Step 23-D: Simulation Runtime Service
# ═══════════════════════════════════════════

from src.open_platform.simulation_runtime import SimulationRuntimeService

simulation_service = SimulationRuntimeService(
    marketplace_store=marketplace_store,
    runtime_store=runtime_store,
    usage_store=usage_store,
)
logger.info("simulation_runtime_service_initialized")

# 注册 Developer API 路由
from src.api.developer_router import create_developer_router
app.include_router(create_developer_router(
    developer_store, submission_store, usage_store,
    marketplace_store=marketplace_store,
    runtime_store=runtime_store,
    simulation_service=simulation_service,
))

logger.info("developer_api_registered",
            extra={"event": "developer_api_ready"})

# ═══════════════════════════════════════════
# Step 23-E: Sandbox Policy Store + Admin API
# ═══════════════════════════════════════════

from src.adapters.sandbox_policy_store import SQLiteSandboxPolicyStore

sandbox_policy_store = SQLiteSandboxPolicyStore(settings)
logger.info("sandbox_policy_store_initialized")

try:
    created = sandbox_policy_store.seed_builtin_policies()
    logger.info("sandbox_policies_seeded", extra={"created_count": created})
except Exception:
    logger.exception("sandbox_policies_seed_failed")

sandbox_policy_store.flush()
logger.debug("sandbox_policy_store_flushed")

from src.api.sandbox_policy_router import create_sandbox_policy_router
app.include_router(create_sandbox_policy_router(
    sandbox_policy_store,
    runtime_store=runtime_store,
    usage_store=usage_store,
))
logger.info("sandbox_policy_api_registered")

# ═══════════════════════════════════════════
# Step 23-G: Runtime Admin API
# ═══════════════════════════════════════════

from src.adapters.runtime_safety_store import SQLiteRuntimeSafetyStore
from src.adapters.package_download_worker_store import SQLitePackageDownloadWorkerStore
from src.adapters.artifact_materialization_store import SQLiteArtifactMaterializationStore
from src.adapters.sandbox_execution_store import SQLiteSandboxExecutionStore
from src.adapters.production_sandbox_gate_store import SQLiteProductionSandboxGateStore
from src.open_platform.runtime_safety_service import RuntimeSafetyService
from src.open_platform.package_download_worker_service import PackageDownloadWorkerService
from src.open_platform.artifact_materialization_service import ArtifactMaterializationService

runtime_safety_store = SQLiteRuntimeSafetyStore(settings)
runtime_safety_service = RuntimeSafetyService(store=runtime_safety_store, usage_store=usage_store)
package_download_worker_store = SQLitePackageDownloadWorkerStore(settings)
package_download_worker_service = PackageDownloadWorkerService(
    store=package_download_worker_store,
    runtime_safety_store=runtime_safety_store,
    usage_store=usage_store,
)
artifact_materialization_store = SQLiteArtifactMaterializationStore(settings)
artifact_materialization_service = ArtifactMaterializationService(
    store=artifact_materialization_store,
    package_download_worker_store=package_download_worker_store,
    runtime_safety_store=runtime_safety_store,
    usage_store=usage_store,
)
sandbox_execution_store = SQLiteSandboxExecutionStore(settings)
production_sandbox_gate_store = SQLiteProductionSandboxGateStore(settings)

try:
    if not runtime_safety_store.list_policies(scope="global_runtime"):
        runtime_safety_service.create_default_kill_switch_policy(created_by="system")
    if not package_download_worker_store.list_policies(scope="global"):
        package_download_worker_service.create_disabled_worker_policy(created_by="system")
    if not artifact_materialization_store.list_policies(scope="global"):
        artifact_materialization_service.create_disabled_materialization_policy(created_by="system")
except Exception:
    logger.exception("runtime_governance_control_plane_seed_failed")

from src.api.runtime_admin_router import create_runtime_admin_router
app.include_router(create_runtime_admin_router(
    runtime_store=runtime_store,
    marketplace_store=marketplace_store,
    sandbox_policy_store=sandbox_policy_store,
    usage_store=usage_store,
    runtime_safety_store=runtime_safety_store,
    package_download_worker_store=package_download_worker_store,
    artifact_materialization_store=artifact_materialization_store,
    sandbox_execution_store=sandbox_execution_store,
    production_sandbox_gate_store=production_sandbox_gate_store,
))
logger.info("runtime_admin_api_registered")

# ═══════════════════════════════════════════
# Step 23-F: Package Validation
# ═══════════════════════════════════════════

from src.adapters.package_validation_store import SQLitePackageValidationStore
from src.open_platform.package_validation_service import PackageValidationService

pv_store = SQLitePackageValidationStore(settings)
logger.info("package_validation_store_initialized")

pv_service = PackageValidationService(
    pv_store=pv_store,
    submission_store=submission_store,
    developer_store=developer_store,
    usage_store=usage_store,
)
logger.info("package_validation_service_initialized")

# 注册 Admin Review API 路由
from src.api.admin_submission_router import create_admin_submission_router
app.include_router(create_admin_submission_router(
    developer_store, submission_store, usage_store,
    marketplace_store=marketplace_store, pv_service=pv_service,
))

logger.info("admin_review_api_registered",
            extra={"event": "admin_review_api_ready"})

# ═══════════════════════════════════════════
# Step 24-H: Runtime Execution API (admin gated)
# ═══════════════════════════════════════════

from src.open_platform.runtime_execution_planner import RuntimeExecutionPlannerService
from src.open_platform.policy_enforcement_translator import SandboxPolicyEnforcementTranslator
from src.open_platform.sandbox_worker_registry import create_default_sandbox_worker_registry
from src.adapters.runtime_execution_plan_store import SQLiteRuntimeExecutionPlanStore

# Initialize runtime execution plan store
runtime_plan_store = SQLiteRuntimeExecutionPlanStore(settings)
logger.info("runtime_plan_store_initialized")

# Runtime execution planner service
runtime_planner = RuntimeExecutionPlannerService(
    plan_store=runtime_plan_store,
    marketplace_store=marketplace_store,
    runtime_store=runtime_store,
    sandbox_policy_store=sandbox_policy_store,
    artifact_store=None,  # artifact store not yet initialized here; plan checks skip unavailable stores
    verification_store=None,
    usage_store=usage_store,
)
logger.info("runtime_planner_initialized")

# Policy enforcement translator
policy_translator = SandboxPolicyEnforcementTranslator()
logger.info("policy_translator_initialized")

# Worker registry (disabled by default)
worker_registry = create_default_sandbox_worker_registry(enable_local_dev_dry_run=False)
logger.info("worker_registry_initialized")

# Register runtime execution API router
from src.api.runtime_execution_router import create_runtime_execution_router
app.include_router(create_runtime_execution_router(
    plan_store=runtime_plan_store,
    planner_service=runtime_planner,
    marketplace_store=marketplace_store,
    runtime_store=runtime_store,
    sandbox_policy_store=sandbox_policy_store,
    artifact_store=None,
    verification_store=None,
    policy_translator=policy_translator,
    worker_registry=worker_registry,
    usage_store=usage_store,
))

logger.info("runtime_execution_api_registered",
            extra={"event": "runtime_execution_api_ready"})

# ═══════════════════════════════════════════
# Sandbox v2 Core Contract — Step 1
# ═══════════════════════════════════════════

from src.adapters.sqlite_sandbox_v2_store import SQLiteSandboxV2Store
from src.adapters.sqlite_sandbox_v2_queue import SQLiteSandboxV2Queue
from src.open_platform.sandbox_v2.service import SandboxV2Service
from src.open_platform.sandbox_v2.worker import SandboxV2Worker
from src.open_platform.sandbox_v2.artifacts import LocalSandboxArtifactStore
from src.open_platform.sandbox_v2.packages import LocalSandboxPackageQuarantineStore
from src.open_platform.sandbox_v2.network import SandboxNetworkEgressService
from src.open_platform.sandbox_v2.execution_provider import create_default_provider_registry
from src.open_platform.sandbox_v2.container_provider import RootlessContainerExecutionProvider, SandboxContainerRuntimeConfig
from src.open_platform.sandbox_v2.models import SandboxV2IsolationProvider, SandboxV2ContainerRuntime
from src.open_platform.sandbox_v2.kill_switch import SandboxKillSwitchService
from src.api.sandbox_v2 import create_sandbox_v2_router
import shutil, platform as _plat

sandbox_v2_store = SQLiteSandboxV2Store(settings)
logger.info("sandbox_v2_store_initialized")

sandbox_v2_queue = SQLiteSandboxV2Queue(settings)
logger.info("sandbox_v2_queue_initialized")

sandbox_v2_artifact_store = LocalSandboxArtifactStore(
    artifact_root=getattr(settings, "sandbox_v2_artifact_root", ".sandbox_v2_artifacts"),
)
logger.info("sandbox_v2_artifact_store_initialized",
            extra={"root": sandbox_v2_artifact_store.root})

sandbox_v2_package_store = LocalSandboxPackageQuarantineStore(
    quarantine_root=getattr(settings, "sandbox_v2_package_quarantine_root", ".sandbox_v2_package_quarantine"),
)
logger.info("sandbox_v2_package_quarantine_store_initialized",
            extra={"root": sandbox_v2_package_store.root})

sandbox_v2_network_service = SandboxNetworkEgressService(store=sandbox_v2_store)
logger.info("sandbox_v2_network_service_initialized")

sandbox_v2_execution_providers = create_default_provider_registry()
# Add RootlessContainerExecutionProvider (disabled by default)
_is_linux = _plat.system() == "Linux"
_has_docker = shutil.which("docker") is not None
_has_podman = shutil.which("podman") is not None
_runtime = SandboxV2ContainerRuntime.DOCKER if _has_docker else (SandboxV2ContainerRuntime.PODMAN if _has_podman else SandboxV2ContainerRuntime.UNAVAILABLE)
_container_config = SandboxContainerRuntimeConfig(
    provider=SandboxV2IsolationProvider.DOCKER_ROOTLESS_FUTURE,
    runtime=_runtime,
    enabled=False,
)
_container_provider = RootlessContainerExecutionProvider(config=_container_config)
sandbox_v2_execution_providers[SandboxV2IsolationProvider.DOCKER_ROOTLESS_FUTURE] = _container_provider
sandbox_v2_execution_providers[SandboxV2IsolationProvider.PODMAN_ROOTLESS_FUTURE] = RootlessContainerExecutionProvider(
    SandboxContainerRuntimeConfig(provider=SandboxV2IsolationProvider.PODMAN_ROOTLESS_FUTURE, runtime=SandboxV2ContainerRuntime.PODMAN, enabled=False)
)
logger.info("sandbox_v2_execution_providers_initialized",
            extra={"providers": list(sandbox_v2_execution_providers.keys()), "container_runtime": _runtime, "is_linux": _is_linux})

sandbox_v2_kill_switch = SandboxKillSwitchService(
    store=sandbox_v2_store, queue=sandbox_v2_queue,
    execution_providers=sandbox_v2_execution_providers,
)
logger.info("sandbox_v2_kill_switch_initialized")

sandbox_v2_service = SandboxV2Service(
    store=sandbox_v2_store,
    queue=sandbox_v2_queue,
    artifact_store=sandbox_v2_artifact_store,
    package_store=sandbox_v2_package_store,
    network_service=sandbox_v2_network_service,
    execution_providers=sandbox_v2_execution_providers,
    kill_switch=sandbox_v2_kill_switch,
)
logger.info("sandbox_v2_service_initialized")

sandbox_v2_worker = SandboxV2Worker(
    queue=sandbox_v2_queue,
    service=sandbox_v2_service,
    worker_id="sbxwkr_main",
)
logger.info("sandbox_v2_worker_initialized",
            extra={"worker_id": sandbox_v2_worker.worker_id})

app.include_router(create_sandbox_v2_router(sandbox_v2_service, worker=sandbox_v2_worker))
logger.info("sandbox_v2_api_registered",
            extra={"event": "sandbox_v2_api_ready"})

# ═══════════════════════════════════════════
# Artifact Sandbox — Agent 不执行，只生成 Artifact
# ═══════════════════════════════════════════

from src.adapters.artifact_store import SQLiteArtifactStore
from src.open_platform.artifact_service import ArtifactService
from src.api.artifact_router import create_artifact_router

artifact_store = SQLiteArtifactStore(settings)
logger.info("artifact_store_initialized")

artifact_service = ArtifactService(artifact_store)
logger.info("artifact_service_initialized")

app.include_router(create_artifact_router(
    artifact_service,
    usage_store=usage_store,
))
logger.info("artifact_api_registered",
            extra={"event": "artifact_sandbox_ready"})

# ═══════════════════════════════════════════
# Package Registry — 将 Artifact 组织为 Package
# ═══════════════════════════════════════════

from src.adapters.package_registry_store import SQLitePackageStore
from src.open_platform.package_registry_service import PackageService
from src.api.package_registry_router import create_package_router

package_store = SQLitePackageStore(settings)
logger.info("package_store_initialized")

package_service = PackageService(package_store)
logger.info("package_service_initialized")

app.include_router(create_package_router(
    package_service,
    usage_store=usage_store,
))
logger.info("package_api_registered",
            extra={"event": "package_registry_ready"})

# ═══════════════════════════════════════════
# Workflow Registry — 将 Package 组合为 Workflow
# ═══════════════════════════════════════════

from src.adapters.workflow_registry_store import SQLiteWorkflowStore
from src.open_platform.workflow_registry_service import WorkflowService
from src.api.workflow_registry_router import create_workflow_router

workflow_store = SQLiteWorkflowStore(settings)
logger.info("workflow_store_initialized")

workflow_service = WorkflowService(workflow_store)
logger.info("workflow_service_initialized")

app.include_router(create_workflow_router(
    workflow_service,
    usage_store=usage_store,
))
logger.info("workflow_api_registered",
            extra={"event": "workflow_registry_ready"})

# ═══════════════════════════════════════════
# Agent Publishing + Marketplace — 发布 Agent 模块到市场
# ═══════════════════════════════════════════

from src.adapters.agent_module_store import SQLiteAgentModuleStore
from src.open_platform.agent_module_service import AgentModuleService, MarketplaceService
from src.api.agent_module_router import create_agent_publishing_router, create_marketplace_router

agent_module_store = SQLiteAgentModuleStore(settings)
logger.info("agent_module_store_initialized")

agent_module_service = AgentModuleService(agent_module_store)
logger.info("agent_module_service_initialized")

marketplace_service = MarketplaceService(agent_module_store)
logger.info("marketplace_service_initialized")

app.include_router(create_agent_publishing_router(
    agent_module_service,
    marketplace_service=marketplace_service,
    usage_store=usage_store,
))
logger.info("agent_publishing_api_registered",
            extra={"event": "agent_publishing_ready"})

app.include_router(create_marketplace_router(
    marketplace_service,
    usage_store=usage_store,
))
logger.info("marketplace_api_registered",
            extra={"event": "marketplace_ready"})

# ═══════════════════════════════════════════
# SaaS Integration — 多租户配额 + 隔离 + Dashboard + 用量
# ═══════════════════════════════════════════

from src.open_platform.saas_integration_service import SaaSIntegrationService
from src.api.saas_integration_router import create_saas_integration_router

saas_integration_service = SaaSIntegrationService(
    artifact_store=artifact_store,
    package_store=package_store,
    workflow_store=workflow_store,
    agent_module_store=agent_module_store,
    subscription_store=subscription_store,
    usage_store=usage_store,
)
logger.info("saas_integration_service_initialized")

app.include_router(create_saas_integration_router(
    saas_integration_service,
    artifact_service=artifact_service,
    package_service=package_service,
    workflow_service=workflow_service,
    agent_module_service=agent_module_service,
    marketplace_service=marketplace_service,
))
logger.info("saas_integration_api_registered",
            extra={"event": "saas_integration_ready"})

# ═══════════════════════════════════════════
# Marketplace Governance & Trust — Review / Report / TrustScore / Risk
# ═══════════════════════════════════════════

from src.adapters.marketplace_governance_store import SQLiteMarketplaceGovernanceStore
from src.open_platform.marketplace_governance_service import MarketplaceGovernanceService
from src.api.marketplace_governance_router import create_marketplace_governance_router

governance_store = SQLiteMarketplaceGovernanceStore(settings)
logger.info("governance_store_initialized")

governance_service = MarketplaceGovernanceService(
    governance_store,
    agent_module_store=agent_module_store,
)
logger.info("governance_service_initialized")

app.include_router(create_marketplace_governance_router(governance_service))
logger.info("governance_api_registered",
            extra={"event": "marketplace_governance_ready"})

# ═══════════════════════════════════════════
# Marketplace Analytics — Recommendations / Rankings / Platform Metrics
# ═══════════════════════════════════════════

from src.adapters.marketplace_analytics_store import SQLiteMarketplaceAnalyticsStore
from src.open_platform.marketplace_analytics_service import MarketplaceAnalyticsService
from src.api.marketplace_analytics_router import create_marketplace_analytics_router

analytics_store = SQLiteMarketplaceAnalyticsStore(settings)
logger.info("analytics_store_initialized")

analytics_service = MarketplaceAnalyticsService(
    analytics_store,
    governance_store=governance_store,
    agent_module_store=agent_module_store,
)
logger.info("analytics_service_initialized")

app.include_router(create_marketplace_analytics_router(analytics_service))
logger.info("analytics_api_registered",
            extra={"event": "marketplace_analytics_ready"})

# ═══════════════════════════════════════════
# SaaS Billing + RBAC + Cross-Tenant Analytics
# ═══════════════════════════════════════════

from src.open_platform.saas_billing_service import SaaSBillingService
from src.open_platform.rbac_service import RBACService
from src.adapters.cross_tenant_analytics_store import CrossTenantAnalyticsStore
from src.open_platform.cross_tenant_analytics_service import CrossTenantAnalyticsService
from src.api.billing_analytics_router import create_billing_analytics_router

billing_service = SaaSBillingService(
    billing_store=billing_store,
    subscription_store=subscription_store,
    usage_store=usage_store,
    payment_gateway=payment_gateway,
)
logger.info("billing_service_initialized")

rbac_service = RBACService(rbac_store=rbac_store)
logger.info("rbac_service_initialized")

ct_analytics_store = CrossTenantAnalyticsStore(settings)
logger.info("ct_analytics_store_initialized")

ct_analytics_service = CrossTenantAnalyticsService(
    ct_analytics_store=ct_analytics_store,
    artifact_store=artifact_store,
    package_store=package_store,
    workflow_store=workflow_store,
    agent_module_store=agent_module_store,
    governance_store=governance_store,
    subscription_store=subscription_store,
    usage_store=usage_store,
    tenant_store=tenant_store,
)
logger.info("ct_analytics_service_initialized")

app.include_router(create_billing_analytics_router(
    billing_service=billing_service,
    rbac_service=rbac_service,
    ct_analytics_service=ct_analytics_service,
))
logger.info("billing_rbac_analytics_api_registered",
            extra={"event": "billing_rbac_analytics_ready"})


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
