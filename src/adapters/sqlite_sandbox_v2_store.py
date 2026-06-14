"""SQLite Sandbox v2 Store — SandboxV2Store 协议的默认实现。

遵循现有 store 模式（sqlite_utils.Database + row_factory）。
接口设计便于后续替换为 PostgreSQL。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from src.adapters.config import Settings
from src.adapters.sqlite_connection import create_sqlite_db, execute_with_retry
from src.open_platform.sandbox_v2.models import (
    SandboxJob,
    SandboxV2ExecutionRecord,
    SandboxV2JobStatus,
    SandboxV2Mode,
    SandboxV2RiskLevel,
    SandboxV2Decision,
    SandboxArtifact,
    SandboxArtifactManifest,
    SandboxV2ArtifactStatus,
    SandboxV2ArtifactType,
    SandboxPackageRequest,
    SandboxPackageQuarantineRecord,
    SandboxPackageSBOM,
    SandboxPackageVulnerabilityScanResult,
    SandboxV2PackageRequestStatus,
    SandboxV2PackageQuarantineStatus,
    SandboxV2PackageManager,
    SandboxV2PackageSourceType,
    SandboxV2SignatureStatus,
    SandboxV2SBOMStatus,
    SandboxV2VulnerabilityStatus,
    SandboxNetworkEgressRequest,
    SandboxNetworkEgressAuditRecord,
    SandboxV2NetworkEgressStatus,
    SandboxV2NetworkEgressAction,
    SandboxIsolationCapability,
    SandboxExecutionPlan,
    SandboxV2IsolationProvider,
    SandboxV2ExecutionPlanStatus,
    SandboxContainerExecutionPlan,
    SandboxContainerExecutionResult,
    SandboxV2ContainerRuntime,
    SandboxV2ContainerExecutionStatus,
    SandboxKillRequest,
    SandboxKillRecord,
    SandboxActiveExecutionHandle,
    SandboxV2KillRequestStatus,
    SandboxV2KillTargetType,
    SandboxV2KillAction,
    SandboxV2ActiveExecutionStatus,
    SandboxV2BenchmarkConfig,
    SandboxV2BenchmarkResult,
    SandboxV2CapacityEstimate,
    SandboxV2IAMProviderConfig,
    SandboxV2ExternalIdentity,
    SandboxV2IAMRoleMapping,
    SandboxV2IAMMappingDecision,
    SandboxV2SSOSimulationResult,
    SandboxV2TraceSpan,
    SandboxV2TelemetryExportRecord,
    SandboxV2GrafanaDashboardSpec,
    SandboxV2LoadTestConfig,
    SandboxV2LoadTestResult,
    SandboxV2SLODefinition,
    SandboxV2SLOEvaluation,
    SandboxV2CapacityPlan,
)

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sandbox_v2_jobs (
    job_id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL DEFAULT '',
    workspace_id TEXT NOT NULL DEFAULT '',
    agent_id TEXT NOT NULL DEFAULT '',
    requested_by TEXT NOT NULL DEFAULT '',
    mode TEXT NOT NULL DEFAULT 'simulation',
    status TEXT NOT NULL DEFAULT 'created',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    requested_action TEXT NOT NULL DEFAULT '',
    input_ref TEXT NOT NULL DEFAULT '',
    policy_snapshot_json TEXT NOT NULL DEFAULT '{}',
    risk_level TEXT NOT NULL DEFAULT 'unknown',
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_sbxv2_jobs_org ON sandbox_v2_jobs(organization_id);
CREATE INDEX IF NOT EXISTS idx_sbxv2_jobs_ws ON sandbox_v2_jobs(workspace_id);
CREATE INDEX IF NOT EXISTS idx_sbxv2_jobs_status ON sandbox_v2_jobs(status);
CREATE INDEX IF NOT EXISTS idx_sbxv2_jobs_mode ON sandbox_v2_jobs(mode);
CREATE INDEX IF NOT EXISTS idx_sbxv2_jobs_created_at ON sandbox_v2_jobs(created_at);

CREATE TABLE IF NOT EXISTS sandbox_v2_execution_records (
    record_id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'created',
    mode TEXT NOT NULL DEFAULT 'simulation',
    started_at TEXT,
    finished_at TEXT,
    duration_ms INTEGER NOT NULL DEFAULT 0,
    decision TEXT NOT NULL DEFAULT 'deny',
    reason TEXT NOT NULL DEFAULT '',
    stdout_ref TEXT NOT NULL DEFAULT '',
    stderr_ref TEXT NOT NULL DEFAULT '',
    artifact_refs_json TEXT NOT NULL DEFAULT '[]',
    audit_refs_json TEXT NOT NULL DEFAULT '[]',
    error_code TEXT NOT NULL DEFAULT '',
    error_message TEXT NOT NULL DEFAULT '',
    no_real_execution INTEGER NOT NULL DEFAULT 1,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_sbxv2_recs_job_id ON sandbox_v2_execution_records(job_id);
CREATE INDEX IF NOT EXISTS idx_sbxv2_recs_status ON sandbox_v2_execution_records(status);
CREATE INDEX IF NOT EXISTS idx_sbxv2_recs_started_at ON sandbox_v2_execution_records(started_at);

CREATE TABLE IF NOT EXISTS sandbox_v2_artifacts (
    artifact_id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL DEFAULT '',
    organization_id TEXT NOT NULL DEFAULT '',
    workspace_id TEXT NOT NULL DEFAULT '',
    record_id TEXT NOT NULL DEFAULT '',
    artifact_type TEXT NOT NULL DEFAULT 'unknown',
    name TEXT NOT NULL DEFAULT '',
    original_filename TEXT NOT NULL DEFAULT '',
    safe_filename TEXT NOT NULL DEFAULT '',
    storage_key TEXT NOT NULL DEFAULT '',
    storage_backend TEXT NOT NULL DEFAULT 'local',
    size_bytes INTEGER NOT NULL DEFAULT 0,
    mime_type TEXT NOT NULL DEFAULT 'text/plain',
    sha256 TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    materialized_at TEXT,
    read_only INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'pending',
    retention_until TEXT,
    risk_level TEXT NOT NULL DEFAULT 'low',
    policy_decision_id TEXT NOT NULL DEFAULT '',
    audit_refs_json TEXT NOT NULL DEFAULT '[]',
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_sbxv2_art_job ON sandbox_v2_artifacts(job_id);
CREATE INDEX IF NOT EXISTS idx_sbxv2_art_rec ON sandbox_v2_artifacts(record_id);
CREATE INDEX IF NOT EXISTS idx_sbxv2_art_org ON sandbox_v2_artifacts(organization_id);
CREATE INDEX IF NOT EXISTS idx_sbxv2_art_status ON sandbox_v2_artifacts(status);
CREATE INDEX IF NOT EXISTS idx_sbxv2_art_retention ON sandbox_v2_artifacts(retention_until);

CREATE TABLE IF NOT EXISTS sandbox_v2_artifact_manifests (
    manifest_id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL DEFAULT '',
    record_id TEXT NOT NULL DEFAULT '',
    artifact_ids_json TEXT NOT NULL DEFAULT '[]',
    total_size_bytes INTEGER NOT NULL DEFAULT 0,
    artifact_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    sealed INTEGER NOT NULL DEFAULT 0,
    sha256 TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_sbxv2_mft_job ON sandbox_v2_artifact_manifests(job_id);
CREATE INDEX IF NOT EXISTS idx_sbxv2_mft_rec ON sandbox_v2_artifact_manifests(record_id);

CREATE TABLE IF NOT EXISTS sandbox_v2_package_requests (
    package_request_id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL DEFAULT '',
    organization_id TEXT NOT NULL DEFAULT '',
    workspace_id TEXT NOT NULL DEFAULT '',
    requested_by TEXT NOT NULL DEFAULT '',
    package_name TEXT NOT NULL DEFAULT '',
    package_version TEXT NOT NULL DEFAULT '',
    package_manager TEXT NOT NULL DEFAULT 'unknown',
    source_url TEXT NOT NULL DEFAULT '',
    source_type TEXT NOT NULL DEFAULT 'unknown',
    requested_action TEXT NOT NULL DEFAULT '',
    expected_sha256 TEXT NOT NULL DEFAULT '',
    expected_signature TEXT NOT NULL DEFAULT '',
    sbom_ref TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    status TEXT NOT NULL DEFAULT 'requested',
    risk_level TEXT NOT NULL DEFAULT 'unknown',
    policy_decision_id TEXT NOT NULL DEFAULT '',
    reason TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_sbxv2_pkgreq_job ON sandbox_v2_package_requests(job_id);
CREATE INDEX IF NOT EXISTS idx_sbxv2_pkgreq_org ON sandbox_v2_package_requests(organization_id);
CREATE INDEX IF NOT EXISTS idx_sbxv2_pkgreq_status ON sandbox_v2_package_requests(status);

CREATE TABLE IF NOT EXISTS sandbox_v2_package_quarantine (
    quarantine_id TEXT PRIMARY KEY,
    package_request_id TEXT NOT NULL DEFAULT '',
    job_id TEXT NOT NULL DEFAULT '',
    organization_id TEXT NOT NULL DEFAULT '',
    workspace_id TEXT NOT NULL DEFAULT '',
    package_name TEXT NOT NULL DEFAULT '',
    package_version TEXT NOT NULL DEFAULT '',
    package_manager TEXT NOT NULL DEFAULT 'unknown',
    storage_key TEXT NOT NULL DEFAULT '',
    size_bytes INTEGER NOT NULL DEFAULT 0,
    sha256 TEXT NOT NULL DEFAULT '',
    signature_status TEXT NOT NULL DEFAULT 'not_provided',
    sbom_status TEXT NOT NULL DEFAULT 'not_provided',
    vulnerability_status TEXT NOT NULL DEFAULT 'not_scanned',
    status TEXT NOT NULL DEFAULT 'quarantined',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    reviewed_at TEXT,
    reviewed_by TEXT NOT NULL DEFAULT '',
    release_decision TEXT NOT NULL DEFAULT '',
    reason TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_sbxv2_qrp_pkgreq ON sandbox_v2_package_quarantine(package_request_id);
CREATE INDEX IF NOT EXISTS idx_sbxv2_qrp_status ON sandbox_v2_package_quarantine(status);

CREATE TABLE IF NOT EXISTS sandbox_v2_package_sboms (
    sbom_id TEXT PRIMARY KEY,
    package_request_id TEXT NOT NULL DEFAULT '',
    package_name TEXT NOT NULL DEFAULT '',
    package_version TEXT NOT NULL DEFAULT '',
    format TEXT NOT NULL DEFAULT 'unknown',
    content_sha256 TEXT NOT NULL DEFAULT '',
    component_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    storage_key TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'provided',
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_sbxv2_sbom_pkgreq ON sandbox_v2_package_sboms(package_request_id);

CREATE TABLE IF NOT EXISTS sandbox_v2_package_vulnerability_scans (
    scan_id TEXT PRIMARY KEY,
    package_request_id TEXT NOT NULL DEFAULT '',
    package_name TEXT NOT NULL DEFAULT '',
    package_version TEXT NOT NULL DEFAULT '',
    scanner TEXT NOT NULL DEFAULT 'sbom_fixture_scanner',
    status TEXT NOT NULL DEFAULT 'not_scanned',
    severity_summary TEXT NOT NULL DEFAULT '',
    critical_count INTEGER NOT NULL DEFAULT 0,
    high_count INTEGER NOT NULL DEFAULT 0,
    medium_count INTEGER NOT NULL DEFAULT 0,
    low_count INTEGER NOT NULL DEFAULT 0,
    findings_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_sbxv2_scan_pkgreq ON sandbox_v2_package_vulnerability_scans(package_request_id);

CREATE TABLE IF NOT EXISTS sandbox_v2_network_egress_requests (
    egress_request_id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL DEFAULT '',
    organization_id TEXT NOT NULL DEFAULT '',
    workspace_id TEXT NOT NULL DEFAULT '',
    requested_by TEXT NOT NULL DEFAULT '',
    url TEXT NOT NULL DEFAULT '',
    scheme TEXT NOT NULL DEFAULT '',
    hostname TEXT NOT NULL DEFAULT '',
    port INTEGER NOT NULL DEFAULT 443,
    resolved_ips_json TEXT NOT NULL DEFAULT '[]',
    method TEXT NOT NULL DEFAULT 'GET',
    purpose TEXT NOT NULL DEFAULT '',
    requested_at TEXT NOT NULL DEFAULT (datetime('now')),
    status TEXT NOT NULL DEFAULT 'requested',
    risk_level TEXT NOT NULL DEFAULT 'medium',
    policy_decision_id TEXT NOT NULL DEFAULT '',
    reason TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_sbxv2_egr_job ON sandbox_v2_network_egress_requests(job_id);
CREATE INDEX IF NOT EXISTS idx_sbxv2_egr_status ON sandbox_v2_network_egress_requests(status);

CREATE TABLE IF NOT EXISTS sandbox_v2_network_egress_audit_records (
    audit_id TEXT PRIMARY KEY,
    egress_request_id TEXT NOT NULL DEFAULT '',
    job_id TEXT NOT NULL DEFAULT '',
    organization_id TEXT NOT NULL DEFAULT '',
    workspace_id TEXT NOT NULL DEFAULT '',
    url TEXT NOT NULL DEFAULT '',
    hostname TEXT NOT NULL DEFAULT '',
    resolved_ips_json TEXT NOT NULL DEFAULT '[]',
    decision TEXT NOT NULL DEFAULT 'deny',
    reason TEXT NOT NULL DEFAULT '',
    risk_level TEXT NOT NULL DEFAULT 'medium',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_sbxv2_aud_egr ON sandbox_v2_network_egress_audit_records(egress_request_id);
CREATE INDEX IF NOT EXISTS idx_sbxv2_aud_job ON sandbox_v2_network_egress_audit_records(job_id);

CREATE TABLE IF NOT EXISTS sandbox_v2_isolation_capabilities (
    capability_id TEXT PRIMARY KEY,
    provider TEXT NOT NULL DEFAULT 'disabled',
    available INTEGER NOT NULL DEFAULT 0,
    enabled INTEGER NOT NULL DEFAULT 0,
    reason TEXT NOT NULL DEFAULT '',
    platform TEXT NOT NULL DEFAULT '',
    os_name TEXT NOT NULL DEFAULT '',
    is_windows INTEGER NOT NULL DEFAULT 0,
    is_linux INTEGER NOT NULL DEFAULT 0,
    has_docker INTEGER NOT NULL DEFAULT 0,
    has_podman INTEGER NOT NULL DEFAULT 0,
    has_firecracker INTEGER NOT NULL DEFAULT 0,
    has_gvisor INTEGER NOT NULL DEFAULT 0,
    has_kata INTEGER NOT NULL DEFAULT 0,
    has_user_namespace INTEGER NOT NULL DEFAULT 0,
    has_cgroup INTEGER NOT NULL DEFAULT 0,
    has_seccomp INTEGER NOT NULL DEFAULT 0,
    has_apparmor INTEGER NOT NULL DEFAULT 0,
    has_selinux INTEGER NOT NULL DEFAULT 0,
    has_network_namespace INTEGER NOT NULL DEFAULT 0,
    has_mount_namespace INTEGER NOT NULL DEFAULT 0,
    checked_at TEXT NOT NULL DEFAULT (datetime('now')),
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_sbxv2_iso_prov ON sandbox_v2_isolation_capabilities(provider);

CREATE TABLE IF NOT EXISTS sandbox_v2_execution_plans (
    execution_plan_id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL DEFAULT '',
    organization_id TEXT NOT NULL DEFAULT '',
    workspace_id TEXT NOT NULL DEFAULT '',
    provider TEXT NOT NULL DEFAULT 'disabled',
    mode TEXT NOT NULL DEFAULT 'simulation',
    command_ref TEXT NOT NULL DEFAULT '',
    image_ref TEXT NOT NULL DEFAULT '',
    input_artifact_refs_json TEXT NOT NULL DEFAULT '[]',
    output_artifact_policy_json TEXT NOT NULL DEFAULT '{}',
    network_policy_snapshot_json TEXT NOT NULL DEFAULT '{}',
    filesystem_policy_snapshot_json TEXT NOT NULL DEFAULT '{}',
    resource_limits_json TEXT NOT NULL DEFAULT '{}',
    environment_policy_json TEXT NOT NULL DEFAULT '{}',
    working_directory_policy_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    status TEXT NOT NULL DEFAULT 'created',
    reason TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_sbxv2_ep_job ON sandbox_v2_execution_plans(job_id);
CREATE INDEX IF NOT EXISTS idx_sbxv2_ep_status ON sandbox_v2_execution_plans(status);

CREATE TABLE IF NOT EXISTS sandbox_v2_container_execution_plans (
    container_plan_id TEXT PRIMARY KEY, execution_plan_id TEXT NOT NULL DEFAULT '',
    job_id TEXT NOT NULL DEFAULT '', provider TEXT NOT NULL DEFAULT 'docker_rootless_future',
    runtime TEXT NOT NULL DEFAULT 'unavailable', image TEXT NOT NULL DEFAULT '',
    fixture_id TEXT NOT NULL DEFAULT '', command_json TEXT NOT NULL DEFAULT '[]',
    env_json TEXT NOT NULL DEFAULT '{}', network_mode TEXT NOT NULL DEFAULT 'none',
    readonly_rootfs INTEGER NOT NULL DEFAULT 1, user TEXT NOT NULL DEFAULT '65532:65532',
    resource_limits_json TEXT NOT NULL DEFAULT '{}', timeout_seconds INTEGER NOT NULL DEFAULT 30,
    status TEXT NOT NULL DEFAULT 'created', reason TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')), metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_sbxv2_cp_job ON sandbox_v2_container_execution_plans(job_id);
CREATE INDEX IF NOT EXISTS idx_sbxv2_cp_status ON sandbox_v2_container_execution_plans(status);

CREATE TABLE IF NOT EXISTS sandbox_v2_container_execution_results (
    container_result_id TEXT PRIMARY KEY, container_plan_id TEXT NOT NULL DEFAULT '',
    execution_plan_id TEXT NOT NULL DEFAULT '', job_id TEXT NOT NULL DEFAULT '',
    provider TEXT NOT NULL DEFAULT 'docker_rootless_future',
    runtime TEXT NOT NULL DEFAULT 'unavailable',
    status TEXT NOT NULL DEFAULT 'created', exit_code INTEGER NOT NULL DEFAULT -1,
    started_at TEXT, finished_at TEXT, duration_ms INTEGER NOT NULL DEFAULT 0,
    stdout_text TEXT NOT NULL DEFAULT '', stderr_text TEXT NOT NULL DEFAULT '',
    stdout_artifact_id TEXT NOT NULL DEFAULT '', stderr_artifact_id TEXT NOT NULL DEFAULT '',
    timeout INTEGER NOT NULL DEFAULT 0, canceled INTEGER NOT NULL DEFAULT 0,
    reason TEXT NOT NULL DEFAULT '', metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_sbxv2_cr_job ON sandbox_v2_container_execution_results(job_id);
CREATE INDEX IF NOT EXISTS idx_sbxv2_cr_cpid ON sandbox_v2_container_execution_results(container_plan_id);

CREATE TABLE IF NOT EXISTS sandbox_v2_kill_requests (
    kill_request_id TEXT PRIMARY KEY, job_id TEXT NOT NULL DEFAULT '',
    execution_plan_id TEXT NOT NULL DEFAULT '', container_plan_id TEXT NOT NULL DEFAULT '',
    execution_record_id TEXT NOT NULL DEFAULT '', queue_id TEXT NOT NULL DEFAULT '',
    organization_id TEXT NOT NULL DEFAULT '', workspace_id TEXT NOT NULL DEFAULT '',
    requested_by TEXT NOT NULL DEFAULT '', reason TEXT NOT NULL DEFAULT '',
    scope TEXT NOT NULL DEFAULT 'job', target_type TEXT NOT NULL DEFAULT 'job',
    target_id TEXT NOT NULL DEFAULT '', force INTEGER NOT NULL DEFAULT 0,
    requested_at TEXT NOT NULL DEFAULT (datetime('now')),
    status TEXT NOT NULL DEFAULT 'requested', policy_decision_id TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_sbxv2_krq_job ON sandbox_v2_kill_requests(job_id);
CREATE INDEX IF NOT EXISTS idx_sbxv2_krq_status ON sandbox_v2_kill_requests(status);

CREATE TABLE IF NOT EXISTS sandbox_v2_kill_records (
    kill_record_id TEXT PRIMARY KEY, kill_request_id TEXT NOT NULL DEFAULT '',
    job_id TEXT NOT NULL DEFAULT '', execution_plan_id TEXT NOT NULL DEFAULT '',
    container_plan_id TEXT NOT NULL DEFAULT '', provider TEXT NOT NULL DEFAULT '',
    target_type TEXT NOT NULL DEFAULT 'unknown', target_id TEXT NOT NULL DEFAULT '',
    action_taken TEXT NOT NULL DEFAULT 'reject', status_before TEXT NOT NULL DEFAULT '',
    status_after TEXT NOT NULL DEFAULT '', provider_result TEXT NOT NULL DEFAULT '',
    error_code TEXT NOT NULL DEFAULT '', error_message TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')), metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_sbxv2_krc_job ON sandbox_v2_kill_records(job_id);
CREATE INDEX IF NOT EXISTS idx_sbxv2_krc_krid ON sandbox_v2_kill_records(kill_request_id);

CREATE TABLE IF NOT EXISTS sandbox_v2_active_execution_handles (
    handle_id TEXT PRIMARY KEY, job_id TEXT NOT NULL DEFAULT '',
    execution_plan_id TEXT NOT NULL DEFAULT '', container_plan_id TEXT NOT NULL DEFAULT '',
    execution_record_id TEXT NOT NULL DEFAULT '', provider TEXT NOT NULL DEFAULT '',
    target_type TEXT NOT NULL DEFAULT 'unknown', target_id TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active', started_at TEXT NOT NULL DEFAULT (datetime('now')),
    last_seen_at TEXT NOT NULL DEFAULT (datetime('now')), timeout_at TEXT,
    cancel_requested INTEGER NOT NULL DEFAULT 0, cancel_reason TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_sbxv2_hdl_job ON sandbox_v2_active_execution_handles(job_id);
CREATE INDEX IF NOT EXISTS idx_sbxv2_hdl_status ON sandbox_v2_active_execution_handles(status);

-- Step 11 — MicroVM Execution Plans & Results
CREATE TABLE IF NOT EXISTS sandbox_v2_microvm_execution_plans (
    microvm_plan_id TEXT PRIMARY KEY,
    execution_plan_id TEXT NOT NULL DEFAULT '',
    job_id TEXT NOT NULL DEFAULT '',
    organization_id TEXT NOT NULL DEFAULT '',
    workspace_id TEXT NOT NULL DEFAULT '',
    runtime TEXT NOT NULL DEFAULT 'unavailable',
    fixture_id TEXT NOT NULL DEFAULT '',
    kernel_ref TEXT NOT NULL DEFAULT '',
    rootfs_ref TEXT NOT NULL DEFAULT '',
    image_ref TEXT NOT NULL DEFAULT '',
    network_enabled INTEGER NOT NULL DEFAULT 0,
    memory_mb INTEGER NOT NULL DEFAULT 128,
    vcpu_count INTEGER NOT NULL DEFAULT 1,
    timeout_seconds INTEGER NOT NULL DEFAULT 10,
    status TEXT NOT NULL DEFAULT 'created',
    reason TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_sbxv2_mvp_job ON sandbox_v2_microvm_execution_plans(job_id);
CREATE INDEX IF NOT EXISTS idx_sbxv2_mvp_status ON sandbox_v2_microvm_execution_plans(status);

CREATE TABLE IF NOT EXISTS sandbox_v2_microvm_execution_results (
    microvm_result_id TEXT PRIMARY KEY,
    microvm_plan_id TEXT NOT NULL DEFAULT '',
    execution_plan_id TEXT NOT NULL DEFAULT '',
    job_id TEXT NOT NULL DEFAULT '',
    runtime TEXT NOT NULL DEFAULT 'unavailable',
    status TEXT NOT NULL DEFAULT 'unavailable',
    exit_code INTEGER NOT NULL DEFAULT -1,
    started_at TEXT,
    finished_at TEXT,
    duration_ms INTEGER NOT NULL DEFAULT 0,
    stdout_text TEXT NOT NULL DEFAULT '',
    stderr_text TEXT NOT NULL DEFAULT '',
    stdout_artifact_id TEXT NOT NULL DEFAULT '',
    stderr_artifact_id TEXT NOT NULL DEFAULT '',
    timeout INTEGER NOT NULL DEFAULT 0,
    canceled INTEGER NOT NULL DEFAULT 0,
    reason TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_sbxv2_mvr_job ON sandbox_v2_microvm_execution_results(job_id);
CREATE INDEX IF NOT EXISTS idx_sbxv2_mvr_plan ON sandbox_v2_microvm_execution_results(microvm_plan_id);

-- Step 14 — Security Audit Events & Evidence Bundles
CREATE TABLE IF NOT EXISTS sandbox_v2_security_audit_events (
    audit_event_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL DEFAULT '',
    severity TEXT NOT NULL DEFAULT 'info',
    principal_id TEXT NOT NULL DEFAULT '',
    principal_type TEXT NOT NULL DEFAULT '',
    organization_id TEXT NOT NULL DEFAULT '',
    workspace_id TEXT NOT NULL DEFAULT '',
    resource_type TEXT NOT NULL DEFAULT '',
    resource_id TEXT NOT NULL DEFAULT '',
    action TEXT NOT NULL DEFAULT '',
    decision TEXT NOT NULL DEFAULT '',
    reason TEXT NOT NULL DEFAULT '',
    request_id TEXT NOT NULL DEFAULT '',
    previous_hash TEXT NOT NULL DEFAULT '',
    event_hash TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_sbxv2_aud_org ON sandbox_v2_security_audit_events(organization_id);
CREATE INDEX IF NOT EXISTS idx_sbxv2_aud_ws ON sandbox_v2_security_audit_events(workspace_id);
CREATE INDEX IF NOT EXISTS idx_sbxv2_aud_type ON sandbox_v2_security_audit_events(event_type);
CREATE INDEX IF NOT EXISTS idx_sbxv2_aud_sev ON sandbox_v2_security_audit_events(severity);
CREATE INDEX IF NOT EXISTS idx_sbxv2_aud_created ON sandbox_v2_security_audit_events(created_at);

CREATE TABLE IF NOT EXISTS sandbox_v2_evidence_bundles (
    evidence_bundle_id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL DEFAULT '',
    workspace_id TEXT NOT NULL DEFAULT '',
    created_by TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    resource_refs_json TEXT NOT NULL DEFAULT '[]',
    audit_event_ids_json TEXT NOT NULL DEFAULT '[]',
    job_ids_json TEXT NOT NULL DEFAULT '[]',
    artifact_ids_json TEXT NOT NULL DEFAULT '[]',
    package_request_ids_json TEXT NOT NULL DEFAULT '[]',
    network_request_ids_json TEXT NOT NULL DEFAULT '[]',
    kill_request_ids_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    bundle_hash TEXT NOT NULL DEFAULT '',
    redacted INTEGER NOT NULL DEFAULT 1,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_sbxv2_evb_org ON sandbox_v2_evidence_bundles(organization_id);
CREATE INDEX IF NOT EXISTS idx_sbxv2_evb_ws ON sandbox_v2_evidence_bundles(workspace_id);

CREATE TABLE IF NOT EXISTS sandbox_v2_access_decisions (
    access_decision_id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL DEFAULT '',
    workspace_id TEXT NOT NULL DEFAULT '',
    allowed INTEGER NOT NULL DEFAULT 0,
    action TEXT NOT NULL DEFAULT 'deny',
    reason TEXT NOT NULL DEFAULT '',
    risk_level TEXT NOT NULL DEFAULT 'medium',
    principal_id TEXT NOT NULL DEFAULT '',
    principal_type TEXT NOT NULL DEFAULT '',
    resource_type TEXT NOT NULL DEFAULT '',
    resource_id TEXT NOT NULL DEFAULT '',
    permission_action TEXT NOT NULL DEFAULT '',
    organization_match INTEGER NOT NULL DEFAULT 0,
    workspace_match INTEGER NOT NULL DEFAULT 0,
    role_allowed INTEGER NOT NULL DEFAULT 0,
    scope_allowed INTEGER NOT NULL DEFAULT 0,
    cross_tenant INTEGER NOT NULL DEFAULT 0,
    fail_closed INTEGER NOT NULL DEFAULT 1,
    matched_rules_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_sbxv2_ad_org ON sandbox_v2_access_decisions(organization_id);

-- Step 15 — Monitoring / Metrics / Alerts / Health
CREATE TABLE IF NOT EXISTS sandbox_v2_metric_samples (
    metric_id TEXT PRIMARY KEY, name TEXT NOT NULL DEFAULT '',
    metric_type TEXT NOT NULL DEFAULT 'gauge', value REAL NOT NULL DEFAULT 0.0,
    labels_json TEXT NOT NULL DEFAULT '{}',
    organization_id TEXT NOT NULL DEFAULT '', workspace_id TEXT NOT NULL DEFAULT '',
    collected_at TEXT NOT NULL DEFAULT (datetime('now')),
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_sbxv2_ms_name ON sandbox_v2_metric_samples(name);
CREATE INDEX IF NOT EXISTS idx_sbxv2_ms_org ON sandbox_v2_metric_samples(organization_id);

CREATE TABLE IF NOT EXISTS sandbox_v2_metrics_snapshots (
    snapshot_id TEXT PRIMARY KEY, organization_id TEXT NOT NULL DEFAULT '',
    workspace_id TEXT NOT NULL DEFAULT '',
    generated_at TEXT NOT NULL DEFAULT (datetime('now')),
    counters_json TEXT NOT NULL DEFAULT '{}', gauges_json TEXT NOT NULL DEFAULT '{}',
    health_json TEXT NOT NULL DEFAULT '{}', warnings_json TEXT NOT NULL DEFAULT '[]',
    blockers_json TEXT NOT NULL DEFAULT '[]', metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_sbxv2_sn_org ON sandbox_v2_metrics_snapshots(organization_id);

CREATE TABLE IF NOT EXISTS sandbox_v2_alert_rules (
    alert_rule_id TEXT PRIMARY KEY, name TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '', rule_type TEXT NOT NULL DEFAULT 'threshold',
    metric_name TEXT NOT NULL DEFAULT '', threshold REAL NOT NULL DEFAULT 0.0,
    comparison TEXT NOT NULL DEFAULT 'gt', severity TEXT NOT NULL DEFAULT 'warning',
    enabled INTEGER NOT NULL DEFAULT 1,
    organization_id TEXT NOT NULL DEFAULT '', workspace_id TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS sandbox_v2_alerts (
    alert_id TEXT PRIMARY KEY, alert_rule_id TEXT NOT NULL DEFAULT '',
    name TEXT NOT NULL DEFAULT '', severity TEXT NOT NULL DEFAULT 'warning',
    status TEXT NOT NULL DEFAULT 'open',
    organization_id TEXT NOT NULL DEFAULT '', workspace_id TEXT NOT NULL DEFAULT '',
    resource_type TEXT NOT NULL DEFAULT '', resource_id TEXT NOT NULL DEFAULT '',
    reason TEXT NOT NULL DEFAULT '', observed_value REAL NOT NULL DEFAULT 0.0,
    threshold REAL NOT NULL DEFAULT 0.0,
    first_seen_at TEXT NOT NULL DEFAULT (datetime('now')),
    last_seen_at TEXT NOT NULL DEFAULT (datetime('now')),
    resolved_at TEXT, acknowledged_by TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_sbxv2_alrt_status ON sandbox_v2_alerts(status);
CREATE INDEX IF NOT EXISTS idx_sbxv2_alrt_sev ON sandbox_v2_alerts(severity);

CREATE TABLE IF NOT EXISTS sandbox_v2_health_check_results (
    health_check_id TEXT PRIMARY KEY, component TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'healthy', ready INTEGER NOT NULL DEFAULT 1,
    reason TEXT NOT NULL DEFAULT '', latency_ms INTEGER NOT NULL DEFAULT 0,
    checked_at TEXT NOT NULL DEFAULT (datetime('now')),
    warnings_json TEXT NOT NULL DEFAULT '[]', blockers_json TEXT NOT NULL DEFAULT '[]',
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_sbxv2_hcr_comp ON sandbox_v2_health_check_results(component);

CREATE TABLE IF NOT EXISTS sandbox_v2_benchmark_configs (
    benchmark_id TEXT PRIMARY KEY,
    profile TEXT NOT NULL DEFAULT 'small',
    targets_json TEXT NOT NULL DEFAULT '[]',
    max_jobs INTEGER NOT NULL DEFAULT 100,
    max_queue_items INTEGER NOT NULL DEFAULT 100,
    max_artifacts INTEGER NOT NULL DEFAULT 50,
    max_concurrency INTEGER NOT NULL DEFAULT 4,
    timeout_seconds INTEGER NOT NULL DEFAULT 60,
    cleanup_after_run INTEGER NOT NULL DEFAULT 1,
    organization_id TEXT NOT NULL DEFAULT '',
    workspace_id TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_sbxv2_bcfg_created_at ON sandbox_v2_benchmark_configs(created_at);
CREATE INDEX IF NOT EXISTS idx_sbxv2_bcfg_profile ON sandbox_v2_benchmark_configs(profile);

CREATE TABLE IF NOT EXISTS sandbox_v2_benchmark_results (
    benchmark_result_id TEXT PRIMARY KEY,
    benchmark_id TEXT NOT NULL DEFAULT '',
    target TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'created',
    started_at TEXT NOT NULL DEFAULT (datetime('now')),
    finished_at TEXT,
    duration_ms INTEGER NOT NULL DEFAULT 0,
    total_operations INTEGER NOT NULL DEFAULT 0,
    success_count INTEGER NOT NULL DEFAULT 0,
    failure_count INTEGER NOT NULL DEFAULT 0,
    p50_ms REAL NOT NULL DEFAULT 0.0,
    p95_ms REAL NOT NULL DEFAULT 0.0,
    p99_ms REAL NOT NULL DEFAULT 0.0,
    ops_per_second REAL NOT NULL DEFAULT 0.0,
    warnings_json TEXT NOT NULL DEFAULT '[]',
    blockers_json TEXT NOT NULL DEFAULT '[]',
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_sbxv2_bres_benchmark ON sandbox_v2_benchmark_results(benchmark_id);
CREATE INDEX IF NOT EXISTS idx_sbxv2_bres_target ON sandbox_v2_benchmark_results(target);
CREATE INDEX IF NOT EXISTS idx_sbxv2_bres_started ON sandbox_v2_benchmark_results(started_at);

CREATE TABLE IF NOT EXISTS sandbox_v2_capacity_estimates (
    capacity_id TEXT PRIMARY KEY,
    generated_at TEXT NOT NULL DEFAULT (datetime('now')),
    profile TEXT NOT NULL DEFAULT 'small',
    estimated_jobs_per_minute REAL NOT NULL DEFAULT 0.0,
    estimated_queue_items_per_minute REAL NOT NULL DEFAULT 0.0,
    estimated_artifact_metadata_per_minute REAL NOT NULL DEFAULT 0.0,
    estimated_network_preflight_per_minute REAL NOT NULL DEFAULT 0.0,
    sqlite_recommended_limit TEXT NOT NULL DEFAULT '',
    postgres_recommended_threshold TEXT NOT NULL DEFAULT '',
    redis_recommended_threshold TEXT NOT NULL DEFAULT '',
    minio_recommended_threshold TEXT NOT NULL DEFAULT '',
    bottlenecks_json TEXT NOT NULL DEFAULT '[]',
    recommendations_json TEXT NOT NULL DEFAULT '[]',
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_sbxv2_cap_generated ON sandbox_v2_capacity_estimates(generated_at);
CREATE INDEX IF NOT EXISTS idx_sbxv2_cap_profile ON sandbox_v2_capacity_estimates(profile);

-- ═══════════════════════════════════════════
-- Step 17 — IAM / SSO Tables
-- ═══════════════════════════════════════════

CREATE TABLE IF NOT EXISTS sandbox_v2_iam_provider_configs (
    provider_config_id TEXT PRIMARY KEY,
    provider_type TEXT NOT NULL DEFAULT 'disabled',
    protocol TEXT NOT NULL DEFAULT 'disabled',
    enabled INTEGER NOT NULL DEFAULT 0,
    issuer TEXT NOT NULL DEFAULT '',
    client_id TEXT NOT NULL DEFAULT '',
    client_secret_ref TEXT NOT NULL DEFAULT '',
    jwks_uri TEXT NOT NULL DEFAULT '',
    discovery_enabled INTEGER NOT NULL DEFAULT 0,
    saml_entity_id TEXT NOT NULL DEFAULT '',
    saml_metadata_ref TEXT NOT NULL DEFAULT '',
    jit_provisioning INTEGER NOT NULL DEFAULT 0,
    default_role TEXT NOT NULL DEFAULT 'viewer',
    allowed_domains_json TEXT NOT NULL DEFAULT '[]',
    require_verified_email INTEGER NOT NULL DEFAULT 1,
    external_group_mapping_enabled INTEGER NOT NULL DEFAULT 0,
    organization_id TEXT NOT NULL DEFAULT '',
    workspace_id TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_sbxv2_iamcfg_org ON sandbox_v2_iam_provider_configs(organization_id);
CREATE INDEX IF NOT EXISTS idx_sbxv2_iamcfg_ws ON sandbox_v2_iam_provider_configs(workspace_id);
CREATE INDEX IF NOT EXISTS idx_sbxv2_iamcfg_created ON sandbox_v2_iam_provider_configs(created_at);

CREATE TABLE IF NOT EXISTS sandbox_v2_external_identities (
    external_identity_id TEXT PRIMARY KEY,
    provider_config_id TEXT NOT NULL DEFAULT '',
    provider_type TEXT NOT NULL DEFAULT 'disabled',
    external_subject TEXT NOT NULL DEFAULT '',
    external_email TEXT NOT NULL DEFAULT '',
    email_verified INTEGER NOT NULL DEFAULT 0,
    external_groups_json TEXT NOT NULL DEFAULT '[]',
    display_name TEXT NOT NULL DEFAULT '',
    organization_id TEXT NOT NULL DEFAULT '',
    workspace_id TEXT NOT NULL DEFAULT '',
    linked_principal_id TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending_review',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    last_seen_at TEXT NOT NULL DEFAULT (datetime('now')),
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_sbxv2_eid_org ON sandbox_v2_external_identities(organization_id);
CREATE INDEX IF NOT EXISTS idx_sbxv2_eid_ws ON sandbox_v2_external_identities(workspace_id);
CREATE INDEX IF NOT EXISTS idx_sbxv2_eid_provider ON sandbox_v2_external_identities(provider_config_id);
CREATE INDEX IF NOT EXISTS idx_sbxv2_eid_created ON sandbox_v2_external_identities(created_at);

CREATE TABLE IF NOT EXISTS sandbox_v2_iam_role_mappings (
    mapping_id TEXT PRIMARY KEY,
    provider_config_id TEXT NOT NULL DEFAULT '',
    external_group TEXT NOT NULL DEFAULT '',
    external_claim TEXT NOT NULL DEFAULT '',
    sandbox_role TEXT NOT NULL DEFAULT 'viewer',
    sandbox_scopes_json TEXT NOT NULL DEFAULT '[]',
    organization_id TEXT NOT NULL DEFAULT '',
    workspace_id TEXT NOT NULL DEFAULT '',
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_sbxv2_irm_org ON sandbox_v2_iam_role_mappings(organization_id);
CREATE INDEX IF NOT EXISTS idx_sbxv2_irm_ws ON sandbox_v2_iam_role_mappings(workspace_id);
CREATE INDEX IF NOT EXISTS idx_sbxv2_irm_provider ON sandbox_v2_iam_role_mappings(provider_config_id);
CREATE INDEX IF NOT EXISTS idx_sbxv2_irm_created ON sandbox_v2_iam_role_mappings(created_at);

CREATE TABLE IF NOT EXISTS sandbox_v2_iam_mapping_decisions (
    decision_id TEXT PRIMARY KEY,
    allowed INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'rejected',
    reason TEXT NOT NULL DEFAULT 'Default deny.',
    principal_id TEXT NOT NULL DEFAULT '',
    principal_type TEXT NOT NULL DEFAULT 'anonymous',
    mapped_roles_json TEXT NOT NULL DEFAULT '[]',
    mapped_scopes_json TEXT NOT NULL DEFAULT '[]',
    organization_id TEXT NOT NULL DEFAULT '',
    workspace_id TEXT NOT NULL DEFAULT '',
    email_domain_allowed INTEGER NOT NULL DEFAULT 0,
    email_verified INTEGER NOT NULL DEFAULT 0,
    tenant_match INTEGER NOT NULL DEFAULT 0,
    group_mapping_applied INTEGER NOT NULL DEFAULT 0,
    jit_provisioning_required INTEGER NOT NULL DEFAULT 0,
    fail_closed INTEGER NOT NULL DEFAULT 1,
    matched_rules_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_sbxv2_imd_org ON sandbox_v2_iam_mapping_decisions(organization_id);
CREATE INDEX IF NOT EXISTS idx_sbxv2_imd_ws ON sandbox_v2_iam_mapping_decisions(workspace_id);
CREATE INDEX IF NOT EXISTS idx_sbxv2_imd_created ON sandbox_v2_iam_mapping_decisions(created_at);

CREATE TABLE IF NOT EXISTS sandbox_v2_sso_simulation_results (
    simulation_id TEXT PRIMARY KEY,
    provider_config_id TEXT NOT NULL DEFAULT '',
    protocol TEXT NOT NULL DEFAULT 'mock',
    login_status TEXT NOT NULL DEFAULT 'disabled',
    claim_set_json TEXT NOT NULL DEFAULT '{}',
    mapping_decision_json TEXT NOT NULL DEFAULT '{}',
    security_context_json TEXT NOT NULL DEFAULT '{}',
    audit_event_id TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_sbxv2_sso_org_ws ON sandbox_v2_sso_simulation_results(provider_config_id);
CREATE INDEX IF NOT EXISTS idx_sbxv2_sso_created ON sandbox_v2_sso_simulation_results(created_at);

-- ═══════════════════════════════════════════
-- Step 18 — Observability / OTel Tables
-- ═══════════════════════════════════════════

CREATE TABLE IF NOT EXISTS sandbox_v2_trace_spans (
    span_id TEXT PRIMARY KEY,
    trace_id TEXT NOT NULL DEFAULT '',
    parent_span_id TEXT NOT NULL DEFAULT '',
    span_name TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'ok',
    organization_id TEXT NOT NULL DEFAULT '',
    workspace_id TEXT NOT NULL DEFAULT '',
    resource_type TEXT NOT NULL DEFAULT '',
    resource_id TEXT NOT NULL DEFAULT '',
    started_at TEXT NOT NULL DEFAULT (datetime('now')),
    finished_at TEXT,
    duration_ms INTEGER NOT NULL DEFAULT 0,
    attributes_redacted_json TEXT NOT NULL DEFAULT '{}',
    events_redacted_json TEXT NOT NULL DEFAULT '[]',
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_sbxv2_ts_org ON sandbox_v2_trace_spans(organization_id);
CREATE INDEX IF NOT EXISTS idx_sbxv2_ts_ws ON sandbox_v2_trace_spans(workspace_id);
CREATE INDEX IF NOT EXISTS idx_sbxv2_ts_trace ON sandbox_v2_trace_spans(trace_id);
CREATE INDEX IF NOT EXISTS idx_sbxv2_ts_created ON sandbox_v2_trace_spans(started_at);

CREATE TABLE IF NOT EXISTS sandbox_v2_telemetry_export_records (
    export_record_id TEXT PRIMARY KEY,
    provider TEXT NOT NULL DEFAULT '',
    signal_type TEXT NOT NULL DEFAULT 'metric',
    status TEXT NOT NULL DEFAULT 'disabled',
    organization_id TEXT NOT NULL DEFAULT '',
    workspace_id TEXT NOT NULL DEFAULT '',
    resource_type TEXT NOT NULL DEFAULT '',
    resource_id TEXT NOT NULL DEFAULT '',
    exported_count INTEGER NOT NULL DEFAULT 0,
    rejected_count INTEGER NOT NULL DEFAULT 0,
    reason TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_sbxv2_ter_provider ON sandbox_v2_telemetry_export_records(provider);
CREATE INDEX IF NOT EXISTS idx_sbxv2_ter_signal ON sandbox_v2_telemetry_export_records(signal_type);
CREATE INDEX IF NOT EXISTS idx_sbxv2_ter_status ON sandbox_v2_telemetry_export_records(status);
CREATE INDEX IF NOT EXISTS idx_sbxv2_ter_created ON sandbox_v2_telemetry_export_records(created_at);

CREATE TABLE IF NOT EXISTS sandbox_v2_grafana_dashboard_specs (
    dashboard_id TEXT PRIMARY KEY,
    title TEXT NOT NULL DEFAULT '',
    version TEXT NOT NULL DEFAULT '1.0',
    panels_json TEXT NOT NULL DEFAULT '[]',
    datasource TEXT NOT NULL DEFAULT '${DS_PROMETHEUS}',
    tags_json TEXT NOT NULL DEFAULT '[]',
    generated_at TEXT NOT NULL DEFAULT (datetime('now')),
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_sbxv2_gds_generated ON sandbox_v2_grafana_dashboard_specs(generated_at);

-- ═══════════════════════════════════════════
-- Step 19 — Load Testing / SLO Tables
-- ═══════════════════════════════════════════

CREATE TABLE IF NOT EXISTS sandbox_v2_load_test_configs (
    load_test_id TEXT PRIMARY KEY,
    profile TEXT NOT NULL DEFAULT 'smoke',
    base_url_masked TEXT NOT NULL DEFAULT '',
    targets_json TEXT NOT NULL DEFAULT '[]',
    max_users INTEGER NOT NULL DEFAULT 5,
    max_rps INTEGER NOT NULL DEFAULT 5,
    duration_seconds INTEGER NOT NULL DEFAULT 30,
    timeout_seconds INTEGER NOT NULL DEFAULT 5,
    allow_production INTEGER NOT NULL DEFAULT 0,
    require_confirmation INTEGER NOT NULL DEFAULT 1,
    organization_id TEXT NOT NULL DEFAULT '',
    workspace_id TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_sbxv2_ltc_created ON sandbox_v2_load_test_configs(created_at);

CREATE TABLE IF NOT EXISTS sandbox_v2_load_test_results (
    load_test_result_id TEXT PRIMARY KEY,
    load_test_id TEXT NOT NULL DEFAULT '',
    target TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'created',
    started_at TEXT NOT NULL DEFAULT (datetime('now')),
    finished_at TEXT,
    duration_ms INTEGER NOT NULL DEFAULT 0,
    total_requests INTEGER NOT NULL DEFAULT 0,
    success_count INTEGER NOT NULL DEFAULT 0,
    failure_count INTEGER NOT NULL DEFAULT 0,
    timeout_count INTEGER NOT NULL DEFAULT 0,
    p50_ms REAL NOT NULL DEFAULT 0.0,
    p95_ms REAL NOT NULL DEFAULT 0.0,
    p99_ms REAL NOT NULL DEFAULT 0.0,
    min_ms REAL NOT NULL DEFAULT 0.0,
    max_ms REAL NOT NULL DEFAULT 0.0,
    requests_per_second REAL NOT NULL DEFAULT 0.0,
    error_rate_percent REAL NOT NULL DEFAULT 0.0,
    warnings_json TEXT NOT NULL DEFAULT '[]',
    blockers_json TEXT NOT NULL DEFAULT '[]',
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_sbxv2_ltr_lt ON sandbox_v2_load_test_results(load_test_id);
CREATE INDEX IF NOT EXISTS idx_sbxv2_ltr_target ON sandbox_v2_load_test_results(target);
CREATE INDEX IF NOT EXISTS idx_sbxv2_ltr_status ON sandbox_v2_load_test_results(status);
CREATE INDEX IF NOT EXISTS idx_sbxv2_ltr_created ON sandbox_v2_load_test_results(started_at);

CREATE TABLE IF NOT EXISTS sandbox_v2_slo_definitions (
    slo_id TEXT PRIMARY KEY,
    name TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    target TEXT NOT NULL DEFAULT '',
    p95_ms INTEGER NOT NULL DEFAULT 500,
    p99_ms INTEGER NOT NULL DEFAULT 1500,
    error_rate_percent REAL NOT NULL DEFAULT 1.0,
    availability_percent REAL NOT NULL DEFAULT 99.0,
    enabled INTEGER NOT NULL DEFAULT 1,
    organization_id TEXT NOT NULL DEFAULT '',
    workspace_id TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_sbxv2_slod_enabled ON sandbox_v2_slo_definitions(enabled);

CREATE TABLE IF NOT EXISTS sandbox_v2_slo_evaluations (
    slo_eval_id TEXT PRIMARY KEY,
    slo_id TEXT NOT NULL DEFAULT '',
    load_test_id TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'not_evaluated',
    target TEXT NOT NULL DEFAULT '',
    observed_p95_ms REAL NOT NULL DEFAULT 0.0,
    observed_p99_ms REAL NOT NULL DEFAULT 0.0,
    observed_error_rate_percent REAL NOT NULL DEFAULT 0.0,
    observed_availability_percent REAL NOT NULL DEFAULT 0.0,
    reason TEXT NOT NULL DEFAULT '',
    evaluated_at TEXT NOT NULL DEFAULT (datetime('now')),
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_sbxv2_sloe_lt ON sandbox_v2_slo_evaluations(load_test_id);
CREATE INDEX IF NOT EXISTS idx_sbxv2_sloe_slo ON sandbox_v2_slo_evaluations(slo_id);
CREATE INDEX IF NOT EXISTS idx_sbxv2_sloe_eval ON sandbox_v2_slo_evaluations(evaluated_at);

CREATE TABLE IF NOT EXISTS sandbox_v2_capacity_plans (
    capacity_plan_id TEXT PRIMARY KEY,
    generated_at TEXT NOT NULL DEFAULT (datetime('now')),
    recommended_profile TEXT NOT NULL DEFAULT 'small',
    recommended_backend TEXT NOT NULL DEFAULT 'sqlite',
    recommended_workers INTEGER NOT NULL DEFAULT 2,
    recommended_queue_backend TEXT NOT NULL DEFAULT 'sqlite',
    recommended_object_storage TEXT NOT NULL DEFAULT 'local',
    expected_daily_jobs INTEGER NOT NULL DEFAULT 1000,
    expected_peak_rps REAL NOT NULL DEFAULT 5.0,
    bottlenecks_json TEXT NOT NULL DEFAULT '[]',
    scaling_recommendations_json TEXT NOT NULL DEFAULT '[]',
    risk_notes_json TEXT NOT NULL DEFAULT '[]',
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_sbxv2_cp_gen ON sandbox_v2_capacity_plans(generated_at);

-- ═══════════════════════════════════════════
-- Step 20 — Real OIDC / SAML Login Tables
-- ═══════════════════════════════════════════

CREATE TABLE IF NOT EXISTS sandbox_v2_sso_states (
    sso_state_id TEXT PRIMARY KEY,
    flow_type TEXT NOT NULL DEFAULT 'disabled',
    state_hash TEXT NOT NULL DEFAULT '',
    nonce_hash TEXT NOT NULL DEFAULT '',
    code_verifier_hash TEXT NOT NULL DEFAULT '',
    code_challenge TEXT NOT NULL DEFAULT '',
    redirect_uri TEXT NOT NULL DEFAULT '',
    provider_config_id TEXT NOT NULL DEFAULT '',
    organization_id TEXT NOT NULL DEFAULT '',
    workspace_id TEXT NOT NULL DEFAULT '',
    principal_hint TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    expires_at TEXT NOT NULL DEFAULT (datetime('now')),
    consumed_at TEXT,
    status TEXT NOT NULL DEFAULT 'created',
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_sbxv2_sss_hash ON sandbox_v2_sso_states(state_hash);
CREATE INDEX IF NOT EXISTS idx_sbxv2_sss_provider ON sandbox_v2_sso_states(provider_config_id);
CREATE INDEX IF NOT EXISTS idx_sbxv2_sss_created ON sandbox_v2_sso_states(created_at);

CREATE TABLE IF NOT EXISTS sandbox_v2_oidc_auth_requests (
    auth_request_id TEXT PRIMARY KEY,
    provider_config_id TEXT NOT NULL DEFAULT '',
    authorization_url TEXT NOT NULL DEFAULT '',
    state_id TEXT NOT NULL DEFAULT '',
    code_challenge TEXT NOT NULL DEFAULT '',
    scopes TEXT NOT NULL DEFAULT 'openid',
    redirect_uri TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_sbxv2_oar_provider ON sandbox_v2_oidc_auth_requests(provider_config_id);

CREATE TABLE IF NOT EXISTS sandbox_v2_oidc_callback_results (
    callback_id TEXT PRIMARY KEY,
    provider_config_id TEXT NOT NULL DEFAULT '',
    state_id TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'rejected',
    validation_status TEXT NOT NULL DEFAULT 'unavailable',
    mapping_decision_json TEXT NOT NULL DEFAULT '{}',
    security_context_json TEXT NOT NULL DEFAULT '{}',
    session_id TEXT NOT NULL DEFAULT '',
    audit_event_id TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_sbxv2_ocr_provider ON sandbox_v2_oidc_callback_results(provider_config_id);

CREATE TABLE IF NOT EXISTS sandbox_v2_oidc_token_validation_results (
    validation_id TEXT PRIMARY KEY,
    issuer_valid INTEGER NOT NULL DEFAULT 0,
    audience_valid INTEGER NOT NULL DEFAULT 0,
    nonce_valid INTEGER NOT NULL DEFAULT 0,
    exp_valid INTEGER NOT NULL DEFAULT 0,
    iat_valid INTEGER NOT NULL DEFAULT 0,
    signature_valid INTEGER NOT NULL DEFAULT 0,
    alg_allowed INTEGER NOT NULL DEFAULT 1,
    email_verified INTEGER NOT NULL DEFAULT 0,
    validation_status TEXT NOT NULL DEFAULT 'unavailable',
    reason TEXT NOT NULL DEFAULT 'Token validation not available',
    claims_redacted_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS sandbox_v2_saml_auth_requests (
    saml_request_id TEXT PRIMARY KEY,
    provider_config_id TEXT NOT NULL DEFAULT '',
    sso_url TEXT NOT NULL DEFAULT '',
    relay_state_id TEXT NOT NULL DEFAULT '',
    saml_request_redacted TEXT NOT NULL DEFAULT '',
    acs_url TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS sandbox_v2_saml_acs_results (
    acs_result_id TEXT PRIMARY KEY,
    provider_config_id TEXT NOT NULL DEFAULT '',
    relay_state_id TEXT NOT NULL DEFAULT '',
    validation_status TEXT NOT NULL DEFAULT 'unavailable',
    mapping_decision_json TEXT NOT NULL DEFAULT '{}',
    security_context_json TEXT NOT NULL DEFAULT '{}',
    session_id TEXT NOT NULL DEFAULT '',
    audit_event_id TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS sandbox_v2_sso_sessions (
    session_id TEXT PRIMARY KEY,
    principal_id TEXT NOT NULL DEFAULT '',
    principal_type TEXT NOT NULL DEFAULT 'user',
    provider_config_id TEXT NOT NULL DEFAULT '',
    external_identity_id TEXT NOT NULL DEFAULT '',
    organization_id TEXT NOT NULL DEFAULT '',
    workspace_id TEXT NOT NULL DEFAULT '',
    roles_json TEXT NOT NULL DEFAULT '[]',
    scopes_json TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    expires_at TEXT NOT NULL DEFAULT (datetime('now')),
    revoked_at TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_sbxv2_ss_org ON sandbox_v2_sso_sessions(organization_id);
CREATE INDEX IF NOT EXISTS idx_sbxv2_ss_ws ON sandbox_v2_sso_sessions(workspace_id);
CREATE INDEX IF NOT EXISTS idx_sbxv2_ss_status ON sandbox_v2_sso_sessions(status);
"""


