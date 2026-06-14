-- Sandbox v2 PostgreSQL Schema
-- Step 12 — Production Backend Migration
--
-- 用法 (仅参考，不强制):
--   psql -U sandbox_v2 -d sandbox_v2 -f docs/sql/sandbox_v2_postgres_schema.sql
--
-- 说明:
-- 1. 此 schema 覆盖当前 SQLite 中所有 Sandbox v2 表。
-- 2. 不存储 artifact 大文件内容，只存 metadata。
-- 3. 所有 ID 字段使用 TEXT (UUID)，与 SQLite 保持一致。
-- 4. 索引覆盖 organization_id, workspace_id, job_id, status, created_at。
-- 5. 本 schema 不包含数据迁移逻辑。

BEGIN;

-- ══════════════════════════════════════════════════════════════════════
-- 1. Jobs
-- ══════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS sandbox_v2_jobs (
    job_id            TEXT PRIMARY KEY,
    organization_id   TEXT NOT NULL DEFAULT '',
    workspace_id      TEXT NOT NULL DEFAULT '',
    agent_id          TEXT NOT NULL DEFAULT '',
    requested_by      TEXT NOT NULL DEFAULT '',
    mode              TEXT NOT NULL DEFAULT 'simulation',
    status            TEXT NOT NULL DEFAULT 'created',
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    requested_action  TEXT NOT NULL DEFAULT '',
    input_ref         TEXT NOT NULL DEFAULT '',
    policy_snapshot_json  TEXT NOT NULL DEFAULT '{}',
    risk_level        TEXT NOT NULL DEFAULT 'unknown',
    metadata_json     TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_sbxv2_jobs_org ON sandbox_v2_jobs(organization_id);
CREATE INDEX IF NOT EXISTS idx_sbxv2_jobs_ws ON sandbox_v2_jobs(workspace_id);
CREATE INDEX IF NOT EXISTS idx_sbxv2_jobs_status ON sandbox_v2_jobs(status);
CREATE INDEX IF NOT EXISTS idx_sbxv2_jobs_created ON sandbox_v2_jobs(created_at);


-- ══════════════════════════════════════════════════════════════════════
-- 2. Execution Records
-- ══════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS sandbox_v2_execution_records (
    record_id         TEXT PRIMARY KEY,
    job_id            TEXT NOT NULL,
    status            TEXT NOT NULL DEFAULT 'created',
    mode              TEXT NOT NULL DEFAULT 'simulation',
    started_at        TIMESTAMPTZ,
    finished_at       TIMESTAMPTZ,
    duration_ms       INTEGER NOT NULL DEFAULT 0,
    decision          TEXT NOT NULL DEFAULT 'deny',
    reason            TEXT NOT NULL DEFAULT '',
    stdout_ref        TEXT NOT NULL DEFAULT '',
    stderr_ref        TEXT NOT NULL DEFAULT '',
    artifact_refs_json  TEXT NOT NULL DEFAULT '[]',
    audit_refs_json   TEXT NOT NULL DEFAULT '[]',
    error_code        TEXT NOT NULL DEFAULT '',
    error_message     TEXT NOT NULL DEFAULT '',
    no_real_execution BOOLEAN NOT NULL DEFAULT TRUE,
    metadata_json     TEXT NOT NULL DEFAULT '{}',
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sbxv2_exec_job ON sandbox_v2_execution_records(job_id);
CREATE INDEX IF NOT EXISTS idx_sbxv2_exec_status ON sandbox_v2_execution_records(status);
CREATE INDEX IF NOT EXISTS idx_sbxv2_exec_created ON sandbox_v2_execution_records(created_at);


-- ══════════════════════════════════════════════════════════════════════
-- 3. Queue Items
-- ══════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS sandbox_v2_queue_items (
    queue_id          TEXT PRIMARY KEY,
    job_id            TEXT NOT NULL UNIQUE,
    organization_id   TEXT NOT NULL DEFAULT '',
    workspace_id      TEXT NOT NULL DEFAULT '',
    priority          INTEGER NOT NULL DEFAULT 100,
    status            TEXT NOT NULL DEFAULT 'queued',
    attempts          INTEGER NOT NULL DEFAULT 0,
    max_attempts      INTEGER NOT NULL DEFAULT 3,
    available_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    leased_by         TEXT NOT NULL DEFAULT '',
    leased_until      TIMESTAMPTZ,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_error        TEXT NOT NULL DEFAULT '',
    dead_letter_reason TEXT NOT NULL DEFAULT '',
    metadata_json     TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_sbxv2_queue_status ON sandbox_v2_queue_items(status);
CREATE INDEX IF NOT EXISTS idx_sbxv2_queue_job ON sandbox_v2_queue_items(job_id);
CREATE INDEX IF NOT EXISTS idx_sbxv2_queue_lease ON sandbox_v2_queue_items(leased_until);
CREATE INDEX IF NOT EXISTS idx_sbxv2_queue_priority ON sandbox_v2_queue_items(priority, available_at);


-- ══════════════════════════════════════════════════════════════════════
-- 4. Worker Heartbeats
-- ══════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS sandbox_v2_worker_heartbeats (
    worker_id         TEXT PRIMARY KEY,
    status            TEXT NOT NULL DEFAULT 'idle',
    current_job_id    TEXT NOT NULL DEFAULT '',
    started_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_heartbeat_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_count   INTEGER NOT NULL DEFAULT 0,
    failed_count      INTEGER NOT NULL DEFAULT 0,
    canceled_count    INTEGER NOT NULL DEFAULT 0,
    metadata_json     TEXT NOT NULL DEFAULT '{}'
);


-- ══════════════════════════════════════════════════════════════════════
-- 5. Artifacts (metadata only)
-- ══════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS sandbox_v2_artifacts (
    artifact_id       TEXT PRIMARY KEY,
    job_id            TEXT NOT NULL DEFAULT '',
    organization_id   TEXT NOT NULL DEFAULT '',
    workspace_id      TEXT NOT NULL DEFAULT '',
    record_id         TEXT NOT NULL DEFAULT '',
    artifact_type     TEXT NOT NULL DEFAULT 'unknown',
    name              TEXT NOT NULL DEFAULT '',
    original_filename TEXT NOT NULL DEFAULT '',
    safe_filename     TEXT NOT NULL DEFAULT '',
    storage_key       TEXT NOT NULL DEFAULT '',
    storage_backend   TEXT NOT NULL DEFAULT 'local',
    size_bytes        INTEGER NOT NULL DEFAULT 0,
    mime_type         TEXT NOT NULL DEFAULT '',
    sha256            TEXT NOT NULL DEFAULT '',
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    materialized_at   TIMESTAMPTZ,
    read_only         BOOLEAN NOT NULL DEFAULT TRUE,
    status            TEXT NOT NULL DEFAULT 'pending',
    retention_until   TIMESTAMPTZ,
    risk_level        TEXT NOT NULL DEFAULT 'unknown',
    policy_decision_id TEXT NOT NULL DEFAULT '',
    audit_refs_json   TEXT NOT NULL DEFAULT '[]',
    metadata_json     TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_sbxv2_art_job ON sandbox_v2_artifacts(job_id);
CREATE INDEX IF NOT EXISTS idx_sbxv2_art_org ON sandbox_v2_artifacts(organization_id);
CREATE INDEX IF NOT EXISTS idx_sbxv2_art_status ON sandbox_v2_artifacts(status);


-- ══════════════════════════════════════════════════════════════════════
-- 6. Artifact Manifests
-- ══════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS sandbox_v2_artifact_manifests (
    manifest_id       TEXT PRIMARY KEY,
    job_id            TEXT NOT NULL DEFAULT '',
    record_id         TEXT NOT NULL DEFAULT '',
    artifact_ids_json TEXT NOT NULL DEFAULT '[]',
    total_size_bytes  INTEGER NOT NULL DEFAULT 0,
    artifact_count    INTEGER NOT NULL DEFAULT 0,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    sealed            BOOLEAN NOT NULL DEFAULT FALSE,
    sha256            TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_sbxv2_man_job ON sandbox_v2_artifact_manifests(job_id);


-- ══════════════════════════════════════════════════════════════════════
-- 7. Package Requests
-- ══════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS sandbox_v2_package_requests (
    package_request_id  TEXT PRIMARY KEY,
    job_id              TEXT NOT NULL DEFAULT '',
    organization_id     TEXT NOT NULL DEFAULT '',
    workspace_id        TEXT NOT NULL DEFAULT '',
    requested_by        TEXT NOT NULL DEFAULT '',
    package_name        TEXT NOT NULL DEFAULT '',
    package_version     TEXT NOT NULL DEFAULT '',
    package_manager     TEXT NOT NULL DEFAULT 'unknown',
    source_url          TEXT NOT NULL DEFAULT '',
    source_type         TEXT NOT NULL DEFAULT 'unknown',
    requested_action    TEXT NOT NULL DEFAULT '',
    expected_sha256     TEXT NOT NULL DEFAULT '',
    expected_signature  TEXT NOT NULL DEFAULT '',
    sbom_ref            TEXT NOT NULL DEFAULT '',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status              TEXT NOT NULL DEFAULT 'requested',
    risk_level          TEXT NOT NULL DEFAULT 'unknown',
    policy_decision_id  TEXT NOT NULL DEFAULT '',
    reason              TEXT NOT NULL DEFAULT '',
    metadata_json       TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_sbxv2_pkg_job ON sandbox_v2_package_requests(job_id);
CREATE INDEX IF NOT EXISTS idx_sbxv2_pkg_org ON sandbox_v2_package_requests(organization_id);
CREATE INDEX IF NOT EXISTS idx_sbxv2_pkg_status ON sandbox_v2_package_requests(status);


-- ══════════════════════════════════════════════════════════════════════
-- 8. Package Quarantine
-- ══════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS sandbox_v2_package_quarantine (
    quarantine_id       TEXT PRIMARY KEY,
    package_request_id  TEXT NOT NULL DEFAULT '',
    job_id              TEXT NOT NULL DEFAULT '',
    organization_id     TEXT NOT NULL DEFAULT '',
    workspace_id        TEXT NOT NULL DEFAULT '',
    package_name        TEXT NOT NULL DEFAULT '',
    package_version     TEXT NOT NULL DEFAULT '',
    package_manager     TEXT NOT NULL DEFAULT 'unknown',
    storage_key         TEXT NOT NULL DEFAULT '',
    size_bytes          INTEGER NOT NULL DEFAULT 0,
    sha256              TEXT NOT NULL DEFAULT '',
    signature_status    TEXT NOT NULL DEFAULT 'not_provided',
    sbom_status         TEXT NOT NULL DEFAULT 'not_provided',
    vulnerability_status TEXT NOT NULL DEFAULT 'not_scanned',
    status              TEXT NOT NULL DEFAULT 'quarantined',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    reviewed_at         TIMESTAMPTZ,
    reviewed_by         TEXT NOT NULL DEFAULT '',
    release_decision    TEXT NOT NULL DEFAULT '',
    reason              TEXT NOT NULL DEFAULT '',
    metadata_json       TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_sbxv2_quar_pkg ON sandbox_v2_package_quarantine(package_request_id);
CREATE INDEX IF NOT EXISTS idx_sbxv2_quar_status ON sandbox_v2_package_quarantine(status);


-- ══════════════════════════════════════════════════════════════════════
-- 9. Package SBOMs
-- ══════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS sandbox_v2_package_sboms (
    sbom_id             TEXT PRIMARY KEY,
    package_request_id  TEXT NOT NULL DEFAULT '',
    package_name        TEXT NOT NULL DEFAULT '',
    package_version     TEXT NOT NULL DEFAULT '',
    format              TEXT NOT NULL DEFAULT 'unknown',
    content_sha256      TEXT NOT NULL DEFAULT '',
    component_count     INTEGER NOT NULL DEFAULT 0,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    storage_key         TEXT NOT NULL DEFAULT '',
    status              TEXT NOT NULL DEFAULT 'provided',
    metadata_json       TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_sbxv2_sbom_pkg ON sandbox_v2_package_sboms(package_request_id);


-- ══════════════════════════════════════════════════════════════════════
-- 10. Package Vulnerability Scans
-- ══════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS sandbox_v2_package_scans (
    scan_id             TEXT PRIMARY KEY,
    package_request_id  TEXT NOT NULL DEFAULT '',
    package_name        TEXT NOT NULL DEFAULT '',
    package_version     TEXT NOT NULL DEFAULT '',
    scanner             TEXT NOT NULL DEFAULT 'fixture',
    status              TEXT NOT NULL DEFAULT 'not_scanned',
    severity_summary    TEXT NOT NULL DEFAULT '{}',
    critical_count      INTEGER NOT NULL DEFAULT 0,
    high_count          INTEGER NOT NULL DEFAULT 0,
    medium_count        INTEGER NOT NULL DEFAULT 0,
    low_count           INTEGER NOT NULL DEFAULT 0,
    findings_json       TEXT NOT NULL DEFAULT '[]',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata_json       TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_sbxv2_scan_pkg ON sandbox_v2_package_scans(package_request_id);


-- ══════════════════════════════════════════════════════════════════════
-- 11. Network Egress Requests
-- ══════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS sandbox_v2_network_egress_requests (
    egress_request_id   TEXT PRIMARY KEY,
    job_id              TEXT NOT NULL DEFAULT '',
    organization_id     TEXT NOT NULL DEFAULT '',
    workspace_id        TEXT NOT NULL DEFAULT '',
    requested_by        TEXT NOT NULL DEFAULT '',
    url                 TEXT NOT NULL DEFAULT '',
    scheme              TEXT NOT NULL DEFAULT '',
    hostname            TEXT NOT NULL DEFAULT '',
    port                INTEGER NOT NULL DEFAULT 443,
    resolved_ips_json   TEXT NOT NULL DEFAULT '[]',
    method              TEXT NOT NULL DEFAULT 'GET',
    purpose             TEXT NOT NULL DEFAULT '',
    requested_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status              TEXT NOT NULL DEFAULT 'pending',
    risk_level          TEXT NOT NULL DEFAULT 'unknown',
    policy_decision_id  TEXT NOT NULL DEFAULT '',
    reason              TEXT NOT NULL DEFAULT '',
    metadata_json       TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_sbxv2_egress_job ON sandbox_v2_network_egress_requests(job_id);
CREATE INDEX IF NOT EXISTS idx_sbxv2_egress_status ON sandbox_v2_network_egress_requests(status);


-- ══════════════════════════════════════════════════════════════════════
-- 12. Network Egress Audit Records
-- ══════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS sandbox_v2_network_egress_audit (
    audit_id            TEXT PRIMARY KEY,
    egress_request_id   TEXT NOT NULL DEFAULT '',
    job_id              TEXT NOT NULL DEFAULT '',
    organization_id     TEXT NOT NULL DEFAULT '',
    workspace_id        TEXT NOT NULL DEFAULT '',
    url                 TEXT NOT NULL DEFAULT '',
    hostname            TEXT NOT NULL DEFAULT '',
    resolved_ips_json   TEXT NOT NULL DEFAULT '[]',
    decision            TEXT NOT NULL DEFAULT '',
    reason              TEXT NOT NULL DEFAULT '',
    risk_level          TEXT NOT NULL DEFAULT '',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata_json       TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_sbxv2_audit_egress ON sandbox_v2_network_egress_audit(egress_request_id);
CREATE INDEX IF NOT EXISTS idx_sbxv2_audit_job ON sandbox_v2_network_egress_audit(job_id);


-- ══════════════════════════════════════════════════════════════════════
-- 13. Isolation Capabilities
-- ══════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS sandbox_v2_isolation_capabilities (
    capability_id       TEXT PRIMARY KEY,
    provider            TEXT NOT NULL DEFAULT '',
    available           BOOLEAN NOT NULL DEFAULT FALSE,
    enabled             BOOLEAN NOT NULL DEFAULT FALSE,
    reason              TEXT NOT NULL DEFAULT '',
    platform            TEXT NOT NULL DEFAULT '',
    os_name             TEXT NOT NULL DEFAULT '',
    is_windows          BOOLEAN NOT NULL DEFAULT FALSE,
    is_linux            BOOLEAN NOT NULL DEFAULT FALSE,
    has_docker          BOOLEAN NOT NULL DEFAULT FALSE,
    has_podman          BOOLEAN NOT NULL DEFAULT FALSE,
    has_firecracker     BOOLEAN NOT NULL DEFAULT FALSE,
    has_user_namespace  BOOLEAN NOT NULL DEFAULT FALSE,
    has_cgroup          BOOLEAN NOT NULL DEFAULT FALSE,
    has_seccomp         BOOLEAN NOT NULL DEFAULT FALSE,
    has_apparmor        BOOLEAN NOT NULL DEFAULT FALSE,
    has_selinux         BOOLEAN NOT NULL DEFAULT FALSE,
    checked_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata_json       TEXT NOT NULL DEFAULT '{}'
);


-- ══════════════════════════════════════════════════════════════════════
-- 14. Execution Plans
-- ══════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS sandbox_v2_execution_plans (
    execution_plan_id   TEXT PRIMARY KEY,
    job_id              TEXT NOT NULL DEFAULT '',
    organization_id     TEXT NOT NULL DEFAULT '',
    workspace_id        TEXT NOT NULL DEFAULT '',
    provider            TEXT NOT NULL DEFAULT 'trusted_fixture',
    mode                TEXT NOT NULL DEFAULT 'simulation',
    command_ref         TEXT NOT NULL DEFAULT '',
    image_ref           TEXT NOT NULL DEFAULT '',
    resource_limits_json TEXT NOT NULL DEFAULT '{}',
    allow_network       BOOLEAN NOT NULL DEFAULT FALSE,
    allow_filesystem_write BOOLEAN NOT NULL DEFAULT FALSE,
    allow_package_install BOOLEAN NOT NULL DEFAULT FALSE,
    allow_artifact_writable BOOLEAN NOT NULL DEFAULT FALSE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status              TEXT NOT NULL DEFAULT 'created',
    reason              TEXT NOT NULL DEFAULT '',
    metadata_json       TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_sbxv2_ep_job ON sandbox_v2_execution_plans(job_id);
CREATE INDEX IF NOT EXISTS idx_sbxv2_ep_status ON sandbox_v2_execution_plans(status);


-- ══════════════════════════════════════════════════════════════════════
-- 15. Container Execution Plans
-- ══════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS sandbox_v2_container_plans (
    container_plan_id   TEXT PRIMARY KEY,
    execution_plan_id   TEXT NOT NULL DEFAULT '',
    job_id              TEXT NOT NULL DEFAULT '',
    provider            TEXT NOT NULL DEFAULT 'docker_rootless_future',
    runtime             TEXT NOT NULL DEFAULT 'unavailable',
    image               TEXT NOT NULL DEFAULT '',
    fixture_id          TEXT NOT NULL DEFAULT '',
    command_json        TEXT NOT NULL DEFAULT '[]',
    network_mode        TEXT NOT NULL DEFAULT 'none',
    readonly_rootfs     BOOLEAN NOT NULL DEFAULT TRUE,
    run_user            TEXT NOT NULL DEFAULT 'nonroot',
    timeout_seconds     INTEGER NOT NULL DEFAULT 30,
    memory_limit_mb     INTEGER NOT NULL DEFAULT 512,
    cpu_limit           REAL NOT NULL DEFAULT 1.0,
    pids_limit          INTEGER NOT NULL DEFAULT 256,
    status              TEXT NOT NULL DEFAULT 'created',
    reason              TEXT NOT NULL DEFAULT '',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata_json       TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_sbxv2_cp_job ON sandbox_v2_container_plans(job_id);
CREATE INDEX IF NOT EXISTS idx_sbxv2_cp_status ON sandbox_v2_container_plans(status);


-- ══════════════════════════════════════════════════════════════════════
-- 16. Container Execution Results
-- ══════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS sandbox_v2_container_results (
    container_result_id TEXT PRIMARY KEY,
    container_plan_id   TEXT NOT NULL DEFAULT '',
    execution_plan_id   TEXT NOT NULL DEFAULT '',
    job_id              TEXT NOT NULL DEFAULT '',
    provider            TEXT NOT NULL DEFAULT '',
    runtime             TEXT NOT NULL DEFAULT '',
    status              TEXT NOT NULL DEFAULT '',
    exit_code           INTEGER NOT NULL DEFAULT 0,
    started_at          TIMESTAMPTZ,
    finished_at         TIMESTAMPTZ,
    duration_ms         INTEGER NOT NULL DEFAULT 0,
    stdout_text         TEXT NOT NULL DEFAULT '',
    stderr_text         TEXT NOT NULL DEFAULT '',
    stdout_artifact_id  TEXT NOT NULL DEFAULT '',
    stderr_artifact_id  TEXT NOT NULL DEFAULT '',
    timeout             BOOLEAN NOT NULL DEFAULT FALSE,
    canceled            BOOLEAN NOT NULL DEFAULT FALSE,
    reason              TEXT NOT NULL DEFAULT '',
    metadata_json       TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_sbxv2_cr_job ON sandbox_v2_container_results(job_id);
CREATE INDEX IF NOT EXISTS idx_sbxv2_cr_cp ON sandbox_v2_container_results(container_plan_id);


-- ══════════════════════════════════════════════════════════════════════
-- 17. Kill Requests
-- ══════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS sandbox_v2_kill_requests (
    kill_request_id     TEXT PRIMARY KEY,
    job_id              TEXT NOT NULL DEFAULT '',
    execution_plan_id   TEXT NOT NULL DEFAULT '',
    container_plan_id   TEXT NOT NULL DEFAULT '',
    organization_id     TEXT NOT NULL DEFAULT '',
    workspace_id        TEXT NOT NULL DEFAULT '',
    requested_by        TEXT NOT NULL DEFAULT '',
    reason              TEXT NOT NULL DEFAULT '',
    scope               TEXT NOT NULL DEFAULT '',
    target_type         TEXT NOT NULL DEFAULT '',
    target_id           TEXT NOT NULL DEFAULT '',
    force               BOOLEAN NOT NULL DEFAULT FALSE,
    requested_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status              TEXT NOT NULL DEFAULT 'pending',
    metadata_json       TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_sbxv2_kr_job ON sandbox_v2_kill_requests(job_id);
CREATE INDEX IF NOT EXISTS idx_sbxv2_kr_status ON sandbox_v2_kill_requests(status);


-- ══════════════════════════════════════════════════════════════════════
-- 18. Kill Records
-- ══════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS sandbox_v2_kill_records (
    kill_record_id      TEXT PRIMARY KEY,
    kill_request_id     TEXT NOT NULL DEFAULT '',
    job_id              TEXT NOT NULL DEFAULT '',
    provider            TEXT NOT NULL DEFAULT '',
    target_type         TEXT NOT NULL DEFAULT '',
    target_id           TEXT NOT NULL DEFAULT '',
    action_taken        TEXT NOT NULL DEFAULT '',
    status_before       TEXT NOT NULL DEFAULT '',
    status_after        TEXT NOT NULL DEFAULT '',
    provider_result     TEXT NOT NULL DEFAULT '',
    error_message       TEXT NOT NULL DEFAULT '',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sbxv2_krec_job ON sandbox_v2_kill_records(job_id);
CREATE INDEX IF NOT EXISTS idx_sbxv2_krec_kr ON sandbox_v2_kill_records(kill_request_id);


-- ══════════════════════════════════════════════════════════════════════
-- 19. Active Execution Handles
-- ══════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS sandbox_v2_active_handles (
    handle_id           TEXT PRIMARY KEY,
    job_id              TEXT NOT NULL DEFAULT '',
    provider            TEXT NOT NULL DEFAULT '',
    target_type         TEXT NOT NULL DEFAULT '',
    target_id           TEXT NOT NULL DEFAULT '',
    status              TEXT NOT NULL DEFAULT 'active',
    started_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    timeout_at          TIMESTAMPTZ,
    cancel_requested    BOOLEAN NOT NULL DEFAULT FALSE,
    cancel_reason       TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_sbxv2_ah_job ON sandbox_v2_active_handles(job_id);
CREATE INDEX IF NOT EXISTS idx_sbxv2_ah_status ON sandbox_v2_active_handles(status);

-- ══════════════════════════════════════════════════════════════════════
-- 20. Performance Benchmark Configs (Step 16)
-- ══════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS sandbox_v2_benchmark_configs (
    benchmark_id        TEXT PRIMARY KEY,
    profile             TEXT NOT NULL DEFAULT 'small',
    targets_json        TEXT NOT NULL DEFAULT '[]',
    max_jobs            INTEGER NOT NULL DEFAULT 100,
    max_queue_items     INTEGER NOT NULL DEFAULT 100,
    max_artifacts       INTEGER NOT NULL DEFAULT 50,
    max_concurrency     INTEGER NOT NULL DEFAULT 4,
    timeout_seconds     INTEGER NOT NULL DEFAULT 60,
    cleanup_after_run   BOOLEAN NOT NULL DEFAULT TRUE,
    organization_id     TEXT NOT NULL DEFAULT '',
    workspace_id        TEXT NOT NULL DEFAULT '',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata_json       TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_sbxv2_bcfg_benchmark ON sandbox_v2_benchmark_configs(benchmark_id);
CREATE INDEX IF NOT EXISTS idx_sbxv2_bcfg_created ON sandbox_v2_benchmark_configs(created_at);


-- ══════════════════════════════════════════════════════════════════════
-- 21. Performance Benchmark Results (Step 16)
-- ══════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS sandbox_v2_benchmark_results (
    benchmark_result_id TEXT PRIMARY KEY,
    benchmark_id        TEXT NOT NULL DEFAULT '',
    target              TEXT NOT NULL DEFAULT '',
    status              TEXT NOT NULL DEFAULT 'created',
    started_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at         TIMESTAMPTZ,
    duration_ms         INTEGER NOT NULL DEFAULT 0,
    total_operations    INTEGER NOT NULL DEFAULT 0,
    success_count       INTEGER NOT NULL DEFAULT 0,
    failure_count       INTEGER NOT NULL DEFAULT 0,
    p50_ms              DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    p95_ms              DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    p99_ms              DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    ops_per_second      DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    warnings_json       TEXT NOT NULL DEFAULT '[]',
    blockers_json       TEXT NOT NULL DEFAULT '[]',
    metadata_json       TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_sbxv2_bres_benchmark ON sandbox_v2_benchmark_results(benchmark_id);
CREATE INDEX IF NOT EXISTS idx_sbxv2_bres_target ON sandbox_v2_benchmark_results(target);
CREATE INDEX IF NOT EXISTS idx_sbxv2_bres_started ON sandbox_v2_benchmark_results(started_at);


-- ══════════════════════════════════════════════════════════════════════
-- 22. Capacity Estimates (Step 16)
-- ══════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS sandbox_v2_capacity_estimates (
    capacity_id         TEXT PRIMARY KEY,
    generated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    profile             TEXT NOT NULL DEFAULT 'small',
    estimated_jobs_per_minute DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    estimated_queue_items_per_minute DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    estimated_artifact_metadata_per_minute DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    estimated_network_preflight_per_minute DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    sqlite_recommended_limit TEXT NOT NULL DEFAULT '',
    postgres_recommended_threshold TEXT NOT NULL DEFAULT '',
    redis_recommended_threshold TEXT NOT NULL DEFAULT '',
    minio_recommended_threshold TEXT NOT NULL DEFAULT '',
    bottlenecks_json    TEXT NOT NULL DEFAULT '[]',
    recommendations_json TEXT NOT NULL DEFAULT '[]',
    metadata_json       TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_sbxv2_cap_generated ON sandbox_v2_capacity_estimates(generated_at);
CREATE INDEX IF NOT EXISTS idx_sbxv2_cap_profile ON sandbox_v2_capacity_estimates(profile);

-- ══════════════════════════════════════════════════════════════════════
-- 23. IAM Provider Configs (Step 17)
-- ══════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS sandbox_v2_iam_provider_configs (
    provider_config_id          TEXT PRIMARY KEY,
    provider_type               TEXT NOT NULL DEFAULT 'disabled',
    protocol                    TEXT NOT NULL DEFAULT 'disabled',
    enabled                     BOOLEAN NOT NULL DEFAULT FALSE,
    issuer                      TEXT NOT NULL DEFAULT '',
    client_id                   TEXT NOT NULL DEFAULT '',
    client_secret_ref           TEXT NOT NULL DEFAULT '',
    jwks_uri                    TEXT NOT NULL DEFAULT '',
    discovery_enabled           BOOLEAN NOT NULL DEFAULT FALSE,
    saml_entity_id              TEXT NOT NULL DEFAULT '',
    saml_metadata_ref           TEXT NOT NULL DEFAULT '',
    jit_provisioning            BOOLEAN NOT NULL DEFAULT FALSE,
    default_role                TEXT NOT NULL DEFAULT 'viewer',
    allowed_domains_json        TEXT NOT NULL DEFAULT '[]',
    require_verified_email      BOOLEAN NOT NULL DEFAULT TRUE,
    external_group_mapping_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    organization_id             TEXT NOT NULL DEFAULT '',
    workspace_id                TEXT NOT NULL DEFAULT '',
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata_json               TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_sbxv2_iamcfg_org ON sandbox_v2_iam_provider_configs(organization_id);
CREATE INDEX IF NOT EXISTS idx_sbxv2_iamcfg_ws ON sandbox_v2_iam_provider_configs(workspace_id);
CREATE INDEX IF NOT EXISTS idx_sbxv2_iamcfg_created ON sandbox_v2_iam_provider_configs(created_at);

-- ══════════════════════════════════════════════════════════════════════
-- 24. External Identities (Step 17)
-- ══════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS sandbox_v2_external_identities (
    external_identity_id        TEXT PRIMARY KEY,
    provider_config_id          TEXT NOT NULL DEFAULT '',
    provider_type               TEXT NOT NULL DEFAULT 'disabled',
    external_subject            TEXT NOT NULL DEFAULT '',
    external_email              TEXT NOT NULL DEFAULT '',
    email_verified              BOOLEAN NOT NULL DEFAULT FALSE,
    external_groups_json        TEXT NOT NULL DEFAULT '[]',
    display_name                TEXT NOT NULL DEFAULT '',
    organization_id             TEXT NOT NULL DEFAULT '',
    workspace_id                TEXT NOT NULL DEFAULT '',
    linked_principal_id         TEXT NOT NULL DEFAULT '',
    status                      TEXT NOT NULL DEFAULT 'pending_review',
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at                TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata_json               TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_sbxv2_eid_org ON sandbox_v2_external_identities(organization_id);
CREATE INDEX IF NOT EXISTS idx_sbxv2_eid_ws ON sandbox_v2_external_identities(workspace_id);
CREATE INDEX IF NOT EXISTS idx_sbxv2_eid_provider ON sandbox_v2_external_identities(provider_config_id);
CREATE INDEX IF NOT EXISTS idx_sbxv2_eid_created ON sandbox_v2_external_identities(created_at);

-- ══════════════════════════════════════════════════════════════════════
-- 25. IAM Role Mappings (Step 17)
-- ══════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS sandbox_v2_iam_role_mappings (
    mapping_id                  TEXT PRIMARY KEY,
    provider_config_id          TEXT NOT NULL DEFAULT '',
    external_group              TEXT NOT NULL DEFAULT '',
    external_claim              TEXT NOT NULL DEFAULT '',
    sandbox_role                TEXT NOT NULL DEFAULT 'viewer',
    sandbox_scopes_json         TEXT NOT NULL DEFAULT '[]',
    organization_id             TEXT NOT NULL DEFAULT '',
    workspace_id                TEXT NOT NULL DEFAULT '',
    enabled                     BOOLEAN NOT NULL DEFAULT TRUE,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata_json               TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_sbxv2_irm_org ON sandbox_v2_iam_role_mappings(organization_id);
CREATE INDEX IF NOT EXISTS idx_sbxv2_irm_ws ON sandbox_v2_iam_role_mappings(workspace_id);
CREATE INDEX IF NOT EXISTS idx_sbxv2_irm_provider ON sandbox_v2_iam_role_mappings(provider_config_id);
CREATE INDEX IF NOT EXISTS idx_sbxv2_irm_created ON sandbox_v2_iam_role_mappings(created_at);

-- ══════════════════════════════════════════════════════════════════════
-- 26. IAM Mapping Decisions (Step 17)
-- ══════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS sandbox_v2_iam_mapping_decisions (
    decision_id                 TEXT PRIMARY KEY,
    allowed                     BOOLEAN NOT NULL DEFAULT FALSE,
    status                      TEXT NOT NULL DEFAULT 'rejected',
    reason                      TEXT NOT NULL DEFAULT 'Default deny.',
    principal_id                TEXT NOT NULL DEFAULT '',
    principal_type              TEXT NOT NULL DEFAULT 'anonymous',
    mapped_roles_json           TEXT NOT NULL DEFAULT '[]',
    mapped_scopes_json          TEXT NOT NULL DEFAULT '[]',
    organization_id             TEXT NOT NULL DEFAULT '',
    workspace_id                TEXT NOT NULL DEFAULT '',
    email_domain_allowed        BOOLEAN NOT NULL DEFAULT FALSE,
    email_verified              BOOLEAN NOT NULL DEFAULT FALSE,
    tenant_match                BOOLEAN NOT NULL DEFAULT FALSE,
    group_mapping_applied       BOOLEAN NOT NULL DEFAULT FALSE,
    jit_provisioning_required   BOOLEAN NOT NULL DEFAULT FALSE,
    fail_closed                 BOOLEAN NOT NULL DEFAULT TRUE,
    matched_rules_json          TEXT NOT NULL DEFAULT '[]',
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata_json               TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_sbxv2_imd_org ON sandbox_v2_iam_mapping_decisions(organization_id);
CREATE INDEX IF NOT EXISTS idx_sbxv2_imd_ws ON sandbox_v2_iam_mapping_decisions(workspace_id);
CREATE INDEX IF NOT EXISTS idx_sbxv2_imd_created ON sandbox_v2_iam_mapping_decisions(created_at);

-- ══════════════════════════════════════════════════════════════════════
-- 27. SSO Simulation Results (Step 17)
-- ══════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS sandbox_v2_sso_simulation_results (
    simulation_id               TEXT PRIMARY KEY,
    provider_config_id          TEXT NOT NULL DEFAULT '',
    protocol                    TEXT NOT NULL DEFAULT 'mock',
    login_status                TEXT NOT NULL DEFAULT 'disabled',
    claim_set_json              TEXT NOT NULL DEFAULT '{}',
    mapping_decision_json       TEXT NOT NULL DEFAULT '{}',
    security_context_json       TEXT NOT NULL DEFAULT '{}',
    audit_event_id              TEXT NOT NULL DEFAULT '',
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata_json               TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_sbxv2_sso_created ON sandbox_v2_sso_simulation_results(created_at);
CREATE INDEX IF NOT EXISTS idx_sbxv2_sso_provider ON sandbox_v2_sso_simulation_results(provider_config_id);

-- ══════════════════════════════════════════════════════════════════════
-- 28. Trace Spans (Step 18)
-- ══════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS sandbox_v2_trace_spans (
    span_id                 TEXT PRIMARY KEY,
    trace_id                TEXT NOT NULL DEFAULT '',
    parent_span_id          TEXT NOT NULL DEFAULT '',
    span_name               TEXT NOT NULL DEFAULT '',
    status                  TEXT NOT NULL DEFAULT 'ok',
    organization_id         TEXT NOT NULL DEFAULT '',
    workspace_id            TEXT NOT NULL DEFAULT '',
    resource_type           TEXT NOT NULL DEFAULT '',
    resource_id             TEXT NOT NULL DEFAULT '',
    started_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at             TIMESTAMPTZ,
    duration_ms             INTEGER NOT NULL DEFAULT 0,
    attributes_redacted_json TEXT NOT NULL DEFAULT '{}',
    events_redacted_json    TEXT NOT NULL DEFAULT '[]',
    metadata_json           TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_sbxv2_ts_org ON sandbox_v2_trace_spans(organization_id);
CREATE INDEX IF NOT EXISTS idx_sbxv2_ts_trace ON sandbox_v2_trace_spans(trace_id);
CREATE INDEX IF NOT EXISTS idx_sbxv2_ts_created ON sandbox_v2_trace_spans(started_at);

-- ══════════════════════════════════════════════════════════════════════
-- 29. Telemetry Export Records (Step 18)
-- ══════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS sandbox_v2_telemetry_export_records (
    export_record_id        TEXT PRIMARY KEY,
    provider                TEXT NOT NULL DEFAULT '',
    signal_type             TEXT NOT NULL DEFAULT 'metric',
    status                  TEXT NOT NULL DEFAULT 'disabled',
    organization_id         TEXT NOT NULL DEFAULT '',
    workspace_id            TEXT NOT NULL DEFAULT '',
    resource_type           TEXT NOT NULL DEFAULT '',
    resource_id             TEXT NOT NULL DEFAULT '',
    exported_count          INTEGER NOT NULL DEFAULT 0,
    rejected_count          INTEGER NOT NULL DEFAULT 0,
    reason                  TEXT NOT NULL DEFAULT '',
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata_json           TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_sbxv2_ter_provider ON sandbox_v2_telemetry_export_records(provider);
CREATE INDEX IF NOT EXISTS idx_sbxv2_ter_signal ON sandbox_v2_telemetry_export_records(signal_type);
CREATE INDEX IF NOT EXISTS idx_sbxv2_ter_created ON sandbox_v2_telemetry_export_records(created_at);

-- ══════════════════════════════════════════════════════════════════════
-- 30. Grafana Dashboard Specs (Step 18)
-- ══════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS sandbox_v2_grafana_dashboard_specs (
    dashboard_id            TEXT PRIMARY KEY,
    title                   TEXT NOT NULL DEFAULT '',
    version                 TEXT NOT NULL DEFAULT '1.0',
    panels_json             TEXT NOT NULL DEFAULT '[]',
    datasource              TEXT NOT NULL DEFAULT '${DS_PROMETHEUS}',
    tags_json               TEXT NOT NULL DEFAULT '[]',
    generated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata_json           TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_sbxv2_gds_generated ON sandbox_v2_grafana_dashboard_specs(generated_at);

-- ══════════════════════════════════════════════════════════════════════
-- 31. Load Test Configs (Step 19)
-- ══════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS sandbox_v2_load_test_configs (
    load_test_id            TEXT PRIMARY KEY,
    profile                 TEXT NOT NULL DEFAULT 'smoke',
    base_url_masked         TEXT NOT NULL DEFAULT '',
    targets_json            TEXT NOT NULL DEFAULT '[]',
    max_users               INTEGER NOT NULL DEFAULT 5,
    max_rps                 INTEGER NOT NULL DEFAULT 5,
    duration_seconds        INTEGER NOT NULL DEFAULT 30,
    timeout_seconds         INTEGER NOT NULL DEFAULT 5,
    allow_production        BOOLEAN NOT NULL DEFAULT FALSE,
    require_confirmation    BOOLEAN NOT NULL DEFAULT TRUE,
    organization_id         TEXT NOT NULL DEFAULT '',
    workspace_id            TEXT NOT NULL DEFAULT '',
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata_json           TEXT NOT NULL DEFAULT '{}'
);

-- 32. Load Test Results (Step 19)
CREATE TABLE IF NOT EXISTS sandbox_v2_load_test_results (
    load_test_result_id     TEXT PRIMARY KEY,
    load_test_id            TEXT NOT NULL DEFAULT '',
    target                  TEXT NOT NULL DEFAULT '',
    status                  TEXT NOT NULL DEFAULT 'created',
    started_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at             TIMESTAMPTZ,
    duration_ms             INTEGER NOT NULL DEFAULT 0,
    total_requests          INTEGER NOT NULL DEFAULT 0,
    success_count           INTEGER NOT NULL DEFAULT 0,
    failure_count           INTEGER NOT NULL DEFAULT 0,
    timeout_count           INTEGER NOT NULL DEFAULT 0,
    p50_ms                  DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    p95_ms                  DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    p99_ms                  DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    min_ms                  DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    max_ms                  DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    requests_per_second     DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    error_rate_percent      DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    warnings_json           TEXT NOT NULL DEFAULT '[]',
    blockers_json           TEXT NOT NULL DEFAULT '[]',
    metadata_json           TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_sbxv2_ltr_lt ON sandbox_v2_load_test_results(load_test_id);
CREATE INDEX IF NOT EXISTS idx_sbxv2_ltr_target ON sandbox_v2_load_test_results(target);

-- 33. SLO Definitions (Step 19)
CREATE TABLE IF NOT EXISTS sandbox_v2_slo_definitions (
    slo_id                  TEXT PRIMARY KEY,
    name                    TEXT NOT NULL DEFAULT '',
    description             TEXT NOT NULL DEFAULT '',
    target                  TEXT NOT NULL DEFAULT '',
    p95_ms                  INTEGER NOT NULL DEFAULT 500,
    p99_ms                  INTEGER NOT NULL DEFAULT 1500,
    error_rate_percent      DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    availability_percent    DOUBLE PRECISION NOT NULL DEFAULT 99.0,
    enabled                 BOOLEAN NOT NULL DEFAULT TRUE,
    organization_id         TEXT NOT NULL DEFAULT '',
    workspace_id            TEXT NOT NULL DEFAULT '',
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata_json           TEXT NOT NULL DEFAULT '{}'
);

-- 34. SLO Evaluations (Step 19)
CREATE TABLE IF NOT EXISTS sandbox_v2_slo_evaluations (
    slo_eval_id             TEXT PRIMARY KEY,
    slo_id                  TEXT NOT NULL DEFAULT '',
    load_test_id            TEXT NOT NULL DEFAULT '',
    status                  TEXT NOT NULL DEFAULT 'not_evaluated',
    target                  TEXT NOT NULL DEFAULT '',
    observed_p95_ms         DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    observed_p99_ms         DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    observed_error_rate_percent DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    observed_availability_percent DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    reason                  TEXT NOT NULL DEFAULT '',
    evaluated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata_json           TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_sbxv2_sloe_lt ON sandbox_v2_slo_evaluations(load_test_id);

-- 35. Capacity Plans (Step 19)
CREATE TABLE IF NOT EXISTS sandbox_v2_capacity_plans (
    capacity_plan_id        TEXT PRIMARY KEY,
    generated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    recommended_profile     TEXT NOT NULL DEFAULT 'small',
    recommended_backend     TEXT NOT NULL DEFAULT 'sqlite',
    recommended_workers     INTEGER NOT NULL DEFAULT 2,
    recommended_queue_backend TEXT NOT NULL DEFAULT 'sqlite',
    recommended_object_storage TEXT NOT NULL DEFAULT 'local',
    expected_daily_jobs     INTEGER NOT NULL DEFAULT 1000,
    expected_peak_rps       DOUBLE PRECISION NOT NULL DEFAULT 5.0,
    bottlenecks_json        TEXT NOT NULL DEFAULT '[]',
    scaling_recommendations_json TEXT NOT NULL DEFAULT '[]',
    risk_notes_json         TEXT NOT NULL DEFAULT '[]',
    metadata_json           TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_sbxv2_cp_gen ON sandbox_v2_capacity_plans(generated_at);

COMMIT;
