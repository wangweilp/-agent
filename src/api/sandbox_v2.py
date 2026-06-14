"""Sandbox v2 API Router — /api/runtime/sandbox-v2 端点。

Step 1 — Core Contract API (保留):
1. POST /api/runtime/sandbox-v2/jobs — 提交 sandbox job (支持 ?enqueue=true)
2. GET  /api/runtime/sandbox-v2/jobs/{job_id} — 查看 job 状态
3. GET  /api/runtime/sandbox-v2/jobs — 列出 jobs
4. POST /api/runtime/sandbox-v2/jobs/{job_id}/cancel — 取消 job
5. GET  /api/runtime/sandbox-v2/execution-records — 查看执行记录
6. GET  /api/runtime/sandbox-v2/readiness — 返回能力状态

Step 2 — Queue / Worker API (新增):
7. GET  /api/runtime/sandbox-v2/queue — 查看队列
8. POST /api/runtime/sandbox-v2/queue/requeue-expired — 回收过期 lease
9. GET  /api/runtime/sandbox-v2/workers — 查看 worker heartbeat
10. POST /api/runtime/sandbox-v2/workers/run-once — 处理一个任务
11. GET  /api/runtime/sandbox-v2/dead-letter — 查看 dead letter

安全约束：
- 不执行第三方代码
- 不连接 Docker/MicroVM
- 所有 mode=simulation 或 metadata_only
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from src.open_platform.sandbox_v2.models import (
    SandboxV2JobStatus,
    SandboxV2Mode,
    SandboxV2ArtifactType,
    MVP_ALLOWED_MODES,
)
from src.open_platform.sandbox_v2.service import SandboxV2Service

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════
# Pydantic Schemas
# ═══════════════════════════════════════════


class SubmitJobRequest(BaseModel):
    organization_id: str = Field(default="")
    workspace_id: str = Field(default="")
    agent_id: str = Field(default="")
    requested_by: str = Field(default="")
    mode: str = Field(default=SandboxV2Mode.SIMULATION)
    requested_action: str = Field(default="")
    input_ref: str = Field(default="")
    metadata: dict[str, Any] = Field(default_factory=dict)
    enqueue: bool = Field(default=False)
    priority: int = Field(default=100)
    max_attempts: int = Field(default=3)


class SubmitJobResponse(BaseModel):
    job_id: str | None = None
    status: str = SandboxV2JobStatus.CREATED
    decision: dict[str, Any] = Field(default_factory=dict)
    queue_id: str | None = None


class ReadinessResponse(BaseModel):
    # ── Step 1-9 已有字段 ──
    sandbox_v2_core_contract: bool = True
    real_task_queue: bool = True
    worker_framework: bool = True
    distributed_worker: bool = False
    redis_queue: bool = False
    process_kill: bool = False
    execution_isolation: bool = False
    network_isolation: bool = False
    filesystem_isolation: bool = False
    package_scanning: bool = False
    artifact_store: bool = True
    read_only_artifact_materialization: bool = True
    path_traversal_protection: bool = True
    artifact_size_limit: bool = True
    artifact_hashing: bool = True
    artifact_retention_policy: bool = True
    unsafe_archive_extraction: bool = False
    arbitrary_filesystem_access: bool = False
    package_download_gate: bool = True
    package_quarantine: bool = True
    external_package_download: bool = False
    public_registry_download: bool = False
    package_hash_verification: bool = True
    package_signature_verification_interface: bool = True
    package_sbom_validation: bool = True
    package_vulnerability_scan_interface: bool = True
    package_installation: bool = False
    package_execution: bool = False
    supply_chain_policy: bool = True
    network_egress_policy: bool = True
    network_preflight: bool = True
    external_network_access: bool = False
    egress_proxy: bool = False
    dns_runtime_resolution: bool = False
    private_network_blocking: bool = True
    metadata_service_blocking: bool = True
    localhost_blocking: bool = True
    allowed_domain_policy: bool = True
    ip_denylist_policy: bool = True
    runtime_network_namespace: bool = False
    iptables_enforcement: bool = False
    isolation_capability_probe: bool = True
    execution_provider_abstraction: bool = True
    trusted_fixture_provider: bool = True
    untrusted_code_execution: bool = False
    local_process_execution: bool = False
    docker_execution: bool = False
    podman_execution: bool = False
    microvm_execution: bool = False
    container_provider_abstraction: bool = True
    # ── Step 11 — MicroVM / Firecracker fields ──
    microvm_provider_abstraction: bool = True
    firecracker_provider_abstraction: bool = True
    microvm_execution_enabled: bool = False
    microvm_integration_enabled: bool = False
    microvm_runnable: bool = False
    kvm_available: bool = False
    firecracker_binary_present: bool = False
    microvm_kernel_present: bool = False
    microvm_rootfs_present: bool = False
    microvm_network_enabled: bool = False
    user_kernel_allowed: bool = False
    user_rootfs_allowed: bool = False
    host_mounts_allowed: bool = False
    real_microvm_execution: bool = False
    # ── Step 13 — Backend Integration Testing 字段 ──
    backend_integration_tests_present: bool = True
    backend_integration_enabled: bool = False
    postgres_integration_ready: bool = False
    redis_integration_ready: bool = False
    minio_integration_ready: bool = False
    backend_integration_blockers: list[str] = Field(default_factory=list)
    backend_integration_warnings: list[str] = Field(default_factory=list)
    postgres_schema_initialized: bool = False
    backend_integration_last_run: str = ""
    # ── Step 14 — Security / Tenant / Audit 字段 ──
    security_context: bool = True
    access_policy_engine: bool = True
    rbac_scope_policy: bool = True
    tenant_isolation: bool = True
    cross_tenant_deny: bool = True
    security_audit_events: bool = True
    audit_hash_chain: bool = True
    evidence_bundle_export: bool = True
    sensitive_metadata_redaction: bool = True
    legacy_endpoint_enforcement: str = "incremental"
    external_iam: bool = False
    sso_integration: bool = False
    # ── Step 15 — Monitoring / Metrics / Alerts / Health ──
    metrics_collector: bool = True
    health_checks: bool = True
    alert_engine: bool = True
    internal_alert_records: bool = True
    prometheus_export: bool = True
    external_notifications: bool = False
    monitoring_dashboard: bool = True
    audit_signal_aggregation: bool = True
    alert_rules_present: bool = True
    monitoring_safe_mode: bool = True
    rootless_container_poc: bool = True
    container_execution_enabled: bool = False
    docker_available: bool = False
    podman_available: bool = False
    rootless_container_available: bool = False
    trusted_container_fixture_only: bool = True
    arbitrary_container_command: bool = False
    arbitrary_container_image: bool = False
    container_network_disabled: bool = True
    container_readonly_rootfs_required: bool = True
    container_no_new_privileges_required: bool = True
    container_cap_drop_all_required: bool = True
    kill_switch: bool = True
    kill_policy: bool = True
    active_execution_handles: bool = True
    queue_cancel: bool = True
    worker_cancel_checkpoints: bool = True
    provider_cancel_interface: bool = True
    process_kill_implemented: bool = False
    arbitrary_pid_kill: bool = False
    container_kill_enabled: bool = False
    docker_kill_available: bool = False
    podman_kill_available: bool = False
    red_team_suite: bool = True
    artifact_escape_tests: bool = True
    network_ssrf_tests: bool = True
    package_supply_chain_tests: bool = True
    kill_switch_abuse_tests: bool = True
    container_escape_tests: bool = True
    policy_fail_closed_tests: bool = True
    api_abuse_tests: bool = True
    worker_queue_abuse_tests: bool = True
    real_attack_execution: bool = False
    real_container_fixture_validation: bool = False
    real_container_fixture_enabled: bool = False
    real_container_fixture_runnable: bool = False
    auto_pull_images: bool = False
    user_command_execution: bool = False
    user_image_execution: bool = False
    network_enabled_in_container: bool = False
    current_execution_mode: str = "simulation_only"
    allowed_modes: list[str] = Field(default_factory=lambda: list(MVP_ALLOWED_MODES))
    boundary_statement: str = (
        "Sandbox v2 Step 1-10 implemented: Core Contract + Task Queue/Worker + "
        "Artifact Isolation + Package Supply Chain + Network Preflight + "
        "Isolation Provider + Container PoC + Kill Switch + Red-Team Suite + "
        "Production Hardening. "
        "All execution is simulation/trusted-fixture only. Red-team tests verify "
        "default-deny, fail-closed, path traversal blocking, SSRF blocking, "
        "arbitrary PID kill rejection, and container escape prevention. "
        "No Docker, MicroVM, Redis/Celery, or real code execution is available."
    )
    # ── Step 10 — Production Hardening 字段 ──
    production_hardening_docs: bool = True
    env_template_present: bool = True
    production_readiness_script: bool = True
    deployment_checklist_present: bool = True
    operations_runbook_present: bool = True
    incident_response_runbook_present: bool = True
    docker_compose_example_present: bool = True
    safe_defaults_configured: bool = True
    production_blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    # ── Step 12 — Backend Readiness 字段 ──
    database_backend: str = "sqlite"
    database_backend_ready: bool = True
    postgres_adapter_available: bool = False
    postgres_dsn_configured: bool = False
    queue_backend: str = "sqlite"
    queue_backend_ready: bool = True
    redis_queue_adapter_available: bool = False
    redis_url_configured: bool = False
    object_storage_backend: str = "local"
    object_storage_ready: bool = True
    minio_adapter_available: bool = False
    minio_endpoint_configured: bool = False
    local_fallback_enabled: bool = True
    production_backend_configured: bool = False
    backend_warnings: list[str] = Field(default_factory=list)
    backend_blockers: list[str] = Field(default_factory=list)
    # ── Step 16 — Performance / Capacity ──
    performance_benchmarking: bool = True
    performance_tests_enabled: bool = False
    performance_benchmarks_enabled: bool = False
    performance_safe_profile: bool = True
    synthetic_fixture_only: bool = True
    external_load_testing: bool = False
    user_code_benchmarking: bool = False
    capacity_estimation: bool = True
    benchmark_cleanup_enabled: bool = True
    # ── Step 17 — IAM / SSO ──
    iam_provider_config: bool = True
    sso_config_model: bool = True
    oidc_provider_skeleton: bool = True
    saml_provider_skeleton: bool = True
    mock_iam_provider: bool = True
    claim_mapping: bool = True
    role_scope_mapping: bool = True
    jit_provisioning: bool = False
    external_iam_enabled: bool = False
    sso_enabled: bool = False
    real_oidc_login: bool = False
    real_saml_login: bool = False
    token_storage: bool = False
    token_introspection: bool = False
    iam_safe_mode: bool = True
    # ── Step 18 — Observability ──
    observability_config: bool = True
    prometheus_scrape_config: bool = True
    prometheus_alert_rules: bool = True
    grafana_dashboard_spec: bool = True
    otel_adapter: bool = True
    otel_real_export: bool = False
    external_telemetry_export: bool = False
    telemetry_redaction: bool = True
    trace_span_store: bool = True
    observability_safe_mode: bool = True
    # ── Step 19 — Load Testing / SLO ──
    load_testing_framework: bool = True
    load_testing_enabled: bool = False
    staging_load_testing_enabled: bool = False
    local_dry_run_enabled: bool = True
    production_load_testing_allowed: bool = False
    slo_definitions: bool = True
    slo_evaluation: bool = True
    capacity_planning: bool = True
    external_load_testing: bool = False
    load_testing_safe_mode: bool = True


# ═══════════════════════════════════════════
# Step 17 — IAM / SSO Request Models
# ═══════════════════════════════════════════

class CreateIAMProviderConfigRequest(BaseModel):
    provider_type: str = Field(default="mock")
    protocol: str = Field(default="mock")
    enabled: bool = Field(default=False)
    issuer: str = Field(default="")
    client_id: str = Field(default="")
    client_secret: str = Field(default="", description="NEVER returned in response")
    jwks_uri: str = Field(default="")
    discovery_enabled: bool = Field(default=False)
    saml_entity_id: str = Field(default="")
    saml_metadata_ref: str = Field(default="")
    jit_provisioning: bool = Field(default=False)
    default_role: str = Field(default="viewer")
    allowed_domains: list[str] = Field(default_factory=list)
    require_verified_email: bool = Field(default=True)
    external_group_mapping_enabled: bool = Field(default=False)
    organization_id: str = Field(default="")
    workspace_id: str = Field(default="")
    metadata: dict[str, Any] = Field(default_factory=dict)


class CreateIAMRoleMappingRequest(BaseModel):
    provider_config_id: str = Field(default="")
    external_group: str = Field(default="")
    external_claim: str = Field(default="")
    sandbox_role: str = Field(default="viewer")
    sandbox_scopes: list[str] = Field(default_factory=list)
    organization_id: str = Field(default="")
    workspace_id: str = Field(default="")
    enabled: bool = Field(default=True)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SimulateSSOLoginRequest(BaseModel):
    claims: dict[str, Any] = Field(default_factory=dict, description="Mock/safe fixture claims (NO real tokens)")
    provider_config_id: str = Field(..., min_length=1)
    organization_id: str = Field(default="")
    workspace_id: str = Field(default="")


class CreateTraceSpanRequest(BaseModel):
    span_name: str = Field(default="")
    trace_id: str = Field(default="")
    parent_span_id: str = Field(default="")
    organization_id: str = Field(default="")
    workspace_id: str = Field(default="")
    resource_type: str = Field(default="")
    resource_id: str = Field(default="")
    attributes: dict[str, Any] = Field(default_factory=dict)


class SimulateOTelExportRequest(BaseModel):
    signal_type: str = Field(default="metric")
    items: list[dict[str, Any]] = Field(default_factory=list)
    organization_id: str = Field(default="")
    workspace_id: str = Field(default="")


class CreateLoadTestConfigRequest(BaseModel):
    profile: str = Field(default="smoke")
    base_url_masked: str = Field(default="")
    targets: list[str] = Field(default_factory=list)
    max_users: int = Field(default=5, ge=1, le=48)
    max_rps: int = Field(default=5, ge=1, le=48)
    duration_seconds: int = Field(default=30, ge=1, le=3600)
    timeout_seconds: int = Field(default=5, ge=1, le=60)
    allow_production: bool = Field(default=False)
    require_confirmation: bool = Field(default=True)
    organization_id: str = Field(default="")
    workspace_id: str = Field(default="")
    metadata: dict[str, Any] = Field(default_factory=dict)


# ═══════════════════════════════════════════
# Router Factory
# ═══════════════════════════════════════════


class MaterializeArtifactRequest(BaseModel):
    job_id: str = Field(default="")
    record_id: str = Field(default="")
    artifact_name: str = Field(..., min_length=1, description="Artifact 名称")
    artifact_type: str = Field(default=SandboxV2ArtifactType.TEXT)
    content_text: str = Field(default="", description="文本内容（仅模拟/内部使用）")
    requested_by: str = Field(default="system")
    mime_type: str = Field(default="")
    organization_id: str = Field(default="")
    workspace_id: str = Field(default="")
    metadata: dict[str, Any] = Field(default_factory=dict)


class CreateManifestRequest(BaseModel):
    job_id: str = Field(..., min_length=1)
    record_id: str = Field(default="")


class PackageRequestSchema(BaseModel):
    job_id: str = Field(default="")
    organization_id: str = Field(default="")
    workspace_id: str = Field(default="")
    requested_by: str = Field(default="")
    package_name: str = Field(..., min_length=1)
    package_version: str = Field(default="")
    package_manager: str = Field(default="unknown")
    source_url: str = Field(default="")
    source_type: str = Field(default="unknown")
    requested_action: str = Field(default="")
    expected_sha256: str = Field(default="")
    expected_signature: str = Field(default="")
    sbom_ref: str = Field(default="")
    metadata: dict[str, Any] = Field(default_factory=dict)


class QuarantineContentRequest(BaseModel):
    content_text: str = Field(default="", description="文本内容（测试用）")
    original_filename: str = Field(default="package.tmp")


class ReviewRequest(BaseModel):
    decision: str = Field(..., description="approved_metadata_only | rejected")
    reviewed_by: str = Field(default="admin")
    reason: str = Field(default="")


class SBOMSubmitRequest(BaseModel):
    package_request_id: str = Field(..., min_length=1)
    sbom_content: str = Field(..., min_length=1, description="SBOM JSON 内容")
    format: str = Field(default="unknown")


class EgressRequestSchema(BaseModel):
    job_id: str = Field(default="")
    organization_id: str = Field(default="")
    workspace_id: str = Field(default="")
    requested_by: str = Field(default="")
    url: str = Field(..., min_length=1)
    hostname: str = Field(default="")
    port: int = Field(default=443)
    resolved_ips: list[str] = Field(default_factory=list)
    method: str = Field(default="GET")
    purpose: str = Field(default="")


class EgressPreflightSchema(BaseModel):
    url: str = Field(..., min_length=1)
    hostname: str = Field(default="")
    port: int = Field(default=443)
    resolved_ips: list[str] = Field(default_factory=list)
    purpose: str = Field(default="")


class ExecutionPlanSchema(BaseModel):
    job_id: str = Field(default="")
    organization_id: str = Field(default="")
    workspace_id: str = Field(default="")
    provider: str = Field(default="trusted_fixture")
    mode: str = Field(default="simulation")
    command_ref: str = Field(default="")
    image_ref: str = Field(default="")
    resource_limits: dict[str, Any] = Field(default_factory=dict)
    allow_network: bool = Field(default=False)
    allow_filesystem_write: bool = Field(default=False)
    allow_package_install: bool = Field(default=False)
    allow_artifact_writable: bool = Field(default=False)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ContainerPlanSchema(BaseModel):
    job_id: str = Field(default="")
    execution_plan_id: str = Field(default="")
    provider: str = Field(default="docker_rootless_future")
    runtime: str = Field(default="unavailable")
    image: str = Field(default="")
    fixture_id: str = Field(default="")
    timeout_seconds: int = Field(default=30)
    resource_limits: dict[str, Any] = Field(default_factory=dict)


class BenchmarkCreateSchema(BaseModel):
    profile: str = Field(default="smoke")
    targets: list[str] = Field(default_factory=lambda: ["jobs", "queue", "metrics", "alerts"])
    max_jobs: int | None = Field(default=None, ge=1, le=500)
    max_queue_items: int | None = Field(default=None, ge=1, le=500)
    max_artifacts: int | None = Field(default=None, ge=1, le=200)
    max_concurrency: int | None = Field(default=None, ge=1, le=16)
    timeout_seconds: int | None = Field(default=None, ge=1, le=300)
    cleanup_after_run: bool | None = Field(default=None)
    organization_id: str = Field(default="")
    workspace_id: str = Field(default="")
    metadata: dict[str, Any] = Field(default_factory=dict)


def create_sandbox_v2_router(
    service: SandboxV2Service,
    worker: Any = None,
) -> APIRouter:
    router = APIRouter(prefix="/api/runtime/sandbox-v2", tags=["sandbox-v2"])

    # ── 1. Submit Job ──
    @router.post("/jobs")
    async def submit_job(req: SubmitJobRequest) -> dict[str, Any]:
        """提交 sandbox job。支持 ?enqueue=true 加入任务队列。"""
        if req.mode not in MVP_ALLOWED_MODES:
            raise HTTPException(
                status_code=400,
                detail=f"Mode '{req.mode}' is not allowed. Allowed modes: {list(MVP_ALLOWED_MODES)}",
            )
        result = service.submit_job(
            organization_id=req.organization_id,
            workspace_id=req.workspace_id,
            agent_id=req.agent_id,
            requested_by=req.requested_by,
            mode=req.mode,
            requested_action=req.requested_action,
            input_ref=req.input_ref,
            metadata=req.metadata,
            enqueue=req.enqueue,
            priority=req.priority,
            max_attempts=req.max_attempts,
        )
        return result

    # ── 2. Get Job ──
    @router.get("/jobs/{job_id}")
    async def get_job(job_id: str) -> dict[str, Any]:
        """查看 job 状态，包含队列信息。"""
        job_dict = service.get_job_status(job_id)
        if job_dict is None:
            raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
        # 附加队列状态
        queue_info = service.get_queue_status(job_id)
        if "error" not in queue_info:
            job_dict["queue"] = queue_info
        return job_dict

    # ── 3. List Jobs ──
    @router.get("/jobs")
    async def list_jobs(
        organization_id: str = Query(default=""),
        workspace_id: str = Query(default=""),
        limit: int = Query(default=50, ge=1, le=200),
    ) -> dict[str, Any]:
        """列出 jobs。"""
        jobs = service.list_jobs(
            organization_id=organization_id or None,
            workspace_id=workspace_id or None,
            limit=limit,
        )
        return {"jobs": jobs, "total": len(jobs)}

    # ── 4. Cancel Job ──
    @router.post("/jobs/{job_id}/cancel")
    async def cancel_job(job_id: str) -> dict[str, Any]:
        """取消 job。同时取消队列中的 item。"""
        result = service.cancel_queued_or_running_job(job_id)
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        return result

    # ── 5. List Execution Records ──
    @router.get("/execution-records")
    async def list_execution_records(
        job_id: str = Query(default=""),
        limit: int = Query(default=50, ge=1, le=200),
    ) -> dict[str, Any]:
        """查看 execution records。"""
        records = service.list_execution_records(
            job_id=job_id or None,
            limit=limit,
        )
        return {"execution_records": records, "total": len(records)}

    # ── 6. Readiness ──
    @router.get("/readiness", response_model=ReadinessResponse)
    async def readiness() -> ReadinessResponse:
        """返回当前 Sandbox v2 能力状态，包含 Step 10 production hardening 字段。"""
        import os
        from pathlib import Path

        # ── Step 10: 动态检查文件存在性 ──
        project_root = Path(__file__).resolve().parent.parent.parent

        docs_dir = project_root / "docs"
        env_template_ok = (project_root / ".env.sandbox-v2.example").is_file()
        compose_ok = (project_root / "docker-compose.sandbox-v2.example.yml").is_file()
        readiness_script_ok = (project_root / "scripts" / "check_sandbox_v2_production_readiness.py").is_file()

        deployment_checklist_ok = (docs_dir / "sandbox-v2-deployment-checklist.md").is_file()
        operations_runbook_ok = (docs_dir / "sandbox-v2-operations-runbook.md").is_file()
        incident_response_ok = (docs_dir / "sandbox-v2-incident-response.md").is_file()
        hardening_docs_ok = (docs_dir / "sandbox-v2-production-hardening.md").is_file()

        all_docs_present = all([
            deployment_checklist_ok, operations_runbook_ok,
            incident_response_ok, hardening_docs_ok,
        ])

        # ── 安全默认值检查（从环境变量） ──
        def _env_bool(name: str, default: bool) -> bool:
            val = os.getenv(name, "").strip().lower()
            if val in ("true", "1", "yes"):
                return True
            if val in ("false", "0", "no"):
                return False
            return default

        safe_configured = (
            _env_bool("SANDBOX_V2_FAIL_CLOSED", True)
            and not _env_bool("SANDBOX_V2_NETWORK_ENABLED", False)
            and not _env_bool("SANDBOX_V2_PACKAGE_DOWNLOAD_ENABLED", False)
            and not _env_bool("SANDBOX_V2_PACKAGE_INSTALLATION_ENABLED", False)
            and not _env_bool("SANDBOX_V2_CONTAINER_EXECUTION_ENABLED", False)
            and not _env_bool("SANDBOX_V2_USER_COMMAND_EXECUTION", False)
            and not _env_bool("SANDBOX_V2_USER_IMAGE_EXECUTION", False)
            and not _env_bool("SANDBOX_V2_ARBITRARY_PID_KILL", False)
            and not _env_bool("SANDBOX_V2_AUTO_PULL_IMAGES", False)
        )

        # ── Production blockers ──
        blockers: list[str] = []
        warns: list[str] = []

        if not env_template_ok:
            blockers.append(".env.sandbox-v2.example is missing")
        if not hardening_docs_ok:
            blockers.append("Production hardening doc is missing")
        if not deployment_checklist_ok:
            blockers.append("Deployment checklist is missing")
        if not operations_runbook_ok:
            blockers.append("Operations runbook is missing")
        if not incident_response_ok:
            blockers.append("Incident response runbook is missing")
        if not safe_configured:
            blockers.append("Safe defaults are not configured — check environment variables")
        if not readiness_script_ok:
            warns.append("Production readiness script is missing")
        if not compose_ok:
            warns.append("docker-compose.sandbox-v2.example.yml is missing")

        # ── Step 12: Backend readiness ──
        try:
            from src.open_platform.sandbox_v2.config import load_sandbox_v2_settings
            from src.open_platform.sandbox_v2.backend_factory import get_backend_readiness
            settings = load_sandbox_v2_settings()
            backend_status = get_backend_readiness(settings)
            backend_blockers: list[str] = backend_status.get("backend_blockers", [])
            backend_warns: list[str] = backend_status.get("backend_warnings", [])
        except Exception:
            backend_status = {}
            backend_blockers = []
            backend_warns = []

        # 合并 backend_blockers 到 production_blockers
        all_blockers = list(blockers) + backend_blockers
        all_warns = list(warns) + backend_warns
        performance_status = service.get_performance_readiness()

        return ReadinessResponse(
            production_hardening_docs=all_docs_present,
            env_template_present=env_template_ok,
            production_readiness_script=readiness_script_ok,
            deployment_checklist_present=deployment_checklist_ok,
            operations_runbook_present=operations_runbook_ok,
            incident_response_runbook_present=incident_response_ok,
            docker_compose_example_present=compose_ok,
            safe_defaults_configured=safe_configured,
            production_blockers=all_blockers,
            warnings=all_warns,
            # Step 12 backend fields
            database_backend=backend_status.get("database_backend", "sqlite"),
            database_backend_ready=backend_status.get("database_backend_ready", True),
            postgres_adapter_available=backend_status.get("postgres_adapter_available", False),
            postgres_dsn_configured=backend_status.get("postgres_dsn_configured", False),
            queue_backend=backend_status.get("queue_backend", "sqlite"),
            queue_backend_ready=backend_status.get("queue_backend_ready", True),
            redis_queue_adapter_available=backend_status.get("redis_queue_adapter_available", False),
            redis_url_configured=backend_status.get("redis_url_configured", False),
            object_storage_backend=backend_status.get("object_storage_backend", "local"),
            object_storage_ready=backend_status.get("object_storage_ready", True),
            minio_adapter_available=backend_status.get("minio_adapter_available", False),
            minio_endpoint_configured=backend_status.get("minio_endpoint_configured", False),
            local_fallback_enabled=backend_status.get("local_fallback_enabled", True),
            production_backend_configured=backend_status.get("production_backend_configured", False),
            backend_warnings=backend_warns,
            backend_blockers=backend_blockers,
            # Step 11 MicroVM fields
            microvm_provider_abstraction=True,
            firecracker_provider_abstraction=True,
            microvm_execution_enabled=_env_bool("SANDBOX_V2_MICROVM_EXECUTION_ENABLED", False),
            microvm_integration_enabled=_env_bool("SANDBOX_V2_RUN_MICROVM_INTEGRATION", False),
            microvm_runnable=False,
            kvm_available=False,
            firecracker_binary_present=False,
            microvm_kernel_present=False,
            microvm_rootfs_present=False,
            microvm_network_enabled=_env_bool("SANDBOX_V2_MICROVM_NETWORK_ENABLED", False),
            user_kernel_allowed=_env_bool("SANDBOX_V2_MICROVM_ALLOW_USER_KERNEL", False),
            user_rootfs_allowed=_env_bool("SANDBOX_V2_MICROVM_ALLOW_USER_ROOTFS", False),
            host_mounts_allowed=_env_bool("SANDBOX_V2_MICROVM_ALLOW_HOST_MOUNTS", False),
            real_microvm_execution=False,
            # Step 13 backend integration fields
            backend_integration_tests_present=(project_root / "tests" / "test_open_platform" / "integration_backend").is_dir(),
            backend_integration_enabled=_env_bool("SANDBOX_V2_RUN_BACKEND_INTEGRATION", False),
            postgres_integration_ready=_env_bool("SANDBOX_V2_RUN_BACKEND_INTEGRATION", False) and _env_str("SANDBOX_V2_DATABASE_BACKEND", "sqlite") == "postgres" and bool(os.getenv("SANDBOX_V2_POSTGRES_DSN", "")),
            redis_integration_ready=_env_bool("SANDBOX_V2_RUN_BACKEND_INTEGRATION", False) and _env_str("SANDBOX_V2_QUEUE_BACKEND", "sqlite") == "redis" and bool(os.getenv("SANDBOX_V2_REDIS_URL", "")),
            minio_integration_ready=_env_bool("SANDBOX_V2_RUN_BACKEND_INTEGRATION", False) and _env_str("SANDBOX_V2_OBJECT_STORAGE_BACKEND", "local") in ("minio", "s3") and bool(os.getenv("SANDBOX_V2_MINIO_ACCESS_KEY", "") or os.getenv("SANDBOX_V2_S3_ACCESS_KEY", "")),
            backend_integration_blockers=[] if not _env_bool("SANDBOX_V2_RUN_BACKEND_INTEGRATION", False) else [],
            backend_integration_warnings=[] if _env_bool("SANDBOX_V2_RUN_BACKEND_INTEGRATION", False) else [],
            postgres_schema_initialized=False,
            backend_integration_last_run="",
            # Step 14 security fields
            security_context=True,
            access_policy_engine=True,
            rbac_scope_policy=True,
            tenant_isolation=True,
            cross_tenant_deny=True,
            security_audit_events=True,
            audit_hash_chain=True,
            evidence_bundle_export=True,
            sensitive_metadata_redaction=True,
            legacy_endpoint_enforcement="incremental",
            external_iam=False,
            sso_integration=False,
            # Step 15 monitoring fields
            metrics_collector=True, health_checks=True, alert_engine=True,
            internal_alert_records=True, prometheus_export=True,
            external_notifications=False, monitoring_dashboard=True,
            audit_signal_aggregation=True, alert_rules_present=True,
            monitoring_safe_mode=True,
            # Step 16 performance/capacity fields
            performance_benchmarking=performance_status.get("performance_benchmarking", True),
            performance_tests_enabled=performance_status.get("performance_tests_enabled", False),
            performance_benchmarks_enabled=performance_status.get("performance_benchmarks_enabled", False),
            performance_safe_profile=performance_status.get("performance_safe_profile", True),
            synthetic_fixture_only=performance_status.get("synthetic_fixture_only", True),
            external_load_testing=performance_status.get("external_load_testing", False),
            user_code_benchmarking=performance_status.get("user_code_benchmarking", False),
            capacity_estimation=performance_status.get("capacity_estimation", True),
            benchmark_cleanup_enabled=performance_status.get("benchmark_cleanup_enabled", True),
            # Step 17 IAM / SSO fields
            iam_provider_config=True,
            sso_config_model=True,
            oidc_provider_skeleton=True,
            saml_provider_skeleton=True,
            mock_iam_provider=True,
            claim_mapping=True,
            role_scope_mapping=True,
            jit_provisioning=_env_bool("SANDBOX_V2_IAM_JIT_PROVISIONING", False),
            external_iam_enabled=_env_bool("SANDBOX_V2_IAM_ENABLED", False),
            sso_enabled=_env_bool("SANDBOX_V2_SSO_ENABLED", False),
            real_oidc_login=False,
            real_saml_login=False,
            token_storage=False,
            token_introspection=False,
            iam_safe_mode=True,
            # Step 18 Observability fields
            observability_config=True,
            prometheus_scrape_config=True,
            prometheus_alert_rules=True,
            grafana_dashboard_spec=True,
            otel_adapter=True,
            otel_real_export=False,
            external_telemetry_export=False,
            telemetry_redaction=True,
            trace_span_store=True,
            observability_safe_mode=True,
            # Step 19 Load Testing / SLO fields
            load_testing_framework=True,
            load_testing_enabled=_env_bool("SANDBOX_V2_LOAD_TESTING_ENABLED", False),
            staging_load_testing_enabled=_env_bool("SANDBOX_V2_RUN_STAGING_LOAD_TEST", False),
            local_dry_run_enabled=True,
            production_load_testing_allowed=_env_bool("SANDBOX_V2_LOAD_TEST_ALLOW_PRODUCTION", False),
            slo_definitions=True, slo_evaluation=True, capacity_planning=True,
            load_testing_safe_mode=not _env_bool("SANDBOX_V2_RUN_STAGING_LOAD_TEST", False),
        )

    # ═══════════════════════════════════════════
    # Step 2 — Queue / Worker endpoints
    # ═══════════════════════════════════════════

    # ── 7. List Queue ──
    @router.get("/queue")
    async def list_queue(
        status: str = Query(default=""),
        limit: int = Query(default=50, ge=1, le=200),
    ) -> dict[str, Any]:
        """查看队列状态。"""
        items = service.list_queue_items(
            status=status or None,
            limit=limit,
        )
        return {"queue_items": items, "total": len(items)}

    # ── 8. Requeue Expired Leases ──
    @router.post("/queue/requeue-expired")
    async def requeue_expired() -> dict[str, Any]:
        """回收过期 lease 的任务。"""
        count = service.requeue_expired_jobs()
        return {"requeued_count": count, "message": f"{count} expired lease(s) requeued."}

    # ── 9. List Workers ──
    @router.get("/workers")
    async def list_workers(
        limit: int = Query(default=50, ge=1, le=200),
    ) -> dict[str, Any]:
        """查看 worker heartbeat。"""
        workers = service.list_worker_heartbeats(limit=limit)
        return {"workers": workers, "total": len(workers)}

    # ── 10. Run Once (dev/test only) ──
    @router.post("/workers/run-once")
    async def worker_run_once() -> dict[str, Any]:
        """手动触发 worker 处理一个任务。仅开发/测试用。只处理 simulation。"""
        if worker is None:
            raise HTTPException(status_code=503, detail="Worker is not configured.")
        result = worker.run_once()
        if result is None:
            return {"message": "No queued jobs available.", "result": None}
        return {
            "message": "Worker processed one job.",
            "result": result.to_dict(),
        }

    # ── 11. Dead Letter ──
    @router.get("/dead-letter")
    async def list_dead_letter(
        limit: int = Query(default=50, ge=1, le=200),
    ) -> dict[str, Any]:
        """查看 dead letter 队列。"""
        items = service.list_dead_letter(limit=limit)
        return {"dead_letter_items": items, "total": len(items)}

    # ═══════════════════════════════════════════
    # Step 3 — Artifact endpoints
    # ═══════════════════════════════════════════

    from src.open_platform.sandbox_v2.models import (
        SandboxArtifactMaterializationRequest,
    )

    # ── 12. Create Artifact ──
    @router.post("/artifacts")
    async def create_artifact(req: MaterializeArtifactRequest) -> dict[str, Any]:
        """创建/物化 artifact。必须经过 artifact policy。"""
        mat_req = SandboxArtifactMaterializationRequest(
            job_id=req.job_id,
            record_id=req.record_id,
            artifact_name=req.artifact_name,
            artifact_type=req.artifact_type,
            content_text=req.content_text,
            requested_by=req.requested_by,
            read_only=True,
            mime_type=req.mime_type,
            organization_id=req.organization_id,
            workspace_id=req.workspace_id,
            metadata=req.metadata,
        )
        result = service.materialize_artifact(mat_req)
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        return result

    # ── 13. List Artifacts ──
    @router.get("/artifacts")
    async def list_artifacts(
        job_id: str = Query(default=""),
        record_id: str = Query(default=""),
        organization_id: str = Query(default=""),
        workspace_id: str = Query(default=""),
        limit: int = Query(default=50, ge=1, le=200),
    ) -> dict[str, Any]:
        """列出 artifacts。"""
        arts = service.list_artifacts(
            job_id=job_id or None,
            record_id=record_id or None,
            organization_id=organization_id or None,
            workspace_id=workspace_id or None,
            limit=limit,
        )
        return {"artifacts": arts, "total": len(arts)}

    # ── 14. Get Artifact Metadata ──
    @router.get("/artifacts/{artifact_id}")
    async def get_artifact(artifact_id: str) -> dict[str, Any]:
        """查看 artifact metadata。"""
        artifact = service.get_artifact(artifact_id)
        if artifact is None:
            raise HTTPException(status_code=404, detail=f"Artifact '{artifact_id}' not found.")
        return artifact.to_dict()

    # ── 15. Get Artifact Content ──
    @router.get("/artifacts/{artifact_id}/content")
    async def get_artifact_content(artifact_id: str) -> dict[str, Any]:
        """读取 artifact 内容。只允许读取 storage root 内文件。"""
        result = service.get_artifact_content(artifact_id)
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        return result

    # ── 16. Expire Artifact ──
    @router.post("/artifacts/{artifact_id}/expire")
    async def expire_artifact(artifact_id: str) -> dict[str, Any]:
        """标记 artifact 为过期。"""
        artifact = service.get_artifact(artifact_id)
        if artifact is None:
            raise HTTPException(status_code=404, detail=f"Artifact '{artifact_id}' not found.")
        updated = service._store.mark_artifact_expired(artifact_id)
        if updated is None:
            raise HTTPException(status_code=500, detail="Failed to expire artifact.")
        return {"artifact_id": artifact_id, "status": updated.status}

    # ── 17. Delete Artifact ──
    @router.delete("/artifacts/{artifact_id}")
    async def delete_artifact(artifact_id: str) -> dict[str, Any]:
        """删除 artifact（文件 + metadata）。只允许删除 artifact root 内文件。"""
        result = service.delete_artifact(artifact_id)
        if result.get("error"):
            raise HTTPException(status_code=404, detail=result["error"])
        return result

    # ── 18. Create Manifest ──
    @router.post("/artifact-manifests")
    async def create_manifest(req: CreateManifestRequest) -> dict[str, Any]:
        """为 job/record 创建 artifact manifest。"""
        result = service.create_artifact_manifest(req.job_id, req.record_id)
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        return result

    # ── 19. Get Manifest ──
    @router.get("/artifact-manifests/{manifest_id}")
    async def get_manifest(manifest_id: str) -> dict[str, Any]:
        """查看 manifest。"""
        m = service.get_artifact_manifest(manifest_id)
        if m is None:
            raise HTTPException(status_code=404, detail=f"Manifest '{manifest_id}' not found.")
        return m.to_dict()

    # ═══════════════════════════════════════════
    # Step 4 — Package / Supply Chain endpoints
    # ═══════════════════════════════════════════

    # ── 20. Create Package Request ──
    @router.post("/packages/requests")
    async def create_package_request(req: PackageRequestSchema) -> dict[str, Any]:
        """创建 package request。external/public 默认拒绝。"""
        result = service.request_package(**req.model_dump())
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        return result

    # ── 21. List Package Requests ──
    @router.get("/packages/requests")
    async def list_package_requests(
        job_id: str = Query(default=""), organization_id: str = Query(default=""),
        workspace_id: str = Query(default=""), status: str = Query(default=""),
        limit: int = Query(default=50, ge=1, le=200),
    ) -> dict[str, Any]:
        reqs = service.list_package_requests(
            job_id=job_id or None, organization_id=organization_id or None,
            workspace_id=workspace_id or None, status=status or None, limit=limit,
        )
        return {"package_requests": reqs, "total": len(reqs)}

    # ── 22. Get Package Request ──
    @router.get("/packages/requests/{package_request_id}")
    async def get_package_request(package_request_id: str) -> dict[str, Any]:
        r = service.get_package_request(package_request_id)
        if r is None:
            raise HTTPException(status_code=404, detail="Package request not found.")
        return r.to_dict()

    # ── 23. Quarantine Package ──
    @router.post("/packages/requests/{package_request_id}/quarantine")
    async def quarantine_package(package_request_id: str, req: QuarantineContentRequest) -> dict[str, Any]:
        result = service.quarantine_package(package_request_id, content_text=req.content_text, original_filename=req.original_filename)
        if result.get("error"):
            raise HTTPException(status_code=400, detail=result["error"])
        return result

    # ── 24. List Quarantine ──
    @router.get("/packages/quarantine")
    async def list_quarantine(
        package_request_id: str = Query(default=""), status: str = Query(default=""),
        limit: int = Query(default=50, ge=1, le=200),
    ) -> dict[str, Any]:
        recs = service.list_quarantine_records(package_request_id=package_request_id or None, status=status or None, limit=limit)
        return {"quarantine_records": recs, "total": len(recs)}

    # ── 25. Get Quarantine Record ──
    @router.get("/packages/quarantine/{quarantine_id}")
    async def get_quarantine(quarantine_id: str) -> dict[str, Any]:
        r = service.get_quarantine_record(quarantine_id)
        if r is None:
            raise HTTPException(status_code=404, detail="Quarantine record not found.")
        return r.to_dict()

    # ── 26. Review Quarantine ──
    @router.post("/packages/quarantine/{quarantine_id}/review")
    async def review_quarantine(quarantine_id: str, req: ReviewRequest) -> dict[str, Any]:
        result = service.review_quarantine_record(quarantine_id, req.decision, req.reviewed_by, req.reason)
        if result.get("error"):
            raise HTTPException(status_code=400, detail=result["error"])
        return result

    # ── 27. Delete Quarantine ──
    @router.delete("/packages/quarantine/{quarantine_id}")
    async def delete_quarantine(quarantine_id: str) -> dict[str, Any]:
        result = service.delete_quarantined_package(quarantine_id)
        if result.get("error"):
            raise HTTPException(status_code=404, detail=result["error"])
        return result

    # ── 28. Submit SBOM ──
    @router.post("/packages/sbom")
    async def submit_sbom(req: SBOMSubmitRequest) -> dict[str, Any]:
        result = service.submit_package_sbom(req.package_request_id, req.sbom_content, req.format)
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        return result

    # ── 29. List SBOMs ──
    @router.get("/packages/sbom")
    async def list_sboms(
        package_request_id: str = Query(default=""), limit: int = Query(default=50, ge=1, le=200),
    ) -> dict[str, Any]:
        items = service.list_package_sboms(package_request_id=package_request_id or None, limit=limit)
        return {"sboms": items, "total": len(items)}

    # ── 30. Run Scan ──
    @router.post("/packages/scans")
    async def run_scan(package_request_id: str = Query(default=""), sbom_id: str = Query(default="")) -> dict[str, Any]:
        if not package_request_id:
            raise HTTPException(status_code=400, detail="package_request_id is required.")
        result = service.run_package_vulnerability_scan(package_request_id, sbom_id=sbom_id or None)
        return result

    # ── 31. List Scans ──
    @router.get("/packages/scans")
    async def list_scans(
        package_request_id: str = Query(default=""), limit: int = Query(default=50, ge=1, le=200),
    ) -> dict[str, Any]:
        items = service.list_vulnerability_scan_results(package_request_id=package_request_id or None, limit=limit)
        return {"scans": items, "total": len(items)}

    # ═══════════════════════════════════════════
    # Step 5 — Network Egress endpoints
    # ═══════════════════════════════════════════

    # ── 32. Create Egress Request ──
    @router.post("/network/egress-requests")
    async def create_egress_request(req: EgressRequestSchema) -> dict[str, Any]:
        result = service.request_network_egress(**req.model_dump())
        if result.get("error"):
            raise HTTPException(status_code=400, detail=result["error"])
        return result

    # ── 33. List Egress Requests ──
    @router.get("/network/egress-requests")
    async def list_egress_requests(
        job_id: str = Query(default=""), organization_id: str = Query(default=""),
        workspace_id: str = Query(default=""), status: str = Query(default=""),
        limit: int = Query(default=50, ge=1, le=200),
    ) -> dict[str, Any]:
        items = service.list_network_egress_requests(
            job_id=job_id or None, organization_id=organization_id or None,
            workspace_id=workspace_id or None, status=status or None, limit=limit)
        return {"egress_requests": items, "total": len(items)}

    # ── 34. Get Egress Request ──
    @router.get("/network/egress-requests/{egress_request_id}")
    async def get_egress_request(egress_request_id: str) -> dict[str, Any]:
        r = service.get_network_egress_request(egress_request_id)
        if r is None:
            raise HTTPException(status_code=404, detail="Egress request not found.")
        return r

    # ── 35. List Audit Records ──
    @router.get("/network/audit-records")
    async def list_audit_records(
        egress_request_id: str = Query(default=""), job_id: str = Query(default=""),
        limit: int = Query(default=50, ge=1, le=200),
    ) -> dict[str, Any]:
        items = service.list_network_egress_audit_records(
            egress_request_id=egress_request_id or None, job_id=job_id or None, limit=limit)
        return {"audit_records": items, "total": len(items)}

    # ── 36. Preflight ──
    @router.post("/network/preflight")
    async def preflight_egress(req: EgressPreflightSchema) -> dict[str, Any]:
        result = service.evaluate_network_egress(**req.model_dump())
        return result

    # ── 37. Network Readiness ──
    @router.get("/network/readiness")
    async def network_readiness() -> dict[str, Any]:
        return service.get_network_egress_readiness()

    # ═══════════════════════════════════════════
    # Step 6A — Isolation / Execution endpoints
    # ═══════════════════════════════════════════

    # ── 38. Isolation Capabilities ──
    @router.get("/isolation/capabilities")
    async def isolation_capabilities() -> dict[str, Any]:
        return service.collect_isolation_capabilities()

    # ── 39. Isolation Readiness ──
    @router.get("/isolation/readiness")
    async def isolation_readiness() -> dict[str, Any]:
        return service.get_isolation_readiness()

    # ── 40. Create Execution Plan ──
    @router.post("/isolation/execution-plans")
    async def create_execution_plan(req: ExecutionPlanSchema) -> dict[str, Any]:
        result = service.create_execution_plan(**req.model_dump())
        if result.get("error"):
            raise HTTPException(status_code=400, detail=result["error"])
        return result

    # ── 41. List Execution Plans ──
    @router.get("/isolation/execution-plans")
    async def list_execution_plans(
        job_id: str = Query(default=""), organization_id: str = Query(default=""),
        workspace_id: str = Query(default=""), status: str = Query(default=""),
        limit: int = Query(default=50, ge=1, le=200),
    ) -> dict[str, Any]:
        items = service.list_execution_plans(
            job_id=job_id or None, organization_id=organization_id or None,
            workspace_id=workspace_id or None, status=status or None, limit=limit)
        return {"execution_plans": items, "total": len(items)}

    # ── 42. Get Execution Plan ──
    @router.get("/isolation/execution-plans/{execution_plan_id}")
    async def get_execution_plan(execution_plan_id: str) -> dict[str, Any]:
        plan = service.get_execution_plan(execution_plan_id)
        if plan is None:
            raise HTTPException(status_code=404, detail="Execution plan not found.")
        return plan.to_dict()

    # ── 43. Run Trusted Fixture ──
    @router.post("/isolation/execution-plans/{execution_plan_id}/run-trusted-fixture")
    async def run_trusted_fixture(execution_plan_id: str) -> dict[str, Any]:
        result = service.run_trusted_fixture_execution(execution_plan_id)
        if result.get("error"):
            raise HTTPException(status_code=400, detail=result["error"])
        return result

    # ── 44. Cancel Execution Plan ──
    @router.post("/isolation/execution-plans/{execution_plan_id}/cancel")
    async def cancel_execution_plan(execution_plan_id: str) -> dict[str, Any]:
        result = service.cancel_execution_plan(execution_plan_id)
        if result.get("error"):
            raise HTTPException(status_code=404, detail=result["error"])
        return result

    # ═══════════════════════════════════════════
    # Step 6B — Container Execution endpoints
    # ═══════════════════════════════════════════

    # ── 45. Create Container Plan ──
    @router.post("/isolation/container-plans")
    async def create_container_plan(req: ContainerPlanSchema) -> dict[str, Any]:
        return service.create_container_execution_plan(**req.model_dump())

    # ── 46. List Container Plans ──
    @router.get("/isolation/container-plans")
    async def list_container_plans(
        job_id: str = Query(default=""), status: str = Query(default=""),
        limit: int = Query(default=50, ge=1, le=200),
    ) -> dict[str, Any]:
        items = service.list_container_execution_plans(job_id=job_id or None, status=status or None, limit=limit)
        return {"container_plans": items, "total": len(items)}

    # ── 47. Get Container Plan ──
    @router.get("/isolation/container-plans/{container_plan_id}")
    async def get_container_plan(container_plan_id: str) -> dict[str, Any]:
        plan = service.get_container_execution_plan(container_plan_id)
        if plan is None: raise HTTPException(status_code=404, detail="Container plan not found.")
        return plan.to_dict()

    # ── 48. Run Container Trusted Fixture ──
    @router.post("/isolation/container-plans/{container_plan_id}/run-trusted-fixture")
    async def run_container_trusted_fixture(container_plan_id: str) -> dict[str, Any]:
        result = service.run_container_trusted_fixture(container_plan_id)
        if result.get("error"): raise HTTPException(status_code=400, detail=result["error"])
        return result

    # ── 49. List Container Results ──
    @router.get("/isolation/container-results")
    async def list_container_results(
        job_id: str = Query(default=""), container_plan_id: str = Query(default=""),
        limit: int = Query(default=50, ge=1, le=200),
    ) -> dict[str, Any]:
        items = service.list_container_execution_results(job_id=job_id or None, container_plan_id=container_plan_id or None, limit=limit)
        return {"container_results": items, "total": len(items)}

    # ── 50. Get Container Result ──
    @router.get("/isolation/container-results/{container_result_id}")
    async def get_container_result(container_result_id: str) -> dict[str, Any]:
        r = service.get_container_execution_result(container_result_id)
        if r is None: raise HTTPException(status_code=404, detail="Container result not found.")
        return r.to_dict()

    # ═══════════════════════════════════════════
    # Step 6C — Real Container Fixture endpoints
    # ═══════════════════════════════════════════

    # ── Container Runtime Preflight ──
    @router.get("/isolation/container-runtime/preflight")
    async def container_runtime_preflight() -> dict[str, Any]:
        return service.get_container_runtime_preflight()

    # ── Run Real Container Trusted Fixture ──
    @router.post("/isolation/container-plans/{container_plan_id}/run-real-trusted-fixture")
    async def run_real_container_trusted_fixture_endpoint(container_plan_id: str) -> dict[str, Any]:
        result = service.run_real_container_trusted_fixture(container_plan_id)
        if result.get("error"): raise HTTPException(status_code=400, detail=result["error"])
        return result

    # ═══════════════════════════════════════════
    # Step 11 — MicroVM / Firecracker endpoints
    # ═══════════════════════════════════════════

    # ── MicroVM Preflight ──
    @router.get("/isolation/microvm/preflight")
    async def microvm_preflight() -> dict[str, Any]:
        """MicroVM 前置条件检查。不启动 Firecracker。"""
        try:
            from src.open_platform.sandbox_v2.isolation_capabilities import SandboxIsolationCapabilityProbe
            probe = SandboxIsolationCapabilityProbe()
            return probe.check_microvm_preconditions()
        except Exception as e:
            return {"error": str(e), "runnable": False}

    # ── MicroVM Readiness ──
    @router.get("/isolation/microvm/readiness")
    async def microvm_readiness() -> dict[str, Any]:
        """MicroVM readiness 状态。"""
        try:
            from src.open_platform.sandbox_v2.isolation_capabilities import SandboxIsolationCapabilityProbe
            probe = SandboxIsolationCapabilityProbe()
            return probe.get_microvm_readiness_summary()
        except Exception as e:
            return {"error": str(e)}

    # ── Create MicroVM Plan ──
    @router.post("/isolation/microvm-plans")
    async def create_microvm_plan(
        job_id: str = Query(default=""),
        organization_id: str = Query(default=""),
        workspace_id: str = Query(default=""),
        fixture_id: str = Query(default="hello-microvm-fixture"),
    ) -> dict[str, Any]:
        """创建 MicroVM execution plan。"""
        try:
            import os as _os
            from src.open_platform.sandbox_v2.models import SandboxMicroVMExecutionPlan
            from src.open_platform.sandbox_v2.microvm_policy import evaluate_microvm_policy

            plan = SandboxMicroVMExecutionPlan(
                job_id=job_id, organization_id=organization_id,
                workspace_id=workspace_id, fixture_id=fixture_id,
            )
            policy = evaluate_microvm_policy(
                plan,
                microvm_execution_enabled=_os.environ.get("SANDBOX_V2_MICROVM_EXECUTION_ENABLED", "").lower() in ("true", "1", "yes"),
                run_microvm_integration=_os.environ.get("SANDBOX_V2_RUN_MICROVM_INTEGRATION", "").lower() in ("true", "1", "yes"),
                is_linux=False, has_kvm=False,
                firecracker_binary_present=False, kernel_present=False, rootfs_present=False,
            )
            if policy["allowed"]:
                try:
                    service._store.create_microvm_execution_plan(plan)
                except Exception:
                    pass
            return {"plan": plan.to_dict(), "policy": policy}
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    # ── List MicroVM Plans ──
    @router.get("/isolation/microvm-plans")
    async def list_microvm_plans(
        job_id: str = Query(default=""), status: str = Query(default=""),
        limit: int = Query(default=50, ge=1, le=200),
    ) -> dict[str, Any]:
        try:
            items = service._store.list_microvm_execution_plans(job_id=job_id or None, status=status or None, limit=limit)
            return {"microvm_plans": [p.to_dict() if hasattr(p, 'to_dict') else p for p in items], "total": len(items)}
        except Exception:
            return {"microvm_plans": [], "total": 0}

    # ── Get MicroVM Plan ──
    @router.get("/isolation/microvm-plans/{microvm_plan_id}")
    async def get_microvm_plan(microvm_plan_id: str) -> dict[str, Any]:
        try:
            plan = service._store.get_microvm_execution_plan(microvm_plan_id)
            if plan is None:
                raise HTTPException(status_code=404, detail="MicroVM plan not found.")
            return plan.to_dict() if hasattr(plan, 'to_dict') else {"microvm_plan": plan}
        except HTTPException:
            raise
        except Exception:
            return {"microvm_plan_id": microvm_plan_id, "status": "error"}

    # ── Run MicroVM Trusted Fixture ──
    @router.post("/isolation/microvm-plans/{microvm_plan_id}/run-trusted-fixture")
    async def run_microvm_trusted_fixture(microvm_plan_id: str) -> dict[str, Any]:
        """运行/预检 MicroVM trusted fixture。环境不满足时返回 disabled/unavailable。"""
        try:
            from src.open_platform.sandbox_v2.microvm_provider import FirecrackerMicroVMExecutionProvider
            from src.open_platform.sandbox_v2.models import SandboxMicroVMRuntimeConfig, SandboxExecutionPlan

            config = SandboxMicroVMRuntimeConfig(
                runtime="firecracker",
                firecracker_bin_path=os.getenv("SANDBOX_V2_FIRECRACKER_BIN_PATH", ""),
                kernel_path=os.getenv("SANDBOX_V2_FIRECRACKER_KERNEL_PATH", ""),
                rootfs_path=os.getenv("SANDBOX_V2_FIRECRACKER_ROOTFS_PATH", ""),
            )
            provider = FirecrackerMicroVMExecutionProvider(config=config)

            plan = service._store.get_microvm_execution_plan(microvm_plan_id)
            if plan is None:
                # 尝试运行不带已存在 plan 的 preflight
                result = provider.run_trusted_fixture(SandboxExecutionPlan(
                    job_id="preflight", command_ref="hello-microvm-fixture",
                ))
                return result

            result = provider.run_trusted_fixture(plan)
            return result
        except Exception as e:
            return {"executed": False, "status": "error", "reason": str(e)}

    # ── List MicroVM Results ──
    @router.get("/isolation/microvm-results")
    async def list_microvm_results(
        job_id: str = Query(default=""), microvm_plan_id: str = Query(default=""),
        limit: int = Query(default=50, ge=1, le=200),
    ) -> dict[str, Any]:
        try:
            items = service._store.list_microvm_execution_results(job_id=job_id or None, microvm_plan_id=microvm_plan_id or None, limit=limit)
            return {"microvm_results": [r.to_dict() if hasattr(r, 'to_dict') else r for r in items], "total": len(items)}
        except Exception:
            return {"microvm_results": [], "total": 0}

    # ── Get MicroVM Result ──
    @router.get("/isolation/microvm-results/{microvm_result_id}")
    async def get_microvm_result(microvm_result_id: str) -> dict[str, Any]:
        try:
            result = service._store.get_microvm_execution_result(microvm_result_id)
            if result is None:
                raise HTTPException(status_code=404, detail="MicroVM result not found.")
            return result.to_dict() if hasattr(result, 'to_dict') else {"microvm_result": result}
        except HTTPException:
            raise
        except Exception:
            return {"microvm_result_id": microvm_result_id, "status": "error"}

    # ═══════════════════════════════════════════
    # Step 7 — Kill Switch endpoints
    # ═══════════════════════════════════════════

    # ── 51. Kill Job ──
    @router.post("/kill/job/{job_id}")
    async def kill_job(job_id: str) -> dict[str, Any]:
        return service.request_kill_job(job_id)

    # ── 52. Kill Execution Plan ──
    @router.post("/kill/execution-plan/{execution_plan_id}")
    async def kill_execution_plan(execution_plan_id: str) -> dict[str, Any]:
        result = service.request_kill_execution_plan(execution_plan_id)
        if result.get("error"): raise HTTPException(status_code=404, detail=result["error"])
        return result

    # ── 53. Kill Container Plan ──
    @router.post("/kill/container-plan/{container_plan_id}")
    async def kill_container_plan(container_plan_id: str) -> dict[str, Any]:
        result = service.request_kill_container_plan(container_plan_id)
        if result.get("error"): raise HTTPException(status_code=404, detail=result["error"])
        return result

    # ── 54. List Kill Requests ──
    @router.get("/kill/requests")
    async def list_kill_requests(job_id: str = Query(default=""), status: str = Query(default=""), limit: int = Query(default=50, ge=1, le=200)) -> dict[str, Any]:
        items = service.list_kill_requests(job_id=job_id or None, status=status or None, limit=limit)
        return {"kill_requests": items, "total": len(items)}

    # ── 55. List Kill Records ──
    @router.get("/kill/records")
    async def list_kill_records(job_id: str = Query(default=""), kill_request_id: str = Query(default=""), limit: int = Query(default=50, ge=1, le=200)) -> dict[str, Any]:
        items = service.list_kill_records(job_id=job_id or None, kill_request_id=kill_request_id or None, limit=limit)
        return {"kill_records": items, "total": len(items)}

    # ── 56. List Active Handles ──
    @router.get("/kill/active-handles")
    async def list_active_handles(status: str = Query(default=""), limit: int = Query(default=50, ge=1, le=200)) -> dict[str, Any]:
        items = service.list_active_execution_handles(status=status or None, limit=limit)
        return {"active_handles": items, "total": len(items)}

    # ── 57. Cancel Handle ──
    @router.post("/kill/handles/{handle_id}/cancel-request")
    async def cancel_handle(handle_id: str, reason: str = Query(default="User requested cancel.")) -> dict[str, Any]:
        return service.request_handle_cancel(handle_id, reason)

    # ── 58. Kill Readiness ──
    @router.get("/kill/readiness")
    async def kill_readiness() -> dict[str, Any]:
        return service.get_kill_readiness()

    # ═══════════════════════════════════════════
    # Step 14 — Security / Access / Audit / Evidence
    # ═══════════════════════════════════════════

    # ── Access Evaluate ──
    @router.post("/security/access/evaluate")
    async def evaluate_access(
        principal_type: str = Query(default="user"),
        roles: str = Query(default="viewer"),
        scopes: str = Query(default=""),
        organization_id: str = Query(default=""),
        workspace_id: str = Query(default=""),
        resource_type: str = Query(default="job"),
        resource_id: str = Query(default=""),
        action: str = Query(default="read"),
        resource_organization_id: str = Query(default=""),
        resource_workspace_id: str = Query(default=""),
    ) -> dict[str, Any]:
        try:
            from src.open_platform.sandbox_v2.access_policy import SandboxV2AccessPolicyEngine
            roles_list = [r.strip() for r in roles.split(",") if r.strip()]
            scopes_list = [s.strip() for s in scopes.split(",") if s.strip()]
            result = SandboxV2AccessPolicyEngine.evaluate_access(
                principal_type=principal_type, roles=roles_list, scopes=scopes_list,
                organization_id=organization_id, workspace_id=workspace_id,
                resource_organization_id=resource_organization_id,
                resource_workspace_id=resource_workspace_id,
                resource_type=resource_type, resource_id=resource_id, action=action,
            )
            return result
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    # ── List Audit Events ──
    @router.get("/security/audit/events")
    async def list_security_audit_events(
        organization_id: str = Query(default=""),
        workspace_id: str = Query(default=""),
        event_type: str = Query(default=""),
        severity: str = Query(default=""),
        limit: int = Query(default=50, ge=1, le=200),
    ) -> dict[str, Any]:
        try:
            from src.open_platform.sandbox_v2.security_audit import SandboxV2SecurityAuditService
            audit = SandboxV2SecurityAuditService(store=service._store)
            items = audit.list_audit_events(
                organization_id=organization_id or None, workspace_id=workspace_id or None,
                event_type=event_type or None, severity=severity or None, limit=limit,
            )
            return {"audit_events": [e.to_dict() if hasattr(e, 'to_dict') else e for e in items], "total": len(items)}
        except Exception as e:
            return {"audit_events": [], "total": 0, "error": str(e)}

    # ── Get Audit Event ──
    @router.get("/security/audit/events/{audit_event_id}")
    async def get_security_audit_event(audit_event_id: str) -> dict[str, Any]:
        try:
            from src.open_platform.sandbox_v2.security_audit import SandboxV2SecurityAuditService
            audit = SandboxV2SecurityAuditService(store=service._store)
            event = audit._store.get_security_audit_event(audit_event_id) if audit._store else None
            if event is None:
                raise HTTPException(status_code=404, detail="Audit event not found.")
            return event.to_dict() if hasattr(event, 'to_dict') else {"audit_event": event}
        except HTTPException:
            raise
        except Exception as e:
            return {"audit_event_id": audit_event_id, "error": str(e)}

    # ── Verify Audit Chain ──
    @router.get("/security/audit/verify-chain")
    async def verify_audit_chain(
        organization_id: str = Query(default=""),
        workspace_id: str = Query(default=""),
    ) -> dict[str, Any]:
        try:
            from src.open_platform.sandbox_v2.security_audit import SandboxV2SecurityAuditService
            audit = SandboxV2SecurityAuditService(store=service._store)
            return audit.verify_audit_chain(organization_id=organization_id, workspace_id=workspace_id)
        except Exception as e:
            return {"valid": False, "reason": str(e), "tampered": [], "events_checked": 0}

    # ── Create Evidence Bundle ──
    @router.post("/security/evidence-bundles")
    async def create_evidence_bundle(
        organization_id: str = Query(default=""),
        workspace_id: str = Query(default=""),
        created_by: str = Query(default="admin"),
        title: str = Query(default="Evidence Bundle"),
    ) -> dict[str, Any]:
        try:
            from src.open_platform.sandbox_v2.security_audit import SandboxV2SecurityAuditService
            audit = SandboxV2SecurityAuditService(store=service._store)
            bundle = audit.create_evidence_bundle(
                organization_id=organization_id, workspace_id=workspace_id,
                created_by=created_by, title=title,
            )
            return bundle.to_dict() if hasattr(bundle, 'to_dict') else {"bundle": bundle}
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    # ── List Evidence Bundles ──
    @router.get("/security/evidence-bundles")
    async def list_evidence_bundles(
        organization_id: str = Query(default=""),
        workspace_id: str = Query(default=""),
        limit: int = Query(default=50, ge=1, le=200),
    ) -> dict[str, Any]:
        try:
            from src.open_platform.sandbox_v2.security_audit import SandboxV2SecurityAuditService
            audit = SandboxV2SecurityAuditService(store=service._store)
            items = audit.list_evidence_bundles(
                organization_id=organization_id or None, workspace_id=workspace_id or None, limit=limit,
            )
            return {"evidence_bundles": [e.to_dict() if hasattr(e, 'to_dict') else e for e in items], "total": len(items)}
        except Exception:
            return {"evidence_bundles": [], "total": 0}

    # ── Get Evidence Bundle ──
    @router.get("/security/evidence-bundles/{evidence_bundle_id}")
    async def get_evidence_bundle(evidence_bundle_id: str) -> dict[str, Any]:
        try:
            from src.open_platform.sandbox_v2.security_audit import SandboxV2SecurityAuditService
            audit = SandboxV2SecurityAuditService(store=service._store)
            result = audit.export_evidence_bundle_json(evidence_bundle_id)
            if "error" in result:
                raise HTTPException(status_code=404, detail=result["error"])
            return result
        except HTTPException:
            raise
        except Exception as e:
            return {"evidence_bundle_id": evidence_bundle_id, "error": str(e)}

    # ── Security Readiness ──
    @router.get("/security/readiness")
    async def security_readiness() -> dict[str, Any]:
        return {
            "security_context": True, "access_policy_engine": True,
            "rbac_scope_policy": True, "tenant_isolation": True,
            "cross_tenant_deny": True, "security_audit_events": True,
            "audit_hash_chain": True, "evidence_bundle_export": True,
            "sensitive_metadata_redaction": True,
            "legacy_endpoint_enforcement": "incremental",
            "external_iam": False, "sso_integration": False,
        }

    # ═══════════════════════════════════════════
    # Step 15 — Monitoring / Metrics / Alerts / Health
    # ═══════════════════════════════════════════

    @router.get("/monitoring/metrics/snapshot")
    async def get_metrics_snapshot() -> dict[str, Any]:
        try:
            from src.open_platform.sandbox_v2.metrics import SandboxV2MetricsCollector
            mc = SandboxV2MetricsCollector(store=service._store)
            snap = mc.create_snapshot()
            return snap.to_dict()
        except Exception as e:
            return {"error": str(e)}

    @router.post("/monitoring/metrics/collect")
    async def collect_metrics() -> dict[str, Any]:
        try:
            from src.open_platform.sandbox_v2.metrics import SandboxV2MetricsCollector
            mc = SandboxV2MetricsCollector(store=service._store)
            data = mc.collect_all()
            return {"collected": True, "samples": len(data.get("samples", []))}
        except Exception as e:
            return {"collected": False, "error": str(e)}

    @router.get("/monitoring/metrics/prometheus")
    async def get_prometheus_metrics() -> Any:
        from fastapi.responses import PlainTextResponse
        try:
            from src.open_platform.sandbox_v2.metrics import SandboxV2MetricsCollector
            mc = SandboxV2MetricsCollector(store=service._store)
            return PlainTextResponse(content=mc.export_prometheus_text(), media_type="text/plain")
        except Exception as e:
            return PlainTextResponse(content=f"# Error: {e}", media_type="text/plain")

    @router.get("/monitoring/health")
    async def get_health() -> dict[str, Any]:
        try:
            from src.open_platform.sandbox_v2.health import SandboxV2HealthService
            hs = SandboxV2HealthService(store=service._store)
            results = hs.run_all()
            return {"health_checks": [r.to_dict() for r in results],
                    "healthy": all(r.ready for r in results),
                    "total": len(results)}
        except Exception as e:
            return {"healthy": False, "error": str(e)}

    @router.get("/monitoring/alerts/rules")
    async def list_alert_rules() -> dict[str, Any]:
        try:
            from src.open_platform.sandbox_v2.alerts import SandboxV2AlertEngine
            engine = SandboxV2AlertEngine(store=service._store)
            rules = engine.list_rules()
            return {"alert_rules": [r if isinstance(r, dict) else r.to_dict() if hasattr(r, 'to_dict') else str(r) for r in rules], "total": len(rules)}
        except Exception as e:
            return {"alert_rules": [], "total": 0, "error": str(e)}

    @router.post("/monitoring/alerts/evaluate")
    async def evaluate_alerts() -> dict[str, Any]:
        try:
            from src.open_platform.sandbox_v2.metrics import SandboxV2MetricsCollector
            from src.open_platform.sandbox_v2.alerts import SandboxV2AlertEngine
            mc = SandboxV2MetricsCollector(store=service._store)
            data = mc.collect_all()
            engine = SandboxV2AlertEngine(store=service._store)
            alerts = engine.evaluate_all(data.get("gauges", {}))
            return {"alerts_triggered": len(alerts), "alerts": [a.to_dict() for a in alerts]}
        except Exception as e:
            return {"alerts_triggered": 0, "error": str(e)}

    @router.get("/monitoring/alerts")
    async def list_alerts(status: str = Query(default=""), severity: str = Query(default=""), limit: int = Query(default=100, ge=1, le=200)) -> dict[str, Any]:
        try:
            from src.open_platform.sandbox_v2.alerts import SandboxV2AlertEngine
            engine = SandboxV2AlertEngine(store=service._store)
            alerts = engine.list_alerts(status=status or None, severity=severity or None, limit=limit)
            return {"alerts": [a if isinstance(a, dict) else a.to_dict() if hasattr(a, 'to_dict') else str(a) for a in alerts], "total": len(alerts)}
        except Exception as e:
            return {"alerts": [], "total": 0, "error": str(e)}

    @router.post("/monitoring/alerts/{alert_id}/ack")
    async def ack_alert(alert_id: str) -> dict[str, Any]:
        try:
            from src.open_platform.sandbox_v2.alerts import SandboxV2AlertEngine
            engine = SandboxV2AlertEngine(store=service._store)
            return engine.acknowledge_alert(alert_id, "admin")
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    @router.post("/monitoring/alerts/{alert_id}/resolve")
    async def resolve_alert(alert_id: str) -> dict[str, Any]:
        try:
            from src.open_platform.sandbox_v2.alerts import SandboxV2AlertEngine
            engine = SandboxV2AlertEngine(store=service._store)
            return engine.resolve_alert(alert_id, "admin")
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    @router.get("/monitoring/readiness")
    async def monitoring_readiness() -> dict[str, Any]:
        return {
            "metrics_collector": True, "health_checks": True, "alert_engine": True,
            "internal_alert_records": True, "prometheus_export": True,
            "external_notifications": False, "monitoring_dashboard": True,
            "audit_signal_aggregation": True, "alert_rules_present": True,
            "monitoring_safe_mode": True,
        }

    # ═══════════════════════════════════════════
    # Step 16 — Performance / Capacity
    # ═══════════════════════════════════════════

    @router.get("/performance/readiness")
    async def performance_readiness() -> dict[str, Any]:
        return service.get_performance_readiness()

    @router.post("/performance/benchmarks")
    async def create_performance_benchmark(req: BenchmarkCreateSchema) -> dict[str, Any]:
        try:
            config = service.create_performance_benchmark_config(
                profile=req.profile,
                targets=req.targets,
                max_jobs=req.max_jobs,
                max_queue_items=req.max_queue_items,
                max_artifacts=req.max_artifacts,
                max_concurrency=req.max_concurrency,
                timeout_seconds=req.timeout_seconds,
                cleanup_after_run=req.cleanup_after_run,
                organization_id=req.organization_id,
                workspace_id=req.workspace_id,
                metadata=req.metadata,
            )
            return {"benchmark": config}
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            logger.warning("sandbox_v2_performance_config_failed", extra={"error": str(e)})
            raise HTTPException(status_code=400, detail="Benchmark config rejected.")

    @router.post("/performance/benchmarks/{benchmark_id}/run")
    async def run_performance_benchmark(benchmark_id: str) -> dict[str, Any]:
        try:
            result = service.run_performance_benchmark(benchmark_id)
            if result.get("status") == "not_found":
                raise HTTPException(status_code=404, detail="Benchmark config not found.")
            return result
        except HTTPException:
            raise
        except Exception as e:
            logger.warning("sandbox_v2_performance_run_failed", extra={"error": str(e)})
            return {"benchmark_id": benchmark_id, "status": "failed", "error": "Benchmark failed closed."}

    @router.get("/performance/benchmarks")
    async def list_performance_benchmarks(
        limit: int = Query(default=50, ge=1, le=100),
    ) -> dict[str, Any]:
        items = service.list_performance_benchmark_configs(limit=limit)
        return {"benchmarks": items, "total": len(items)}

    @router.get("/performance/results")
    async def list_performance_results(
        benchmark_id: str = Query(default=""),
        target: str = Query(default=""),
        limit: int = Query(default=100, ge=1, le=200),
    ) -> dict[str, Any]:
        items = service.list_performance_benchmark_results(
            benchmark_id=benchmark_id or None,
            target=target or None,
            limit=limit,
        )
        return {"results": items, "total": len(items)}

    @router.get("/performance/capacity/latest")
    async def latest_capacity_estimate() -> dict[str, Any]:
        estimate = service.get_latest_capacity_estimate()
        return {"capacity_estimate": estimate}

    @router.get("/performance/report/{benchmark_id}")
    async def get_performance_report(
        benchmark_id: str,
        format: str = Query(default="markdown", pattern="^(markdown|json)$"),
    ) -> dict[str, Any]:
        report = service.get_performance_report(benchmark_id, report_format=format)
        if report.get("error"):
            raise HTTPException(status_code=404, detail="Benchmark config not found.")
        return report

    # ═══════════════════════════════════════════
    # Step 17 — IAM / SSO endpoints
    # ═══════════════════════════════════════════

    # ── IAM Readiness ──
    @router.get("/iam/readiness")
    async def iam_readiness() -> dict[str, Any]:
        return service.get_iam_readiness()

    # ── Provider Configs ──
    @router.post("/iam/provider-configs")
    async def create_iam_provider_config(payload: CreateIAMProviderConfigRequest) -> dict[str, Any]:
        try:
            config = service.create_iam_provider_config(
                provider_type=payload.provider_type,
                protocol=payload.protocol,
                enabled=payload.enabled,
                issuer=payload.issuer,
                client_id=payload.client_id,
                client_secret=payload.client_secret,
                jwks_uri=payload.jwks_uri,
                discovery_enabled=payload.discovery_enabled,
                saml_entity_id=payload.saml_entity_id,
                saml_metadata_ref=payload.saml_metadata_ref,
                jit_provisioning=payload.jit_provisioning,
                default_role=payload.default_role,
                allowed_domains=payload.allowed_domains,
                require_verified_email=payload.require_verified_email,
                external_group_mapping_enabled=payload.external_group_mapping_enabled,
                organization_id=payload.organization_id,
                workspace_id=payload.workspace_id,
                metadata=payload.metadata,
            )
            if config is None:
                raise HTTPException(status_code=500, detail="Failed to create provider config")
            return {"provider_config": config.to_dict()}
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    @router.get("/iam/provider-configs")
    async def list_iam_provider_configs(
        organization_id: str = Query(default=""),
        workspace_id: str = Query(default=""),
        limit: int = Query(default=50, ge=1, le=100),
    ) -> dict[str, Any]:
        items = service.list_iam_provider_configs(
            organization_id=organization_id or None,
            workspace_id=workspace_id or None,
            limit=limit,
        )
        return {"provider_configs": [c.to_dict() for c in items], "total": len(items)}

    @router.get("/iam/provider-configs/{provider_config_id}")
    async def get_iam_provider_config(provider_config_id: str) -> dict[str, Any]:
        config = service.get_iam_provider_config(provider_config_id)
        if config is None:
            raise HTTPException(status_code=404, detail="Provider config not found")
        return {"provider_config": config.to_dict()}

    # ── Role Mappings ──
    @router.post("/iam/role-mappings")
    async def create_iam_role_mapping(payload: CreateIAMRoleMappingRequest) -> dict[str, Any]:
        try:
            mapping = service.create_iam_role_mapping(
                provider_config_id=payload.provider_config_id,
                external_group=payload.external_group,
                external_claim=payload.external_claim,
                sandbox_role=payload.sandbox_role,
                sandbox_scopes=payload.sandbox_scopes,
                organization_id=payload.organization_id,
                workspace_id=payload.workspace_id,
                enabled=payload.enabled,
                metadata=payload.metadata,
            )
            if mapping is None:
                raise HTTPException(status_code=500, detail="Failed to create role mapping")
            return {"role_mapping": mapping.to_dict()}
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    @router.get("/iam/role-mappings")
    async def list_iam_role_mappings(
        provider_config_id: str = Query(default=""),
        organization_id: str = Query(default=""),
        workspace_id: str = Query(default=""),
        limit: int = Query(default=50, ge=1, le=100),
    ) -> dict[str, Any]:
        items = service.list_iam_role_mappings(
            provider_config_id=provider_config_id or None,
            organization_id=organization_id or None,
            workspace_id=workspace_id or None,
            limit=limit,
        )
        return {"role_mappings": [m.to_dict() for m in items], "total": len(items)}

    # ── SSO Simulation ──
    @router.post("/iam/simulate-login")
    async def simulate_sso_login(payload: SimulateSSOLoginRequest) -> dict[str, Any]:
        # Reject real tokens
        claims = payload.claims or {}
        token_keys = {"access_token", "id_token", "refresh_token", "token", "jwt", "code", "SAMLResponse"}
        if any(k in claims for k in token_keys):
            raise HTTPException(status_code=400, detail="Real tokens are not accepted. Use mock claims only.")
        try:
            result = service.simulate_sso_login(
                claims=claims,
                provider_config_id=payload.provider_config_id,
                organization_id=payload.organization_id,
                workspace_id=payload.workspace_id,
            )
            return result
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    # ── External Identities ──
    @router.get("/iam/external-identities")
    async def list_external_identities(
        organization_id: str = Query(default=""),
        workspace_id: str = Query(default=""),
        provider_config_id: str = Query(default=""),
        limit: int = Query(default=50, ge=1, le=100),
    ) -> dict[str, Any]:
        items = service.list_external_identities(
            organization_id=organization_id or None,
            workspace_id=workspace_id or None,
            provider_config_id=provider_config_id or None,
            limit=limit,
        )
        return {"external_identities": [e.to_dict() for e in items], "total": len(items)}

    # ── Mapping Decisions ──
    @router.get("/iam/mapping-decisions")
    async def list_iam_mapping_decisions(
        organization_id: str = Query(default=""),
        workspace_id: str = Query(default=""),
        limit: int = Query(default=50, ge=1, le=100),
    ) -> dict[str, Any]:
        items = service.list_iam_mapping_decisions(
            organization_id=organization_id or None,
            workspace_id=workspace_id or None,
            limit=limit,
        )
        return {"mapping_decisions": [d.to_dict() for d in items], "total": len(items)}

    # ── SSO Simulations ──
    @router.get("/iam/sso-simulations")
    async def list_sso_simulations(
        organization_id: str = Query(default=""),
        workspace_id: str = Query(default=""),
        limit: int = Query(default=50, ge=1, le=100),
    ) -> dict[str, Any]:
        items = service.list_sso_simulation_results(
            organization_id=organization_id or None,
            workspace_id=workspace_id or None,
            limit=limit,
        )
        return {"sso_simulations": [s.to_dict() for s in items], "total": len(items)}

    # ═══════════════════════════════════════════
    # Step 18 — Observability / OTel endpoints
    # ═══════════════════════════════════════════

    @router.get("/observability/readiness")
    async def observability_readiness() -> dict[str, Any]:
        return service.get_observability_readiness()

    @router.get("/observability/prometheus/scrape-config")
    async def prometheus_scrape_config(
        job_name: str = Query(default="sandbox-v2"),
        host: str = Query(default="localhost:8000"),
    ) -> dict[str, Any]:
        return service.generate_prometheus_scrape_config(job_name=job_name, host=host)

    @router.get("/observability/prometheus/alert-rules")
    async def prometheus_alert_rules() -> dict[str, Any]:
        return service.generate_prometheus_alert_rules()

    @router.get("/observability/grafana/dashboard")
    async def grafana_dashboard(
        dashboard_type: str = Query(default="overview"),
    ) -> dict[str, Any]:
        return {"dashboard": service.generate_grafana_dashboard(dashboard_type)}

    @router.post("/observability/grafana/dashboard/generate")
    async def generate_grafana_dashboard(
        dashboard_type: str = Query(default="overview"),
    ) -> dict[str, Any]:
        dash = service.generate_grafana_dashboard(dashboard_type)
        return {"dashboard": dash, "generated": True}

    @router.get("/observability/traces")
    async def list_trace_spans(
        organization_id: str = Query(default=""),
        workspace_id: str = Query(default=""),
        trace_id: str = Query(default=""),
        limit: int = Query(default=100, ge=1, le=200),
    ) -> dict[str, Any]:
        items = service.list_trace_spans(
            organization_id=organization_id or None,
            workspace_id=workspace_id or None,
            trace_id=trace_id or None,
            limit=limit,
        )
        return {"traces": [t.to_dict() for t in items], "total": len(items)}

    @router.post("/observability/traces")
    async def create_trace_span(payload: CreateTraceSpanRequest) -> dict[str, Any]:
        try:
            span = service.create_trace_span(
                span_name=payload.span_name, trace_id=payload.trace_id,
                parent_span_id=payload.parent_span_id,
                organization_id=payload.organization_id,
                workspace_id=payload.workspace_id,
                resource_type=payload.resource_type, resource_id=payload.resource_id,
                attributes=payload.attributes,
            )
            if span is None:
                raise HTTPException(status_code=500, detail="Failed to create trace span")
            return {"trace_span": span.to_dict()}
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    @router.post("/observability/otel/simulate-export")
    async def simulate_otel_export(payload: SimulateOTelExportRequest) -> dict[str, Any]:
        try:
            return service.simulate_otel_export(
                signal_type=payload.signal_type, items=payload.items,
                organization_id=payload.organization_id,
                workspace_id=payload.workspace_id,
            )
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    @router.get("/observability/export-records")
    async def list_telemetry_export_records(
        provider: str = Query(default=""),
        signal_type: str = Query(default=""),
        status: str = Query(default=""),
        limit: int = Query(default=100, ge=1, le=200),
    ) -> dict[str, Any]:
        items = service.list_telemetry_export_records(
            provider=provider or None,
            signal_type=signal_type or None,
            status=status or None,
            limit=limit,
        )
        return {"export_records": [r.to_dict() for r in items], "total": len(items)}

    # ═══════════════════════════════════════════
    # Step 19 — Load Testing / SLO endpoints
    # ═══════════════════════════════════════════

    @router.get("/load-testing/readiness")
    async def load_testing_readiness() -> dict[str, Any]:
        return service.get_load_testing_readiness()

    @router.post("/load-testing/configs")
    async def create_load_test_config(payload: CreateLoadTestConfigRequest) -> dict[str, Any]:
        try:
            config = service.create_load_test_config(
                profile=payload.profile, base_url_masked=payload.base_url_masked,
                targets=payload.targets, max_users=payload.max_users,
                max_rps=payload.max_rps, duration_seconds=payload.duration_seconds,
                timeout_seconds=payload.timeout_seconds,
                allow_production=payload.allow_production,
                require_confirmation=payload.require_confirmation,
                organization_id=payload.organization_id,
                workspace_id=payload.workspace_id,
                metadata=payload.metadata,
            )
            if config is None:
                raise HTTPException(status_code=500, detail="Failed to create load test config")
            return {"load_test_config": config.to_dict()}
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    @router.get("/load-testing/configs")
    async def list_load_test_configs(
        limit: int = Query(default=50, ge=1, le=100),
    ) -> dict[str, Any]:
        if not service._store:
            return {"load_test_configs": [], "total": 0}
        items = service._store.list_load_test_configs(limit=limit)
        return {"load_test_configs": [c.to_dict() for c in items], "total": len(items)}

    @router.post("/load-testing/configs/{load_test_id}/run")
    async def run_load_test(
        load_test_id: str,
        mode: str = Query(default="local"),
    ) -> dict[str, Any]:
        try:
            result = service.run_load_test(load_test_id, mode=mode)
            return result
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    @router.get("/load-testing/results")
    async def list_load_test_results(
        load_test_id: str = Query(default=""),
        target: str = Query(default=""),
        limit: int = Query(default=100, ge=1, le=200),
    ) -> dict[str, Any]:
        items = service.list_load_test_results(
            load_test_id=load_test_id or None,
            target=target or None, limit=limit,
        )
        return {"load_test_results": [r.to_dict() for r in items], "total": len(items)}

    @router.get("/load-testing/slo/definitions")
    async def list_slo_definitions(
        limit: int = Query(default=100, ge=1, le=200),
    ) -> dict[str, Any]:
        items = service.list_slo_definitions(limit=limit)
        return {"slo_definitions": [s.to_dict() for s in items], "total": len(items)}

    @router.get("/load-testing/slo/evaluations")
    async def list_slo_evaluations(
        load_test_id: str = Query(default=""),
        slo_id: str = Query(default=""),
        limit: int = Query(default=100, ge=1, le=200),
    ) -> dict[str, Any]:
        items = service.list_slo_evaluations(
            load_test_id=load_test_id or None, slo_id=slo_id or None, limit=limit,
        )
        return {"slo_evaluations": [e.to_dict() for e in items], "total": len(items)}

    @router.post("/load-testing/slo/evaluate/{load_test_id}")
    async def evaluate_slo(load_test_id: str) -> dict[str, Any]:
        try:
            result = service.evaluate_slo_for_load_test(load_test_id)
            return result
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    @router.get("/load-testing/capacity/latest")
    async def latest_capacity_plan() -> dict[str, Any]:
        plan = service.get_latest_capacity_plan()
        return {"capacity_plan": plan}

    @router.get("/load-testing/report/{load_test_id}")
    async def get_load_test_report(
        load_test_id: str,
        format: str = Query(default="json", pattern="^(json|markdown)$"),
    ) -> dict[str, Any]:
        if not service._load_tester:
            raise HTTPException(status_code=503, detail="Load tester not configured")
        if format == "markdown":
            report = service._load_tester.export_load_test_report_markdown(load_test_id)
            return {"load_test_id": load_test_id, "format": "markdown", "report": report}
        report = service._load_tester.export_load_test_report_json(load_test_id)
        return {"load_test_id": load_test_id, "format": "json", "report": report}

    return router