class SQLiteSandboxV2Store:
    """SandboxV2Store 的 SQLite 实现。

    线程安全：通过 busy_timeout + execute_with_retry 处理并发写入。
    """

    def __init__(self, config: Settings, db_path: str | None = None):
        path = db_path or config.sqlite_db_path
        self._db = create_sqlite_db(path)
        execute_with_retry(lambda: self._init_schema(), label="sbx_v2_init_schema")

    def _init_schema(self):
        for stmt in _SCHEMA.strip().split(";"):
            s = stmt.strip()
            if s:
                self._db.execute(s)
        try:
            self._db.conn.commit()
        except Exception:
            pass

    def flush(self) -> None:
        """显式提交底层连接事务。"""
        try:
            if hasattr(self._db, "conn") and self._db.conn:
                self._db.conn.commit()
        except Exception:
            pass

    def _exec(self, sql: str, params: list[Any] | None = None) -> Any:
        return self._db.execute(sql, params or [])

    # ═══════════════════════════════════════════
    # Job CRUD
    # ═══════════════════════════════════════════

    def create_job(self, job: SandboxJob) -> SandboxJob:
        self._exec("""INSERT OR REPLACE INTO sandbox_v2_jobs (
            job_id, organization_id, workspace_id, agent_id, requested_by,
            mode, status, created_at, updated_at, requested_action, input_ref,
            policy_snapshot_json, risk_level, metadata_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", [
            job.job_id, job.organization_id, job.workspace_id, job.agent_id,
            job.requested_by, job.mode, job.status,
            job.created_at.isoformat(), job.updated_at.isoformat(),
            job.requested_action, job.input_ref,
            json.dumps(job.policy_snapshot, ensure_ascii=False),
            job.risk_level,
            json.dumps(job.metadata, ensure_ascii=False),
        ])
        return job

    def get_job(self, job_id: str) -> SandboxJob | None:
        row = next(self._exec(
            "SELECT * FROM sandbox_v2_jobs WHERE job_id=?", [job_id]), None)
        return self._row_to_job(dict(row)) if row else None

    def list_jobs(
        self,
        organization_id: str | None = None,
        workspace_id: str | None = None,
        limit: int = 50,
    ) -> list[SandboxJob]:
        sql = "SELECT * FROM sandbox_v2_jobs WHERE 1=1"
        params: list[Any] = []
        if organization_id:
            sql += " AND organization_id=?"
            params.append(organization_id)
        if workspace_id:
            sql += " AND workspace_id=?"
            params.append(workspace_id)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        return [self._row_to_job(dict(r)) for r in self._exec(sql, params)]

    def update_job_status(self, job_id: str, status: str) -> SandboxJob | None:
        existing = self.get_job(job_id)
        if existing is None:
            return None
        now = datetime.now(timezone.utc).isoformat()
        self._exec("""UPDATE sandbox_v2_jobs
            SET status=?, updated_at=? WHERE job_id=?""",
            [status, now, job_id])
        return self.get_job(job_id)

    # ═══════════════════════════════════════════
    # Execution Record CRUD
    # ═══════════════════════════════════════════

    def create_execution_record(self, record: SandboxV2ExecutionRecord) -> SandboxV2ExecutionRecord:
        self._exec("""INSERT OR REPLACE INTO sandbox_v2_execution_records (
            record_id, job_id, status, mode, started_at, finished_at,
            duration_ms, decision, reason, stdout_ref, stderr_ref,
            artifact_refs_json, audit_refs_json, error_code, error_message,
            no_real_execution, metadata_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", [
            record.record_id, record.job_id, record.status, record.mode,
            record.started_at.isoformat() if record.started_at else None,
            record.finished_at.isoformat() if record.finished_at else None,
            record.duration_ms, record.decision, record.reason,
            record.stdout_ref, record.stderr_ref,
            json.dumps(record.artifact_refs, ensure_ascii=False),
            json.dumps(record.audit_refs, ensure_ascii=False),
            record.error_code, record.error_message,
            1 if record.no_real_execution else 0,
            json.dumps(record.metadata, ensure_ascii=False),
        ])
        return record

    def get_execution_record(self, record_id: str) -> SandboxV2ExecutionRecord | None:
        row = next(self._exec(
            "SELECT * FROM sandbox_v2_execution_records WHERE record_id=?", [record_id]), None)
        return self._row_to_record(dict(row)) if row else None

    def list_execution_records(
        self,
        job_id: str | None = None,
        limit: int = 50,
    ) -> list[SandboxV2ExecutionRecord]:
        sql = "SELECT * FROM sandbox_v2_execution_records WHERE 1=1"
        params: list[Any] = []
        if job_id:
            sql += " AND job_id=?"
            params.append(job_id)
        sql += " ORDER BY started_at DESC LIMIT ?"
        params.append(limit)
        return [self._row_to_record(dict(r)) for r in self._exec(sql, params)]

    # ═══════════════════════════════════════════
    # Row mapping helpers
    # ═══════════════════════════════════════════

    @staticmethod
    def _row_to_job(row: dict[str, Any]) -> SandboxJob:
        def _parse_dt(v):
            if v is None:
                return datetime.now(timezone.utc)
            if isinstance(v, datetime):
                return v
            try:
                return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
            except (ValueError, TypeError):
                return datetime.now(timezone.utc)

        return SandboxJob(
            job_id=row.get("job_id", ""),
            organization_id=row.get("organization_id", ""),
            workspace_id=row.get("workspace_id", ""),
            agent_id=row.get("agent_id", ""),
            requested_by=row.get("requested_by", ""),
            mode=row.get("mode", SandboxV2Mode.SIMULATION),
            status=row.get("status", SandboxV2JobStatus.CREATED),
            created_at=_parse_dt(row.get("created_at")),
            updated_at=_parse_dt(row.get("updated_at")),
            requested_action=row.get("requested_action", ""),
            input_ref=row.get("input_ref", ""),
            policy_snapshot=json.loads(row.get("policy_snapshot_json", "{}")),
            risk_level=row.get("risk_level", SandboxV2RiskLevel.UNKNOWN),
            metadata=json.loads(row.get("metadata_json", "{}")),
        )

    # ═══════════════════════════════════════════
    # Step 3 — Artifact CRUD
    # ═══════════════════════════════════════════

    def create_artifact(self, artifact: SandboxArtifact) -> SandboxArtifact:
        self._exec("""INSERT OR REPLACE INTO sandbox_v2_artifacts (
            artifact_id, job_id, organization_id, workspace_id, record_id,
            artifact_type, name, original_filename, safe_filename,
            storage_key, storage_backend, size_bytes, mime_type, sha256,
            created_at, materialized_at, read_only, status, retention_until,
            risk_level, policy_decision_id, audit_refs_json, metadata_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", [
            artifact.artifact_id, artifact.job_id, artifact.organization_id,
            artifact.workspace_id, artifact.record_id, artifact.artifact_type,
            artifact.name, artifact.original_filename, artifact.safe_filename,
            artifact.storage_key, artifact.storage_backend, artifact.size_bytes,
            artifact.mime_type, artifact.sha256,
            artifact.created_at.isoformat(),
            artifact.materialized_at.isoformat() if artifact.materialized_at else None,
            1 if artifact.read_only else 0, artifact.status,
            artifact.retention_until.isoformat() if artifact.retention_until else None,
            artifact.risk_level, artifact.policy_decision_id,
            json.dumps(artifact.audit_refs, ensure_ascii=False),
            json.dumps(artifact.metadata, ensure_ascii=False),
        ])
        return artifact

    def get_artifact(self, artifact_id: str) -> SandboxArtifact | None:
        row = next(self._exec(
            "SELECT * FROM sandbox_v2_artifacts WHERE artifact_id=?", [artifact_id]), None)
        return self._row_to_artifact(dict(row)) if row else None

    def list_artifacts(
        self,
        job_id: str | None = None,
        record_id: str | None = None,
        organization_id: str | None = None,
        workspace_id: str | None = None,
        limit: int = 50,
    ) -> list[SandboxArtifact]:
        sql = "SELECT * FROM sandbox_v2_artifacts WHERE status != 'deleted'"
        params: list[Any] = []
        if job_id:
            sql += " AND job_id=?"
            params.append(job_id)
        if record_id:
            sql += " AND record_id=?"
            params.append(record_id)
        if organization_id:
            sql += " AND organization_id=?"
            params.append(organization_id)
        if workspace_id:
            sql += " AND workspace_id=?"
            params.append(workspace_id)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        return [self._row_to_artifact(dict(r)) for r in self._exec(sql, params)]

    def update_artifact_status(self, artifact_id: str, status: str) -> SandboxArtifact | None:
        existing = self.get_artifact(artifact_id)
        if existing is None:
            return None
        self._exec("UPDATE sandbox_v2_artifacts SET status=? WHERE artifact_id=?",
                   [status, artifact_id])
        self._db.conn.commit()
        return self.get_artifact(artifact_id)

    def create_artifact_manifest(self, manifest: SandboxArtifactManifest) -> SandboxArtifactManifest:
        self._exec("""INSERT OR REPLACE INTO sandbox_v2_artifact_manifests (
            manifest_id, job_id, record_id, artifact_ids_json,
            total_size_bytes, artifact_count, created_at, sealed, sha256
        ) VALUES (?,?,?,?,?,?,?,?,?)""", [
            manifest.manifest_id, manifest.job_id, manifest.record_id,
            json.dumps(manifest.artifact_ids, ensure_ascii=False),
            manifest.total_size_bytes, manifest.artifact_count,
            manifest.created_at.isoformat(),
            1 if manifest.sealed else 0, manifest.sha256,
        ])
        return manifest

    def get_artifact_manifest(self, manifest_id: str) -> SandboxArtifactManifest | None:
        row = next(self._exec(
            "SELECT * FROM sandbox_v2_artifact_manifests WHERE manifest_id=?", [manifest_id]), None)
        return self._row_to_manifest(dict(row)) if row else None

    def list_artifact_manifests(
        self,
        job_id: str | None = None,
        record_id: str | None = None,
        limit: int = 50,
    ) -> list[SandboxArtifactManifest]:
        sql = "SELECT * FROM sandbox_v2_artifact_manifests WHERE 1=1"
        params: list[Any] = []
        if job_id:
            sql += " AND job_id=? and params.append(job_id)"
            params.append(job_id)
        if record_id:
            sql += " AND record_id=?"
            params.append(record_id)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        return [self._row_to_manifest(dict(r)) for r in self._exec(sql, params)]

    def mark_artifact_expired(self, artifact_id: str) -> SandboxArtifact | None:
        return self.update_artifact_status(artifact_id, SandboxV2ArtifactStatus.EXPIRED)

    def delete_artifact_metadata(self, artifact_id: str) -> bool:
        existing = self.get_artifact(artifact_id)
        if existing is None:
            return False
        self._exec("UPDATE sandbox_v2_artifacts SET status=? WHERE artifact_id=?",
                   [SandboxV2ArtifactStatus.DELETED, artifact_id])
        self._db.conn.commit()
        return True

    # ═══════════════════════════════════════════
    # Row mapping helpers (continued)
    # ═══════════════════════════════════════════

    @staticmethod
    def _row_to_record(row: dict[str, Any]) -> SandboxV2ExecutionRecord:
        def _parse_dt(v):
            if v is None:
                return None
            if isinstance(v, datetime):
                return v
            try:
                return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
            except (ValueError, TypeError):
                return None

        return SandboxV2ExecutionRecord(
            record_id=row.get("record_id", ""),
            job_id=row.get("job_id", ""),
            status=row.get("status", SandboxV2JobStatus.CREATED),
            mode=row.get("mode", SandboxV2Mode.SIMULATION),
            started_at=_parse_dt(row.get("started_at")),
            finished_at=_parse_dt(row.get("finished_at")),
            duration_ms=row.get("duration_ms", 0),
            decision=row.get("decision", SandboxV2Decision.DENY),
            reason=row.get("reason", ""),
            stdout_ref=row.get("stdout_ref", ""),
            stderr_ref=row.get("stderr_ref", ""),
            artifact_refs=json.loads(row.get("artifact_refs_json", "[]")),
            audit_refs=json.loads(row.get("audit_refs_json", "[]")),
            error_code=row.get("error_code", ""),
            error_message=row.get("error_message", ""),
            no_real_execution=bool(row.get("no_real_execution", 1)),
            metadata=json.loads(row.get("metadata_json", "{}")),
        )

    @staticmethod
    def _row_to_artifact(row: dict[str, Any]) -> SandboxArtifact:
        def _parse_dt(v):
            if v is None:
                return None
            if isinstance(v, datetime):
                return v
            try:
                return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
            except (ValueError, TypeError):
                return None

        return SandboxArtifact(
            artifact_id=row.get("artifact_id", ""),
            job_id=row.get("job_id", ""),
            organization_id=row.get("organization_id", ""),
            workspace_id=row.get("workspace_id", ""),
            record_id=row.get("record_id", ""),
            artifact_type=row.get("artifact_type", SandboxV2ArtifactType.UNKNOWN),
            name=row.get("name", ""),
            original_filename=row.get("original_filename", ""),
            safe_filename=row.get("safe_filename", ""),
            storage_key=row.get("storage_key", ""),
            storage_backend=row.get("storage_backend", "local"),
            size_bytes=row.get("size_bytes", 0),
            mime_type=row.get("mime_type", "text/plain"),
            sha256=row.get("sha256", ""),
            created_at=_parse_dt(row.get("created_at")) or datetime.now(timezone.utc),
            materialized_at=_parse_dt(row.get("materialized_at")),
            read_only=bool(row.get("read_only", 1)),
            status=row.get("status", SandboxV2ArtifactStatus.PENDING),
            retention_until=_parse_dt(row.get("retention_until")),
            risk_level=row.get("risk_level", SandboxV2RiskLevel.LOW),
            policy_decision_id=row.get("policy_decision_id", ""),
            audit_refs=json.loads(row.get("audit_refs_json", "[]")),
            metadata=json.loads(row.get("metadata_json", "{}")),
        )

    # ═══════════════════════════════════════════
    # Step 4 — Package / Supply Chain CRUD
    # ═══════════════════════════════════════════

    def create_package_request(self, request: SandboxPackageRequest) -> SandboxPackageRequest:
        self._exec("""INSERT OR REPLACE INTO sandbox_v2_package_requests (
            package_request_id, job_id, organization_id, workspace_id, requested_by,
            package_name, package_version, package_manager, source_url, source_type,
            requested_action, expected_sha256, expected_signature, sbom_ref,
            created_at, status, risk_level, policy_decision_id, reason, metadata_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", [
            request.package_request_id, request.job_id, request.organization_id,
            request.workspace_id, request.requested_by, request.package_name,
            request.package_version, request.package_manager, request.source_url,
            request.source_type, request.requested_action, request.expected_sha256,
            request.expected_signature, request.sbom_ref,
            request.created_at.isoformat(), request.status, request.risk_level,
            request.policy_decision_id, request.reason,
            json.dumps(request.metadata, ensure_ascii=False),
        ])
        return request

    def get_package_request(self, package_request_id: str) -> SandboxPackageRequest | None:
        row = next(self._exec(
            "SELECT * FROM sandbox_v2_package_requests WHERE package_request_id=?", [package_request_id]), None)
        return self._row_to_package_request(dict(row)) if row else None

    def list_package_requests(
        self, job_id: str | None = None, organization_id: str | None = None,
        workspace_id: str | None = None, status: str | None = None, limit: int = 50,
    ) -> list[SandboxPackageRequest]:
        sql = "SELECT * FROM sandbox_v2_package_requests WHERE 1=1"
        params: list[Any] = []
        if job_id: sql += " AND job_id=?"; params.append(job_id)
        if organization_id: sql += " AND organization_id=?"; params.append(organization_id)
        if workspace_id: sql += " AND workspace_id=?"; params.append(workspace_id)
        if status: sql += " AND status=?"; params.append(status)
        sql += " ORDER BY created_at DESC LIMIT ?"; params.append(limit)
        return [self._row_to_package_request(dict(r)) for r in self._exec(sql, params)]

    def update_package_request_status(self, package_request_id: str, status: str, reason: str = "") -> SandboxPackageRequest | None:
        existing = self.get_package_request(package_request_id)
        if existing is None: return None
        self._exec("UPDATE sandbox_v2_package_requests SET status=?, reason=? WHERE package_request_id=?",
                   [status, reason or existing.reason, package_request_id])
        self._db.conn.commit()
        return self.get_package_request(package_request_id)

    def create_quarantine_record(self, record: SandboxPackageQuarantineRecord) -> SandboxPackageQuarantineRecord:
        self._exec("""INSERT OR REPLACE INTO sandbox_v2_package_quarantine (
            quarantine_id, package_request_id, job_id, organization_id, workspace_id,
            package_name, package_version, package_manager, storage_key, size_bytes, sha256,
            signature_status, sbom_status, vulnerability_status, status, created_at,
            reviewed_at, reviewed_by, release_decision, reason, metadata_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", [
            record.quarantine_id, record.package_request_id, record.job_id,
            record.organization_id, record.workspace_id, record.package_name,
            record.package_version, record.package_manager, record.storage_key,
            record.size_bytes, record.sha256, record.signature_status, record.sbom_status,
            record.vulnerability_status, record.status, record.created_at.isoformat(),
            record.reviewed_at.isoformat() if record.reviewed_at else None,
            record.reviewed_by, record.release_decision, record.reason,
            json.dumps(record.metadata, ensure_ascii=False),
        ])
        return record

    def get_quarantine_record(self, quarantine_id: str) -> SandboxPackageQuarantineRecord | None:
        row = next(self._exec("SELECT * FROM sandbox_v2_package_quarantine WHERE quarantine_id=?", [quarantine_id]), None)
        return self._row_to_quarantine(dict(row)) if row else None

    def list_quarantine_records(self, package_request_id: str | None = None, status: str | None = None, limit: int = 50) -> list[SandboxPackageQuarantineRecord]:
        sql = "SELECT * FROM sandbox_v2_package_quarantine WHERE 1=1"
        params: list[Any] = []
        if package_request_id: sql += " AND package_request_id=?"; params.append(package_request_id)
        if status: sql += " AND status=?"; params.append(status)
        sql += " ORDER BY created_at DESC LIMIT ?"; params.append(limit)
        return [self._row_to_quarantine(dict(r)) for r in self._exec(sql, params)]

    def update_quarantine_status(self, quarantine_id: str, status: str, reason: str = "") -> SandboxPackageQuarantineRecord | None:
        existing = self.get_quarantine_record(quarantine_id)
        if existing is None: return None
        now = datetime.now(timezone.utc).isoformat()
        self._exec("UPDATE sandbox_v2_package_quarantine SET status=?, reason=?, reviewed_at=? WHERE quarantine_id=?",
                   [status, reason or existing.reason, now, quarantine_id])
        self._db.conn.commit()
        return self.get_quarantine_record(quarantine_id)

    def create_package_sbom(self, sbom: SandboxPackageSBOM) -> SandboxPackageSBOM:
        self._exec("""INSERT OR REPLACE INTO sandbox_v2_package_sboms (
            sbom_id, package_request_id, package_name, package_version, format,
            content_sha256, component_count, created_at, storage_key, status, metadata_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?)""", [
            sbom.sbom_id, sbom.package_request_id, sbom.package_name, sbom.package_version,
            sbom.format, sbom.content_sha256, sbom.component_count,
            sbom.created_at.isoformat(), sbom.storage_key, sbom.status,
            json.dumps(sbom.metadata, ensure_ascii=False),
        ])
        return sbom

    def get_package_sbom(self, sbom_id: str) -> SandboxPackageSBOM | None:
        row = next(self._exec("SELECT * FROM sandbox_v2_package_sboms WHERE sbom_id=?", [sbom_id]), None)
        return self._row_to_sbom(dict(row)) if row else None

    def list_package_sboms(self, package_request_id: str | None = None, limit: int = 50) -> list[SandboxPackageSBOM]:
        sql = "SELECT * FROM sandbox_v2_package_sboms WHERE 1=1"
        params: list[Any] = []
        if package_request_id: sql += " AND package_request_id=?"; params.append(package_request_id)
        sql += " ORDER BY created_at DESC LIMIT ?"; params.append(limit)
        return [self._row_to_sbom(dict(r)) for r in self._exec(sql, params)]

    def create_vulnerability_scan_result(self, result: SandboxPackageVulnerabilityScanResult) -> SandboxPackageVulnerabilityScanResult:
        self._exec("""INSERT OR REPLACE INTO sandbox_v2_package_vulnerability_scans (
            scan_id, package_request_id, package_name, package_version, scanner, status,
            severity_summary, critical_count, high_count, medium_count, low_count,
            findings_json, created_at, metadata_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", [
            result.scan_id, result.package_request_id, result.package_name,
            result.package_version, result.scanner, result.status,
            result.severity_summary, result.critical_count, result.high_count,
            result.medium_count, result.low_count,
            json.dumps(result.findings, ensure_ascii=False),
            result.created_at.isoformat(),
            json.dumps(result.metadata, ensure_ascii=False),
        ])
        return result

    def get_vulnerability_scan_result(self, scan_id: str) -> SandboxPackageVulnerabilityScanResult | None:
        row = next(self._exec("SELECT * FROM sandbox_v2_package_vulnerability_scans WHERE scan_id=?", [scan_id]), None)
        return self._row_to_scan(dict(row)) if row else None

    def list_vulnerability_scan_results(self, package_request_id: str | None = None, limit: int = 50) -> list[SandboxPackageVulnerabilityScanResult]:
        sql = "SELECT * FROM sandbox_v2_package_vulnerability_scans WHERE 1=1"
        params: list[Any] = []
        if package_request_id: sql += " AND package_request_id=?"; params.append(package_request_id)
        sql += " ORDER BY created_at DESC LIMIT ?"; params.append(limit)
        return [self._row_to_scan(dict(r)) for r in self._exec(sql, params)]

    # ═══════════════════════════════════════════
    # Composed row mappers
    # ═══════════════════════════════════════════

    @staticmethod
    def _row_to_manifest(row: dict[str, Any]) -> SandboxArtifactManifest:
        def _parse_dt(v):
            if isinstance(v, datetime):
                return v
            try:
                return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
            except (ValueError, TypeError):
                return datetime.now(timezone.utc)

        return SandboxArtifactManifest(
            manifest_id=row.get("manifest_id", ""),
            job_id=row.get("job_id", ""),
            record_id=row.get("record_id", ""),
            artifact_ids=json.loads(row.get("artifact_ids_json", "[]")),
            total_size_bytes=row.get("total_size_bytes", 0),
            artifact_count=row.get("artifact_count", 0),
            created_at=_parse_dt(row.get("created_at")),
            sealed=bool(row.get("sealed", 0)),
            sha256=row.get("sha256", ""),
        )

    @staticmethod
    def _row_to_package_request(row: dict[str, Any]) -> SandboxPackageRequest:
        def _p(v):
            if isinstance(v, datetime): return v
            if isinstance(v, str) and v:
                try: return datetime.fromisoformat(v.replace("Z", "+00:00"))
                except: return datetime.now(timezone.utc)
            return datetime.now(timezone.utc)
        return SandboxPackageRequest(
            package_request_id=row.get("package_request_id", ""),
            job_id=row.get("job_id", ""), organization_id=row.get("organization_id", ""),
            workspace_id=row.get("workspace_id", ""), requested_by=row.get("requested_by", ""),
            package_name=row.get("package_name", ""), package_version=row.get("package_version", ""),
            package_manager=row.get("package_manager", "unknown"),
            source_url=row.get("source_url", ""), source_type=row.get("source_type", "unknown"),
            requested_action=row.get("requested_action", ""),
            expected_sha256=row.get("expected_sha256", ""),
            expected_signature=row.get("expected_signature", ""),
            sbom_ref=row.get("sbom_ref", ""), created_at=_p(row.get("created_at")),
            status=row.get("status", "requested"), risk_level=row.get("risk_level", "unknown"),
            policy_decision_id=row.get("policy_decision_id", ""),
            reason=row.get("reason", ""),
            metadata=json.loads(row.get("metadata_json", "{}")),
        )

    @staticmethod
    def _row_to_quarantine(row: dict[str, Any]) -> SandboxPackageQuarantineRecord:
        def _p(v):
            if isinstance(v, datetime): return v
            if isinstance(v, str) and v:
                try: return datetime.fromisoformat(v.replace("Z", "+00:00"))
                except: return None
            return None
        return SandboxPackageQuarantineRecord(
            quarantine_id=row.get("quarantine_id", ""),
            package_request_id=row.get("package_request_id", ""),
            job_id=row.get("job_id", ""), organization_id=row.get("organization_id", ""),
            workspace_id=row.get("workspace_id", ""), package_name=row.get("package_name", ""),
            package_version=row.get("package_version", ""),
            package_manager=row.get("package_manager", "unknown"),
            storage_key=row.get("storage_key", ""), size_bytes=row.get("size_bytes", 0),
            sha256=row.get("sha256", ""), signature_status=row.get("signature_status", "not_provided"),
            sbom_status=row.get("sbom_status", "not_provided"),
            vulnerability_status=row.get("vulnerability_status", "not_scanned"),
            status=row.get("status", "quarantined"),
            created_at=_p(row.get("created_at")) or datetime.now(timezone.utc),
            reviewed_at=_p(row.get("reviewed_at")), reviewed_by=row.get("reviewed_by", ""),
            release_decision=row.get("release_decision", ""), reason=row.get("reason", ""),
            metadata=json.loads(row.get("metadata_json", "{}")),
        )

    @staticmethod
    def _row_to_sbom(row: dict[str, Any]) -> SandboxPackageSBOM:
        def _p(v):
            if isinstance(v, datetime): return v
            if isinstance(v, str) and v:
                try: return datetime.fromisoformat(v.replace("Z", "+00:00"))
                except: return datetime.now(timezone.utc)
            return datetime.now(timezone.utc)
        return SandboxPackageSBOM(
            sbom_id=row.get("sbom_id", ""), package_request_id=row.get("package_request_id", ""),
            package_name=row.get("package_name", ""), package_version=row.get("package_version", ""),
            format=row.get("format", "unknown"), content_sha256=row.get("content_sha256", ""),
            component_count=row.get("component_count", 0),
            created_at=_p(row.get("created_at")), storage_key=row.get("storage_key", ""),
            status=row.get("status", "provided"),
            metadata=json.loads(row.get("metadata_json", "{}")),
        )

    # ═══════════════════════════════════════════
    # Step 5 — Network Egress CRUD
    # ═══════════════════════════════════════════

    def create_network_egress_request(self, request: SandboxNetworkEgressRequest) -> SandboxNetworkEgressRequest:
        self._exec("""INSERT OR REPLACE INTO sandbox_v2_network_egress_requests (
            egress_request_id, job_id, organization_id, workspace_id, requested_by,
            url, scheme, hostname, port, resolved_ips_json, method, purpose,
            requested_at, status, risk_level, policy_decision_id, reason, metadata_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", [
            request.egress_request_id, request.job_id, request.organization_id,
            request.workspace_id, request.requested_by, request.url, request.scheme,
            request.hostname, request.port,
            json.dumps(request.resolved_ips, ensure_ascii=False),
            request.method, request.purpose, request.requested_at.isoformat(),
            request.status, request.risk_level, request.policy_decision_id,
            request.reason, json.dumps(request.metadata, ensure_ascii=False),
        ])
        return request

    def get_network_egress_request(self, egress_request_id: str) -> SandboxNetworkEgressRequest | None:
        row = next(self._exec("SELECT * FROM sandbox_v2_network_egress_requests WHERE egress_request_id=?", [egress_request_id]), None)
        return self._row_to_egress_request(dict(row)) if row else None

    def list_network_egress_requests(self, job_id: str | None = None, organization_id: str | None = None, workspace_id: str | None = None, status: str | None = None, limit: int = 50) -> list[SandboxNetworkEgressRequest]:
        sql = "SELECT * FROM sandbox_v2_network_egress_requests WHERE 1=1"
        params: list[Any] = []
        if job_id: sql += " AND job_id=?"; params.append(job_id)
        if organization_id: sql += " AND organization_id=?"; params.append(organization_id)
        if workspace_id: sql += " AND workspace_id=?"; params.append(workspace_id)
        if status: sql += " AND status=?"; params.append(status)
        sql += " ORDER BY requested_at DESC LIMIT ?"; params.append(limit)
        return [self._row_to_egress_request(dict(r)) for r in self._exec(sql, params)]

    def update_network_egress_request_status(self, egress_request_id: str, status: str, reason: str = "") -> SandboxNetworkEgressRequest | None:
        existing = self.get_network_egress_request(egress_request_id)
        if existing is None: return None
        self._exec("UPDATE sandbox_v2_network_egress_requests SET status=?, reason=? WHERE egress_request_id=?",
                   [status, reason or existing.reason, egress_request_id])
        self._db.conn.commit()
        return self.get_network_egress_request(egress_request_id)

    def create_network_egress_audit_record(self, record: SandboxNetworkEgressAuditRecord) -> SandboxNetworkEgressAuditRecord:
        self._exec("""INSERT OR REPLACE INTO sandbox_v2_network_egress_audit_records (
            audit_id, egress_request_id, job_id, organization_id, workspace_id,
            url, hostname, resolved_ips_json, decision, reason, risk_level,
            created_at, metadata_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""", [
            record.audit_id, record.egress_request_id, record.job_id,
            record.organization_id, record.workspace_id, record.url,
            record.hostname, json.dumps(record.resolved_ips, ensure_ascii=False),
            record.decision, record.reason, record.risk_level,
            record.created_at.isoformat(),
            json.dumps(record.metadata, ensure_ascii=False),
        ])
        return record

    def get_network_egress_audit_record(self, audit_id: str) -> SandboxNetworkEgressAuditRecord | None:
        row = next(self._exec("SELECT * FROM sandbox_v2_network_egress_audit_records WHERE audit_id=?", [audit_id]), None)
        return self._row_to_egress_audit(dict(row)) if row else None

    def list_network_egress_audit_records(self, egress_request_id: str | None = None, job_id: str | None = None, limit: int = 50) -> list[SandboxNetworkEgressAuditRecord]:
        sql = "SELECT * FROM sandbox_v2_network_egress_audit_records WHERE 1=1"
        params: list[Any] = []
        if egress_request_id: sql += " AND egress_request_id=?"; params.append(egress_request_id)
        if job_id: sql += " AND job_id=?"; params.append(job_id)
        sql += " ORDER BY created_at DESC LIMIT ?"; params.append(limit)
        return [self._row_to_egress_audit(dict(r)) for r in self._exec(sql, params)]

    # ═══════════════════════════════════════════
    # Step 5 — Network row mappers
    # ═══════════════════════════════════════════

    @staticmethod
    def _row_to_egress_request(row: dict[str, Any]) -> SandboxNetworkEgressRequest:
        def _p(v):
            if isinstance(v, datetime): return v
            if isinstance(v, str) and v:
                try: return datetime.fromisoformat(v.replace("Z", "+00:00"))
                except: return datetime.now(timezone.utc)
            return datetime.now(timezone.utc)
        return SandboxNetworkEgressRequest(
            egress_request_id=row.get("egress_request_id", ""), job_id=row.get("job_id", ""),
            organization_id=row.get("organization_id", ""), workspace_id=row.get("workspace_id", ""),
            requested_by=row.get("requested_by", ""), url=row.get("url", ""),
            scheme=row.get("scheme", ""), hostname=row.get("hostname", ""),
            port=row.get("port", 443), resolved_ips=json.loads(row.get("resolved_ips_json", "[]")),
            method=row.get("method", "GET"), purpose=row.get("purpose", ""),
            requested_at=_p(row.get("requested_at")), status=row.get("status", "requested"),
            risk_level=row.get("risk_level", "medium"), policy_decision_id=row.get("policy_decision_id", ""),
            reason=row.get("reason", ""), metadata=json.loads(row.get("metadata_json", "{}")),
        )

    @staticmethod
    def _row_to_egress_audit(row: dict[str, Any]) -> SandboxNetworkEgressAuditRecord:
        def _p(v):
            if isinstance(v, datetime): return v
            if isinstance(v, str) and v:
                try: return datetime.fromisoformat(v.replace("Z", "+00:00"))
                except: return datetime.now(timezone.utc)
            return datetime.now(timezone.utc)
        return SandboxNetworkEgressAuditRecord(
            audit_id=row.get("audit_id", ""), egress_request_id=row.get("egress_request_id", ""),
            job_id=row.get("job_id", ""), organization_id=row.get("organization_id", ""),
            workspace_id=row.get("workspace_id", ""), url=row.get("url", ""),
            hostname=row.get("hostname", ""), resolved_ips=json.loads(row.get("resolved_ips_json", "[]")),
            decision=row.get("decision", "deny"), reason=row.get("reason", ""),
            risk_level=row.get("risk_level", "medium"), created_at=_p(row.get("created_at")),
            metadata=json.loads(row.get("metadata_json", "{}")),
        )

    # ═══════════════════════════════════════════
    # Step 6A — Isolation / Execution Plan CRUD
    # ═══════════════════════════════════════════

    def create_isolation_capability(self, capability: SandboxIsolationCapability) -> SandboxIsolationCapability:
        self._exec("""INSERT OR REPLACE INTO sandbox_v2_isolation_capabilities (
            capability_id, provider, available, enabled, reason, platform, os_name,
            is_windows, is_linux, has_docker, has_podman, has_firecracker,
            has_gvisor, has_kata, has_user_namespace, has_cgroup, has_seccomp,
            has_apparmor, has_selinux, has_network_namespace, has_mount_namespace,
            checked_at, metadata_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", [
            capability.capability_id, capability.provider,
            1 if capability.available else 0, 1 if capability.enabled else 0,
            capability.reason, capability.platform, capability.os_name,
            1 if capability.is_windows else 0, 1 if capability.is_linux else 0,
            1 if capability.has_docker else 0, 1 if capability.has_podman else 0,
            1 if capability.has_firecracker else 0, 1 if capability.has_gvisor else 0,
            1 if capability.has_kata else 0, 1 if capability.has_user_namespace else 0,
            1 if capability.has_cgroup else 0, 1 if capability.has_seccomp else 0,
            1 if capability.has_apparmor else 0, 1 if capability.has_selinux else 0,
            1 if capability.has_network_namespace else 0, 1 if capability.has_mount_namespace else 0,
            capability.checked_at.isoformat(),
            json.dumps(capability.metadata, ensure_ascii=False),
        ])
        return capability

    def get_latest_isolation_capability(self, provider: str | None = None) -> SandboxIsolationCapability | None:
        sql = "SELECT * FROM sandbox_v2_isolation_capabilities WHERE 1=1"
        params: list[Any] = []
        if provider: sql += " AND provider LIKE ?"; params.append(f"%{provider}%")
        sql += " ORDER BY checked_at DESC LIMIT 1"
        row = next(self._exec(sql, params), None)
        return self._row_to_isolation_capability(dict(row)) if row else None

    def list_isolation_capabilities(self, provider: str | None = None, limit: int = 50) -> list[SandboxIsolationCapability]:
        sql = "SELECT * FROM sandbox_v2_isolation_capabilities WHERE 1=1"
        params: list[Any] = []
        if provider: sql += " AND provider LIKE ?"; params.append(f"%{provider}%")
        sql += " ORDER BY checked_at DESC LIMIT ?"; params.append(limit)
        return [self._row_to_isolation_capability(dict(r)) for r in self._exec(sql, params)]

    def create_execution_plan(self, plan: SandboxExecutionPlan) -> SandboxExecutionPlan:
        self._exec("""INSERT OR REPLACE INTO sandbox_v2_execution_plans (
            execution_plan_id, job_id, organization_id, workspace_id,
            provider, mode, command_ref, image_ref,
            input_artifact_refs_json, output_artifact_policy_json,
            network_policy_snapshot_json, filesystem_policy_snapshot_json,
            resource_limits_json, environment_policy_json,
            working_directory_policy_json, created_at, status, reason, metadata_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", [
            plan.execution_plan_id, plan.job_id, plan.organization_id, plan.workspace_id,
            plan.provider, plan.mode, plan.command_ref, plan.image_ref,
            json.dumps(plan.input_artifact_refs, ensure_ascii=False),
            json.dumps(plan.output_artifact_policy, ensure_ascii=False),
            json.dumps(plan.network_policy_snapshot, ensure_ascii=False),
            json.dumps(plan.filesystem_policy_snapshot, ensure_ascii=False),
            json.dumps(plan.resource_limits, ensure_ascii=False),
            json.dumps(plan.environment_policy, ensure_ascii=False),
            json.dumps(plan.working_directory_policy, ensure_ascii=False),
            plan.created_at.isoformat(), plan.status, plan.reason,
            json.dumps(plan.metadata, ensure_ascii=False),
        ])
        return plan

    def get_execution_plan(self, execution_plan_id: str) -> SandboxExecutionPlan | None:
        row = next(self._exec("SELECT * FROM sandbox_v2_execution_plans WHERE execution_plan_id=?", [execution_plan_id]), None)
        return self._row_to_execution_plan(dict(row)) if row else None

    def list_execution_plans(self, job_id: str | None = None, organization_id: str | None = None, workspace_id: str | None = None, status: str | None = None, limit: int = 50) -> list[SandboxExecutionPlan]:
        sql = "SELECT * FROM sandbox_v2_execution_plans WHERE 1=1"
        params: list[Any] = []
        if job_id: sql += " AND job_id=?"; params.append(job_id)
        if organization_id: sql += " AND organization_id=?"; params.append(organization_id)
        if workspace_id: sql += " AND workspace_id=?"; params.append(workspace_id)
        if status: sql += " AND status=?"; params.append(status)
        sql += " ORDER BY created_at DESC LIMIT ?"; params.append(limit)
        return [self._row_to_execution_plan(dict(r)) for r in self._exec(sql, params)]

    def update_execution_plan_status(self, execution_plan_id: str, status: str, reason: str = "") -> SandboxExecutionPlan | None:
        existing = self.get_execution_plan(execution_plan_id)
        if existing is None: return None
        self._exec("UPDATE sandbox_v2_execution_plans SET status=?, reason=? WHERE execution_plan_id=?",
                   [status, reason or existing.reason, execution_plan_id])
        self._db.conn.commit()
        return self.get_execution_plan(execution_plan_id)

    @staticmethod
    def _row_to_isolation_capability(row: dict[str, Any]) -> SandboxIsolationCapability:
        def _p(v):
            if isinstance(v, datetime): return v
            if isinstance(v, str) and v:
                try: return datetime.fromisoformat(v.replace("Z", "+00:00"))
                except: return datetime.now(timezone.utc)
            return datetime.now(timezone.utc)
        return SandboxIsolationCapability(
            capability_id=row.get("capability_id", ""), provider=row.get("provider", "disabled"),
            available=bool(row.get("available", 0)), enabled=bool(row.get("enabled", 0)),
            reason=row.get("reason", ""), platform=row.get("platform", ""),
            os_name=row.get("os_name", ""), is_windows=bool(row.get("is_windows", 0)),
            is_linux=bool(row.get("is_linux", 0)), has_docker=bool(row.get("has_docker", 0)),
            has_podman=bool(row.get("has_podman", 0)), has_firecracker=bool(row.get("has_firecracker", 0)),
            has_gvisor=bool(row.get("has_gvisor", 0)), has_kata=bool(row.get("has_kata", 0)),
            has_user_namespace=bool(row.get("has_user_namespace", 0)),
            has_cgroup=bool(row.get("has_cgroup", 0)), has_seccomp=bool(row.get("has_seccomp", 0)),
            has_apparmor=bool(row.get("has_apparmor", 0)), has_selinux=bool(row.get("has_selinux", 0)),
            has_network_namespace=bool(row.get("has_network_namespace", 0)),
            has_mount_namespace=bool(row.get("has_mount_namespace", 0)),
            checked_at=_p(row.get("checked_at")),
            metadata=json.loads(row.get("metadata_json", "{}")),
        )

    @staticmethod
    def _row_to_execution_plan(row: dict[str, Any]) -> SandboxExecutionPlan:
        def _p(v):
            if isinstance(v, datetime): return v
            if isinstance(v, str) and v:
                try: return datetime.fromisoformat(v.replace("Z", "+00:00"))
                except: return datetime.now(timezone.utc)
            return datetime.now(timezone.utc)
        return SandboxExecutionPlan(
            execution_plan_id=row.get("execution_plan_id", ""), job_id=row.get("job_id", ""),
            organization_id=row.get("organization_id", ""), workspace_id=row.get("workspace_id", ""),
            provider=row.get("provider", SandboxV2IsolationProvider.DISABLED),
            mode=row.get("mode", SandboxV2Mode.SIMULATION),
            command_ref=row.get("command_ref", ""), image_ref=row.get("image_ref", ""),
            input_artifact_refs=json.loads(row.get("input_artifact_refs_json", "[]")),
            output_artifact_policy=json.loads(row.get("output_artifact_policy_json", "{}")),
            network_policy_snapshot=json.loads(row.get("network_policy_snapshot_json", "{}")),
            filesystem_policy_snapshot=json.loads(row.get("filesystem_policy_snapshot_json", "{}")),
            resource_limits=json.loads(row.get("resource_limits_json", "{}")),
            environment_policy=json.loads(row.get("environment_policy_json", "{}")),
            working_directory_policy=json.loads(row.get("working_directory_policy_json", "{}")),
            created_at=_p(row.get("created_at")), status=row.get("status", "created"),
            reason=row.get("reason", ""), metadata=json.loads(row.get("metadata_json", "{}")),
        )

    # ═══════════════════════════════════════════
    # Step 6B — Container Execution CRUD
    # ═══════════════════════════════════════════

    def create_container_execution_plan(self, plan: SandboxContainerExecutionPlan) -> SandboxContainerExecutionPlan:
        self._exec("""INSERT OR REPLACE INTO sandbox_v2_container_execution_plans (
            container_plan_id, execution_plan_id, job_id, provider, runtime, image,
            fixture_id, command_json, env_json, network_mode, readonly_rootfs, user,
            resource_limits_json, timeout_seconds, status, reason, created_at, metadata_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", [
            plan.container_plan_id, plan.execution_plan_id, plan.job_id, plan.provider,
            plan.runtime, plan.image, plan.fixture_id,
            json.dumps(plan.command, ensure_ascii=False),
            json.dumps(plan.env, ensure_ascii=False), plan.network_mode,
            1 if plan.readonly_rootfs else 0, plan.user,
            json.dumps(plan.resource_limits, ensure_ascii=False),
            plan.timeout_seconds, plan.status, plan.reason,
            plan.created_at.isoformat(),
            json.dumps(plan.metadata, ensure_ascii=False),
        ])
        return plan

    def get_container_execution_plan(self, container_plan_id: str) -> SandboxContainerExecutionPlan | None:
        row = next(self._exec("SELECT * FROM sandbox_v2_container_execution_plans WHERE container_plan_id=?", [container_plan_id]), None)
        return self._row_to_container_plan(dict(row)) if row else None

    def list_container_execution_plans(self, job_id: str | None = None, status: str | None = None, limit: int = 50) -> list[SandboxContainerExecutionPlan]:
        sql = "SELECT * FROM sandbox_v2_container_execution_plans WHERE 1=1"
        params: list[Any] = []
        if job_id: sql += " AND job_id=?"; params.append(job_id)
        if status: sql += " AND status=?"; params.append(status)
        sql += " ORDER BY created_at DESC LIMIT ?"; params.append(limit)
        return [self._row_to_container_plan(dict(r)) for r in self._exec(sql, params)]

    def update_container_execution_plan_status(self, container_plan_id: str, status: str, reason: str = "") -> SandboxContainerExecutionPlan | None:
        existing = self.get_container_execution_plan(container_plan_id)
        if existing is None: return None
        self._exec("UPDATE sandbox_v2_container_execution_plans SET status=?, reason=? WHERE container_plan_id=?",
                   [status, reason or existing.reason, container_plan_id])
        self._db.conn.commit()
        return self.get_container_execution_plan(container_plan_id)

    def create_container_execution_result(self, result: SandboxContainerExecutionResult) -> SandboxContainerExecutionResult:
        self._exec("""INSERT OR REPLACE INTO sandbox_v2_container_execution_results (
            container_result_id, container_plan_id, execution_plan_id, job_id,
            provider, runtime, status, exit_code, started_at, finished_at,
            duration_ms, stdout_text, stderr_text, stdout_artifact_id,
            stderr_artifact_id, timeout, canceled, reason, metadata_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", [
            result.container_result_id, result.container_plan_id, result.execution_plan_id,
            result.job_id, result.provider, result.runtime, result.status, result.exit_code,
            result.started_at.isoformat() if result.started_at else None,
            result.finished_at.isoformat() if result.finished_at else None,
            result.duration_ms, result.stdout_text, result.stderr_text,
            result.stdout_artifact_id, result.stderr_artifact_id,
            1 if result.timeout else 0, 1 if result.canceled else 0,
            result.reason, json.dumps(result.metadata, ensure_ascii=False),
        ])
        return result

    def get_container_execution_result(self, container_result_id: str) -> SandboxContainerExecutionResult | None:
        row = next(self._exec("SELECT * FROM sandbox_v2_container_execution_results WHERE container_result_id=?", [container_result_id]), None)
        return self._row_to_container_result(dict(row)) if row else None

    def list_container_execution_results(self, job_id: str | None = None, container_plan_id: str | None = None, limit: int = 50) -> list[SandboxContainerExecutionResult]:
        sql = "SELECT * FROM sandbox_v2_container_execution_results WHERE 1=1"
        params: list[Any] = []
        if job_id: sql += " AND job_id=?"; params.append(job_id)
        if container_plan_id: sql += " AND container_plan_id=?"; params.append(container_plan_id)
        sql += " ORDER BY started_at DESC LIMIT ?"; params.append(limit)
        return [self._row_to_container_result(dict(r)) for r in self._exec(sql, params)]

    @staticmethod
    def _row_to_container_plan(row: dict[str, Any]) -> SandboxContainerExecutionPlan:
        def _p(v):
            if isinstance(v, datetime): return v
            if isinstance(v, str) and v:
                try: return datetime.fromisoformat(v.replace("Z", "+00:00"))
                except: return datetime.now(timezone.utc)
            return datetime.now(timezone.utc)
        return SandboxContainerExecutionPlan(
            container_plan_id=row.get("container_plan_id", ""),
            execution_plan_id=row.get("execution_plan_id", ""), job_id=row.get("job_id", ""),
            provider=row.get("provider", SandboxV2IsolationProvider.DOCKER_ROOTLESS_FUTURE),
            runtime=row.get("runtime", SandboxV2ContainerRuntime.UNAVAILABLE),
            image=row.get("image", ""), fixture_id=row.get("fixture_id", ""),
            command=json.loads(row.get("command_json", "[]")),
            env=json.loads(row.get("env_json", "{}")),
            network_mode=row.get("network_mode", "none"),
            readonly_rootfs=bool(row.get("readonly_rootfs", 1)), user=row.get("user", "65532:65532"),
            resource_limits=json.loads(row.get("resource_limits_json", "{}")),
            timeout_seconds=row.get("timeout_seconds", 30),
            status=row.get("status", "created"), reason=row.get("reason", ""),
            created_at=_p(row.get("created_at")),
            metadata=json.loads(row.get("metadata_json", "{}")),
        )

    @staticmethod
    def _row_to_container_result(row: dict[str, Any]) -> SandboxContainerExecutionResult:
        def _p(v):
            if v is None: return None
            if isinstance(v, datetime): return v
            if isinstance(v, str) and v:
                try: return datetime.fromisoformat(v.replace("Z", "+00:00"))
                except: return None
            return None
        return SandboxContainerExecutionResult(
            container_result_id=row.get("container_result_id", ""),
            container_plan_id=row.get("container_plan_id", ""),
            execution_plan_id=row.get("execution_plan_id", ""), job_id=row.get("job_id", ""),
            provider=row.get("provider", SandboxV2IsolationProvider.DOCKER_ROOTLESS_FUTURE),
            runtime=row.get("runtime", SandboxV2ContainerRuntime.UNAVAILABLE),
            status=row.get("status", "created"), exit_code=row.get("exit_code", -1),
            started_at=_p(row.get("started_at")), finished_at=_p(row.get("finished_at")),
            duration_ms=row.get("duration_ms", 0), stdout_text=row.get("stdout_text", ""),
            stderr_text=row.get("stderr_text", ""),
            stdout_artifact_id=row.get("stdout_artifact_id", ""),
            stderr_artifact_id=row.get("stderr_artifact_id", ""),
            timeout=bool(row.get("timeout", 0)), canceled=bool(row.get("canceled", 0)),
            reason=row.get("reason", ""), metadata=json.loads(row.get("metadata_json", "{}")),
        )

    # ═══════════════════════════════════════════
    # Step 7 — Kill Switch CRUD
    # ═══════════════════════════════════════════

    def create_kill_request(self, request: SandboxKillRequest) -> SandboxKillRequest:
        self._exec("""INSERT OR REPLACE INTO sandbox_v2_kill_requests (
            kill_request_id, job_id, execution_plan_id, container_plan_id,
            execution_record_id, queue_id, organization_id, workspace_id,
            requested_by, reason, scope, target_type, target_id, force,
            requested_at, status, policy_decision_id, metadata_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", [
            request.kill_request_id, request.job_id, request.execution_plan_id,
            request.container_plan_id, request.execution_record_id, request.queue_id,
            request.organization_id, request.workspace_id, request.requested_by,
            request.reason, request.scope, request.target_type, request.target_id,
            1 if request.force else 0, request.requested_at.isoformat(), request.status,
            request.policy_decision_id, json.dumps(request.metadata, ensure_ascii=False),
        ])
        return request

    def get_kill_request(self, kill_request_id: str) -> SandboxKillRequest | None:
        row = next(self._exec("SELECT * FROM sandbox_v2_kill_requests WHERE kill_request_id=?", [kill_request_id]), None)
        return self._row_to_kill_request(dict(row)) if row else None

    def list_kill_requests(self, job_id: str | None = None, status: str | None = None, limit: int = 50) -> list[SandboxKillRequest]:
        sql = "SELECT * FROM sandbox_v2_kill_requests WHERE 1=1"; params: list[Any] = []
        if job_id: sql += " AND job_id=?"; params.append(job_id)
        if status: sql += " AND status=?"; params.append(status)
        sql += " ORDER BY requested_at DESC LIMIT ?"; params.append(limit)
        return [self._row_to_kill_request(dict(r)) for r in self._exec(sql, params)]

    def update_kill_request_status(self, kill_request_id: str, status: str, reason: str = "") -> SandboxKillRequest | None:
        existing = self.get_kill_request(kill_request_id)
        if existing is None: return None
        self._exec("UPDATE sandbox_v2_kill_requests SET status=?, reason=? WHERE kill_request_id=?",
                   [status, reason or existing.reason, kill_request_id])
        self._db.conn.commit()
        return self.get_kill_request(kill_request_id)

    def create_kill_record(self, record: SandboxKillRecord) -> SandboxKillRecord:
        self._exec("""INSERT OR REPLACE INTO sandbox_v2_kill_records (
            kill_record_id, kill_request_id, job_id, execution_plan_id,
            container_plan_id, provider, target_type, target_id, action_taken,
            status_before, status_after, provider_result, error_code, error_message,
            created_at, metadata_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", [
            record.kill_record_id, record.kill_request_id, record.job_id,
            record.execution_plan_id, record.container_plan_id, record.provider,
            record.target_type, record.target_id, record.action_taken,
            record.status_before, record.status_after, record.provider_result,
            record.error_code, record.error_message, record.created_at.isoformat(),
            json.dumps(record.metadata, ensure_ascii=False),
        ])
        return record

    def get_kill_record(self, kill_record_id: str) -> SandboxKillRecord | None:
        row = next(self._exec("SELECT * FROM sandbox_v2_kill_records WHERE kill_record_id=?", [kill_record_id]), None)
        return self._row_to_kill_record(dict(row)) if row else None

    def list_kill_records(self, job_id: str | None = None, kill_request_id: str | None = None, limit: int = 50) -> list[SandboxKillRecord]:
        sql = "SELECT * FROM sandbox_v2_kill_records WHERE 1=1"; params: list[Any] = []
        if job_id: sql += " AND job_id=?"; params.append(job_id)
        if kill_request_id: sql += " AND kill_request_id=?"; params.append(kill_request_id)
        sql += " ORDER BY created_at DESC LIMIT ?"; params.append(limit)
        return [self._row_to_kill_record(dict(r)) for r in self._exec(sql, params)]

    def create_active_execution_handle(self, handle: SandboxActiveExecutionHandle) -> SandboxActiveExecutionHandle:
        self._exec("""INSERT OR REPLACE INTO sandbox_v2_active_execution_handles (
            handle_id, job_id, execution_plan_id, container_plan_id,
            execution_record_id, provider, target_type, target_id, status,
            started_at, last_seen_at, timeout_at, cancel_requested, cancel_reason, metadata_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", [
            handle.handle_id, handle.job_id, handle.execution_plan_id,
            handle.container_plan_id, handle.execution_record_id, handle.provider,
            handle.target_type, handle.target_id, handle.status,
            handle.started_at.isoformat(), handle.last_seen_at.isoformat(),
            handle.timeout_at.isoformat() if handle.timeout_at else None,
            1 if handle.cancel_requested else 0, handle.cancel_reason,
            json.dumps(handle.metadata, ensure_ascii=False),
        ])
        return handle

    def get_active_execution_handle(self, handle_id: str) -> SandboxActiveExecutionHandle | None:
        row = next(self._exec("SELECT * FROM sandbox_v2_active_execution_handles WHERE handle_id=?", [handle_id]), None)
        return self._row_to_active_handle(dict(row)) if row else None

    def get_active_execution_handle_for_job(self, job_id: str) -> SandboxActiveExecutionHandle | None:
        row = next(self._exec("SELECT * FROM sandbox_v2_active_execution_handles WHERE job_id=? ORDER BY started_at DESC LIMIT 1", [job_id]), None)
        return self._row_to_active_handle(dict(row)) if row else None

    def list_active_execution_handles(self, status: str | None = None, limit: int = 50) -> list[SandboxActiveExecutionHandle]:
        sql = "SELECT * FROM sandbox_v2_active_execution_handles WHERE 1=1"; params: list[Any] = []
        if status: sql += " AND status=?"; params.append(status)
        sql += " ORDER BY started_at DESC LIMIT ?"; params.append(limit)
        return [self._row_to_active_handle(dict(r)) for r in self._exec(sql, params)]

    def update_active_execution_handle_status(self, handle_id: str, status: str, reason: str = "") -> SandboxActiveExecutionHandle | None:
        existing = self.get_active_execution_handle(handle_id)
        if existing is None: return None
        self._exec("UPDATE sandbox_v2_active_execution_handles SET status=?, last_seen_at=?, cancel_reason=? WHERE handle_id=?",
                   [status, datetime.now(timezone.utc).isoformat(), reason or existing.cancel_reason, handle_id])
        self._db.conn.commit()
        return self.get_active_execution_handle(handle_id)

    def mark_active_execution_cancel_requested(self, handle_id: str, reason: str) -> SandboxActiveExecutionHandle | None:
        existing = self.get_active_execution_handle(handle_id)
        if existing is None: return None
        self._exec("UPDATE sandbox_v2_active_execution_handles SET status=?, cancel_requested=1, cancel_reason=?, last_seen_at=? WHERE handle_id=?",
                   [SandboxV2ActiveExecutionStatus.CANCEL_REQUESTED, reason, datetime.now(timezone.utc).isoformat(), handle_id])
        self._db.conn.commit()
        return self.get_active_execution_handle(handle_id)

    @staticmethod
    def _row_to_kill_request(row: dict[str, Any]) -> SandboxKillRequest:
        def _p(v):
            if isinstance(v, datetime): return v
            if isinstance(v, str) and v:
                try: return datetime.fromisoformat(v.replace("Z", "+00:00"))
                except: return datetime.now(timezone.utc)
            return datetime.now(timezone.utc)
        return SandboxKillRequest(
            kill_request_id=row.get("kill_request_id", ""), job_id=row.get("job_id", ""),
            execution_plan_id=row.get("execution_plan_id", ""), container_plan_id=row.get("container_plan_id", ""),
            execution_record_id=row.get("execution_record_id", ""), queue_id=row.get("queue_id", ""),
            organization_id=row.get("organization_id", ""), workspace_id=row.get("workspace_id", ""),
            requested_by=row.get("requested_by", ""), reason=row.get("reason", ""),
            scope=row.get("scope", "job"), target_type=row.get("target_type", "job"),
            target_id=row.get("target_id", ""), force=bool(row.get("force", 0)),
            requested_at=_p(row.get("requested_at")), status=row.get("status", "requested"),
            policy_decision_id=row.get("policy_decision_id", ""),
            metadata=json.loads(row.get("metadata_json", "{}")),
        )

    @staticmethod
    def _row_to_kill_record(row: dict[str, Any]) -> SandboxKillRecord:
        def _p(v):
            if isinstance(v, datetime): return v
            if isinstance(v, str) and v:
                try: return datetime.fromisoformat(v.replace("Z", "+00:00"))
                except: return datetime.now(timezone.utc)
            return datetime.now(timezone.utc)
        return SandboxKillRecord(
            kill_record_id=row.get("kill_record_id", ""), kill_request_id=row.get("kill_request_id", ""),
            job_id=row.get("job_id", ""), execution_plan_id=row.get("execution_plan_id", ""),
            container_plan_id=row.get("container_plan_id", ""), provider=row.get("provider", ""),
            target_type=row.get("target_type", "unknown"), target_id=row.get("target_id", ""),
            action_taken=row.get("action_taken", "reject"), status_before=row.get("status_before", ""),
            status_after=row.get("status_after", ""), provider_result=row.get("provider_result", ""),
            error_code=row.get("error_code", ""), error_message=row.get("error_message", ""),
            created_at=_p(row.get("created_at")), metadata=json.loads(row.get("metadata_json", "{}")),
        )

    @staticmethod
    def _row_to_active_handle(row: dict[str, Any]) -> SandboxActiveExecutionHandle:
        def _p(v):
            if v is None: return None
            if isinstance(v, datetime): return v
            if isinstance(v, str) and v:
                try: return datetime.fromisoformat(v.replace("Z", "+00:00"))
                except: return None
            return None
        return SandboxActiveExecutionHandle(
            handle_id=row.get("handle_id", ""), job_id=row.get("job_id", ""),
            execution_plan_id=row.get("execution_plan_id", ""), container_plan_id=row.get("container_plan_id", ""),
            execution_record_id=row.get("execution_record_id", ""), provider=row.get("provider", ""),
            target_type=row.get("target_type", "unknown"), target_id=row.get("target_id", ""),
            status=row.get("status", "active"),
            started_at=_p(row.get("started_at")) or datetime.now(timezone.utc),
            last_seen_at=_p(row.get("last_seen_at")) or datetime.now(timezone.utc),
            timeout_at=_p(row.get("timeout_at")),
            cancel_requested=bool(row.get("cancel_requested", 0)),
            cancel_reason=row.get("cancel_reason", ""),
            metadata=json.loads(row.get("metadata_json", "{}")),
        )

    @staticmethod
    def _row_to_scan(row: dict[str, Any]) -> SandboxPackageVulnerabilityScanResult:
        def _p(v):
            if isinstance(v, datetime): return v
            if isinstance(v, str) and v:
                try: return datetime.fromisoformat(v.replace("Z", "+00:00"))
                except: return datetime.now(timezone.utc)
            return datetime.now(timezone.utc)
        return SandboxPackageVulnerabilityScanResult(
            scan_id=row.get("scan_id", ""), package_request_id=row.get("package_request_id", ""),
            package_name=row.get("package_name", ""), package_version=row.get("package_version", ""),
            scanner=row.get("scanner", "sbom_fixture_scanner"), status=row.get("status", "not_scanned"),
            severity_summary=row.get("severity_summary", ""),
            critical_count=row.get("critical_count", 0), high_count=row.get("high_count", 0),
            medium_count=row.get("medium_count", 0), low_count=row.get("low_count", 0),
            findings=json.loads(row.get("findings_json", "[]")),
            created_at=_p(row.get("created_at")),
            metadata=json.loads(row.get("metadata_json", "{}")),
        )

    # ═══════════════════════════════════════════
    # Step 11 — MicroVM Execution Plans & Results
    # ═══════════════════════════════════════════

    def create_microvm_execution_plan(self, plan: Any) -> Any:
        from src.open_platform.sandbox_v2.models import SandboxMicroVMExecutionPlan
        self._exec("""INSERT OR REPLACE INTO sandbox_v2_microvm_execution_plans (
            microvm_plan_id, execution_plan_id, job_id, organization_id, workspace_id,
            runtime, fixture_id, kernel_ref, rootfs_ref, image_ref, network_enabled,
            memory_mb, vcpu_count, timeout_seconds, status, reason, created_at, metadata_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", [
            plan.microvm_plan_id, plan.execution_plan_id, plan.job_id,
            plan.organization_id, plan.workspace_id, plan.runtime, plan.fixture_id,
            plan.kernel_ref, plan.rootfs_ref, plan.image_ref,
            1 if plan.network_enabled else 0, plan.memory_mb, plan.vcpu_count,
            plan.timeout_seconds, plan.status, plan.reason,
            plan.created_at.isoformat() if hasattr(plan.created_at, 'isoformat') else str(plan.created_at),
            json.dumps(plan.metadata, ensure_ascii=False),
        ])
        self._db.conn.commit()
        return plan

    def get_microvm_execution_plan(self, microvm_plan_id: str) -> Any | None:
        from src.open_platform.sandbox_v2.models import SandboxMicroVMExecutionPlan
        row = next(self._exec("SELECT * FROM sandbox_v2_microvm_execution_plans WHERE microvm_plan_id=?", [microvm_plan_id]), None)
        return self._row_to_microvm_plan(dict(row)) if row else None

    def list_microvm_execution_plans(self, job_id: str | None = None, status: str | None = None, limit: int = 50) -> list[Any]:
        sql = "SELECT * FROM sandbox_v2_microvm_execution_plans WHERE 1=1"
        params: list[Any] = []
        if job_id: sql += " AND job_id=?"; params.append(job_id)
        if status: sql += " AND status=?"; params.append(status)
        sql += " ORDER BY created_at DESC LIMIT ?"; params.append(limit)
        return [self._row_to_microvm_plan(dict(r)) for r in self._exec(sql, params)]

    def update_microvm_execution_plan_status(self, microvm_plan_id: str, status: str, reason: str = "") -> Any | None:
        existing = self.get_microvm_execution_plan(microvm_plan_id)
        if existing is None: return None
        self._exec("UPDATE sandbox_v2_microvm_execution_plans SET status=?, reason=?, metadata_json=? WHERE microvm_plan_id=?",
                   [status, reason or existing.reason,
                    json.dumps(getattr(existing, 'metadata', {}) or {}, ensure_ascii=False),
                    microvm_plan_id])
        self._db.conn.commit()
        return self.get_microvm_execution_plan(microvm_plan_id)

    def create_microvm_execution_result(self, result: Any) -> Any:
        from src.open_platform.sandbox_v2.models import SandboxMicroVMExecutionResult
        self._exec("""INSERT OR REPLACE INTO sandbox_v2_microvm_execution_results (
            microvm_result_id, microvm_plan_id, execution_plan_id, job_id, runtime,
            status, exit_code, started_at, finished_at, duration_ms,
            stdout_text, stderr_text, stdout_artifact_id, stderr_artifact_id,
            timeout, canceled, reason, metadata_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", [
            result.microvm_result_id, result.microvm_plan_id, result.execution_plan_id,
            result.job_id, result.runtime, result.status, result.exit_code,
            result.started_at.isoformat() if result.started_at else None,
            result.finished_at.isoformat() if result.finished_at else None,
            result.duration_ms, result.stdout_text, result.stderr_text,
            result.stdout_artifact_id, result.stderr_artifact_id,
            1 if result.timeout else 0, 1 if result.canceled else 0,
            result.reason, json.dumps(result.metadata, ensure_ascii=False),
        ])
        self._db.conn.commit()
        return result

    def get_microvm_execution_result(self, microvm_result_id: str) -> Any | None:
        from src.open_platform.sandbox_v2.models import SandboxMicroVMExecutionResult
        row = next(self._exec("SELECT * FROM sandbox_v2_microvm_execution_results WHERE microvm_result_id=?", [microvm_result_id]), None)
        return self._row_to_microvm_result(dict(row)) if row else None

    def list_microvm_execution_results(self, job_id: str | None = None, microvm_plan_id: str | None = None, limit: int = 50) -> list[Any]:
        sql = "SELECT * FROM sandbox_v2_microvm_execution_results WHERE 1=1"
        params: list[Any] = []
        if job_id: sql += " AND job_id=?"; params.append(job_id)
        if microvm_plan_id: sql += " AND microvm_plan_id=?"; params.append(microvm_plan_id)
        sql += " ORDER BY COALESCE(started_at, '') DESC LIMIT ?"; params.append(limit)
        return [self._row_to_microvm_result(dict(r)) for r in self._exec(sql, params)]

    @staticmethod
    def _row_to_microvm_plan(row: dict[str, Any]) -> Any:
        from src.open_platform.sandbox_v2.models import SandboxMicroVMExecutionPlan
        def _p(v):
            if isinstance(v, str) and v:
                try: return datetime.fromisoformat(v.replace("Z", "+00:00"))
                except: pass
            return datetime.now(timezone.utc)
        return SandboxMicroVMExecutionPlan(
            microvm_plan_id=row.get("microvm_plan_id", ""),
            execution_plan_id=row.get("execution_plan_id", ""),
            job_id=row.get("job_id", ""),
            organization_id=row.get("organization_id", ""),
            workspace_id=row.get("workspace_id", ""),
            runtime=row.get("runtime", "unavailable"),
            fixture_id=row.get("fixture_id", ""),
            kernel_ref=row.get("kernel_ref", ""),
            rootfs_ref=row.get("rootfs_ref", ""),
            image_ref=row.get("image_ref", ""),
            network_enabled=bool(row.get("network_enabled", 0)),
            memory_mb=row.get("memory_mb", 128),
            vcpu_count=row.get("vcpu_count", 1),
            timeout_seconds=row.get("timeout_seconds", 10),
            status=row.get("status", "created"),
            reason=row.get("reason", ""),
            created_at=_p(row.get("created_at")),
            metadata=json.loads(row.get("metadata_json", "{}")),
        )

    @staticmethod
    def _row_to_microvm_result(row: dict[str, Any]) -> Any:
        from src.open_platform.sandbox_v2.models import SandboxMicroVMExecutionResult
        def _p(v):
            if v is None: return None
            if isinstance(v, str) and v:
                try: return datetime.fromisoformat(v.replace("Z", "+00:00"))
                except: pass
            return None
        return SandboxMicroVMExecutionResult(
            microvm_result_id=row.get("microvm_result_id", ""),
            microvm_plan_id=row.get("microvm_plan_id", ""),
            execution_plan_id=row.get("execution_plan_id", ""),
            job_id=row.get("job_id", ""),
            runtime=row.get("runtime", "unavailable"),
            status=row.get("status", "unavailable"),
            exit_code=row.get("exit_code", -1),
            started_at=_p(row.get("started_at")),
            finished_at=_p(row.get("finished_at")),
            duration_ms=row.get("duration_ms", 0),
            stdout_text=row.get("stdout_text", ""),
            stderr_text=row.get("stderr_text", ""),
            stdout_artifact_id=row.get("stdout_artifact_id", ""),
            stderr_artifact_id=row.get("stderr_artifact_id", ""),
            timeout=bool(row.get("timeout", 0)),
            canceled=bool(row.get("canceled", 0)),
            reason=row.get("reason", ""),
            metadata=json.loads(row.get("metadata_json", "{}")),
        )

    # ═══════════════════════════════════════════
    # Step 14 — Security Audit / Evidence / Access Decisions
    # ═══════════════════════════════════════════

    def create_security_audit_event(self, event: Any) -> Any:
        self._exec("""INSERT OR REPLACE INTO sandbox_v2_security_audit_events (
            audit_event_id, event_type, severity, principal_id, principal_type,
            organization_id, workspace_id, resource_type, resource_id,
            action, decision, reason, request_id, previous_hash, event_hash,
            created_at, metadata_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", [
            event.audit_event_id, event.event_type, event.severity,
            event.principal_id, event.principal_type,
            event.organization_id, event.workspace_id,
            event.resource_type, event.resource_id,
            event.action, event.decision, event.reason,
            event.request_id, event.previous_hash, event.event_hash,
            event.created_at.isoformat() if hasattr(event.created_at, 'isoformat') else str(event.created_at),
            json.dumps(event.metadata, ensure_ascii=False),
        ])
        self._db.conn.commit()
        return event

    def get_security_audit_event(self, audit_event_id: str) -> Any | None:
        row = next(self._exec("SELECT * FROM sandbox_v2_security_audit_events WHERE audit_event_id=?", [audit_event_id]), None)
        return self._row_to_audit_event(dict(row)) if row else None

    def get_latest_security_audit_event(self, organization_id: str | None = None, workspace_id: str | None = None) -> Any | None:
        sql = "SELECT * FROM sandbox_v2_security_audit_events WHERE 1=1"
        params: list[Any] = []
        if organization_id: sql += " AND organization_id=?"; params.append(organization_id)
        if workspace_id: sql += " AND workspace_id=?"; params.append(workspace_id)
        sql += " ORDER BY created_at DESC LIMIT 1"
        row = next(self._exec(sql, params), None)
        return self._row_to_audit_event(dict(row)) if row else None

    def list_security_audit_events(self, organization_id: str | None = None, workspace_id: str | None = None,
                                    event_type: str | None = None, severity: str | None = None,
                                    limit: int = 50) -> list[Any]:
        sql = "SELECT * FROM sandbox_v2_security_audit_events WHERE 1=1"
        params: list[Any] = []
        if organization_id: sql += " AND organization_id=?"; params.append(organization_id)
        if workspace_id: sql += " AND workspace_id=?"; params.append(workspace_id)
        if event_type: sql += " AND event_type=?"; params.append(event_type)
        if severity: sql += " AND severity=?"; params.append(severity)
        sql += " ORDER BY created_at DESC LIMIT ?"; params.append(limit)
        return [self._row_to_audit_event(dict(r)) for r in self._exec(sql, params)]

    def create_evidence_bundle(self, bundle: Any) -> Any:
        self._exec("""INSERT OR REPLACE INTO sandbox_v2_evidence_bundles (
            evidence_bundle_id, organization_id, workspace_id, created_by,
            title, description, resource_refs_json, audit_event_ids_json,
            job_ids_json, artifact_ids_json, package_request_ids_json,
            network_request_ids_json, kill_request_ids_json,
            created_at, bundle_hash, redacted, metadata_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", [
            bundle.evidence_bundle_id, bundle.organization_id, bundle.workspace_id,
            bundle.created_by, bundle.title, bundle.description,
            json.dumps(bundle.resource_refs, ensure_ascii=False),
            json.dumps(bundle.audit_event_ids, ensure_ascii=False),
            json.dumps(bundle.job_ids, ensure_ascii=False),
            json.dumps(bundle.artifact_ids, ensure_ascii=False),
            json.dumps(bundle.package_request_ids, ensure_ascii=False),
            json.dumps(bundle.network_request_ids, ensure_ascii=False),
            json.dumps(bundle.kill_request_ids, ensure_ascii=False),
            bundle.created_at.isoformat() if hasattr(bundle.created_at, 'isoformat') else str(bundle.created_at),
            bundle.bundle_hash, 1 if bundle.redacted else 0,
            json.dumps(bundle.metadata, ensure_ascii=False),
        ])
        self._db.conn.commit()
        return bundle

    def get_evidence_bundle(self, evidence_bundle_id: str) -> Any | None:
        row = next(self._exec("SELECT * FROM sandbox_v2_evidence_bundles WHERE evidence_bundle_id=?", [evidence_bundle_id]), None)
        return self._row_to_evidence_bundle(dict(row)) if row else None

    def list_evidence_bundles(self, organization_id: str | None = None, workspace_id: str | None = None,
                               limit: int = 50) -> list[Any]:
        sql = "SELECT * FROM sandbox_v2_evidence_bundles WHERE 1=1"
        params: list[Any] = []
        if organization_id: sql += " AND organization_id=?"; params.append(organization_id)
        if workspace_id: sql += " AND workspace_id=?"; params.append(workspace_id)
        sql += " ORDER BY created_at DESC LIMIT ?"; params.append(limit)
        return [self._row_to_evidence_bundle(dict(r)) for r in self._exec(sql, params)]

    def create_access_decision_record(self, decision: Any) -> Any:
        aid = getattr(decision, 'access_decision_id', f"ad_{__import__('uuid').uuid4().hex[:16]}")
        self._exec("""INSERT OR REPLACE INTO sandbox_v2_access_decisions (
            access_decision_id, allowed, action, reason, risk_level,
            principal_id, principal_type, resource_type, resource_id,
            permission_action, organization_match, workspace_match,
            role_allowed, scope_allowed, cross_tenant, fail_closed,
            matched_rules_json, created_at, metadata_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", [
            aid, 1 if decision.allowed else 0, decision.action, decision.reason,
            decision.risk_level, decision.principal_id, decision.principal_type,
            decision.resource_type, decision.resource_id, decision.permission_action,
            1 if decision.organization_match else 0, 1 if decision.workspace_match else 0,
            1 if decision.role_allowed else 0, 1 if decision.scope_allowed else 0,
            1 if decision.cross_tenant else 0, 1 if decision.fail_closed else 0,
            json.dumps(decision.matched_rules, ensure_ascii=False),
            decision.created_at.isoformat() if hasattr(decision.created_at, 'isoformat') else str(decision.created_at),
            json.dumps(decision.metadata, ensure_ascii=False),
        ])
        self._db.conn.commit()
        return decision

    def list_access_decision_records(self, organization_id: str | None = None, workspace_id: str | None = None,
                                      limit: int = 50) -> list[Any]:
        sql = "SELECT * FROM sandbox_v2_access_decisions WHERE 1=1"
        params: list[Any] = []
        sql += " ORDER BY created_at DESC LIMIT ?"; params.append(limit)
        return [dict(r) for r in self._exec(sql, params)]

    @staticmethod
    def _row_to_audit_event(row: dict[str, Any]) -> Any:
        from src.open_platform.sandbox_v2.models import SandboxV2AuditEvent
        def _p(v):
            if isinstance(v, str) and v:
                try: return datetime.fromisoformat(v.replace("Z", "+00:00"))
                except: pass
            return datetime.now(timezone.utc)
        return SandboxV2AuditEvent(
            audit_event_id=row.get("audit_event_id", ""), event_type=row.get("event_type", ""),
            severity=row.get("severity", "info"), principal_id=row.get("principal_id", ""),
            principal_type=row.get("principal_type", ""),
            organization_id=row.get("organization_id", ""), workspace_id=row.get("workspace_id", ""),
            resource_type=row.get("resource_type", ""), resource_id=row.get("resource_id", ""),
            action=row.get("action", ""), decision=row.get("decision", ""),
            reason=row.get("reason", ""), request_id=row.get("request_id", ""),
            previous_hash=row.get("previous_hash", ""), event_hash=row.get("event_hash", ""),
            created_at=_p(row.get("created_at")),
            metadata=json.loads(row.get("metadata_json", "{}")),
        )

    @staticmethod
    def _row_to_evidence_bundle(row: dict[str, Any]) -> Any:
        from src.open_platform.sandbox_v2.models import SandboxV2EvidenceBundle
        def _p(v):
            if isinstance(v, str) and v:
                try: return datetime.fromisoformat(v.replace("Z", "+00:00"))
                except: pass
            return datetime.now(timezone.utc)
        return SandboxV2EvidenceBundle(
            evidence_bundle_id=row.get("evidence_bundle_id", ""),
            organization_id=row.get("organization_id", ""), workspace_id=row.get("workspace_id", ""),
            created_by=row.get("created_by", ""), title=row.get("title", ""),
            description=row.get("description", ""),
            resource_refs=json.loads(row.get("resource_refs_json", "[]")),
            audit_event_ids=json.loads(row.get("audit_event_ids_json", "[]")),
            job_ids=json.loads(row.get("job_ids_json", "[]")),
            artifact_ids=json.loads(row.get("artifact_ids_json", "[]")),
            package_request_ids=json.loads(row.get("package_request_ids_json", "[]")),
            network_request_ids=json.loads(row.get("network_request_ids_json", "[]")),
            kill_request_ids=json.loads(row.get("kill_request_ids_json", "[]")),
            created_at=_p(row.get("created_at")), bundle_hash=row.get("bundle_hash", ""),
            redacted=bool(row.get("redacted", 1)), metadata=json.loads(row.get("metadata_json", "{}")),
        )

    # ═══════════════════════════════════════════
    # Step 15 — Monitoring / Metrics / Alerts / Health
    # ═══════════════════════════════════════════

    def create_metric_sample(self, sample: Any) -> Any:
        self._exec("""INSERT OR REPLACE INTO sandbox_v2_metric_samples (
            metric_id, name, metric_type, value, labels_json,
            organization_id, workspace_id, collected_at, metadata_json
        ) VALUES (?,?,?,?,?,?,?,?,?)""", [
            sample.metric_id, sample.name, sample.metric_type, sample.value,
            json.dumps(getattr(sample, 'labels', {}) or {}, ensure_ascii=False),
            sample.organization_id, sample.workspace_id,
            sample.collected_at.isoformat() if hasattr(sample.collected_at, 'isoformat') else str(sample.collected_at),
            json.dumps(getattr(sample, 'metadata', {}) or {}, ensure_ascii=False),
        ])
        self._db.conn.commit()
        return sample

    def list_metric_samples(self, name: str | None = None, organization_id: str | None = None,
                             workspace_id: str | None = None, limit: int = 100) -> list[Any]:
        sql = "SELECT * FROM sandbox_v2_metric_samples WHERE 1=1"; params = []
        if name: sql += " AND name=?"; params.append(name)
        if organization_id: sql += " AND organization_id=?"; params.append(organization_id)
        if workspace_id: sql += " AND workspace_id=?"; params.append(workspace_id)
        sql += " ORDER BY collected_at DESC LIMIT ?"; params.append(limit)
        return [dict(r) for r in self._exec(sql, params)]

    def create_metrics_snapshot(self, snapshot: Any) -> Any:
        self._exec("""INSERT OR REPLACE INTO sandbox_v2_metrics_snapshots (
            snapshot_id, organization_id, workspace_id, generated_at,
            counters_json, gauges_json, health_json, warnings_json, blockers_json, metadata_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?)""", [
            snapshot.snapshot_id, snapshot.organization_id, snapshot.workspace_id,
            snapshot.generated_at.isoformat() if hasattr(snapshot.generated_at, 'isoformat') else str(snapshot.generated_at),
            json.dumps(getattr(snapshot, 'counters', {}) or {}, ensure_ascii=False),
            json.dumps(getattr(snapshot, 'gauges', {}) or {}, ensure_ascii=False),
            json.dumps(getattr(snapshot, 'health', {}) or {}, ensure_ascii=False),
            json.dumps(getattr(snapshot, 'warnings', []) or [], ensure_ascii=False),
            json.dumps(getattr(snapshot, 'blockers', []) or [], ensure_ascii=False),
            json.dumps(getattr(snapshot, 'metadata', {}) or {}, ensure_ascii=False),
        ])
        self._db.conn.commit()
        return snapshot

    def get_latest_metrics_snapshot(self, organization_id: str | None = None, workspace_id: str | None = None) -> Any | None:
        sql = "SELECT * FROM sandbox_v2_metrics_snapshots WHERE 1=1"; params = []
        if organization_id: sql += " AND organization_id=?"; params.append(organization_id)
        if workspace_id: sql += " AND workspace_id=?"; params.append(workspace_id)
        sql += " ORDER BY generated_at DESC LIMIT 1"
        row = next(self._exec(sql, params), None)
        return dict(row) if row else None

    def list_metrics_snapshots(self, organization_id: str | None = None, workspace_id: str | None = None, limit: int = 20) -> list[Any]:
        sql = "SELECT * FROM sandbox_v2_metrics_snapshots WHERE 1=1"; params = []
        if organization_id: sql += " AND organization_id=?"; params.append(organization_id)
        if workspace_id: sql += " AND workspace_id=?"; params.append(workspace_id)
        sql += " ORDER BY generated_at DESC LIMIT ?"; params.append(limit)
        return [dict(r) for r in self._exec(sql, params)]

    def create_alert_rule(self, rule: Any) -> Any:
        self._exec("""INSERT OR REPLACE INTO sandbox_v2_alert_rules (
            alert_rule_id, name, description, rule_type, metric_name, threshold,
            comparison, severity, enabled, organization_id, workspace_id, created_at, metadata_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""", [
            rule.alert_rule_id, rule.name, getattr(rule, 'description', ''),
            getattr(rule, 'rule_type', 'threshold'), getattr(rule, 'metric_name', ''),
            getattr(rule, 'threshold', 0.0), getattr(rule, 'comparison', 'gt'),
            getattr(rule, 'severity', 'warning'), 1 if getattr(rule, 'enabled', True) else 0,
            rule.organization_id, rule.workspace_id,
            rule.created_at.isoformat() if hasattr(rule.created_at, 'isoformat') else str(rule.created_at),
            json.dumps(getattr(rule, 'metadata', {}) or {}, ensure_ascii=False),
        ])
        self._db.conn.commit()
        return rule

    def list_alert_rules(self, organization_id: str | None = None, workspace_id: str | None = None,
                          enabled: bool | None = None, limit: int = 100) -> list[Any]:
        sql = "SELECT * FROM sandbox_v2_alert_rules WHERE 1=1"; params = []
        if organization_id: sql += " AND organization_id=?"; params.append(organization_id)
        if workspace_id: sql += " AND workspace_id=?"; params.append(workspace_id)
        if enabled is not None: sql += " AND enabled=?"; params.append(1 if enabled else 0)
        sql += " ORDER BY created_at DESC LIMIT ?"; params.append(limit)
        return [dict(r) for r in self._exec(sql, params)]

    def create_alert(self, alert: Any) -> Any:
        self._exec("""INSERT OR REPLACE INTO sandbox_v2_alerts (
            alert_id, alert_rule_id, name, severity, status,
            organization_id, workspace_id, resource_type, resource_id,
            reason, observed_value, threshold, first_seen_at, last_seen_at,
            resolved_at, acknowledged_by, metadata_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", [
            alert.alert_id, alert.alert_rule_id, alert.name, alert.severity, alert.status,
            alert.organization_id, alert.workspace_id,
            alert.resource_type, alert.resource_id, alert.reason,
            alert.observed_value, alert.threshold,
            alert.first_seen_at.isoformat() if hasattr(alert.first_seen_at, 'isoformat') else str(alert.first_seen_at),
            alert.last_seen_at.isoformat() if hasattr(alert.last_seen_at, 'isoformat') else str(alert.last_seen_at),
            alert.resolved_at.isoformat() if alert.resolved_at and hasattr(alert.resolved_at, 'isoformat') else None,
            alert.acknowledged_by,
            json.dumps(getattr(alert, 'metadata', {}) or {}, ensure_ascii=False),
        ])
        self._db.conn.commit()
        return alert

    def get_alert(self, alert_id: str) -> Any | None:
        row = next(self._exec("SELECT * FROM sandbox_v2_alerts WHERE alert_id=?", [alert_id]), None)
        return dict(row) if row else None

    def list_alerts(self, status: str | None = None, severity: str | None = None,
                     organization_id: str | None = None, workspace_id: str | None = None,
                     limit: int = 100) -> list[Any]:
        sql = "SELECT * FROM sandbox_v2_alerts WHERE 1=1"; params = []
        if status: sql += " AND status=?"; params.append(status)
        if severity: sql += " AND severity=?"; params.append(severity)
        if organization_id: sql += " AND organization_id=?"; params.append(organization_id)
        if workspace_id: sql += " AND workspace_id=?"; params.append(workspace_id)
        sql += " ORDER BY last_seen_at DESC LIMIT ?"; params.append(limit)
        return [dict(r) for r in self._exec(sql, params)]

    def update_alert_status(self, alert_id: str, status: str, reason: str = "", actor: str = "") -> Any | None:
        import time
        sql = "UPDATE sandbox_v2_alerts SET status=?, acknowledged_by=? WHERE alert_id=?"
        self._exec(sql, [status, actor, alert_id])
        if status == "resolved":
            self._exec("UPDATE sandbox_v2_alerts SET resolved_at=datetime('now') WHERE alert_id=?", [alert_id])
        self._db.conn.commit()
        row = next(self._exec("SELECT * FROM sandbox_v2_alerts WHERE alert_id=?", [alert_id]), None)
        return dict(row) if row else None

    def create_health_check_result(self, result: Any) -> Any:
        self._exec("""INSERT OR REPLACE INTO sandbox_v2_health_check_results (
            health_check_id, component, status, ready, reason, latency_ms, checked_at,
            warnings_json, blockers_json, metadata_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?)""", [
            result.health_check_id, result.component, result.status,
            1 if result.ready else 0, result.reason, result.latency_ms,
            result.checked_at.isoformat() if hasattr(result.checked_at, 'isoformat') else str(result.checked_at),
            json.dumps(result.warnings or [], ensure_ascii=False),
            json.dumps(result.blockers or [], ensure_ascii=False),
            json.dumps(result.metadata or {}, ensure_ascii=False),
        ])
        self._db.conn.commit()
        return result

    def list_health_check_results(self, component: str | None = None, limit: int = 100) -> list[Any]:
        sql = "SELECT * FROM sandbox_v2_health_check_results WHERE 1=1"; params = []
        if component: sql += " AND component=?"; params.append(component)
        sql += " ORDER BY checked_at DESC LIMIT ?"; params.append(limit)
        return [dict(r) for r in self._exec(sql, params)]

    def get_latest_health_check_results(self) -> list[Any]:
        return self.list_health_check_results(limit=100)

    # ═══════════════════════════════════════════
    # Step 16 — Performance / Capacity
    # ═══════════════════════════════════════════

    def create_benchmark_config(self, config: SandboxV2BenchmarkConfig) -> SandboxV2BenchmarkConfig:
        self._exec("""INSERT OR REPLACE INTO sandbox_v2_benchmark_configs (
            benchmark_id, profile, targets_json, max_jobs, max_queue_items,
            max_artifacts, max_concurrency, timeout_seconds, cleanup_after_run,
            organization_id, workspace_id, created_at, metadata_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""", [
            config.benchmark_id, config.profile,
            json.dumps(config.targets or [], ensure_ascii=False),
            config.max_jobs, config.max_queue_items, config.max_artifacts,
            config.max_concurrency, config.timeout_seconds,
            1 if config.cleanup_after_run else 0,
            config.organization_id, config.workspace_id,
            config.created_at.isoformat() if hasattr(config.created_at, 'isoformat') else str(config.created_at),
            json.dumps(config.metadata or {}, ensure_ascii=False),
        ])
        self._db.conn.commit()
        return config

    def get_benchmark_config(self, benchmark_id: str) -> SandboxV2BenchmarkConfig | None:
        row = next(self._exec(
            "SELECT * FROM sandbox_v2_benchmark_configs WHERE benchmark_id=?", [benchmark_id]), None)
        return self._row_to_benchmark_config(dict(row)) if row else None

    def list_benchmark_configs(self, limit: int = 50) -> list[SandboxV2BenchmarkConfig]:
        rows = self._exec(
            "SELECT * FROM sandbox_v2_benchmark_configs ORDER BY created_at DESC LIMIT ?",
            [min(max(int(limit or 50), 1), 200)],
        )
        return [self._row_to_benchmark_config(dict(r)) for r in rows]

    def create_benchmark_result(self, result: SandboxV2BenchmarkResult) -> SandboxV2BenchmarkResult:
        self._exec("""INSERT OR REPLACE INTO sandbox_v2_benchmark_results (
            benchmark_result_id, benchmark_id, target, status, started_at, finished_at,
            duration_ms, total_operations, success_count, failure_count,
            p50_ms, p95_ms, p99_ms, ops_per_second,
            warnings_json, blockers_json, metadata_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", [
            result.benchmark_result_id, result.benchmark_id, result.target, result.status,
            result.started_at.isoformat() if hasattr(result.started_at, 'isoformat') else str(result.started_at),
            result.finished_at.isoformat() if result.finished_at and hasattr(result.finished_at, 'isoformat') else None,
            result.duration_ms, result.total_operations, result.success_count, result.failure_count,
            result.p50_ms, result.p95_ms, result.p99_ms, result.ops_per_second,
            json.dumps(result.warnings or [], ensure_ascii=False),
            json.dumps(result.blockers or [], ensure_ascii=False),
            json.dumps(result.metadata or {}, ensure_ascii=False),
        ])
        self._db.conn.commit()
        return result

    def list_benchmark_results(
        self,
        benchmark_id: str | None = None,
        target: str | None = None,
        limit: int = 100,
    ) -> list[SandboxV2BenchmarkResult]:
        sql = "SELECT * FROM sandbox_v2_benchmark_results WHERE 1=1"
        params: list[Any] = []
        if benchmark_id:
            sql += " AND benchmark_id=?"
            params.append(benchmark_id)
        if target:
            sql += " AND target=?"
            params.append(target)
        sql += " ORDER BY started_at DESC LIMIT ?"
        params.append(min(max(int(limit or 100), 1), 500))
        return [self._row_to_benchmark_result(dict(r)) for r in self._exec(sql, params)]

    def create_capacity_estimate(self, estimate: SandboxV2CapacityEstimate) -> SandboxV2CapacityEstimate:
        self._exec("""INSERT OR REPLACE INTO sandbox_v2_capacity_estimates (
            capacity_id, generated_at, profile,
            estimated_jobs_per_minute, estimated_queue_items_per_minute,
            estimated_artifact_metadata_per_minute, estimated_network_preflight_per_minute,
            sqlite_recommended_limit, postgres_recommended_threshold,
            redis_recommended_threshold, minio_recommended_threshold,
            bottlenecks_json, recommendations_json, metadata_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", [
            estimate.capacity_id,
            estimate.generated_at.isoformat() if hasattr(estimate.generated_at, 'isoformat') else str(estimate.generated_at),
            estimate.profile,
            estimate.estimated_jobs_per_minute,
            estimate.estimated_queue_items_per_minute,
            estimate.estimated_artifact_metadata_per_minute,
            estimate.estimated_network_preflight_per_minute,
            estimate.sqlite_recommended_limit,
            estimate.postgres_recommended_threshold,
            estimate.redis_recommended_threshold,
            estimate.minio_recommended_threshold,
            json.dumps(estimate.bottlenecks or [], ensure_ascii=False),
            json.dumps(estimate.recommendations or [], ensure_ascii=False),
            json.dumps(estimate.metadata or {}, ensure_ascii=False),
        ])
        self._db.conn.commit()
        return estimate

    def get_latest_capacity_estimate(self) -> SandboxV2CapacityEstimate | None:
        row = next(self._exec(
            "SELECT * FROM sandbox_v2_capacity_estimates ORDER BY generated_at DESC LIMIT 1"), None)
        return self._row_to_capacity_estimate(dict(row)) if row else None

    def list_capacity_estimates(self, limit: int = 20) -> list[SandboxV2CapacityEstimate]:
        rows = self._exec(
            "SELECT * FROM sandbox_v2_capacity_estimates ORDER BY generated_at DESC LIMIT ?",
            [min(max(int(limit or 20), 1), 100)],
        )
        return [self._row_to_capacity_estimate(dict(r)) for r in rows]

    @staticmethod
    def _row_to_benchmark_config(row: dict[str, Any]) -> SandboxV2BenchmarkConfig:
        return SandboxV2BenchmarkConfig.from_dict({
            "benchmark_id": row.get("benchmark_id", ""),
            "profile": row.get("profile", "small"),
            "targets": json.loads(row.get("targets_json", "[]") or "[]"),
            "max_jobs": row.get("max_jobs", 100),
            "max_queue_items": row.get("max_queue_items", 100),
            "max_artifacts": row.get("max_artifacts", 50),
            "max_concurrency": row.get("max_concurrency", 4),
            "timeout_seconds": row.get("timeout_seconds", 60),
            "cleanup_after_run": bool(row.get("cleanup_after_run", 1)),
            "organization_id": row.get("organization_id", ""),
            "workspace_id": row.get("workspace_id", ""),
            "created_at": row.get("created_at"),
            "metadata": json.loads(row.get("metadata_json", "{}") or "{}"),
        })

    @staticmethod
    def _row_to_benchmark_result(row: dict[str, Any]) -> SandboxV2BenchmarkResult:
        return SandboxV2BenchmarkResult.from_dict({
            "benchmark_result_id": row.get("benchmark_result_id", ""),
            "benchmark_id": row.get("benchmark_id", ""),
            "target": row.get("target", ""),
            "status": row.get("status", ""),
            "started_at": row.get("started_at"),
            "finished_at": row.get("finished_at"),
            "duration_ms": row.get("duration_ms", 0),
            "total_operations": row.get("total_operations", 0),
            "success_count": row.get("success_count", 0),
            "failure_count": row.get("failure_count", 0),
            "p50_ms": row.get("p50_ms", 0.0),
            "p95_ms": row.get("p95_ms", 0.0),
            "p99_ms": row.get("p99_ms", 0.0),
            "ops_per_second": row.get("ops_per_second", 0.0),
            "warnings": json.loads(row.get("warnings_json", "[]") or "[]"),
            "blockers": json.loads(row.get("blockers_json", "[]") or "[]"),
            "metadata": json.loads(row.get("metadata_json", "{}") or "{}"),
        })

    @staticmethod
    def _row_to_capacity_estimate(row: dict[str, Any]) -> SandboxV2CapacityEstimate:
        return SandboxV2CapacityEstimate.from_dict({
            "capacity_id": row.get("capacity_id", ""),
            "generated_at": row.get("generated_at"),
            "profile": row.get("profile", "small"),
            "estimated_jobs_per_minute": row.get("estimated_jobs_per_minute", 0.0),
            "estimated_queue_items_per_minute": row.get("estimated_queue_items_per_minute", 0.0),
            "estimated_artifact_metadata_per_minute": row.get("estimated_artifact_metadata_per_minute", 0.0),
            "estimated_network_preflight_per_minute": row.get("estimated_network_preflight_per_minute", 0.0),
            "sqlite_recommended_limit": row.get("sqlite_recommended_limit", ""),
            "postgres_recommended_threshold": row.get("postgres_recommended_threshold", ""),
            "redis_recommended_threshold": row.get("redis_recommended_threshold", ""),
            "minio_recommended_threshold": row.get("minio_recommended_threshold", ""),
            "bottlenecks": json.loads(row.get("bottlenecks_json", "[]") or "[]"),
            "recommendations": json.loads(row.get("recommendations_json", "[]") or "[]"),
            "metadata": json.loads(row.get("metadata_json", "{}") or "{}"),
        })

    # ═══════════════════════════════════════════
    # Step 17 — IAM / SSO Store Methods
    # ═══════════════════════════════════════════

    def create_iam_provider_config(self, config: SandboxV2IAMProviderConfig) -> SandboxV2IAMProviderConfig:
        self._exec("""INSERT OR REPLACE INTO sandbox_v2_iam_provider_configs (
            provider_config_id, provider_type, protocol, enabled,
            issuer, client_id, client_secret_ref, jwks_uri, discovery_enabled,
            saml_entity_id, saml_metadata_ref, jit_provisioning, default_role,
            allowed_domains_json, require_verified_email, external_group_mapping_enabled,
            organization_id, workspace_id, created_at, metadata_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", [
            config.provider_config_id, config.provider_type, config.protocol,
            1 if config.enabled else 0, config.issuer, config.client_id,
            config.client_secret_ref, config.jwks_uri, 1 if config.discovery_enabled else 0,
            config.saml_entity_id, config.saml_metadata_ref,
            1 if config.jit_provisioning else 0, config.default_role,
            json.dumps(config.allowed_domains or [], ensure_ascii=False),
            1 if config.require_verified_email else 0,
            1 if config.external_group_mapping_enabled else 0,
            config.organization_id, config.workspace_id,
            config.created_at.isoformat() if hasattr(config.created_at, 'isoformat') else str(config.created_at),
            json.dumps(config.metadata or {}, ensure_ascii=False),
        ])
        self._db.conn.commit()
        return config

    def get_iam_provider_config(self, provider_config_id: str) -> SandboxV2IAMProviderConfig | None:
        row = next(self._exec(
            "SELECT * FROM sandbox_v2_iam_provider_configs WHERE provider_config_id = ?",
            [provider_config_id],
        ), None)
        return self._row_to_iam_provider_config(dict(row)) if row else None

    def list_iam_provider_configs(
        self, organization_id: str | None = None, workspace_id: str | None = None,
        enabled: bool | None = None, limit: int = 50,
    ) -> list[SandboxV2IAMProviderConfig]:
        limit = min(max(int(limit or 50), 1), 100)
        q = "SELECT * FROM sandbox_v2_iam_provider_configs WHERE 1=1"
        params: list[Any] = []
        if organization_id:
            q += " AND organization_id = ?"; params.append(organization_id)
        if workspace_id:
            q += " AND workspace_id = ?"; params.append(workspace_id)
        if enabled is not None:
            q += " AND enabled = ?"; params.append(1 if enabled else 0)
        q += " ORDER BY created_at DESC LIMIT ?"; params.append(limit)
        rows = self._exec(q, params)
        return [self._row_to_iam_provider_config(dict(r)) for r in rows]

    def update_iam_provider_config_status(
        self, provider_config_id: str, enabled: bool, reason: str = "",
    ) -> SandboxV2IAMProviderConfig | None:
        self._exec(
            "UPDATE sandbox_v2_iam_provider_configs SET enabled = ? WHERE provider_config_id = ?",
            [1 if enabled else 0, provider_config_id],
        )
        self._db.conn.commit()
        return self.get_iam_provider_config(provider_config_id)

    def create_external_identity(self, identity: SandboxV2ExternalIdentity) -> SandboxV2ExternalIdentity:
        self._exec("""INSERT OR REPLACE INTO sandbox_v2_external_identities (
            external_identity_id, provider_config_id, provider_type,
            external_subject, external_email, email_verified,
            external_groups_json, display_name, organization_id, workspace_id,
            linked_principal_id, status, created_at, last_seen_at, metadata_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", [
            identity.external_identity_id, identity.provider_config_id,
            identity.provider_type, identity.external_subject,
            identity.external_email, 1 if identity.email_verified else 0,
            json.dumps(identity.external_groups or [], ensure_ascii=False),
            identity.display_name, identity.organization_id, identity.workspace_id,
            identity.linked_principal_id, identity.status,
            identity.created_at.isoformat() if hasattr(identity.created_at, 'isoformat') else str(identity.created_at),
            identity.last_seen_at.isoformat() if hasattr(identity.last_seen_at, 'isoformat') else str(identity.last_seen_at),
            json.dumps(identity.metadata or {}, ensure_ascii=False),
        ])
        self._db.conn.commit()
        return identity

    def get_external_identity(self, external_identity_id: str) -> SandboxV2ExternalIdentity | None:
        row = next(self._exec(
            "SELECT * FROM sandbox_v2_external_identities WHERE external_identity_id = ?",
            [external_identity_id],
        ), None)
        return self._row_to_external_identity(dict(row)) if row else None

    def list_external_identities(
        self, organization_id: str | None = None, workspace_id: str | None = None,
        provider_config_id: str | None = None, limit: int = 50,
    ) -> list[SandboxV2ExternalIdentity]:
        limit = min(max(int(limit or 50), 1), 100)
        q = "SELECT * FROM sandbox_v2_external_identities WHERE 1=1"
        params: list[Any] = []
        if organization_id:
            q += " AND organization_id = ?"; params.append(organization_id)
        if workspace_id:
            q += " AND workspace_id = ?"; params.append(workspace_id)
        if provider_config_id:
            q += " AND provider_config_id = ?"; params.append(provider_config_id)
        q += " ORDER BY created_at DESC LIMIT ?"; params.append(limit)
        rows = self._exec(q, params)
        return [self._row_to_external_identity(dict(r)) for r in rows]

    def create_iam_role_mapping(self, mapping: SandboxV2IAMRoleMapping) -> SandboxV2IAMRoleMapping:
        self._exec("""INSERT OR REPLACE INTO sandbox_v2_iam_role_mappings (
            mapping_id, provider_config_id, external_group, external_claim,
            sandbox_role, sandbox_scopes_json, organization_id, workspace_id,
            enabled, created_at, metadata_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?)""", [
            mapping.mapping_id, mapping.provider_config_id,
            mapping.external_group, mapping.external_claim,
            mapping.sandbox_role,
            json.dumps(mapping.sandbox_scopes or [], ensure_ascii=False),
            mapping.organization_id, mapping.workspace_id,
            1 if mapping.enabled else 0,
            mapping.created_at.isoformat() if hasattr(mapping.created_at, 'isoformat') else str(mapping.created_at),
            json.dumps(mapping.metadata or {}, ensure_ascii=False),
        ])
        self._db.conn.commit()
        return mapping

    def list_iam_role_mappings(
        self, provider_config_id: str | None = None, organization_id: str | None = None,
        workspace_id: str | None = None, enabled: bool | None = None, limit: int = 50,
    ) -> list[SandboxV2IAMRoleMapping]:
        limit = min(max(int(limit or 50), 1), 100)
        q = "SELECT * FROM sandbox_v2_iam_role_mappings WHERE 1=1"
        params: list[Any] = []
        if provider_config_id:
            q += " AND provider_config_id = ?"; params.append(provider_config_id)
        if organization_id:
            q += " AND organization_id = ?"; params.append(organization_id)
        if workspace_id:
            q += " AND workspace_id = ?"; params.append(workspace_id)
        if enabled is not None:
            q += " AND enabled = ?"; params.append(1 if enabled else 0)
        q += " ORDER BY created_at DESC LIMIT ?"; params.append(limit)
        rows = self._exec(q, params)
        return [self._row_to_iam_role_mapping(dict(r)) for r in rows]

    def create_iam_mapping_decision(self, decision: SandboxV2IAMMappingDecision) -> SandboxV2IAMMappingDecision:
        self._exec("""INSERT OR REPLACE INTO sandbox_v2_iam_mapping_decisions (
            decision_id, allowed, status, reason, principal_id, principal_type,
            mapped_roles_json, mapped_scopes_json, organization_id, workspace_id,
            email_domain_allowed, email_verified, tenant_match, group_mapping_applied,
            jit_provisioning_required, fail_closed, matched_rules_json, created_at, metadata_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", [
            decision.decision_id, 1 if decision.allowed else 0,
            decision.status, decision.reason, decision.principal_id,
            decision.principal_type,
            json.dumps(decision.mapped_roles or [], ensure_ascii=False),
            json.dumps(decision.mapped_scopes or [], ensure_ascii=False),
            decision.organization_id, decision.workspace_id,
            1 if decision.email_domain_allowed else 0,
            1 if decision.email_verified else 0,
            1 if decision.tenant_match else 0,
            1 if decision.group_mapping_applied else 0,
            1 if decision.jit_provisioning_required else 0,
            1 if decision.fail_closed else 0,
            json.dumps(decision.matched_rules or [], ensure_ascii=False),
            decision.created_at.isoformat() if hasattr(decision.created_at, 'isoformat') else str(decision.created_at),
            json.dumps(decision.metadata or {}, ensure_ascii=False),
        ])
        self._db.conn.commit()
        return decision

    def list_iam_mapping_decisions(
        self, organization_id: str | None = None, workspace_id: str | None = None,
        limit: int = 50,
    ) -> list[SandboxV2IAMMappingDecision]:
        limit = min(max(int(limit or 50), 1), 100)
        q = "SELECT * FROM sandbox_v2_iam_mapping_decisions WHERE 1=1"
        params: list[Any] = []
        if organization_id:
            q += " AND organization_id = ?"; params.append(organization_id)
        if workspace_id:
            q += " AND workspace_id = ?"; params.append(workspace_id)
        q += " ORDER BY created_at DESC LIMIT ?"; params.append(limit)
        rows = self._exec(q, params)
        return [self._row_to_iam_mapping_decision(dict(r)) for r in rows]

    def create_sso_simulation_result(self, result: SandboxV2SSOSimulationResult) -> SandboxV2SSOSimulationResult:
        self._exec("""INSERT OR REPLACE INTO sandbox_v2_sso_simulation_results (
            simulation_id, provider_config_id, protocol, login_status,
            claim_set_json, mapping_decision_json, security_context_json,
            audit_event_id, created_at, metadata_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?)""", [
            result.simulation_id, result.provider_config_id, result.protocol,
            result.login_status,
            json.dumps(result.claim_set or {}, ensure_ascii=False),
            json.dumps(result.mapping_decision or {}, ensure_ascii=False),
            json.dumps(result.security_context or {}, ensure_ascii=False),
            result.audit_event_id,
            result.created_at.isoformat() if hasattr(result.created_at, 'isoformat') else str(result.created_at),
            json.dumps(result.metadata or {}, ensure_ascii=False),
        ])
        self._db.conn.commit()
        return result

    def list_sso_simulation_results(
        self, organization_id: str | None = None, workspace_id: str | None = None,
        limit: int = 50,
    ) -> list[SandboxV2SSOSimulationResult]:
        limit = min(max(int(limit or 50), 1), 100)
        q = "SELECT * FROM sandbox_v2_sso_simulation_results WHERE 1=1"
        params: list[Any] = []
        if organization_id:
            q += " AND provider_config_id IN (SELECT provider_config_id FROM sandbox_v2_iam_provider_configs WHERE organization_id = ?)"
            params.append(organization_id)
        if workspace_id:
            q += " AND provider_config_id IN (SELECT provider_config_id FROM sandbox_v2_iam_provider_configs WHERE workspace_id = ?)"
            params.append(workspace_id)
        q += " ORDER BY created_at DESC LIMIT ?"; params.append(limit)
        rows = self._exec(q, params)
        return [self._row_to_sso_simulation_result(dict(r)) for r in rows]

    # ── IAM row converters ──

    @staticmethod
    def _row_to_iam_provider_config(row: dict[str, Any]) -> SandboxV2IAMProviderConfig:
        return SandboxV2IAMProviderConfig.from_dict({
            "provider_config_id": row.get("provider_config_id", ""),
            "provider_type": row.get("provider_type", "disabled"),
            "protocol": row.get("protocol", "disabled"),
            "enabled": bool(row.get("enabled", 0)),
            "issuer": row.get("issuer", ""),
            "client_id": row.get("client_id", ""),
            "client_secret_ref": row.get("client_secret_ref", ""),
            "jwks_uri": row.get("jwks_uri", ""),
            "discovery_enabled": bool(row.get("discovery_enabled", 0)),
            "saml_entity_id": row.get("saml_entity_id", ""),
            "saml_metadata_ref": row.get("saml_metadata_ref", ""),
            "jit_provisioning": bool(row.get("jit_provisioning", 0)),
            "default_role": row.get("default_role", "viewer"),
            "allowed_domains": json.loads(row.get("allowed_domains_json", "[]") or "[]"),
            "require_verified_email": bool(row.get("require_verified_email", 1)),
            "external_group_mapping_enabled": bool(row.get("external_group_mapping_enabled", 0)),
            "organization_id": row.get("organization_id", ""),
            "workspace_id": row.get("workspace_id", ""),
            "created_at": row.get("created_at"),
            "metadata": json.loads(row.get("metadata_json", "{}") or "{}"),
        })

    @staticmethod
    def _row_to_external_identity(row: dict[str, Any]) -> SandboxV2ExternalIdentity:
        return SandboxV2ExternalIdentity.from_dict({
            "external_identity_id": row.get("external_identity_id", ""),
            "provider_config_id": row.get("provider_config_id", ""),
            "provider_type": row.get("provider_type", "disabled"),
            "external_subject": row.get("external_subject", ""),
            "external_email": row.get("external_email", ""),
            "email_verified": bool(row.get("email_verified", 0)),
            "external_groups": json.loads(row.get("external_groups_json", "[]") or "[]"),
            "display_name": row.get("display_name", ""),
            "organization_id": row.get("organization_id", ""),
            "workspace_id": row.get("workspace_id", ""),
            "linked_principal_id": row.get("linked_principal_id", ""),
            "status": row.get("status", "pending_review"),
            "created_at": row.get("created_at"),
            "last_seen_at": row.get("last_seen_at"),
            "metadata": json.loads(row.get("metadata_json", "{}") or "{}"),
        })

    @staticmethod
    def _row_to_iam_role_mapping(row: dict[str, Any]) -> SandboxV2IAMRoleMapping:
        return SandboxV2IAMRoleMapping.from_dict({
            "mapping_id": row.get("mapping_id", ""),
            "provider_config_id": row.get("provider_config_id", ""),
            "external_group": row.get("external_group", ""),
            "external_claim": row.get("external_claim", ""),
            "sandbox_role": row.get("sandbox_role", "viewer"),
            "sandbox_scopes": json.loads(row.get("sandbox_scopes_json", "[]") or "[]"),
            "organization_id": row.get("organization_id", ""),
            "workspace_id": row.get("workspace_id", ""),
            "enabled": bool(row.get("enabled", 1)),
            "created_at": row.get("created_at"),
            "metadata": json.loads(row.get("metadata_json", "{}") or "{}"),
        })

    @staticmethod
    def _row_to_iam_mapping_decision(row: dict[str, Any]) -> SandboxV2IAMMappingDecision:
        return SandboxV2IAMMappingDecision.from_dict({
            "decision_id": row.get("decision_id", ""),
            "allowed": bool(row.get("allowed", 0)),
            "status": row.get("status", "rejected"),
            "reason": row.get("reason", "Default deny."),
            "principal_id": row.get("principal_id", ""),
            "principal_type": row.get("principal_type", "anonymous"),
            "mapped_roles": json.loads(row.get("mapped_roles_json", "[]") or "[]"),
            "mapped_scopes": json.loads(row.get("mapped_scopes_json", "[]") or "[]"),
            "organization_id": row.get("organization_id", ""),
            "workspace_id": row.get("workspace_id", ""),
            "email_domain_allowed": bool(row.get("email_domain_allowed", 0)),
            "email_verified": bool(row.get("email_verified", 0)),
            "tenant_match": bool(row.get("tenant_match", 0)),
            "group_mapping_applied": bool(row.get("group_mapping_applied", 0)),
            "jit_provisioning_required": bool(row.get("jit_provisioning_required", 0)),
            "fail_closed": bool(row.get("fail_closed", 1)),
            "matched_rules": json.loads(row.get("matched_rules_json", "[]") or "[]"),
            "created_at": row.get("created_at"),
            "metadata": json.loads(row.get("metadata_json", "{}") or "{}"),
        })

    @staticmethod
    def _row_to_sso_simulation_result(row: dict[str, Any]) -> SandboxV2SSOSimulationResult:
        return SandboxV2SSOSimulationResult.from_dict({
            "simulation_id": row.get("simulation_id", ""),
            "provider_config_id": row.get("provider_config_id", ""),
            "protocol": row.get("protocol", "mock"),
            "login_status": row.get("login_status", "disabled"),
            "claim_set": json.loads(row.get("claim_set_json", "{}") or "{}"),
            "mapping_decision": json.loads(row.get("mapping_decision_json", "{}") or "{}"),
            "security_context": json.loads(row.get("security_context_json", "{}") or "{}"),
            "audit_event_id": row.get("audit_event_id", ""),
            "created_at": row.get("created_at"),
            "metadata": json.loads(row.get("metadata_json", "{}") or "{}"),
        })

    # ═══════════════════════════════════════════
    # Step 18 — Observability / OTel Store Methods
    # ═══════════════════════════════════════════

    def create_trace_span(self, span: SandboxV2TraceSpan) -> SandboxV2TraceSpan:
        self._exec("""INSERT OR REPLACE INTO sandbox_v2_trace_spans (
            span_id, trace_id, parent_span_id, span_name, status,
            organization_id, workspace_id, resource_type, resource_id,
            started_at, finished_at, duration_ms,
            attributes_redacted_json, events_redacted_json, metadata_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", [
            span.span_id, span.trace_id, span.parent_span_id, span.span_name, span.status,
            span.organization_id, span.workspace_id, span.resource_type, span.resource_id,
            span.started_at.isoformat() if hasattr(span.started_at, 'isoformat') else str(span.started_at),
            span.finished_at.isoformat() if span.finished_at and hasattr(span.finished_at, 'isoformat') else None,
            span.duration_ms,
            json.dumps(span.attributes_redacted or {}, ensure_ascii=False),
            json.dumps(span.events_redacted or [], ensure_ascii=False),
            json.dumps(span.metadata or {}, ensure_ascii=False),
        ])
        self._db.conn.commit()
        return span

    def update_trace_span(self, span_id: str, status: str,
                          finished_at: Any = None, duration_ms: int = 0,
                          metadata: dict[str, Any] | None = None) -> SandboxV2TraceSpan | None:
        if finished_at and hasattr(finished_at, 'isoformat'):
            finished_at_str = finished_at.isoformat()
        elif finished_at:
            finished_at_str = str(finished_at)
        else:
            finished_at_str = datetime.now(timezone.utc).isoformat()
        self._exec(
            "UPDATE sandbox_v2_trace_spans SET status=?, finished_at=?, duration_ms=? WHERE span_id=?",
            [status, finished_at_str, duration_ms, span_id],
        )
        self._db.conn.commit()
        row = next(self._exec("SELECT * FROM sandbox_v2_trace_spans WHERE span_id=?", [span_id]), None)
        return self._row_to_trace_span(dict(row)) if row else None

    def list_trace_spans(self, organization_id: str | None = None,
                         workspace_id: str | None = None,
                         trace_id: str | None = None, limit: int = 100) -> list[SandboxV2TraceSpan]:
        limit = min(max(int(limit or 100), 1), 200)
        q = "SELECT * FROM sandbox_v2_trace_spans WHERE 1=1"
        params: list[Any] = []
        if organization_id:
            q += " AND organization_id = ?"; params.append(organization_id)
        if workspace_id:
            q += " AND workspace_id = ?"; params.append(workspace_id)
        if trace_id:
            q += " AND trace_id = ?"; params.append(trace_id)
        q += " ORDER BY started_at DESC LIMIT ?"; params.append(limit)
        return [self._row_to_trace_span(dict(r)) for r in self._exec(q, params)]

    def create_telemetry_export_record(self, record: SandboxV2TelemetryExportRecord) -> SandboxV2TelemetryExportRecord:
        self._exec("""INSERT OR REPLACE INTO sandbox_v2_telemetry_export_records (
            export_record_id, provider, signal_type, status,
            organization_id, workspace_id, resource_type, resource_id,
            exported_count, rejected_count, reason, created_at, metadata_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""", [
            record.export_record_id, record.provider, record.signal_type, record.status,
            record.organization_id, record.workspace_id, record.resource_type, record.resource_id,
            record.exported_count, record.rejected_count, record.reason,
            record.created_at.isoformat() if hasattr(record.created_at, 'isoformat') else str(record.created_at),
            json.dumps(record.metadata or {}, ensure_ascii=False),
        ])
        self._db.conn.commit()
        return record

    def list_telemetry_export_records(self, provider: str | None = None,
                                      signal_type: str | None = None,
                                      status: str | None = None,
                                      limit: int = 100) -> list[SandboxV2TelemetryExportRecord]:
        limit = min(max(int(limit or 100), 1), 200)
        q = "SELECT * FROM sandbox_v2_telemetry_export_records WHERE 1=1"
        params: list[Any] = []
        if provider:
            q += " AND provider = ?"; params.append(provider)
        if signal_type:
            q += " AND signal_type = ?"; params.append(signal_type)
        if status:
            q += " AND status = ?"; params.append(status)
        q += " ORDER BY created_at DESC LIMIT ?"; params.append(limit)
        return [self._row_to_telemetry_export_record(dict(r)) for r in self._exec(q, params)]

    def create_grafana_dashboard_spec(self, spec: SandboxV2GrafanaDashboardSpec) -> SandboxV2GrafanaDashboardSpec:
        self._exec("""INSERT OR REPLACE INTO sandbox_v2_grafana_dashboard_specs (
            dashboard_id, title, version, panels_json, datasource, tags_json,
            generated_at, metadata_json
        ) VALUES (?,?,?,?,?,?,?,?)""", [
            spec.dashboard_id, spec.title, spec.version,
            json.dumps(spec.panels or [], ensure_ascii=False),
            spec.datasource,
            json.dumps(spec.tags or [], ensure_ascii=False),
            spec.generated_at.isoformat() if hasattr(spec.generated_at, 'isoformat') else str(spec.generated_at),
            json.dumps(spec.metadata or {}, ensure_ascii=False),
        ])
        self._db.conn.commit()
        return spec

    def get_latest_grafana_dashboard_spec(self) -> SandboxV2GrafanaDashboardSpec | None:
        row = next(self._exec(
            "SELECT * FROM sandbox_v2_grafana_dashboard_specs ORDER BY generated_at DESC LIMIT 1"), None)
        return self._row_to_grafana_dashboard_spec(dict(row)) if row else None

    def list_grafana_dashboard_specs(self, limit: int = 20) -> list[SandboxV2GrafanaDashboardSpec]:
        limit = min(max(int(limit or 20), 1), 50)
        rows = self._exec(
            "SELECT * FROM sandbox_v2_grafana_dashboard_specs ORDER BY generated_at DESC LIMIT ?",
            [limit],
        )
        return [self._row_to_grafana_dashboard_spec(dict(r)) for r in rows]

    # ── Observability row converters ──

    @staticmethod
    def _row_to_trace_span(row: dict[str, Any]) -> SandboxV2TraceSpan:
        return SandboxV2TraceSpan.from_dict({
            "span_id": row.get("span_id", ""),
            "trace_id": row.get("trace_id", ""),
            "parent_span_id": row.get("parent_span_id", ""),
            "span_name": row.get("span_name", ""),
            "status": row.get("status", "ok"),
            "organization_id": row.get("organization_id", ""),
            "workspace_id": row.get("workspace_id", ""),
            "resource_type": row.get("resource_type", ""),
            "resource_id": row.get("resource_id", ""),
            "started_at": row.get("started_at"),
            "finished_at": row.get("finished_at"),
            "duration_ms": row.get("duration_ms", 0),
            "attributes_redacted": json.loads(row.get("attributes_redacted_json", "{}") or "{}"),
            "events_redacted": json.loads(row.get("events_redacted_json", "[]") or "[]"),
            "metadata": json.loads(row.get("metadata_json", "{}") or "{}"),
        })

    @staticmethod
    def _row_to_telemetry_export_record(row: dict[str, Any]) -> SandboxV2TelemetryExportRecord:
        return SandboxV2TelemetryExportRecord.from_dict({
            "export_record_id": row.get("export_record_id", ""),
            "provider": row.get("provider", ""),
            "signal_type": row.get("signal_type", "metric"),
            "status": row.get("status", "disabled"),
            "organization_id": row.get("organization_id", ""),
            "workspace_id": row.get("workspace_id", ""),
            "resource_type": row.get("resource_type", ""),
            "resource_id": row.get("resource_id", ""),
            "exported_count": row.get("exported_count", 0),
            "rejected_count": row.get("rejected_count", 0),
            "reason": row.get("reason", ""),
            "created_at": row.get("created_at"),
            "metadata": json.loads(row.get("metadata_json", "{}") or "{}"),
        })

    @staticmethod
    def _row_to_grafana_dashboard_spec(row: dict[str, Any]) -> SandboxV2GrafanaDashboardSpec:
        return SandboxV2GrafanaDashboardSpec.from_dict({
            "dashboard_id": row.get("dashboard_id", ""),
            "title": row.get("title", ""),
            "version": row.get("version", "1.0"),
            "panels": json.loads(row.get("panels_json", "[]") or "[]"),
            "datasource": row.get("datasource", "${DS_PROMETHEUS}"),
            "tags": json.loads(row.get("tags_json", "[]") or "[]"),
            "generated_at": row.get("generated_at"),
            "metadata": json.loads(row.get("metadata_json", "{}") or "{}"),
        })

    # ═══════════════════════════════════════════
    # Step 19 — Load Testing / SLO Store Methods
    # ═══════════════════════════════════════════

    def create_load_test_config(self, config: SandboxV2LoadTestConfig) -> SandboxV2LoadTestConfig:
        self._exec("""INSERT OR REPLACE INTO sandbox_v2_load_test_configs (
            load_test_id, profile, base_url_masked, targets_json,
            max_users, max_rps, duration_seconds, timeout_seconds,
            allow_production, require_confirmation, organization_id, workspace_id,
            created_at, metadata_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", [
            config.load_test_id, config.profile, config.base_url_masked,
            json.dumps(config.targets or [], ensure_ascii=False),
            config.max_users, config.max_rps, config.duration_seconds,
            config.timeout_seconds, 1 if config.allow_production else 0,
            1 if config.require_confirmation else 0,
            config.organization_id, config.workspace_id,
            config.created_at.isoformat() if hasattr(config.created_at, 'isoformat') else str(config.created_at),
            json.dumps(config.metadata or {}, ensure_ascii=False),
        ])
        self._db.conn.commit()
        return config

    def get_load_test_config(self, load_test_id: str) -> SandboxV2LoadTestConfig | None:
        row = next(self._exec("SELECT * FROM sandbox_v2_load_test_configs WHERE load_test_id=?", [load_test_id]), None)
        return self._row_to_load_test_config(dict(row)) if row else None

    def list_load_test_configs(self, limit: int = 50) -> list[SandboxV2LoadTestConfig]:
        limit = min(max(int(limit or 50), 1), 100)
        return [self._row_to_load_test_config(dict(r)) for r in
                self._exec("SELECT * FROM sandbox_v2_load_test_configs ORDER BY created_at DESC LIMIT ?", [limit])]

    def create_load_test_result(self, result: SandboxV2LoadTestResult) -> SandboxV2LoadTestResult:
        self._exec("""INSERT OR REPLACE INTO sandbox_v2_load_test_results (
            load_test_result_id, load_test_id, target, status, started_at, finished_at,
            duration_ms, total_requests, success_count, failure_count, timeout_count,
            p50_ms, p95_ms, p99_ms, min_ms, max_ms, requests_per_second,
            error_rate_percent, warnings_json, blockers_json, metadata_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", [
            result.load_test_result_id, result.load_test_id, result.target, result.status,
            result.started_at.isoformat() if hasattr(result.started_at, 'isoformat') else str(result.started_at),
            result.finished_at.isoformat() if result.finished_at and hasattr(result.finished_at, 'isoformat') else None,
            result.duration_ms, result.total_requests, result.success_count,
            result.failure_count, result.timeout_count,
            result.p50_ms, result.p95_ms, result.p99_ms, result.min_ms, result.max_ms,
            result.requests_per_second, result.error_rate_percent,
            json.dumps(result.warnings or [], ensure_ascii=False),
            json.dumps(result.blockers or [], ensure_ascii=False),
            json.dumps(result.metadata or {}, ensure_ascii=False),
        ])
        self._db.conn.commit()
        return result

    def list_load_test_results(self, load_test_id: str | None = None,
                               target: str | None = None, limit: int = 100) -> list[SandboxV2LoadTestResult]:
        limit = min(max(int(limit or 100), 1), 200)
        q = "SELECT * FROM sandbox_v2_load_test_results WHERE 1=1"; params: list[Any] = []
        if load_test_id: q += " AND load_test_id = ?"; params.append(load_test_id)
        if target: q += " AND target = ?"; params.append(target)
        q += " ORDER BY started_at DESC LIMIT ?"; params.append(limit)
        return [self._row_to_load_test_result(dict(r)) for r in self._exec(q, params)]

    def create_slo_definition(self, slo: SandboxV2SLODefinition) -> SandboxV2SLODefinition:
        self._exec("""INSERT OR REPLACE INTO sandbox_v2_slo_definitions (
            slo_id, name, description, target, p95_ms, p99_ms,
            error_rate_percent, availability_percent, enabled,
            organization_id, workspace_id, created_at, metadata_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""", [
            slo.slo_id, slo.name, slo.description, slo.target, slo.p95_ms, slo.p99_ms,
            slo.error_rate_percent, slo.availability_percent, 1 if slo.enabled else 0,
            slo.organization_id, slo.workspace_id,
            slo.created_at.isoformat() if hasattr(slo.created_at, 'isoformat') else str(slo.created_at),
            json.dumps(slo.metadata or {}, ensure_ascii=False),
        ])
        self._db.conn.commit()
        return slo

    def list_slo_definitions(self, enabled: bool | None = None, limit: int = 100) -> list[SandboxV2SLODefinition]:
        limit = min(max(int(limit or 100), 1), 200)
        q = "SELECT * FROM sandbox_v2_slo_definitions WHERE 1=1"; params: list[Any] = []
        if enabled is not None: q += " AND enabled = ?"; params.append(1 if enabled else 0)
        q += " ORDER BY created_at DESC LIMIT ?"; params.append(limit)
        return [self._row_to_slo_definition(dict(r)) for r in self._exec(q, params)]

    def create_slo_evaluation(self, evaluation: SandboxV2SLOEvaluation) -> SandboxV2SLOEvaluation:
        self._exec("""INSERT OR REPLACE INTO sandbox_v2_slo_evaluations (
            slo_eval_id, slo_id, load_test_id, status, target,
            observed_p95_ms, observed_p99_ms, observed_error_rate_percent,
            observed_availability_percent, reason, evaluated_at, metadata_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""", [
            evaluation.slo_eval_id, evaluation.slo_id, evaluation.load_test_id,
            evaluation.status, evaluation.target,
            evaluation.observed_p95_ms, evaluation.observed_p99_ms,
            evaluation.observed_error_rate_percent, evaluation.observed_availability_percent,
            evaluation.reason,
            evaluation.evaluated_at.isoformat() if hasattr(evaluation.evaluated_at, 'isoformat') else str(evaluation.evaluated_at),
            json.dumps(evaluation.metadata or {}, ensure_ascii=False),
        ])
        self._db.conn.commit()
        return evaluation

    def list_slo_evaluations(self, load_test_id: str | None = None,
                             slo_id: str | None = None, limit: int = 100) -> list[SandboxV2SLOEvaluation]:
        limit = min(max(int(limit or 100), 1), 200)
        q = "SELECT * FROM sandbox_v2_slo_evaluations WHERE 1=1"; params: list[Any] = []
        if load_test_id: q += " AND load_test_id = ?"; params.append(load_test_id)
        if slo_id: q += " AND slo_id = ?"; params.append(slo_id)
        q += " ORDER BY evaluated_at DESC LIMIT ?"; params.append(limit)
        return [self._row_to_slo_evaluation(dict(r)) for r in self._exec(q, params)]

    def create_capacity_plan(self, plan: SandboxV2CapacityPlan) -> SandboxV2CapacityPlan:
        self._exec("""INSERT OR REPLACE INTO sandbox_v2_capacity_plans (
            capacity_plan_id, generated_at, recommended_profile, recommended_backend,
            recommended_workers, recommended_queue_backend, recommended_object_storage,
            expected_daily_jobs, expected_peak_rps, bottlenecks_json,
            scaling_recommendations_json, risk_notes_json, metadata_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""", [
            plan.capacity_plan_id,
            plan.generated_at.isoformat() if hasattr(plan.generated_at, 'isoformat') else str(plan.generated_at),
            plan.recommended_profile, plan.recommended_backend, plan.recommended_workers,
            plan.recommended_queue_backend, plan.recommended_object_storage,
            plan.expected_daily_jobs, plan.expected_peak_rps,
            json.dumps(plan.bottlenecks or [], ensure_ascii=False),
            json.dumps(plan.scaling_recommendations or [], ensure_ascii=False),
            json.dumps(plan.risk_notes or [], ensure_ascii=False),
            json.dumps(plan.metadata or {}, ensure_ascii=False),
        ])
        self._db.conn.commit()
        return plan

    def get_latest_capacity_plan(self) -> SandboxV2CapacityPlan | None:
        row = next(self._exec("SELECT * FROM sandbox_v2_capacity_plans ORDER BY generated_at DESC LIMIT 1"), None)
        return self._row_to_capacity_plan(dict(row)) if row else None

    def list_capacity_plans(self, limit: int = 20) -> list[SandboxV2CapacityPlan]:
        limit = min(max(int(limit or 20), 1), 50)
        return [self._row_to_capacity_plan(dict(r)) for r in
                self._exec("SELECT * FROM sandbox_v2_capacity_plans ORDER BY generated_at DESC LIMIT ?", [limit])]

    # ── Load Test row converters ──

    @staticmethod
    def _row_to_load_test_config(row: dict[str, Any]) -> SandboxV2LoadTestConfig:
        return SandboxV2LoadTestConfig.from_dict({
            "load_test_id": row.get("load_test_id", ""), "profile": row.get("profile", "smoke"),
            "base_url_masked": row.get("base_url_masked", ""),
            "targets": json.loads(row.get("targets_json", "[]") or "[]"),
            "max_users": row.get("max_users", 5), "max_rps": row.get("max_rps", 5),
            "duration_seconds": row.get("duration_seconds", 30),
            "timeout_seconds": row.get("timeout_seconds", 5),
            "allow_production": bool(row.get("allow_production", 0)),
            "require_confirmation": bool(row.get("require_confirmation", 1)),
            "organization_id": row.get("organization_id", ""),
            "workspace_id": row.get("workspace_id", ""),
            "created_at": row.get("created_at"),
            "metadata": json.loads(row.get("metadata_json", "{}") or "{}"),
        })

    @staticmethod
    def _row_to_load_test_result(row: dict[str, Any]) -> SandboxV2LoadTestResult:
        return SandboxV2LoadTestResult.from_dict({
            "load_test_result_id": row.get("load_test_result_id", ""),
            "load_test_id": row.get("load_test_id", ""), "target": row.get("target", ""),
            "status": row.get("status", "created"), "started_at": row.get("started_at"),
            "finished_at": row.get("finished_at"), "duration_ms": row.get("duration_ms", 0),
            "total_requests": row.get("total_requests", 0), "success_count": row.get("success_count", 0),
            "failure_count": row.get("failure_count", 0), "timeout_count": row.get("timeout_count", 0),
            "p50_ms": row.get("p50_ms", 0.0), "p95_ms": row.get("p95_ms", 0.0),
            "p99_ms": row.get("p99_ms", 0.0), "min_ms": row.get("min_ms", 0.0),
            "max_ms": row.get("max_ms", 0.0), "requests_per_second": row.get("requests_per_second", 0.0),
            "error_rate_percent": row.get("error_rate_percent", 0.0),
            "warnings": json.loads(row.get("warnings_json", "[]") or "[]"),
            "blockers": json.loads(row.get("blockers_json", "[]") or "[]"),
            "metadata": json.loads(row.get("metadata_json", "{}") or "{}"),
        })

    @staticmethod
    def _row_to_slo_definition(row: dict[str, Any]) -> SandboxV2SLODefinition:
        return SandboxV2SLODefinition.from_dict({
            "slo_id": row.get("slo_id", ""), "name": row.get("name", ""),
            "description": row.get("description", ""), "target": row.get("target", ""),
            "p95_ms": row.get("p95_ms", 500), "p99_ms": row.get("p99_ms", 1500),
            "error_rate_percent": row.get("error_rate_percent", 1.0),
            "availability_percent": row.get("availability_percent", 99.0),
            "enabled": bool(row.get("enabled", 1)),
            "organization_id": row.get("organization_id", ""),
            "workspace_id": row.get("workspace_id", ""),
            "created_at": row.get("created_at"),
            "metadata": json.loads(row.get("metadata_json", "{}") or "{}"),
        })

    @staticmethod
    def _row_to_slo_evaluation(row: dict[str, Any]) -> SandboxV2SLOEvaluation:
        return SandboxV2SLOEvaluation.from_dict({
            "slo_eval_id": row.get("slo_eval_id", ""), "slo_id": row.get("slo_id", ""),
            "load_test_id": row.get("load_test_id", ""), "status": row.get("status", "not_evaluated"),
            "target": row.get("target", ""),
            "observed_p95_ms": row.get("observed_p95_ms", 0.0),
            "observed_p99_ms": row.get("observed_p99_ms", 0.0),
            "observed_error_rate_percent": row.get("observed_error_rate_percent", 0.0),
            "observed_availability_percent": row.get("observed_availability_percent", 0.0),
            "reason": row.get("reason", ""), "evaluated_at": row.get("evaluated_at"),
            "metadata": json.loads(row.get("metadata_json", "{}") or "{}"),
        })

    @staticmethod
    def _row_to_capacity_plan(row: dict[str, Any]) -> SandboxV2CapacityPlan:
        return SandboxV2CapacityPlan.from_dict({
            "capacity_plan_id": row.get("capacity_plan_id", ""),
            "generated_at": row.get("generated_at"),
            "recommended_profile": row.get("recommended_profile", "small"),
            "recommended_backend": row.get("recommended_backend", "sqlite"),
            "recommended_workers": row.get("recommended_workers", 2),
            "recommended_queue_backend": row.get("recommended_queue_backend", "sqlite"),
            "recommended_object_storage": row.get("recommended_object_storage", "local"),
            "expected_daily_jobs": row.get("expected_daily_jobs", 1000),
            "expected_peak_rps": row.get("expected_peak_rps", 5.0),
            "bottlenecks": json.loads(row.get("bottlenecks_json", "[]") or "[]"),
            "scaling_recommendations": json.loads(row.get("scaling_recommendations_json", "[]") or "[]"),
            "risk_notes": json.loads(row.get("risk_notes_json", "[]") or "[]"),
            "metadata": json.loads(row.get("metadata_json", "{}") or "{}"),
        })

    # ═══════════════════════════════════════════
    # Step 20 — Real OIDC / SAML Store Methods
    # ═══════════════════════════════════════════

    def create_sso_state(self, state: Any) -> Any:
        from src.open_platform.sandbox_v2.models import SandboxV2SSOState
        s = state if isinstance(state, SandboxV2SSOState) else SandboxV2SSOState(**state) if isinstance(state, dict) else state
        self._exec("""INSERT OR REPLACE INTO sandbox_v2_sso_states (
            sso_state_id, flow_type, state_hash, nonce_hash, code_verifier_hash,
            code_challenge, redirect_uri, provider_config_id, organization_id, workspace_id,
            principal_hint, created_at, expires_at, consumed_at, status, metadata_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", [
            s.sso_state_id, s.flow_type, s.state_hash, s.nonce_hash, s.code_verifier_hash,
            s.code_challenge, s.redirect_uri, s.provider_config_id,
            s.organization_id, s.workspace_id, s.principal_hint,
            s.created_at.isoformat() if hasattr(s.created_at, 'isoformat') else str(s.created_at),
            s.expires_at.isoformat() if hasattr(s.expires_at, 'isoformat') else str(s.expires_at),
            s.consumed_at.isoformat() if s.consumed_at and hasattr(s.consumed_at, 'isoformat') else None,
            s.status, json.dumps(getattr(s, 'metadata', {}) or {}, ensure_ascii=False),
        ]); self._db.conn.commit(); return s

    def get_sso_state(self, sso_state_id: str) -> Any | None:
        row = next(self._exec("SELECT * FROM sandbox_v2_sso_states WHERE sso_state_id=?", [sso_state_id]), None)
        return self._row_to_sso_state(dict(row)) if row else None

    def get_sso_state_by_hash(self, state_hash: str) -> Any | None:
        row = next(self._exec("SELECT * FROM sandbox_v2_sso_states WHERE state_hash=? ORDER BY created_at DESC LIMIT 1", [state_hash]), None)
        return self._row_to_sso_state(dict(row)) if row else None

    def consume_sso_state(self, sso_state_id: str) -> Any | None:
        now = datetime.now(timezone.utc).isoformat()
        self._exec("UPDATE sandbox_v2_sso_states SET consumed_at=?, status='consumed' WHERE sso_state_id=? AND consumed_at IS NULL", [now, sso_state_id])
        self._db.conn.commit()
        return self.get_sso_state(sso_state_id)

    def create_oidc_auth_request(self, request: Any) -> Any:
        from src.open_platform.sandbox_v2.models import SandboxV2OIDCAuthRequest
        r = request if isinstance(request, SandboxV2OIDCAuthRequest) else SandboxV2OIDCAuthRequest(**request) if isinstance(request, dict) else request
        self._exec("""INSERT OR REPLACE INTO sandbox_v2_oidc_auth_requests (
            auth_request_id, provider_config_id, authorization_url, state_id,
            code_challenge, scopes, redirect_uri, created_at, metadata_json
        ) VALUES (?,?,?,?,?,?,?,?,?)""", [
            r.auth_request_id, r.provider_config_id, r.authorization_url, r.state_id,
            r.code_challenge, r.scopes, r.redirect_uri,
            r.created_at.isoformat() if hasattr(r.created_at, 'isoformat') else str(r.created_at),
            json.dumps(getattr(r, 'metadata', {}) or {}, ensure_ascii=False),
        ]); self._db.conn.commit(); return r

    def create_oidc_callback_result(self, result: Any) -> Any:
        from src.open_platform.sandbox_v2.models import SandboxV2OIDCCallbackResult
        r = result if isinstance(result, SandboxV2OIDCCallbackResult) else SandboxV2OIDCCallbackResult(**result) if isinstance(result, dict) else result
        self._exec("""INSERT OR REPLACE INTO sandbox_v2_oidc_callback_results (
            callback_id, provider_config_id, state_id, status, validation_status,
            mapping_decision_json, security_context_json, session_id, audit_event_id,
            created_at, metadata_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?)""", [
            r.callback_id, r.provider_config_id, r.state_id, r.status, r.validation_status,
            json.dumps(r.mapping_decision or {}, ensure_ascii=False),
            json.dumps(r.security_context or {}, ensure_ascii=False),
            r.session_id, r.audit_event_id,
            r.created_at.isoformat() if hasattr(r.created_at, 'isoformat') else str(r.created_at),
            json.dumps(getattr(r, 'metadata', {}) or {}, ensure_ascii=False),
        ]); self._db.conn.commit(); return r

    def create_oidc_token_validation_result(self, result: Any) -> Any:
        from src.open_platform.sandbox_v2.models import SandboxV2OIDCTokenValidationResult
        r = result if isinstance(result, SandboxV2OIDCTokenValidationResult) else SandboxV2OIDCTokenValidationResult(**result) if isinstance(result, dict) else result
        self._exec("""INSERT OR REPLACE INTO sandbox_v2_oidc_token_validation_results (
            validation_id, issuer_valid, audience_valid, nonce_valid, exp_valid,
            iat_valid, signature_valid, alg_allowed, email_verified,
            validation_status, reason, claims_redacted_json, created_at, metadata_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", [
            r.validation_id, 1 if r.issuer_valid else 0, 1 if r.audience_valid else 0,
            1 if r.nonce_valid else 0, 1 if r.exp_valid else 0, 1 if r.iat_valid else 0,
            1 if r.signature_valid else 0, 1 if r.alg_allowed else 0,
            1 if r.email_verified else 0, r.validation_status, r.reason,
            json.dumps(r.claims_redacted or {}, ensure_ascii=False),
            r.created_at.isoformat() if hasattr(r.created_at, 'isoformat') else str(r.created_at),
            json.dumps(getattr(r, 'metadata', {}) or {}, ensure_ascii=False),
        ]); self._db.conn.commit(); return r

    def create_saml_auth_request(self, request: Any) -> Any:
        from src.open_platform.sandbox_v2.models import SandboxV2SAMLAuthRequest
        r = request if isinstance(request, SandboxV2SAMLAuthRequest) else SandboxV2SAMLAuthRequest(**request) if isinstance(request, dict) else request
        self._exec("""INSERT OR REPLACE INTO sandbox_v2_saml_auth_requests (
            saml_request_id, provider_config_id, sso_url, relay_state_id,
            saml_request_redacted, acs_url, created_at, metadata_json
        ) VALUES (?,?,?,?,?,?,?,?)""", [
            r.saml_request_id, r.provider_config_id, r.sso_url, r.relay_state_id,
            r.saml_request_redacted, r.acs_url,
            r.created_at.isoformat() if hasattr(r.created_at, 'isoformat') else str(r.created_at),
            json.dumps(getattr(r, 'metadata', {}) or {}, ensure_ascii=False),
        ]); self._db.conn.commit(); return r

    def create_saml_acs_result(self, result: Any) -> Any:
        from src.open_platform.sandbox_v2.models import SandboxV2SAMLACSResult
        r = result if isinstance(result, SandboxV2SAMLACSResult) else SandboxV2SAMLACSResult(**result) if isinstance(result, dict) else result
        self._exec("""INSERT OR REPLACE INTO sandbox_v2_saml_acs_results (
            acs_result_id, provider_config_id, relay_state_id, validation_status,
            mapping_decision_json, security_context_json, session_id, audit_event_id,
            created_at, metadata_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?)""", [
            r.acs_result_id, r.provider_config_id, r.relay_state_id, r.validation_status,
            json.dumps(r.mapping_decision or {}, ensure_ascii=False),
            json.dumps(r.security_context or {}, ensure_ascii=False),
            r.session_id, r.audit_event_id,
            r.created_at.isoformat() if hasattr(r.created_at, 'isoformat') else str(r.created_at),
            json.dumps(getattr(r, 'metadata', {}) or {}, ensure_ascii=False),
        ]); self._db.conn.commit(); return r

    def create_sso_session(self, session: Any) -> Any:
        from src.open_platform.sandbox_v2.models import SandboxV2SSOSession
        s = session if isinstance(session, SandboxV2SSOSession) else SandboxV2SSOSession(**session) if isinstance(session, dict) else session
        self._exec("""INSERT OR REPLACE INTO sandbox_v2_sso_sessions (
            session_id, principal_id, principal_type, provider_config_id,
            external_identity_id, organization_id, workspace_id, roles_json, scopes_json,
            status, created_at, expires_at, revoked_at, metadata_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", [
            s.session_id, s.principal_id, s.principal_type, s.provider_config_id,
            s.external_identity_id, s.organization_id, s.workspace_id,
            json.dumps(s.roles or [], ensure_ascii=False),
            json.dumps(s.scopes or [], ensure_ascii=False),
            s.status,
            s.created_at.isoformat() if hasattr(s.created_at, 'isoformat') else str(s.created_at),
            s.expires_at.isoformat() if hasattr(s.expires_at, 'isoformat') else str(s.expires_at),
            s.revoked_at.isoformat() if s.revoked_at and hasattr(s.revoked_at, 'isoformat') else None,
            json.dumps(getattr(s, 'metadata', {}) or {}, ensure_ascii=False),
        ]); self._db.conn.commit(); return s

    def get_sso_session(self, session_id: str) -> Any | None:
        row = next(self._exec("SELECT * FROM sandbox_v2_sso_sessions WHERE session_id=?", [session_id]), None)
        return self._row_to_sso_session(dict(row)) if row else None

    def list_sso_sessions(self, organization_id: str | None = None, workspace_id: str | None = None,
                          status: str | None = None, limit: int = 50) -> list[Any]:
        limit = min(max(int(limit or 50), 1), 100)
        q = "SELECT * FROM sandbox_v2_sso_sessions WHERE 1=1"; params: list[Any] = []
        if organization_id: q += " AND organization_id = ?"; params.append(organization_id)
        if workspace_id: q += " AND workspace_id = ?"; params.append(workspace_id)
        if status: q += " AND status = ?"; params.append(status)
        q += " ORDER BY created_at DESC LIMIT ?"; params.append(limit)
        return [self._row_to_sso_session(dict(r)) for r in self._exec(q, params)]

    def revoke_sso_session(self, session_id: str, reason: str | None = None) -> Any | None:
        now = datetime.now(timezone.utc).isoformat()
        self._exec("UPDATE sandbox_v2_sso_sessions SET status='revoked', revoked_at=? WHERE session_id=?", [now, session_id])
        self._db.conn.commit()
        return self.get_sso_session(session_id)

    # ── Step 20 row converters ──

    def list_oidc_auth_requests(self, provider_config_id: str | None = None, limit: int = 50) -> list[Any]:
        limit = min(max(int(limit or 50), 1), 100)
        q = "SELECT * FROM sandbox_v2_oidc_auth_requests WHERE 1=1"; params: list[Any] = []
        if provider_config_id: q += " AND provider_config_id = ?"; params.append(provider_config_id)
        q += " ORDER BY created_at DESC LIMIT ?"; params.append(limit)
        return [dict(r) for r in self._exec(q, params)]

    def list_oidc_callback_results(self, provider_config_id: str | None = None, limit: int = 50) -> list[Any]:
        limit = min(max(int(limit or 50), 1), 100)
        q = "SELECT * FROM sandbox_v2_oidc_callback_results WHERE 1=1"; params: list[Any] = []
        if provider_config_id: q += " AND provider_config_id = ?"; params.append(provider_config_id)
        q += " ORDER BY created_at DESC LIMIT ?"; params.append(limit)
        return [dict(r) for r in self._exec(q, params)]

    def list_saml_auth_requests(self, provider_config_id: str | None = None, limit: int = 50) -> list[Any]:
        limit = min(max(int(limit or 50), 1), 100)
        q = "SELECT * FROM sandbox_v2_saml_auth_requests WHERE 1=1"; params: list[Any] = []
        if provider_config_id: q += " AND provider_config_id = ?"; params.append(provider_config_id)
        q += " ORDER BY created_at DESC LIMIT ?"; params.append(limit)
        return [dict(r) for r in self._exec(q, params)]

    def list_saml_acs_results(self, provider_config_id: str | None = None, limit: int = 50) -> list[Any]:
        limit = min(max(int(limit or 50), 1), 100)
        q = "SELECT * FROM sandbox_v2_saml_acs_results WHERE 1=1"; params: list[Any] = []
        if provider_config_id: q += " AND provider_config_id = ?"; params.append(provider_config_id)
        q += " ORDER BY created_at DESC LIMIT ?"; params.append(limit)
        return [dict(r) for r in self._exec(q, params)]

    @staticmethod
    def _row_to_sso_state(row: dict[str, Any]) -> Any:
        from src.open_platform.sandbox_v2.models import SandboxV2SSOState
        return SandboxV2SSOState.from_dict({
            "sso_state_id": row.get("sso_state_id", ""), "flow_type": row.get("flow_type", "disabled"),
            "state_hash": row.get("state_hash", ""), "nonce_hash": row.get("nonce_hash", ""),
            "code_verifier_hash": row.get("code_verifier_hash", ""),
            "code_challenge": row.get("code_challenge", ""),
            "redirect_uri": row.get("redirect_uri", ""),
            "provider_config_id": row.get("provider_config_id", ""),
            "organization_id": row.get("organization_id", ""),
            "workspace_id": row.get("workspace_id", ""),
            "principal_hint": row.get("principal_hint", ""),
            "created_at": row.get("created_at"), "expires_at": row.get("expires_at"),
            "consumed_at": row.get("consumed_at"), "status": row.get("status", "created"),
            "metadata": json.loads(row.get("metadata_json", "{}") or "{}"),
        })

    @staticmethod
    def _row_to_sso_session(row: dict[str, Any]) -> Any:
        from src.open_platform.sandbox_v2.models import SandboxV2SSOSession
        return SandboxV2SSOSession.from_dict({
            "session_id": row.get("session_id", ""), "principal_id": row.get("principal_id", ""),
            "principal_type": row.get("principal_type", "user"),
            "provider_config_id": row.get("provider_config_id", ""),
            "external_identity_id": row.get("external_identity_id", ""),
            "organization_id": row.get("organization_id", ""),
            "workspace_id": row.get("workspace_id", ""),
            "roles": json.loads(row.get("roles_json", "[]") or "[]"),
            "scopes": json.loads(row.get("scopes_json", "[]") or "[]"),
            "status": row.get("status", "active"),
            "created_at": row.get("created_at"), "expires_at": row.get("expires_at"),
            "revoked_at": row.get("revoked_at"),
            "metadata": json.loads(row.get("metadata_json", "{}") or "{}"),
        })
