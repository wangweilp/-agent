"""Usage Tracking Domain Models — UsageEvent / UsageStats / CostStats / UserProfile.

六边形架构核心层：纯数据类 + 协议。
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Protocol, runtime_checkable
from uuid import uuid4


# ── Enums ──

class UsageResource(StrEnum):
    """用量资源类型。"""
    LLM_CALL = "llm_call"
    EMBEDDING = "embedding"
    SEARCH = "search"
    UPLOAD = "upload"
    IMPORT = "import"
    SYNC = "sync"
    COACH = "coach"
    STORAGE = "storage"
    MEMORY = "memory"
    AGENT_RUN = "agent_run"          # Enterprise AI Agent 执行
    WORKFLOW_RUN = "workflow_run"    # Workflow 执行
    AGENT_INSTALL = "agent_install"   # Agent Marketplace 安装
    AGENT_MARKETPLACE_VIEW = "agent_marketplace_view"  # Marketplace 浏览
    DEVELOPER_REGISTER = "developer_register"  # 开发者注册
    DEVELOPER_API_KEY_CREATE = "developer_api_key_create"  # API Key 创建
    DEVELOPER_API_KEY_REVOKE = "developer_api_key_revoke"  # API Key 撤销
    AGENT_SUBMISSION_CREATE = "agent_submission_create"  # Agent 提交创建
    AGENT_SUBMISSION_SUBMIT = "agent_submission_submit"  # Agent 提交审核
    AGENT_SUBMISSION_REVIEW = "agent_submission_review"  # Agent 审核
    AGENT_SUBMISSION_PUBLISH = "agent_submission_publish"  # Agent 发布
    DEVELOPER_API_KEY_AUTH = "developer_api_key_auth"  # API Key 认证
    AGENT_SIMULATION_RUN = "agent_simulation_run"  # Agent 仿真运行
    SANDBOX_POLICY_CREATE = "sandbox_policy_create"  # Sandbox Policy 创建
    SANDBOX_POLICY_UPDATE = "sandbox_policy_update"  # Sandbox Policy 更新
    SANDBOX_POLICY_TEST = "sandbox_policy_test"  # Sandbox Policy 测试
    SANDBOX_POLICY_ASSIGN = "sandbox_policy_assign"  # Sandbox Policy 分配到 Binding
    PACKAGE_VALIDATION_RUN = "package_validation_run"  # Package 验证运行
    MANIFEST_SCHEMA_VIEW = "manifest_schema_view"  # Manifest schema 查看
    MANIFEST_VALIDATE = "manifest_validate"  # Manifest 校验
    PACKAGE_ARTIFACT_DECLARE = "package_artifact_declare"  # Package Artifact 声明
    PACKAGE_ARTIFACT_QUARANTINE = "package_artifact_quarantine"  # Package Artifact 隔离
    PACKAGE_ARTIFACT_STATUS_CHANGE = "package_artifact_status_change"  # Package Artifact 状态变更
    PACKAGE_VERIFICATION_RUN = "package_verification_run"  # Package 验证运行
    PACKAGE_CHECKSUM_VERIFY = "package_checksum_verify"  # Checksum 验证
    PACKAGE_SIGNATURE_VERIFY = "package_signature_verify"  # Signature 验证
    RUNTIME_EXECUTION_PLAN_CREATE = "runtime_execution_plan_create"  # Runtime Execution Plan 创建
    RUNTIME_EXECUTION_PLAN_STATUS_CHANGE = "runtime_execution_plan_status_change"  # Plan 状态变更
    RUNTIME_EXECUTION_PLAN_CANCEL = "runtime_execution_plan_cancel"  # Plan 取消
    SANDBOX_WORKER_EVALUATE = "sandbox_worker_evaluate"  # Sandbox Worker 评估
    SANDBOX_WORKER_BLOCKED = "sandbox_worker_blocked"  # Sandbox Worker 阻止
    SANDBOX_WORKER_FAIL_CLOSED = "sandbox_worker_fail_closed"  # Sandbox Worker fail-closed
    POLICY_TRANSLATION_RUN = "policy_translation_run"  # Policy Translation 运行
    POLICY_TRANSLATION_BLOCKED = "policy_translation_blocked"  # Policy Translation blocked
    POLICY_TRANSLATION_FAIL_CLOSED = "policy_translation_fail_closed"  # Policy Translation fail-closed
    LOCAL_DEV_SANDBOX_EVALUATE = "local_dev_sandbox_evaluate"  # Local Dev Sandbox 评估
    LOCAL_DEV_SANDBOX_BLOCKED = "local_dev_sandbox_blocked"  # Local Dev Sandbox blocked
    LOCAL_DEV_SANDBOX_DRY_RUN = "local_dev_sandbox_dry_run"  # Local Dev Sandbox dry-run
    RUNTIME_EXECUTION_PLAN_API_CREATE = "runtime_execution_plan_api_create"  # Plan API 创建
    RUNTIME_EXECUTION_PLAN_API_VIEW = "runtime_execution_plan_api_view"  # Plan API 查看
    RUNTIME_EXECUTION_POLICY_PREVIEW = "runtime_execution_policy_preview"  # Policy preview
    RUNTIME_EXECUTION_WORKER_PREVIEW = "runtime_execution_worker_preview"  # Worker preview
    RUNTIME_EXECUTION_DRAFT_BLOCKED = "runtime_execution_draft_blocked"  # Execute draft blocked
    SANDBOX_EXECUTION_RECORD_CREATE = "sandbox_execution_record_create"  # Execution record 创建
    SANDBOX_EXECUTION_AUDIT_EVENT = "sandbox_execution_audit_event"  # Execution audit event
    SANDBOX_EXECUTION_STATUS_CHANGE = "sandbox_execution_status_change"  # Execution status 变更
    SANDBOX_EXECUTION_CANCEL = "sandbox_execution_cancel"  # Execution cancel
    SANDBOX_EXECUTION_EXPIRE = "sandbox_execution_expire"  # Execution expire
    SANDBOX_ADAPTER_FEASIBILITY_ASSESS = "sandbox_adapter_feasibility_assess"  # Feasibility assess
    SANDBOX_ADAPTER_FEASIBILITY_PROFILE = "sandbox_adapter_feasibility_profile"  # Feasibility profile
    SANDBOX_ADAPTER_FEASIBILITY_DESCRIPTOR = "sandbox_adapter_feasibility_descriptor"  # Feasibility descriptor
    SANDBOX_ADAPTER_FEASIBILITY_BLOCKED = "sandbox_adapter_feasibility_blocked"  # Feasibility blocked
    PACKAGE_DOWNLOAD_REQUEST_CREATE = "package_download_request_create"  # Download request 创建
    PACKAGE_DOWNLOAD_ADMIN_GATE_EVALUATE = "package_download_admin_gate_evaluate"  # Admin gate evaluate
    PACKAGE_DOWNLOAD_ADMIN_APPROVE_RESERVED = "package_download_admin_approve_reserved"  # Admin approve reserved
    PACKAGE_DOWNLOAD_ADMIN_REJECT = "package_download_admin_reject"  # Admin reject
    PACKAGE_DOWNLOAD_QUARANTINE_RESERVE = "package_download_quarantine_reserve"  # Quarantine reserve
    PACKAGE_DOWNLOAD_BLOCKED = "package_download_blocked"  # Download blocked
    ARTIFACT_EXTRACTION_GUARD_REQUEST_CREATE = "artifact_extraction_guard_request_create"  # Extraction guard request
    ARTIFACT_EXTRACTION_GUARD_EVALUATE = "artifact_extraction_guard_evaluate"  # Extraction guard evaluate
    ARTIFACT_EXTRACTION_GUARD_BLOCKED = "artifact_extraction_guard_blocked"  # Extraction guard blocked
    ARTIFACT_EXTRACTION_PLAN_RESERVE = "artifact_extraction_plan_reserve"  # Extraction plan reserve
    ARTIFACT_EXTRACTION_AUDIT_EVENT = "artifact_extraction_audit_event"  # Extraction audit event
    SANDBOX_WORKER_QUEUE_RECORD_CREATE = "sandbox_worker_queue_record_create"  # Queue record 创建
    SANDBOX_WORKER_QUEUE_GATE_EVALUATE = "sandbox_worker_queue_gate_evaluate"  # Queue gate evaluate
    SANDBOX_WORKER_QUEUE_BLOCKED = "sandbox_worker_queue_blocked"  # Queue blocked
    SANDBOX_WORKER_QUEUE_CANCEL = "sandbox_worker_queue_cancel"  # Queue cancel
    SANDBOX_WORKER_QUEUE_EXPIRE = "sandbox_worker_queue_expire"  # Queue expire
    SANDBOX_WORKER_QUEUE_AUDIT_EVENT = "sandbox_worker_queue_audit_event"  # Queue audit event
    SANDBOX_ENFORCEMENT_PROOF_REQUEST_CREATE = "sandbox_enforcement_proof_request_create"  # Enforcement proof request
    SANDBOX_ENFORCEMENT_PROOF_EVALUATE = "sandbox_enforcement_proof_evaluate"  # Enforcement proof evaluate
    SANDBOX_ENFORCEMENT_PROOF_BLOCKED = "sandbox_enforcement_proof_blocked"  # Enforcement proof blocked
    SANDBOX_ENFORCEMENT_PROOF_CANCEL = "sandbox_enforcement_proof_cancel"  # Enforcement proof cancel
    SANDBOX_ENFORCEMENT_PROOF_EXPIRE = "sandbox_enforcement_proof_expire"  # Enforcement proof expire
    SANDBOX_ENFORCEMENT_PROOF_AUDIT_EVENT = "sandbox_enforcement_proof_audit_event"  # Enforcement proof audit
    TRUSTED_FIXTURE_REQUEST_CREATE = "trusted_fixture_request_create"  # Trusted fixture request
    TRUSTED_FIXTURE_RUN = "trusted_fixture_run"  # Trusted fixture run
    TRUSTED_FIXTURE_BLOCKED = "trusted_fixture_blocked"  # Trusted fixture blocked
    TRUSTED_FIXTURE_CANCEL = "trusted_fixture_cancel"  # Trusted fixture cancel
    TRUSTED_FIXTURE_EXPIRE = "trusted_fixture_expire"  # Trusted fixture expire
    TRUSTED_FIXTURE_AUDIT_EVENT = "trusted_fixture_audit_event"  # Trusted fixture audit
    PRODUCTION_SANDBOX_GATE_REQUEST_CREATE = "production_sandbox_gate_request_create"  # PS gate request
    PRODUCTION_SANDBOX_GATE_EVALUATE = "production_sandbox_gate_evaluate"  # PS gate evaluate
    PRODUCTION_SANDBOX_GATE_BLOCKED = "production_sandbox_gate_blocked"  # PS gate blocked
    PRODUCTION_SANDBOX_GATE_CANCEL = "production_sandbox_gate_cancel"  # PS gate cancel
    PRODUCTION_SANDBOX_GATE_EXPIRE = "production_sandbox_gate_expire"  # PS gate expire
    PRODUCTION_SANDBOX_GATE_AUDIT_EVENT = "production_sandbox_gate_audit_event"  # PS gate audit
    RUNTIME_KILL_SWITCH_POLICY_CREATE = "runtime_kill_switch_policy_create"  # KS policy
    RUNTIME_KILL_SWITCH_TRIGGER_METADATA_ONLY = "runtime_kill_switch_trigger_metadata_only"  # KS trigger
    RUNTIME_KILL_SWITCH_RELEASE_METADATA_ONLY = "runtime_kill_switch_release_metadata_only"  # KS release
    RUNTIME_INCIDENT_CREATE = "runtime_incident_create"  # Incident create
    RUNTIME_INCIDENT_TRIAGE = "runtime_incident_triage"  # Incident triage
    RUNTIME_INCIDENT_CLOSE_METADATA_ONLY = "runtime_incident_close_metadata_only"  # Incident close
    RUNTIME_SAFETY_AUDIT_EVENT = "runtime_safety_audit_event"  # Safety audit
    PACKAGE_DOWNLOAD_WORKER_POLICY_CREATE = "package_download_worker_policy_create"  # DW policy
    PACKAGE_DOWNLOAD_WORKER_JOB_CREATE = "package_download_worker_job_create"  # DW job
    PACKAGE_DOWNLOAD_WORKER_GATE_EVALUATE = "package_download_worker_gate_evaluate"  # DW gate
    PACKAGE_DOWNLOAD_WORKER_LEASE_RESERVE_METADATA_ONLY = "package_download_worker_lease_reserve_metadata_only"  # DW lease reserve
    PACKAGE_DOWNLOAD_WORKER_LEASE_RELEASE_METADATA_ONLY = "package_download_worker_lease_release_metadata_only"  # DW lease release
    PACKAGE_DOWNLOAD_WORKER_JOB_BLOCKED = "package_download_worker_job_blocked"  # DW job blocked
    PACKAGE_DOWNLOAD_WORKER_AUDIT_EVENT = "package_download_worker_audit_event"  # DW audit
    ARTIFACT_MATERIALIZATION_POLICY_CREATE = "artifact_materialization_policy_create"  # Mat policy
    ARTIFACT_MATERIALIZATION_REQUEST_CREATE = "artifact_materialization_request_create"  # Mat request
    ARTIFACT_MATERIALIZATION_GATE_EVALUATE = "artifact_materialization_gate_evaluate"  # Mat gate
    ARTIFACT_MATERIALIZATION_PLAN_RESERVE_METADATA_ONLY = "artifact_materialization_plan_reserve_metadata_only"  # Mat plan
    ARTIFACT_MATERIALIZATION_REFERENCE_RESERVE = "artifact_materialization_reference_reserve"  # Mat ref
    ARTIFACT_MATERIALIZATION_BLOCKED = "artifact_materialization_blocked"  # Mat blocked
    ARTIFACT_MATERIALIZATION_AUDIT_EVENT = "artifact_materialization_audit_event"  # Mat audit
    ROOTLESS_CONTAINER_POLICY_CREATE = "rootless_container_policy_create"  # RC policy
    ROOTLESS_CONTAINER_REQUEST_CREATE = "rootless_container_request_create"  # RC request
    ROOTLESS_CONTAINER_CAPABILITY_ASSESS = "rootless_container_capability_assess"  # RC capability
    ROOTLESS_CONTAINER_GATE_EVALUATE = "rootless_container_gate_evaluate"  # RC gate
    ROOTLESS_CONTAINER_PLAN_RESERVE_METADATA_ONLY = "rootless_container_plan_reserve_metadata_only"  # RC plan
    ROOTLESS_CONTAINER_BLOCKED = "rootless_container_blocked"  # RC blocked
    ROOTLESS_CONTAINER_AUDIT_EVENT = "rootless_container_audit_event"  # RC audit
    TRUSTED_FIXTURE_ISOLATION_POLICY_CREATE = "trusted_fixture_isolation_policy_create"  # TFI policy
    TRUSTED_FIXTURE_ISOLATION_REQUEST_CREATE = "trusted_fixture_isolation_request_create"  # TFI request
    TRUSTED_FIXTURE_ISOLATION_REQUIREMENT_ASSESS = "trusted_fixture_isolation_requirement_assess"  # TFI req
    TRUSTED_FIXTURE_ISOLATION_GATE_EVALUATE = "trusted_fixture_isolation_gate_evaluate"  # TFI gate
    TRUSTED_FIXTURE_ISOLATION_PLAN_RESERVE_METADATA_ONLY = "trusted_fixture_isolation_plan_reserve_metadata_only"  # TFI plan
    TRUSTED_FIXTURE_ISOLATION_BLOCKED = "trusted_fixture_isolation_blocked"  # TFI blocked
    TRUSTED_FIXTURE_ISOLATION_AUDIT_EVENT = "trusted_fixture_isolation_audit_event"  # TFI audit
    RUNTIME_CAPABILITY_ACCESS = "runtime_capability_access"  # Capability registry
    RUNTIME_CAPABILITY_MATRIX_EXPORT = "runtime_capability_matrix_export"  # Capability export
    POLICY_ENFORCEMENT_DECISION = "policy_enforcement_decision"  # Policy decision
    POLICY_ENFORCEMENT_AUDIT = "policy_enforcement_audit"  # Policy audit
    PRODUCTION_MIGRATION_ASSESSMENT = "production_migration_assessment"  # Migration assessment
    PRODUCTION_POSTGRES_READINESS = "production_postgres_readiness"  # PG readiness
    PRODUCTION_REDIS_READINESS = "production_redis_readiness"  # Redis readiness
    PRODUCTION_OBJECT_STORAGE_READINESS = "production_object_storage_readiness"  # Object storage
    PRODUCTION_TASK_QUEUE_READINESS = "production_task_queue_readiness"  # Task queue
    PRODUCTION_IMPORT_HUB_READINESS = "production_import_hub_readiness"  # Import hub
    PRODUCTION_SYNC_HUB_READINESS = "production_sync_hub_readiness"  # Sync hub
    PRODUCTION_AUDIT_EVENT = "production_audit_event"  # Production audit


class UsageUnit(StrEnum):
    COUNT = "count"
    TOKEN = "token"
    BYTE = "byte"
    SECOND = "second"


# ── Data Classes ──


@dataclass
class UsageEvent:
    """单次用量事件。"""
    tenant_id: str
    user_id: str
    resource: UsageResource
    quantity: int = 1
    id: str = field(default_factory=lambda: f"use_{uuid4().hex[:12]}")
    workspace_id: str = ""
    unit: UsageUnit = UsageUnit.COUNT
    metadata: dict = field(default_factory=dict)
    # {"model": "deepseek-chat", "tokens": 1500, "endpoint": "/chat"}
    cost_cents: int = 0  # 预估成本（分）
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class UsageStats:
    """用量统计（月度/自定义周期）。"""
    tenant_id: str
    period_start: datetime
    period_end: datetime
    total_events: int = 0
    by_resource: dict[str, int] = field(default_factory=dict)
    # {"llm_call": 150, "search": 45, ...}
    total_cost_cents: int = 0
    by_resource_cost: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "tenant_id": self.tenant_id,
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat(),
            "total_events": self.total_events,
            "by_resource": self.by_resource,
            "total_cost_cents": self.total_cost_cents,
            "by_resource_cost": self.by_resource_cost,
        }


@dataclass
class CostStats:
    """成本统计。"""
    tenant_id: str
    month: str  # "2026-06"
    llm_cost_cents: int = 0
    embedding_cost_cents: int = 0
    storage_cost_cents: int = 0
    total_cost_cents: int = 0
    gross_revenue_cents: int = 0  # 毛收入
    net_revenue_cents: int = 0     # 净收入
    margin_percent: float = 0.0

    def as_dict(self) -> dict:
        return {
            "tenant_id": self.tenant_id,
            "month": self.month,
            "llm_cost_cents": self.llm_cost_cents,
            "embedding_cost_cents": self.embedding_cost_cents,
            "storage_cost_cents": self.storage_cost_cents,
            "total_cost_cents": self.total_cost_cents,
            "gross_revenue_cents": self.gross_revenue_cents,
            "net_revenue_cents": self.net_revenue_cents,
            "margin_percent": self.margin_percent,
        }


@dataclass
class UserProfile:
    """用户画像（基于用量数据聚合）。"""
    tenant_id: str
    user_id: str
    total_memories: int = 0
    total_searches: int = 0
    total_imports: int = 0
    total_syncs: int = 0
    coach_sessions: int = 0
    active_days: int = 0
    last_active: datetime | None = None
    preferred_features: list[str] = field(default_factory=list)
    # 活跃度评分 0-100
    engagement_score: int = 0
    # 是否为重度用户
    is_power_user: bool = False

    def as_dict(self) -> dict:
        return {
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "total_memories": self.total_memories,
            "total_searches": self.total_searches,
            "total_imports": self.total_imports,
            "total_syncs": self.total_syncs,
            "coach_sessions": self.coach_sessions,
            "active_days": self.active_days,
            "last_active": self.last_active.isoformat() if self.last_active else None,
            "preferred_features": self.preferred_features,
            "engagement_score": self.engagement_score,
            "is_power_user": self.is_power_user,
        }


@dataclass
class PlatformStats:
    """平台级统计（SaaS Dashboard 用）。"""
    mrr_cents: int = 0           # Monthly Recurring Revenue
    arr_cents: int = 0           # Annual Run Rate
    total_tenants: int = 0
    active_tenants: int = 0
    trial_tenants: int = 0
    paying_tenants: int = 0
    conversion_rate: float = 0.0  # trial → paid
    churn_rate: float = 0.0       # 月流失率
    retention_rate: float = 0.0   # 月留存率
    avg_revenue_per_user: int = 0  # ARPU（分）
    total_revenue_cents: int = 0

    def as_dict(self) -> dict:
        return {
            "mrr_cents": self.mrr_cents,
            "arr_cents": self.arr_cents,
            "total_tenants": self.total_tenants,
            "active_tenants": self.active_tenants,
            "trial_tenants": self.trial_tenants,
            "paying_tenants": self.paying_tenants,
            "conversion_rate": self.conversion_rate,
            "churn_rate": self.churn_rate,
            "retention_rate": self.retention_rate,
            "avg_revenue_per_user": self.avg_revenue_per_user,
            "total_revenue_cents": self.total_revenue_cents,
        }


# ── Protocols ──


@runtime_checkable
class UsageStore(Protocol):
    """用量存储协议。"""

    def record_event(self, event: UsageEvent) -> str: ...
    def query_events(self, tenant_id: str, resource: str | None = None,
                     start: datetime | None = None, end: datetime | None = None,
                     limit: int = 100) -> list[UsageEvent]: ...
    def get_monthly_stats(self, tenant_id: str, year: int,
                          month: int) -> UsageStats: ...
    def get_cost_stats(self, tenant_id: str, year: int,
                       month: int) -> CostStats: ...
    def get_user_profile(self, tenant_id: str, user_id: str) -> UserProfile: ...
    def get_platform_stats(self) -> PlatformStats: ...
    def get_daily_usage(self, tenant_id: str, resource: str,
                        days: int = 30) -> list[dict]: ...
