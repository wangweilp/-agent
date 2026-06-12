"""Agent Marketplace Domain Model — 企业内部与平台级 Agent 分发中心。

提供：
- MarketplaceAgent — 可被发现的 Agent 描述（不含运行时实例）
- TenantAgentInstallation — per-tenant/workspace 安装状态
- MarketplaceStore Protocol — 存储层抽象

与 AgentRegistry 的关系：
- AgentRegistry 管理 Agent 运行时实例（全局进程内状态）
- MarketplaceStore 管理 Agent 的发现、安装、配置状态（per-tenant 持久化）
- 两者通过 agent_id 关联，互不侵入
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable
from uuid import uuid4


# ═══════════════════════════════════════════
# Enums
# ═══════════════════════════════════════════


class MarketplaceAgentStatus(StrEnum):
    ACTIVE = "active"
    BETA = "beta"
    DEPRECATED = "deprecated"
    DISABLED = "disabled"


class MarketplaceAgentVisibility(StrEnum):
    PUBLIC = "public"
    PRIVATE = "private"
    BETA = "beta"


class MarketplaceCategory(StrEnum):
    AUTOMATION = "automation"
    ASSISTANT = "assistant"
    KNOWLEDGE = "knowledge"
    TRAINING = "training"
    SALES = "sales"
    SUPPORT = "support"
    ENGINEERING = "engineering"
    HR = "hr"
    ANALYTICS = "analytics"


class MarketplacePricingModel(StrEnum):
    FREE = "free"
    PER_USE = "per_use"
    PER_SEAT = "per_seat"
    SUBSCRIPTION = "subscription"


class InstallationStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"
    ERROR = "error"
    UNINSTALLED = "uninstalled"


class PublisherType(StrEnum):
    BUILTIN = "builtin"
    PLATFORM = "platform"
    DEVELOPER = "developer"


# ═══════════════════════════════════════════
# Domain Models
# ═══════════════════════════════════════════


@dataclass
class MarketplaceAgent:
    """可被发现的 Agent 描述。

    与 AgentRegistration 的区别：
    - MarketplaceAgent 是展示/发现层（category, capabilities, pricing_model）
    - AgentRegistration 是运行时层（usage_count, success_rate, avg_duration_ms）
    - marketplace_agent_id 是 marketplace 独立标识，agent_id 关联 Registry
    """
    marketplace_agent_id: str = field(default_factory=lambda: f"mkp_{uuid4().hex[:12]}")
    agent_id: str = ""                          # 关联 AgentRegistry 中的 agent_id
    name: str = ""                              # 技术名（英文）
    display_name: str = ""                      # 展示名（中文）
    description: str = ""                       # 简要描述
    long_description: str = ""                  # 详细描述（markdown）
    category: str = ""                          # automation | assistant | knowledge | ...
    department: str | None = None                # 所属部门（None=跨部门）
    capabilities: list[str] = field(default_factory=list)
    required_permissions: list[str] = field(default_factory=list)
    supported_workflows: list[str] = field(default_factory=list)
    version: str = "1.0.0"
    publisher_type: str = "builtin"             # builtin | platform
    publisher_name: str = "Cognitive OS"
    icon: str | None = None                     # lucide icon 名
    visibility: str = "public"                  # public | private | beta
    pricing_model: str = "free"                 # free | per_use | per_seat | subscription
    usage_limits: dict[str, Any] = field(default_factory=dict)
    install_count: int = 0
    rating: float = 0.0
    status: str = "active"                       # active | beta | deprecated | disabled
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {
            "marketplace_agent_id": self.marketplace_agent_id,
            "agent_id": self.agent_id,
            "name": self.name,
            "display_name": self.display_name,
            "description": self.description,
            "long_description": self.long_description,
            "category": self.category,
            "department": self.department,
            "capabilities": self.capabilities,
            "required_permissions": self.required_permissions,
            "supported_workflows": self.supported_workflows,
            "version": self.version,
            "publisher_type": self.publisher_type,
            "publisher_name": self.publisher_name,
            "icon": self.icon,
            "visibility": self.visibility,
            "pricing_model": self.pricing_model,
            "usage_limits": self.usage_limits,
            "install_count": self.install_count,
            "rating": self.rating,
            "status": self.status,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


@dataclass
class TenantAgentInstallation:
    """Per-tenant/workspace Agent 安装状态。

    tenant_id + workspace_id + marketplace_agent_id 联合唯一。
    """
    installation_id: str = field(default_factory=lambda: f"inst_{uuid4().hex[:12]}")
    tenant_id: str = ""
    workspace_id: str = ""
    marketplace_agent_id: str = ""
    agent_id: str = ""
    installed_by: str = ""
    installed_at: datetime | None = None
    status: str = "active"                      # active | disabled | error | uninstalled
    enabled: bool = True
    config: dict[str, Any] = field(default_factory=dict)
    permissions_granted: list[str] = field(default_factory=list)
    usage_limit_override: dict[str, Any] = field(default_factory=dict)
    version_pinned: str | None = None           # 锁定版本，None=跟随最新
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {
            "installation_id": self.installation_id,
            "tenant_id": self.tenant_id,
            "workspace_id": self.workspace_id,
            "marketplace_agent_id": self.marketplace_agent_id,
            "agent_id": self.agent_id,
            "installed_by": self.installed_by,
            "installed_at": self.installed_at.isoformat() if self.installed_at else None,
            "status": self.status,
            "enabled": self.enabled,
            "config": self.config,
            "permissions_granted": self.permissions_granted,
            "usage_limit_override": self.usage_limit_override,
            "version_pinned": self.version_pinned,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# ═══════════════════════════════════════════
# MarketplaceStore Protocol
# ═══════════════════════════════════════════


@runtime_checkable
class MarketplaceStore(Protocol):
    """Marketplace 存储协议 — Agent 发现与安装管理。

    所有 installation 操作必须按 tenant_id + workspace_id 隔离。
    uninstall 为软删除（status=UNINSTALLED, enabled=False）。
    """

    # ── MarketplaceAgent CRUD ──

    def create_agent(self, agent: MarketplaceAgent) -> MarketplaceAgent: ...

    def get_agent(self, marketplace_agent_id: str) -> MarketplaceAgent | None: ...

    def get_agent_by_agent_id(self, agent_id: str) -> MarketplaceAgent | None: ...

    def list_agents(
        self,
        *,
        category: str = "",
        department: str | None = None,
        status: str = "",
        visibility: str = "",
    ) -> list[MarketplaceAgent]: ...

    def update_agent(self, agent: MarketplaceAgent) -> None: ...

    def deactivate_agent(self, marketplace_agent_id: str) -> None: ...

    def increment_install_count(self, marketplace_agent_id: str) -> None: ...

    # ── Installation Management ──

    def install_agent(
        self,
        marketplace_agent_id: str,
        agent_id: str,
        tenant_id: str,
        workspace_id: str,
        installed_by: str,
        *,
        config: dict[str, Any] | None = None,
        permissions_granted: list[str] | None = None,
    ) -> TenantAgentInstallation: ...

    def get_installation(self, installation_id: str) -> TenantAgentInstallation | None: ...

    def get_installation_by_agent(
        self, marketplace_agent_id: str, tenant_id: str, workspace_id: str,
    ) -> TenantAgentInstallation | None: ...

    def list_installations(
        self,
        *,
        tenant_id: str = "",
        workspace_id: str = "",
        marketplace_agent_id: str = "",
        status: str = "",
    ) -> list[TenantAgentInstallation]: ...

    def enable_installation(self, installation_id: str, tenant_id: str, workspace_id: str) -> bool: ...

    def disable_installation(self, installation_id: str, tenant_id: str, workspace_id: str) -> bool: ...

    def update_installation_config(
        self, installation_id: str, tenant_id: str, workspace_id: str, config: dict[str, Any],
    ) -> bool: ...

    def uninstall_agent(
        self, installation_id: str, tenant_id: str, workspace_id: str,
    ) -> bool: ...

    def is_agent_installed(self, marketplace_agent_id: str, tenant_id: str, workspace_id: str) -> bool: ...


# ═══════════════════════════════════════════
# Built-in Marketplace Agent Catalog
# ═══════════════════════════════════════════

BUILTIN_MARKETPLACE_AGENTS: list[dict[str, Any]] = [
    {
        "marketplace_agent_id": "mkp_meeting_training",
        "agent_id": "builtin-meeting",
        "name": "meeting-to-training",
        "display_name": "会议纪要自动沉淀与培训生成",
        "description": "将会议纪要自动提取要点、沉淀知识、生成培训材料的全自动闭环",
        "long_description": "会议结束后，Meeting Agent 提取关键决策和行动项，Knowledge Agent 将知识点存入知识图谱，Training Agent 自动生成培训大纲和练习题。整个过程通过 WorkflowEngine 编排，每一步可追溯、可审计。",
        "category": "automation",
        "department": None,
        "capabilities": ["会议纪要提取", "决策识别", "行动项生成", "知识沉淀", "培训材料生成"],
        "required_permissions": ["agent:execute", "memory:read", "memory:write", "kg:query"],
        "supported_workflows": ["meeting-to-knowledge-to-training"],
        "version": "1.0.0",
        "publisher_type": "builtin",
        "publisher_name": "黔智脑 Cognitive OS",
        "icon": "FileText",
        "visibility": "public",
        "pricing_model": "free",
        "status": "active",
    },
    {
        "marketplace_agent_id": "mkp_dept_assistant",
        "agent_id": "dept-rd",
        "name": "department-assistant",
        "display_name": "部门知识助手",
        "description": "向部门 Agent 提问，获取基于部门知识库的结构化建议",
        "long_description": "支持研发部、产品部、运营部、销售部、人力资源部、客服部六大部门。每个部门有专属知识空间，Agent 默认不跨部门访问。基于确定性规则引擎生成结构化建议，含置信度和局限性透明标注。",
        "category": "assistant",
        "department": None,
        "capabilities": ["部门知识检索", "结构化建议", "风险分析", "学习计划生成", "FAQ 回答"],
        "required_permissions": ["agent:execute", "memory:read", "kg:query"],
        "supported_workflows": ["department-knowledge-assistant"],
        "version": "1.0.0",
        "publisher_type": "builtin",
        "publisher_name": "黔智脑 Cognitive OS",
        "icon": "Building2",
        "visibility": "public",
        "pricing_model": "free",
        "status": "active",
    },
    {
        "marketplace_agent_id": "mkp_knowledge",
        "agent_id": "builtin-knowledge",
        "name": "knowledge-agent",
        "display_name": "知识管理 Agent",
        "description": "企业知识管理：入库、检索、整理、推荐",
        "long_description": "自动将对话/文档中的知识点结构化存储到 Memory Store 和 Knowledge Graph。支持语义搜索、图谱遍历、实体关联。可识别重复/矛盾/过时内容并生成整理建议。",
        "category": "knowledge",
        "department": None,
        "capabilities": ["知识入库", "语义搜索", "图谱遍历", "知识整理", "知识推荐"],
        "required_permissions": ["agent:execute", "memory:read", "memory:write", "kg:query", "kg:write"],
        "supported_workflows": ["meeting-to-knowledge-to-training", "research-to-report"],
        "version": "1.0.0",
        "publisher_type": "builtin",
        "publisher_name": "黔智脑 Cognitive OS",
        "icon": "Brain",
        "visibility": "public",
        "pricing_model": "free",
        "status": "active",
    },
    {
        "marketplace_agent_id": "mkp_training",
        "agent_id": "builtin-training",
        "name": "training-agent",
        "display_name": "培训辅助 Agent",
        "description": "基于知识库生成培训内容、学习路径、掌握度评估",
        "long_description": "从知识库检索相关内容，自动生成培训大纲、练习题和评估题。支持生成分阶学习路径（入门→进阶→高级→专家）。可评估学员知识掌握度并识别知识盲区。",
        "category": "training",
        "department": None,
        "capabilities": ["培训大纲生成", "练习题生成", "学习路径规划", "知识掌握度评估", "个性化推荐"],
        "required_permissions": ["agent:execute", "memory:read"],
        "supported_workflows": ["meeting-to-knowledge-to-training"],
        "version": "1.0.0",
        "publisher_type": "builtin",
        "publisher_name": "黔智脑 Cognitive OS",
        "icon": "GraduationCap",
        "visibility": "public",
        "pricing_model": "free",
        "status": "active",
    },
    {
        "marketplace_agent_id": "mkp_sales",
        "agent_id": "dept-sales",
        "name": "sales-agent",
        "display_name": "销售辅助 Agent",
        "description": "销售漏斗分析、客户分群、成单预测、话术优化",
        "long_description": "销售部门专属 Agent。自动分析销售漏斗各阶段转化率，识别瓶颈。基于客户数据生成高价值客户画像和待激活客户名单。提供成单预测和话术优化建议。",
        "category": "sales",
        "department": "销售部",
        "capabilities": ["漏斗分析", "客户分群", "成单预测", "话术生成", "竞品对比"],
        "required_permissions": ["agent:execute", "memory:read"],
        "supported_workflows": [],
        "version": "1.0.0",
        "publisher_type": "builtin",
        "publisher_name": "黔智脑 Cognitive OS",
        "icon": "TrendingUp",
        "visibility": "public",
        "pricing_model": "per_use",
        "status": "active",
    },
    {
        "marketplace_agent_id": "mkp_support",
        "agent_id": "dept-cs",
        "name": "support-agent",
        "display_name": "客服辅助 Agent",
        "description": "客诉趋势分析、高频问题识别、服务质量评估、知识库优化",
        "long_description": "客服部门专属 Agent。自动分析客诉趋势和热点问题。评估服务质量（响应时间、满意度、首次解决率）。识别知识库缺失话题并生成答案更新建议。",
        "category": "support",
        "department": "客服部",
        "capabilities": ["客诉趋势", "高频问题", "质量评估", "知识库优化", "升级判断"],
        "required_permissions": ["agent:execute", "memory:read"],
        "supported_workflows": [],
        "version": "1.0.0",
        "publisher_type": "builtin",
        "publisher_name": "黔智脑 Cognitive OS",
        "icon": "MessageCircle",
        "visibility": "public",
        "pricing_model": "free",
        "status": "active",
    },
]


def seed_builtin_marketplace_agents(store: "MarketplaceStore") -> int:
    """初始化内置 Marketplace Agent catalog。

    幂等：已存在的 marketplace_agent_id 会更新字段，不重复创建。
    返回实际新增数量。
    """
    import logging
    logger = logging.getLogger(__name__)
    created = 0
    updated = 0

    for data in BUILTIN_MARKETPLACE_AGENTS:
        mkp_id = data["marketplace_agent_id"]
        existing = store.get_agent(mkp_id)

        agent = MarketplaceAgent(**{k: v for k, v in data.items() if k in MarketplaceAgent.__dataclass_fields__})

        if existing is None:
            store.create_agent(agent)
            created += 1
            logger.info("marketplace_agent_created", extra={"mkp_id": mkp_id, "agent_name": agent.name})
        else:
            # 更新字段但保留 install_count
            agent.install_count = existing.install_count
            store.update_agent(agent)
            updated += 1
            logger.info("marketplace_agent_updated", extra={"mkp_id": mkp_id, "agent_name": agent.name})

    logger.info("marketplace_seed_complete", extra={"created_count": created, "updated_count": updated,
                                                       "agent_total": len(BUILTIN_MARKETPLACE_AGENTS)})
    return created
