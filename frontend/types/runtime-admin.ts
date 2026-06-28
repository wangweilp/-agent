/** Runtime Admin — Step 23-G 类型定义 */

// ═══════════════════ Runtime Adapter ═══════════════════
export interface RuntimeAdapter {
  adapter_id: string;
  adapter_type: string;    // manifest_only | simulation | http_webhook | sandboxed_process | container
  name: string;
  description: string;
  supports_network: boolean;
  supports_user_data_read: boolean;
  supports_user_data_write: boolean;
  sandbox_required: boolean;
  max_timeout_ms: number;
  max_memory_mb: number;
  status: string;         // active | beta | disabled | deprecated
  version: string;
  config_schema: Record<string, unknown>;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

// ═══════════════════ Runtime Binding ═══════════════════
export interface DeveloperAgentRuntimeBinding {
  binding_id: string;
  marketplace_agent_id: string;
  submission_id: string | null;
  developer_id: string;
  tenant_id: string;
  adapter_id: string;
  adapter_type: string;
  runtime_status: string;  // pending | enabled | disabled | suspended
  sandbox_policy_id: string | null;
  enabled_by: string | null;
  disabled_by: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

// ═══════════════════ Eligibility ═══════════════════
export interface RuntimeEligibilityResult {
  eligible: boolean;
  code: string;
  message: string;
  marketplace_agent_id: string;
  binding_id: string | null;
  adapter_id: string | null;
  adapter_type: string | null;
  required_action: string | null;
  metadata: Record<string, unknown>;
}

// ═══════════════════ Sandbox Policy ═══════════════════
export interface SandboxPolicy {
  policy_id: string;
  name: string;
  description: string;
  scope: string;          // system | tenant
  tenant_id: string | null;
  sandbox_level: string;  // no_execution | simulation_only | restricted | isolated
  allow_network: boolean;
  allowed_domains: string[];
  allow_filesystem_read: boolean;
  allow_filesystem_write: boolean;
  allowed_paths: string[];
  allow_secrets: boolean;
  allowed_secret_names: string[];
  max_timeout_ms: number;
  max_memory_mb: number;
  max_cpu_percent: number;
  max_output_bytes: number;
  max_requests_per_minute: number;
  data_access_scope: string[];
  audit_enabled: boolean;
  kill_switch_enabled: boolean;
  status: string;         // active | disabled | deprecated
  system_managed: boolean;
  created_by: string | null;
  updated_by: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface SandboxPolicyTestRequest {
  sandbox_level: string;
  requested_network: boolean;
  requested_domains: string[];
  requested_filesystem_read: boolean;
  requested_filesystem_write: boolean;
  requested_secret_names: string[];
  requested_timeout_ms: number;
  requested_memory_mb: number;
  requested_data_access_scope: string[];
}

export interface SandboxPolicyTestResult {
  policy_id: string;
  decision: string;
  allowed: boolean;
  warnings: string[];
  violations: string[];
  evaluated_rules: string[];
  metadata: Record<string, unknown>;
}

// ═══════════════════ Package Validation ═══════════════════
export interface PackageValidationCheck {
  check_id: string;
  code: string;
  severity: string;  // info | warning | error | blocker
  passed: boolean;
  message: string;
  metadata: Record<string, unknown>;
}

export interface PackageValidationResult {
  validation_id: string;
  submission_id: string;
  tenant_id: string;
  requested_by: string;
  status: string;     // not_validated | passed | passed_with_warnings | failed | blocked
  source_type: string;
  package_url: string | null;
  repository_url: string | null;
  manifest_name: string;
  manifest_version: string;
  checks: PackageValidationCheck[];
  warnings: string[];
  errors: string[];
  blockers: string[];
  package_metadata: Record<string, unknown>;
  review_recommendation: string;
  no_download_performed: boolean;
  no_execution_performed: boolean;
  no_network_performed: boolean;
  summary: { total: number; passed: number; failed: number; warnings: number; errors: number; blockers: number };
  created_at: string;
  completed_at: string | null;
  metadata: Record<string, unknown>;
}

// ═══════════════════ API Response Wrappers ═══════════════════
export interface RuntimeAdaptersResponse { adapters: RuntimeAdapter[]; total: number; }
export interface RuntimeBindingsResponse { bindings: DeveloperAgentRuntimeBinding[]; total: number; }
export interface RuntimeBindingDetailResponse {
  binding: DeveloperAgentRuntimeBinding;
  adapter: RuntimeAdapter | null;
  eligibility: RuntimeEligibilityResult;
}
export interface RuntimeBindingActionResponse { binding: DeveloperAgentRuntimeBinding | null; message?: string; }
export interface SandboxPoliciesResponse { policies: SandboxPolicy[]; total: number; }
export interface PackageValidationResponse { validation: PackageValidationResult | null; }

export interface RuntimeGovernancePanel {
  title: string;
  status: string;
  enabled: boolean;
  mode: string;
  risk_level: string;
  last_checked_at: string;
  evidence: string[];
  reason: string;
  recommended_next_step: string;
  [key: string]: unknown;
}

export interface RuntimeGovernanceSummary {
  runtime_governance_status: string;
  current_mode: string;
  production_sandbox: string;
  default_policy: string;
  audit_first: boolean;
  boundary_statement: string;
  modules: {
    kill_switch: RuntimeGovernancePanel & {
      active?: boolean;
      latest_trigger?: Record<string, unknown> | null;
      policies?: Record<string, unknown>[];
    };
    incident_store: RuntimeGovernancePanel & {
      incidents?: Record<string, unknown>[];
    };
    package_download_worker_gate: RuntimeGovernancePanel & {
      recent_denials?: Record<string, unknown>[];
      policies?: Record<string, unknown>[];
    };
    artifact_materialization_gate: RuntimeGovernancePanel & {
      blocked_records?: Record<string, unknown>[];
      policies?: Record<string, unknown>[];
    };
    sandbox_execution_record: RuntimeGovernancePanel & {
      records?: Record<string, unknown>[];
    };
    red_team_result: RuntimeGovernancePanel & {
      results?: Record<string, unknown>[];
    };
    production_sandbox_gate: RuntimeGovernancePanel & {
      gate_result?: Record<string, unknown>;
      unmet_conditions?: string[];
      roadmap?: string[];
    };
  };
}

// ═══════════════════ Phase 4 — Security Control Plane Dashboard ═══════════════════

/** GET /admin/runtime/status — 安全控制面全局状态（模拟模式） */
export interface RuntimeControlPlaneStatus {
  status: string;              // "active"
  mode: string;                // 硬编码 "simulation"
  production_sandbox: string;  // "disabled"
  default_policy: string;      // "deny_by_default"
  boundary_statement: string;
  last_checked_at: string;
}

/** GET /admin/runtime/incidents — 模拟安全事件流 */
export interface RuntimeIncident {
  incident_id: string;
  timestamp: string;
  agent_id: string;
  severity: "critical" | "high" | "medium" | "low";
  incident_type: string;
  title: string;
  description: string;
  action_taken: string;        // blocked | throttled | allowed
  status: string;              // resolved | investigating | open
  policy_triggered: string;
  metadata_only: boolean;
}

export interface RuntimeIncidentsResponse {
  mode: string;
  total: number;
  incidents: RuntimeIncident[];
}

// ═══════════════════ Sandbox v2 (Step 1 — Core Contract) ═══════════════════

export interface SandboxV2SubmitJobRequest {
  organization_id?: string;
  workspace_id?: string;
  agent_id?: string;
  requested_by?: string;
  mode?: string;               // metadata_only | simulation | disabled
  requested_action?: string;
  input_ref?: string;
  metadata?: Record<string, unknown>;
}

export interface SandboxV2PolicyDecision {
  allowed: boolean;
  action: string;              // allow | deny | fail_closed
  reason: string;
  risk_level: string;          // low | medium | high | critical | unknown
  required_approvals: string[];
  matched_rules: string[];
  fail_closed: boolean;
  policy_snapshot: Record<string, unknown>;
}

export interface SandboxV2SubmitJobResponse {
  job_id: string | null;
  status: string;
  decision: SandboxV2PolicyDecision;
}

export interface SandboxV2Job {
  job_id: string;
  organization_id: string;
  workspace_id: string;
  agent_id: string;
  requested_by: string;
  mode: string;
  status: string;
  created_at: string;
  updated_at: string;
  requested_action: string;
  input_ref: string;
  policy_snapshot: Record<string, unknown>;
  risk_level: string;
  metadata: Record<string, unknown>;
}

export interface SandboxV2ExecutionRecord {
  record_id: string;
  job_id: string;
  status: string;
  mode: string;
  started_at: string | null;
  finished_at: string | null;
  duration_ms: number;
  decision: string;
  reason: string;
  stdout_ref: string;
  stderr_ref: string;
  artifact_refs: string[];
  audit_refs: string[];
  error_code: string;
  error_message: string;
  no_real_execution: boolean;
  metadata: Record<string, unknown>;
}

export interface SandboxV2CancelJobResponse {
  job_id: string;
  status: string;
  message: string;
  canceled: boolean;
  execution_record: SandboxV2ExecutionRecord | null;
}

export interface SandboxV2ReadinessResponse {
  sandbox_v2_core_contract: boolean;
  real_task_queue: boolean;
  worker_framework: boolean;
  process_kill: boolean;
  execution_isolation: boolean;
  network_isolation: boolean;
  filesystem_isolation: boolean;
  artifact_store: boolean;
  package_quarantine: boolean;
  external_package_download: boolean;
  public_registry_download: boolean;
  package_execution: boolean;
  package_installation: boolean;
  network_preflight: boolean;
  external_network_access: boolean;
  egress_proxy: boolean;
  execution_provider_abstraction: boolean;
  trusted_fixture_provider: boolean;
  untrusted_code_execution: boolean;
  docker_execution: boolean;
  podman_execution: boolean;
  microvm_execution: boolean;
  container_provider_abstraction: boolean;
  rootless_container_poc: boolean;
  container_execution_enabled: boolean;
  docker_available: boolean;
  podman_available: boolean;
  rootless_container_available: boolean;
  trusted_container_fixture_only: boolean;
  arbitrary_container_command: boolean;
  arbitrary_container_image: boolean;
  container_network_disabled: boolean;
  container_readonly_rootfs_required: boolean;
  container_no_new_privileges_required: boolean;
  container_cap_drop_all_required: boolean;
  kill_switch: boolean;
  kill_policy: boolean;
  active_execution_handles: boolean;
  queue_cancel: boolean;
  worker_cancel_checkpoints: boolean;
  provider_cancel_interface: boolean;
  process_kill_implemented: boolean;
  arbitrary_pid_kill: boolean;
  container_kill_enabled: boolean;
  docker_kill_available: boolean;
  podman_kill_available: boolean;
  red_team_suite: boolean;
  artifact_escape_tests: boolean;
  network_ssrf_tests: boolean;
  package_supply_chain_tests: boolean;
  kill_switch_abuse_tests: boolean;
  container_escape_tests: boolean;
  policy_fail_closed_tests: boolean;
  api_abuse_tests: boolean;
  worker_queue_abuse_tests: boolean;
  real_attack_execution: boolean;
  real_container_fixture_validation: boolean;
  real_container_fixture_enabled: boolean;
  real_container_fixture_runnable: boolean;
  auto_pull_images: boolean;
  user_command_execution: boolean;
  user_image_execution: boolean;
  network_enabled_in_container: boolean;
  current_execution_mode: string;
  allowed_modes: string[];
  boundary_statement: string;
  // Step 10 — Production Hardening
  production_hardening_docs: boolean;
  env_template_present: boolean;
  production_readiness_script: boolean;
  deployment_checklist_present: boolean;
  operations_runbook_present: boolean;
  incident_response_runbook_present: boolean;
  docker_compose_example_present: boolean;
  safe_defaults_configured: boolean;
  production_blockers: string[];
  warnings: string[];
  // Step 12 — Backend Readiness
  database_backend: string;
  database_backend_ready: boolean;
  postgres_adapter_available: boolean;
  postgres_dsn_configured: boolean;
  queue_backend: string;
  queue_backend_ready: boolean;
  redis_queue_adapter_available: boolean;
  redis_url_configured: boolean;
  object_storage_backend: string;
  object_storage_ready: boolean;
  minio_adapter_available: boolean;
  minio_endpoint_configured: boolean;
  local_fallback_enabled: boolean;
  production_backend_configured: boolean;
  backend_warnings: string[];
  backend_blockers: string[];
  // Step 11 — MicroVM / Firecracker
  microvm_provider_abstraction: boolean;
  firecracker_provider_abstraction: boolean;
  microvm_execution_enabled: boolean;
  microvm_integration_enabled: boolean;
  microvm_runnable: boolean;
  kvm_available: boolean;
  firecracker_binary_present: boolean;
  microvm_kernel_present: boolean;
  microvm_rootfs_present: boolean;
  microvm_network_enabled: boolean;
  user_kernel_allowed: boolean;
  user_rootfs_allowed: boolean;
  host_mounts_allowed: boolean;
  real_microvm_execution: boolean;
  // Step 13 — Backend Integration Testing
  backend_integration_tests_present: boolean;
  backend_integration_enabled: boolean;
  postgres_integration_ready: boolean;
  redis_integration_ready: boolean;
  minio_integration_ready: boolean;
  backend_integration_blockers: string[];
  backend_integration_warnings: string[];
  postgres_schema_initialized: boolean;
  backend_integration_last_run: string;
  // Step 14 — Security/Tenant/Audit
  security_context: boolean;
  access_policy_engine: boolean;
  rbac_scope_policy: boolean;
  tenant_isolation: boolean;
  cross_tenant_deny: boolean;
  security_audit_events: boolean;
  audit_hash_chain: boolean;
  evidence_bundle_export: boolean;
  sensitive_metadata_redaction: boolean;
  legacy_endpoint_enforcement: string;
  external_iam: boolean;
  sso_integration: boolean;
  // Step 15 — Monitoring / Alerts / Health
  metrics_collector: boolean;
  health_checks: boolean;
  alert_engine: boolean;
  internal_alert_records: boolean;
  prometheus_export: boolean;
  external_notifications: boolean;
  monitoring_dashboard: boolean;
  audit_signal_aggregation: boolean;
  alert_rules_present: boolean;
  monitoring_safe_mode: boolean;
  // Step 16 — Performance / Capacity
  performance_benchmarking: boolean;
  performance_tests_enabled: boolean;
  performance_benchmarks_enabled: boolean;
  performance_safe_profile: boolean;
  synthetic_fixture_only: boolean;
  external_load_testing: boolean;
  user_code_benchmarking: boolean;
  capacity_estimation: boolean;
  benchmark_cleanup_enabled: boolean;
  [key: string]: unknown;
}

export interface SandboxV2JobsListResponse {
  jobs: SandboxV2Job[];
  total: number;
}

export interface SandboxV2ExecutionRecordsListResponse {
  execution_records: SandboxV2ExecutionRecord[];
  total: number;
}

// ═══════════════════ Sandbox v2 Step 2 — Queue / Worker ═══════════════════

export interface SandboxV2QueueItem {
  queue_id: string;
  job_id: string;
  organization_id: string;
  workspace_id: string;
  priority: number;
  status: string;          // queued | leased | processing | completed | failed | canceled | timeout | dead_letter
  attempts: number;
  max_attempts: number;
  available_at: string;
  leased_by: string;
  leased_until: string | null;
  created_at: string;
  updated_at: string;
  last_error: string;
  dead_letter_reason: string;
  metadata: Record<string, unknown>;
}

export interface SandboxV2WorkerHeartbeat {
  worker_id: string;
  status: string;          // idle | processing | stopping | stopped | failed
  current_job_id: string;
  started_at: string;
  last_heartbeat_at: string;
  processed_count: number;
  failed_count: number;
  canceled_count: number;
  metadata: Record<string, unknown>;
}

export interface SandboxV2DeadLetterItem {
  queue_id: string;
  job_id: string;
  status: string;
  attempts: number;
  max_attempts: number;
  last_error: string;
  dead_letter_reason: string;
  created_at: string;
  updated_at: string;
}

export interface SandboxV2QueueStatusResponse {
  job_id: string;
  in_queue: boolean;
  queue_item?: SandboxV2QueueItem;
}

export interface SandboxV2WorkerRunOnceResult {
  message: string;
  result: {
    worker_id: string;
    job_id: string;
    status: string;
    execution_record_id: string;
    error_code: string;
    error_message: string;
    duration_ms: number;
  } | null;
}

export interface SandboxV2QueueListResponse {
  queue_items: SandboxV2QueueItem[];
  total: number;
}

export interface SandboxV2WorkersListResponse {
  workers: SandboxV2WorkerHeartbeat[];
  total: number;
}

export interface SandboxV2DeadLetterListResponse {
  dead_letter_items: SandboxV2DeadLetterItem[];
  total: number;
}

export interface SandboxV2RequeueResponse {
  requeued_count: number;
  message: string;
}

// ═══════════════════ Sandbox v2 Step 3 — Artifacts ═══════════════════

export interface SandboxV2Artifact {
  artifact_id: string;
  job_id: string;
  organization_id: string;
  workspace_id: string;
  record_id: string;
  artifact_type: string;       // stdout | stderr | log | report | json | text | input | output | diagnostic | unknown
  name: string;
  original_filename: string;
  safe_filename: string;
  storage_key: string;
  storage_backend: string;
  size_bytes: number;
  mime_type: string;
  sha256: string;
  created_at: string;
  materialized_at: string | null;
  read_only: boolean;
  status: string;              // pending | materialized | rejected | quarantined | deleted | expired | failed
  retention_until: string | null;
  risk_level: string;
  policy_decision_id: string;
  audit_refs: string[];
  metadata: Record<string, unknown>;
}

export interface SandboxV2ArtifactManifest {
  manifest_id: string;
  job_id: string;
  record_id: string;
  artifact_ids: string[];
  total_size_bytes: number;
  artifact_count: number;
  created_at: string;
  sealed: boolean;
  sha256: string;
}

export interface SandboxV2ArtifactMaterializationRequest {
  job_id?: string;
  record_id?: string;
  artifact_name: string;
  artifact_type?: string;
  content_text?: string;
  requested_by?: string;
  mime_type?: string;
  organization_id?: string;
  workspace_id?: string;
  metadata?: Record<string, unknown>;
}

export interface SandboxV2ArtifactPolicyDecision {
  allowed: boolean;
  reason: string;
  risk_level: string;
  max_size_bytes: number;
  allowed_mime_types: string[];
  read_only_required: boolean;
  fail_closed: boolean;
  matched_rules: string[];
}

export interface SandboxV2MaterializeArtifactResponse {
  artifact: SandboxV2Artifact;
  decision: SandboxV2ArtifactPolicyDecision;
  materialized: boolean;
}

export interface SandboxV2ArtifactContentResponse {
  artifact_id: string;
  content: string;
  size_bytes: number;
  mime_type: string;
  sha256: string;
}

export interface SandboxV2ArtifactsListResponse {
  artifacts: SandboxV2Artifact[];
  total: number;
}

// ═══════════════════ Sandbox v2 Step 4 — Package / Supply Chain ═══════════════════

export interface SandboxV2PackageRequest {
  package_request_id: string;
  job_id: string;
  organization_id: string;
  workspace_id: string;
  requested_by: string;
  package_name: string;
  package_version: string;
  package_manager: string;       // pip | npm | pnpm | yarn | cargo | maven | unknown
  source_url: string;
  source_type: string;           // offline_upload | internal_registry | external_url | public_registry | unknown
  requested_action: string;
  expected_sha256: string;
  expected_signature: string;
  sbom_ref: string;
  created_at: string;
  status: string;               // requested | rejected | quarantined | pending_review | approved_metadata_only | ...
  risk_level: string;
  policy_decision_id: string;
  reason: string;
  metadata: Record<string, unknown>;
}

export interface SandboxV2PackagePolicyDecision {
  allowed: boolean;
  action: string;
  reason: string;
  risk_level: string;
  require_hash: boolean;
  require_signature: boolean;
  require_sbom: boolean;
  require_vulnerability_scan: boolean;
  quarantine_required: boolean;
  network_download_allowed: boolean;
  matched_rules: string[];
  fail_closed: boolean;
}

export interface SandboxV2PackageQuarantineRecord {
  quarantine_id: string;
  package_request_id: string;
  job_id: string;
  organization_id: string;
  workspace_id: string;
  package_name: string;
  package_version: string;
  package_manager: string;
  storage_key: string;
  size_bytes: number;
  sha256: string;
  signature_status: string;      // not_provided | pending | verified | failed | unsupported
  sbom_status: string;           // not_provided | provided | verified | failed | unsupported
  vulnerability_status: string;  // not_scanned | clean | findings_low/medium/high/critical | scanner_unavailable
  status: string;               // quarantined | pending_scan | pending_review | approved | rejected | deleted
  created_at: string;
  reviewed_at: string | null;
  reviewed_by: string;
  release_decision: string;
  reason: string;
  metadata: Record<string, unknown>;
}

export interface SandboxV2PackageSBOM {
  sbom_id: string;
  package_request_id: string;
  package_name: string;
  package_version: string;
  format: string;               // cyclonedx-json | spdx-json | unknown
  content_sha256: string;
  component_count: number;
  created_at: string;
  storage_key: string;
  status: string;
  metadata: Record<string, unknown>;
}

export interface SandboxV2PackageVulnerabilityScanResult {
  scan_id: string;
  package_request_id: string;
  package_name: string;
  package_version: string;
  scanner: string;
  status: string;
  severity_summary: string;
  critical_count: number;
  high_count: number;
  medium_count: number;
  low_count: number;
  findings: Record<string, unknown>[];
  created_at: string;
  metadata: Record<string, unknown>;
}

export interface SandboxV2PackageRequestsListResponse {
  package_requests: SandboxV2PackageRequest[];
  total: number;
}

export interface SandboxV2QuarantineListResponse {
  quarantine_records: SandboxV2PackageQuarantineRecord[];
  total: number;
}

export interface SandboxV2SbomListResponse {
  sboms: SandboxV2PackageSBOM[];
  total: number;
}

export interface SandboxV2ScanListResponse {
  scans: SandboxV2PackageVulnerabilityScanResult[];
  total: number;
}

// ═══════════════════ Sandbox v2 Step 5 — Network Egress ═══════════════════

export interface SandboxV2NetworkEgressRequest {
  egress_request_id: string;
  job_id: string;
  organization_id: string;
  workspace_id: string;
  requested_by: string;
  url: string;
  scheme: string;
  hostname: string;
  port: number;
  resolved_ips: string[];
  method: string;
  purpose: string;
  requested_at: string;
  status: string;
  risk_level: string;
  policy_decision_id: string;
  reason: string;
  metadata: Record<string, unknown>;
}

export interface SandboxV2NetworkEgressPolicyDecision {
  allowed: boolean;
  action: string;
  reason: string;
  risk_level: string;
  scheme_allowed: boolean;
  host_allowed: boolean;
  ip_allowed: boolean;
  port_allowed: boolean;
  dns_resolution_allowed: boolean;
  metadata_service_blocked: boolean;
  private_network_blocked: boolean;
  matched_rules: string[];
  fail_closed: boolean;
}

export interface SandboxV2NetworkEgressAuditRecord {
  audit_id: string;
  egress_request_id: string;
  job_id: string;
  organization_id: string;
  workspace_id: string;
  url: string;
  hostname: string;
  resolved_ips: string[];
  decision: string;
  reason: string;
  risk_level: string;
  created_at: string;
  metadata: Record<string, unknown>;
}

export interface SandboxV2NetworkPolicyConfig {
  allow_network: boolean;
  allowed_domains: string[];
  denied_domains: string[];
  allowed_ports: number[];
  denied_ports: number[];
  allowed_schemes: string[];
  block_private_networks: boolean;
  block_loopback: boolean;
  block_link_local: boolean;
  block_metadata_service: boolean;
  require_dns_preflight: boolean;
  default_action: string;
}

export interface SandboxV2NetworkReadiness {
  network_egress_policy: boolean;
  network_preflight: boolean;
  external_network_access: boolean;
  egress_proxy: boolean;
  dns_runtime_resolution: boolean;
  private_network_blocking: boolean;
  metadata_service_blocking: boolean;
  localhost_blocking: boolean;
  allowed_domain_policy: boolean;
  ip_denylist_policy: boolean;
  runtime_network_namespace: boolean;
  iptables_enforcement: boolean;
  current_mode: string;
  no_real_network: boolean;
}

export interface SandboxV2EgressRequestsListResponse {
  egress_requests: SandboxV2NetworkEgressRequest[];
  total: number;
}

export interface SandboxV2AuditRecordsListResponse {
  audit_records: SandboxV2NetworkEgressAuditRecord[];
  total: number;
}

// ═══════════════════ Sandbox v2 Step 6A — Isolation / Execution ═══════════════════

export interface SandboxV2IsolationCapability {
  capability_id: string; provider: string; available: boolean; enabled: boolean;
  reason: string; platform: string; os_name: string;
  is_windows: boolean; is_linux: boolean;
  has_docker: boolean; has_podman: boolean; has_firecracker: boolean;
  has_gvisor: boolean; has_kata: boolean;
  has_user_namespace: boolean; has_cgroup: boolean; has_seccomp: boolean;
  has_apparmor: boolean; has_selinux: boolean;
  has_network_namespace: boolean; has_mount_namespace: boolean;
  checked_at: string; metadata: Record<string, unknown>;
}

export interface SandboxV2ExecutionPlan {
  execution_plan_id: string; job_id: string; organization_id: string;
  workspace_id: string; provider: string; mode: string;
  command_ref: string; image_ref: string;
  created_at: string; status: string; reason: string;
  metadata: Record<string, unknown>;
}

export interface SandboxV2IsolationDecision {
  allowed: boolean; provider: string; action: string; reason: string;
  risk_level: string; required_capabilities: string[];
  missing_capabilities: string[]; fail_closed: boolean;
  execution_allowed: boolean; network_allowed: boolean;
  filesystem_write_allowed: boolean; package_install_allowed: boolean;
  matched_rules: string[];
}

export interface SandboxV2TrustedFixtureExecutionResult {
  fixture_id: string; job_id: string; provider: string; status: string;
  started_at: string | null; finished_at: string | null; duration_ms: number;
  stdout_text: string; stderr_text: string; exit_code: number;
  artifact_refs: string[]; decision: string; reason: string;
  metadata: Record<string, unknown>;
}

export interface SandboxV2IsolationReadiness {
  isolation_capability_probe: boolean;
  execution_provider_abstraction: boolean;
  trusted_fixture_provider: boolean;
  untrusted_code_execution: boolean;
  platform: string; is_windows: boolean;
  capability: SandboxV2IsolationCapability;
  [key: string]: unknown;
}

export interface SandboxV2ExecutionPlansListResponse {
  execution_plans: SandboxV2ExecutionPlan[];
  total: number;
}

// ═══════════════════ Sandbox v2 Step 6B — Container Execution ═══════════════════

export interface SandboxV2ContainerRuntimeConfig {
  provider: string; runtime: string; enabled: boolean;
  rootless_required: boolean; network_disabled: boolean;
  readonly_rootfs: boolean; no_new_privileges: boolean;
  drop_all_capabilities: boolean; run_as_non_root: boolean;
  memory_limit_mb: number; cpu_limit: number; pids_limit: number;
  timeout_seconds: number; tmpfs_enabled: boolean;
  allowed_images: string[]; allowed_fixture_ids: string[];
  artifact_output_mode: string;
}

export interface SandboxV2ContainerExecutionPlan {
  container_plan_id: string; execution_plan_id: string; job_id: string;
  provider: string; runtime: string; image: string; fixture_id: string;
  command: string[]; network_mode: string; readonly_rootfs: boolean;
  user: string; timeout_seconds: number; status: string; reason: string;
  created_at: string; metadata: Record<string, unknown>;
}

export interface SandboxV2ContainerExecutionResult {
  container_result_id: string; container_plan_id: string;
  execution_plan_id: string; job_id: string; provider: string;
  runtime: string; status: string; exit_code: number;
  started_at: string | null; finished_at: string | null; duration_ms: number;
  stdout_text: string; stderr_text: string;
  stdout_artifact_id: string; stderr_artifact_id: string;
  timeout: boolean; canceled: boolean; reason: string;
  metadata: Record<string, unknown>;
}

export interface SandboxV2ContainerPlansListResponse {
  container_plans: SandboxV2ContainerExecutionPlan[];
  total: number;
}

export interface SandboxV2ContainerResultsListResponse {
  container_results: SandboxV2ContainerExecutionResult[];
  total: number;
}

// ═══════════════════ Sandbox v2 Step 7 — Kill Switch ═══════════════════

export interface SandboxV2KillRequest {
  kill_request_id: string; job_id: string; execution_plan_id: string;
  container_plan_id: string; organization_id: string; workspace_id: string;
  requested_by: string; reason: string; scope: string; target_type: string;
  target_id: string; force: boolean; requested_at: string; status: string;
  metadata: Record<string, unknown>;
}
export interface SandboxV2KillDecision {
  allowed: boolean; action: string; reason: string; risk_level: string;
  target_owned_by_sandbox: boolean; provider_cancel_supported: boolean;
  process_kill_allowed: boolean; container_kill_allowed: boolean;
  queue_cancel_allowed: boolean; job_state_cancel_allowed: boolean;
  fail_closed: boolean; matched_rules: string[];
}
export interface SandboxV2KillRecord {
  kill_record_id: string; kill_request_id: string; job_id: string;
  provider: string; target_type: string; target_id: string;
  action_taken: string; status_before: string; status_after: string;
  provider_result: string; error_message: string; created_at: string;
}
export interface SandboxV2ActiveExecutionHandle {
  handle_id: string; job_id: string; provider: string; target_type: string;
  target_id: string; status: string; started_at: string; last_seen_at: string;
  timeout_at: string | null; cancel_requested: boolean; cancel_reason: string;
}
export interface SandboxV2KillReadiness {
  kill_switch: boolean; kill_policy: boolean;
  active_execution_handles: boolean; queue_cancel: boolean;
  worker_cancel_checkpoints: boolean; provider_cancel_interface: boolean;
  process_kill_implemented: boolean; arbitrary_pid_kill: boolean;
  container_kill_enabled: boolean; platform: string;
}

export interface SandboxV2BenchmarkConfig {
  benchmark_id: string;
  profile: string;
  targets: string[];
  max_jobs: number;
  max_queue_items: number;
  max_artifacts: number;
  max_concurrency: number;
  timeout_seconds: number;
  cleanup_after_run: boolean;
  organization_id: string;
  workspace_id: string;
  created_at: string;
  metadata: Record<string, unknown>;
}

export interface SandboxV2BenchmarkResult {
  benchmark_result_id: string;
  benchmark_id: string;
  target: string;
  status: string;
  started_at: string;
  finished_at: string | null;
  duration_ms: number;
  total_operations: number;
  success_count: number;
  failure_count: number;
  p50_ms: number;
  p95_ms: number;
  p99_ms: number;
  ops_per_second: number;
  warnings: string[];
  blockers: string[];
  metadata: Record<string, unknown>;
}

export interface SandboxV2CapacityEstimate {
  capacity_id: string;
  generated_at: string;
  profile: string;
  estimated_jobs_per_minute: number;
  estimated_queue_items_per_minute: number;
  estimated_artifact_metadata_per_minute: number;
  estimated_network_preflight_per_minute: number;
  sqlite_recommended_limit: string;
  postgres_recommended_threshold: string;
  redis_recommended_threshold: string;
  minio_recommended_threshold: string;
  bottlenecks: string[];
  recommendations: string[];
  metadata: Record<string, unknown>;
}

export interface SandboxV2PerformanceReadiness {
  performance_benchmarking: boolean;
  performance_tests_enabled: boolean;
  performance_benchmarks_enabled: boolean;
  performance_safe_profile: boolean;
  default_profile: string;
  synthetic_fixture_only: boolean;
  external_load_testing: boolean;
  user_code_benchmarking: boolean;
  container_benchmarking: boolean;
  microvm_benchmarking: boolean;
  capacity_estimation: boolean;
  benchmark_cleanup_enabled: boolean;
  max_jobs: number;
  max_queue_items: number;
  max_artifacts: number;
  max_concurrency: number;
  timeout_seconds: number;
  allowed_profiles: string[];
  large_profile_enabled: boolean;
  warnings: string[];
  blockers: string[];
}

// ═══════════════════ Step 17 — IAM / SSO Types ═══════════════════

export interface SandboxV2IAMReadiness {
  iam_provider_config: boolean;
  sso_config_model: boolean;
  oidc_provider_skeleton: boolean;
  saml_provider_skeleton: boolean;
  mock_iam_provider: boolean;
  claim_mapping: boolean;
  role_scope_mapping: boolean;
  jit_provisioning: boolean;
  external_iam_enabled: boolean;
  sso_enabled: boolean;
  real_oidc_login: boolean;
  real_saml_login: boolean;
  token_storage: boolean;
  token_introspection: boolean;
  iam_safe_mode: boolean;
}

export interface SandboxV2IAMProviderConfig {
  provider_config_id: string;
  provider_type: string;       // disabled | oidc | saml | mock
  protocol: string;            // oidc | saml | mock | disabled
  enabled: boolean;
  issuer: string;
  client_id: string;           // masked in response
  client_secret_ref: string;   // NEVER plaintext
  jwks_uri: string;
  discovery_enabled: boolean;
  saml_entity_id: string;
  saml_metadata_ref: string;
  jit_provisioning: boolean;
  default_role: string;
  allowed_domains: string[];
  require_verified_email: boolean;
  external_group_mapping_enabled: boolean;
  organization_id: string;
  workspace_id: string;
  created_at: string;
  metadata: Record<string, unknown>;
}

export interface SandboxV2ExternalIdentity {
  external_identity_id: string;
  provider_config_id: string;
  provider_type: string;
  external_subject: string;
  external_email: string;
  email_verified: boolean;
  external_groups: string[];
  display_name: string;
  organization_id: string;
  workspace_id: string;
  linked_principal_id: string;
  status: string;              // active | disabled | revoked | pending_review
  created_at: string;
  last_seen_at: string;
  metadata: Record<string, unknown>;
}

export interface SandboxV2IAMClaimSet {
  issuer: string;
  subject: string;
  email: string;
  email_verified: boolean;
  name: string;
  groups: string[];
  tenant: string;
  audience: string;
  issued_at: number;
  expires_at: number;
  raw_claims_redacted: Record<string, unknown>;
  metadata: Record<string, unknown>;
}

export interface SandboxV2IAMRoleMapping {
  mapping_id: string;
  provider_config_id: string;
  external_group: string;
  external_claim: string;
  sandbox_role: string;
  sandbox_scopes: string[];
  organization_id: string;
  workspace_id: string;
  enabled: boolean;
  created_at: string;
  metadata: Record<string, unknown>;
}

export interface SandboxV2IAMMappingDecision {
  decision_id: string;
  allowed: boolean;
  status: string;              // mapped | rejected | requires_review | failed
  reason: string;
  principal_id: string;
  principal_type: string;
  mapped_roles: string[];
  mapped_scopes: string[];
  organization_id: string;
  workspace_id: string;
  email_domain_allowed: boolean;
  email_verified: boolean;
  tenant_match: boolean;
  group_mapping_applied: boolean;
  jit_provisioning_required: boolean;
  fail_closed: boolean;
  matched_rules: string[];
  created_at: string;
  metadata: Record<string, unknown>;
}

// ═══════════════════ Step 18 — Observability Types ═══════════════════

export interface SandboxV2ObservabilityReadiness {
  observability_config: boolean;
  prometheus_scrape_config: boolean;
  prometheus_alert_rules: boolean;
  grafana_dashboard_spec: boolean;
  otel_adapter: boolean;
  otel_real_export: boolean;
  external_telemetry_export: boolean;
  telemetry_redaction: boolean;
  trace_span_store: boolean;
  observability_safe_mode: boolean;
  observability_enabled: boolean;
  prometheus_export_enabled: boolean;
  grafana_dashboard_enabled: boolean;
  otel_enabled: boolean;
  otel_exporter: string;
  traces_enabled: boolean;
  metrics_enabled: boolean;
  logs_enabled: boolean;
  sensitive_attributes_allowed: boolean;
  blockers: string[];
  warnings: string[];
}

export interface SandboxV2ObservabilityConfig {
  observability_enabled: boolean;
  prometheus_export_enabled: boolean;
  prometheus_scrape_path: string;
  grafana_dashboard_enabled: boolean;
  otel_enabled: boolean;
  otel_exporter: string;
  otel_endpoint_ref: string;
  otel_service_name: string;
  otel_traces_enabled: boolean;
  otel_metrics_enabled: boolean;
  otel_logs_enabled: boolean;
  include_sensitive_attributes: boolean;
  safe_mode: boolean;
  created_at: string;
}

export interface SandboxV2TelemetryExportRecord {
  export_record_id: string;
  provider: string;
  signal_type: string;       // metric | trace | log | event
  status: string;            // disabled | configured | skipped | exported | failed | rejected
  organization_id: string;
  workspace_id: string;
  resource_type: string;
  resource_id: string;
  exported_count: number;
  rejected_count: number;
  reason: string;
  created_at: string;
}

export interface SandboxV2TraceSpan {
  span_id: string;
  trace_id: string;
  parent_span_id: string;
  span_name: string;
  status: string;           // ok | error | skipped | disabled
  organization_id: string;
  workspace_id: string;
  resource_type: string;
  resource_id: string;
  started_at: string;
  finished_at: string | null;
  duration_ms: number;
  attributes_redacted: Record<string, unknown>;
  events_redacted: Record<string, unknown>[];
}

export interface SandboxV2GrafanaDashboardSpec {
  dashboard_id: string;
  title: string;
  version: string;
  panels: Record<string, unknown>[];
  datasource: string;
  tags: string[];
  generated_at: string;
}

// ═══════════════════ Step 19 — Load Testing / SLO Types ═══════════════════

export interface SandboxV2LoadTestingReadiness {
  load_testing_framework: boolean;
  load_testing_enabled: boolean;
  staging_load_testing_enabled: boolean;
  local_dry_run_enabled: boolean;
  production_load_testing_allowed: boolean;
  slo_definitions: boolean;
  slo_evaluation: boolean;
  capacity_planning: boolean;
  external_load_testing: boolean;
  load_testing_safe_mode: boolean;
}

export interface SandboxV2LoadTestConfig {
  load_test_id: string;
  profile: string;           // smoke | staging_small | staging_medium | production_readonly | custom
  base_url_masked: string;
  targets: string[];
  max_users: number;
  max_rps: number;
  duration_seconds: number;
  timeout_seconds: number;
  allow_production: boolean;
  require_confirmation: boolean;
  organization_id: string;
  workspace_id: string;
  created_at: string;
}

export interface SandboxV2LoadTestResult {
  load_test_result_id: string;
  load_test_id: string;
  target: string;
  status: string;
  started_at: string;
  finished_at: string | null;
  duration_ms: number;
  total_requests: number;
  success_count: number;
  failure_count: number;
  timeout_count: number;
  p50_ms: number;
  p95_ms: number;
  p99_ms: number;
  min_ms: number;
  max_ms: number;
  requests_per_second: number;
  error_rate_percent: number;
}

export interface SandboxV2SLODefinition {
  slo_id: string;
  name: string;
  description: string;
  target: string;
  p95_ms: number;
  p99_ms: number;
  error_rate_percent: number;
  availability_percent: number;
  enabled: boolean;
  organization_id: string;
  workspace_id: string;
  created_at: string;
}

export interface SandboxV2SLOEvaluation {
  slo_eval_id: string;
  slo_id: string;
  load_test_id: string;
  status: string;           // passed | failed | warning | not_evaluated
  target: string;
  observed_p95_ms: number;
  observed_p99_ms: number;
  observed_error_rate_percent: number;
  observed_availability_percent: number;
  reason: string;
  evaluated_at: string;
}

export interface SandboxV2CapacityPlan {
  capacity_plan_id: string;
  generated_at: string;
  recommended_profile: string;
  recommended_backend: string;
  recommended_workers: number;
  recommended_queue_backend: string;
  recommended_object_storage: string;
  expected_daily_jobs: number;
  expected_peak_rps: number;
  bottlenecks: string[];
  scaling_recommendations: string[];
  risk_notes: string[];
}

export interface SandboxV2SSOSimulationResult {
  simulation_id: string;
  provider_config_id: string;
  protocol: string;
  login_status: string;        // simulated | mapped | rejected | failed | disabled
  claim_set: Record<string, unknown>;
  mapping_decision: Record<string, unknown>;
  security_context: Record<string, unknown>;
  audit_event_id: string;
  created_at: string;
  metadata: Record<string, unknown>;
}
