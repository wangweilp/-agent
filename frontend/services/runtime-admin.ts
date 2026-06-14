/** Runtime Admin API Client — /admin/runtime 端点 */
import { getAccessToken } from "@/stores/auth-store";
import type {
  RuntimeAdaptersResponse, RuntimeBindingsResponse, RuntimeBindingDetailResponse,
  RuntimeBindingActionResponse, RuntimeEligibilityResult,
  SandboxPoliciesResponse, SandboxPolicy, SandboxPolicyTestRequest,
  SandboxPolicyTestResult, RuntimeGovernanceSummary,
  SandboxV2SubmitJobRequest, SandboxV2SubmitJobResponse,
  SandboxV2Job, SandboxV2JobsListResponse,
  SandboxV2CancelJobResponse, SandboxV2ReadinessResponse,
  SandboxV2ExecutionRecordsListResponse,
  SandboxV2QueueListResponse, SandboxV2WorkersListResponse,
  SandboxV2DeadLetterListResponse, SandboxV2RequeueResponse,
  SandboxV2WorkerRunOnceResult,
  SandboxV2ArtifactMaterializationRequest, SandboxV2MaterializeArtifactResponse,
  SandboxV2Artifact, SandboxV2ArtifactsListResponse,
  SandboxV2ArtifactContentResponse, SandboxV2ArtifactManifest,
  SandboxV2PackageRequest, SandboxV2PackageRequestsListResponse,
  SandboxV2PackagePolicyDecision, SandboxV2PackageQuarantineRecord,
  SandboxV2QuarantineListResponse, SandboxV2SbomListResponse, SandboxV2ScanListResponse,
  SandboxV2NetworkEgressRequest, SandboxV2NetworkEgressPolicyDecision,
  SandboxV2NetworkEgressAuditRecord, SandboxV2NetworkPolicyConfig,
  SandboxV2NetworkReadiness, SandboxV2EgressRequestsListResponse,
  SandboxV2AuditRecordsListResponse,
  SandboxV2IsolationCapability, SandboxV2IsolationReadiness,
  SandboxV2ExecutionPlan, SandboxV2IsolationDecision,
  SandboxV2TrustedFixtureExecutionResult, SandboxV2ExecutionPlansListResponse,
  SandboxV2ContainerRuntimeConfig, SandboxV2ContainerExecutionPlan,
  SandboxV2ContainerExecutionResult, SandboxV2ContainerPlansListResponse,
  SandboxV2ContainerResultsListResponse,
  SandboxV2KillRequest, SandboxV2KillDecision, SandboxV2KillRecord,
  SandboxV2ActiveExecutionHandle, SandboxV2KillReadiness,
  SandboxV2BenchmarkConfig, SandboxV2BenchmarkResult,
  SandboxV2CapacityEstimate, SandboxV2PerformanceReadiness,
  SandboxV2IAMReadiness, SandboxV2IAMProviderConfig,
  SandboxV2ExternalIdentity, SandboxV2IAMRoleMapping,
  SandboxV2IAMMappingDecision, SandboxV2SSOSimulationResult,
  SandboxV2ObservabilityReadiness, SandboxV2TelemetryExportRecord,
  SandboxV2TraceSpan, SandboxV2GrafanaDashboardSpec,
  SandboxV2LoadTestingReadiness, SandboxV2LoadTestConfig,
  SandboxV2LoadTestResult, SandboxV2SLODefinition,
  SandboxV2SLOEvaluation, SandboxV2CapacityPlan,
} from "@/types/runtime-admin";

const API_BASE = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "");
const RA_BASE = API_BASE ? `${API_BASE}/admin/runtime` : "/api/runtime";
const SP_BASE = API_BASE ? `${API_BASE}/admin/sandbox-policies` : "/api/sandbox-policies";

export class RuntimeAdminApiError extends Error {
  constructor(public status: number, message: string, public detail: unknown = null) {
    super(message); this.name = "RuntimeAdminApiError";
  }
}

function getToken(): string | null {
  if (typeof window === "undefined") return null;
  const t = getAccessToken(); if (t) return t;
  try { const raw = localStorage.getItem("agent-os-auth"); if (!raw) return null; return JSON.parse(raw)?.state?.token?.access_token || null; } catch { return null; }
}

async function fetchJSON<T>(base: string, path: string, init?: RequestInit): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(`${base}${path}`, { ...init, headers });
  const raw = await res.text();
  if (!res.ok) {
    let msg = `[${res.status}]`; let detail: unknown = null;
    try { const p = JSON.parse(raw); detail = p.detail || p; msg = typeof detail === "string" ? `${msg} ${detail}` : `${msg} ${JSON.stringify(detail).slice(0, 200)}`; } catch { msg = `${msg} ${raw.slice(0, 200)}`; }
    throw new RuntimeAdminApiError(res.status, msg, detail);
  }
  if (!raw.trim()) return {} as T;
  return JSON.parse(raw) as T;
}

// ── Adapters ──
export async function listRuntimeAdapters(params?: { status?: string; adapter_type?: string; mvp_only?: boolean }) {
  const sp = new URLSearchParams();
  if (params?.status) sp.set("status", params.status);
  if (params?.adapter_type) sp.set("adapter_type", params.adapter_type);
  if (params?.mvp_only) sp.set("mvp_only", "true");
  const qs = sp.toString();
  return fetchJSON<RuntimeAdaptersResponse>(RA_BASE, `/adapters${qs ? `?${qs}` : ""}`);
}

// ── Bindings ──
export async function listRuntimeBindings(params?: { tenant_id?: string; developer_id?: string; marketplace_agent_id?: string; runtime_status?: string; adapter_type?: string }) {
  const sp = new URLSearchParams();
  if (params?.tenant_id) sp.set("tenant_id", params.tenant_id);
  if (params?.developer_id) sp.set("developer_id", params.developer_id);
  if (params?.marketplace_agent_id) sp.set("marketplace_agent_id", params.marketplace_agent_id);
  if (params?.runtime_status) sp.set("runtime_status", params.runtime_status);
  if (params?.adapter_type) sp.set("adapter_type", params.adapter_type);
  const qs = sp.toString();
  return fetchJSON<RuntimeBindingsResponse>(RA_BASE, `/bindings${qs ? `?${qs}` : ""}`);
}

export async function createRuntimeBinding(payload: { marketplace_agent_id: string; adapter_id?: string; sandbox_policy_id?: string | null; metadata?: Record<string, unknown> }) {
  return fetchJSON<RuntimeBindingActionResponse>(RA_BASE, "/bindings", { method: "POST", body: JSON.stringify(payload) });
}

export async function getRuntimeBinding(bindingId: string) {
  return fetchJSON<RuntimeBindingDetailResponse>(RA_BASE, `/${encodeURIComponent(bindingId)}`);
}

export async function enableRuntimeBinding(bindingId: string) {
  return fetchJSON<RuntimeBindingActionResponse>(RA_BASE, `/bindings/${encodeURIComponent(bindingId)}/enable`, { method: "POST", body: "{}" });
}

export async function disableRuntimeBinding(bindingId: string) {
  return fetchJSON<RuntimeBindingActionResponse>(RA_BASE, `/bindings/${encodeURIComponent(bindingId)}/disable`, { method: "POST", body: "{}" });
}

export async function suspendRuntimeBinding(bindingId: string) {
  return fetchJSON<RuntimeBindingActionResponse>(RA_BASE, `/bindings/${encodeURIComponent(bindingId)}/suspend`, { method: "POST", body: "{}" });
}

export async function assignRuntimeBindingSandboxPolicy(bindingId: string, sandboxPolicyId: string) {
  return fetchJSON<RuntimeBindingActionResponse>(RA_BASE, `/bindings/${encodeURIComponent(bindingId)}/sandbox-policy`, { method: "POST", body: JSON.stringify({ sandbox_policy_id: sandboxPolicyId }) });
}

export async function getRuntimeEligibility(marketplaceAgentId: string, tenantId?: string) {
  const qs = tenantId ? `?tenant_id=${encodeURIComponent(tenantId)}` : "";
  return fetchJSON<RuntimeEligibilityResult>(RA_BASE, `/developer-agents/${encodeURIComponent(marketplaceAgentId)}/eligibility${qs}`);
}

// ── Sandbox Policies ──
export async function listSandboxPolicies(params?: { status?: string; scope?: string }) {
  const sp = new URLSearchParams();
  if (params?.status) sp.set("status", params.status);
  if (params?.scope) sp.set("scope", params.scope);
  const qs = sp.toString();
  return fetchJSON<SandboxPoliciesResponse>(SP_BASE, `${qs ? `?${qs}` : ""}`);
}

export async function getSandboxPolicy(policyId: string) {
  return fetchJSON<{ policy: SandboxPolicy }>(SP_BASE, `/${encodeURIComponent(policyId)}`);
}

export async function createSandboxPolicy(payload: Record<string, unknown>) {
  return fetchJSON<{ policy: SandboxPolicy }>(SP_BASE, "", { method: "POST", body: JSON.stringify(payload) });
}

export async function updateSandboxPolicy(policyId: string, payload: Record<string, unknown>) {
  return fetchJSON<{ policy: SandboxPolicy }>(SP_BASE, `/${encodeURIComponent(policyId)}`, { method: "PATCH", body: JSON.stringify(payload) });
}

export async function testSandboxPolicy(policyId: string, payload: SandboxPolicyTestRequest) {
  return fetchJSON<SandboxPolicyTestResult>(SP_BASE, `/${encodeURIComponent(policyId)}/test`, { method: "POST", body: JSON.stringify(payload) });
}

export async function enableSandboxPolicy(policyId: string) {
  return fetchJSON<{ success: boolean }>(SP_BASE, `/${encodeURIComponent(policyId)}/enable`, { method: "POST", body: "{}" });
}

export async function disableSandboxPolicy(policyId: string) {
  return fetchJSON<{ success: boolean }>(SP_BASE, `/${encodeURIComponent(policyId)}/disable`, { method: "POST", body: "{}" });
}

export async function getRuntimeGovernanceSummary() {
  return fetchJSON<RuntimeGovernanceSummary>(RA_BASE, "/governance/summary");
}

// ═══════════════════ Sandbox v2 (Step 1 — Core Contract) ═══════════════════

const SBV2_BASE = API_BASE ? `${API_BASE}/api/runtime/sandbox-v2` : "/api/runtime/sandbox-v2";

/** 提交 sandbox v2 job */
export async function submitSandboxV2Job(payload: SandboxV2SubmitJobRequest) {
  return fetchJSON<SandboxV2SubmitJobResponse>(SBV2_BASE, "/jobs", { method: "POST", body: JSON.stringify(payload) });
}

/** 查看 sandbox v2 job 状态 */
export async function getSandboxV2Job(jobId: string) {
  return fetchJSON<SandboxV2Job>(SBV2_BASE, `/jobs/${encodeURIComponent(jobId)}`);
}

/** 列出 sandbox v2 jobs */
export async function listSandboxV2Jobs(params?: { organization_id?: string; workspace_id?: string; limit?: number }) {
  const sp = new URLSearchParams();
  if (params?.organization_id) sp.set("organization_id", params.organization_id);
  if (params?.workspace_id) sp.set("workspace_id", params.workspace_id);
  if (params?.limit) sp.set("limit", String(params.limit));
  const qs = sp.toString();
  return fetchJSON<SandboxV2JobsListResponse>(SBV2_BASE, `/jobs${qs ? `?${qs}` : ""}`);
}

/** 取消 sandbox v2 job */
export async function cancelSandboxV2Job(jobId: string) {
  return fetchJSON<SandboxV2CancelJobResponse>(SBV2_BASE, `/jobs/${encodeURIComponent(jobId)}/cancel`, { method: "POST", body: "{}" });
}

/** 列出 sandbox v2 execution records */
export async function listSandboxV2ExecutionRecords(params?: { job_id?: string; limit?: number }) {
  const sp = new URLSearchParams();
  if (params?.job_id) sp.set("job_id", params.job_id);
  if (params?.limit) sp.set("limit", String(params.limit));
  const qs = sp.toString();
  return fetchJSON<SandboxV2ExecutionRecordsListResponse>(SBV2_BASE, `/execution-records${qs ? `?${qs}` : ""}`);
}

/** 获取 sandbox v2 能力状态 */
export async function getSandboxV2Readiness() {
  return fetchJSON<SandboxV2ReadinessResponse>(SBV2_BASE, "/readiness");
}

// ═══════════════════ Sandbox v2 Step 2 — Queue / Worker ═══════════════════

/** 提交 sandbox v2 job（带 enqueue 选项） */
export async function submitSandboxV2JobToQueue(payload: SandboxV2SubmitJobRequest & { enqueue: true; priority?: number; max_attempts?: number }) {
  return fetchJSON<SandboxV2SubmitJobResponse>(SBV2_BASE, "/jobs", { method: "POST", body: JSON.stringify(payload) });
}

/** 列出 sandbox v2 队列 */
export async function listSandboxV2Queue(params?: { status?: string; limit?: number }) {
  const sp = new URLSearchParams();
  if (params?.status) sp.set("status", params.status);
  if (params?.limit) sp.set("limit", String(params.limit));
  const qs = sp.toString();
  return fetchJSON<SandboxV2QueueListResponse>(SBV2_BASE, `/queue${qs ? `?${qs}` : ""}`);
}

/** 回收过期 lease */
export async function requeueSandboxV2ExpiredJobs() {
  return fetchJSON<SandboxV2RequeueResponse>(SBV2_BASE, "/queue/requeue-expired", { method: "POST", body: "{}" });
}

/** 列出 sandbox v2 workers */
export async function listSandboxV2Workers(params?: { limit?: number }) {
  const sp = new URLSearchParams();
  if (params?.limit) sp.set("limit", String(params.limit));
  const qs = sp.toString();
  return fetchJSON<SandboxV2WorkersListResponse>(SBV2_BASE, `/workers${qs ? `?${qs}` : ""}`);
}

/** 手动触发 worker 处理一个任务（开发/测试用） */
export async function runSandboxV2WorkerOnce() {
  return fetchJSON<SandboxV2WorkerRunOnceResult>(SBV2_BASE, "/workers/run-once", { method: "POST", body: "{}" });
}

/** 列出 dead letter */
export async function listSandboxV2DeadLetter(params?: { limit?: number }) {
  const sp = new URLSearchParams();
  if (params?.limit) sp.set("limit", String(params.limit));
  const qs = sp.toString();
  return fetchJSON<SandboxV2DeadLetterListResponse>(SBV2_BASE, `/dead-letter${qs ? `?${qs}` : ""}`);
}

// ═══════════════════ Sandbox v2 Step 3 — Artifacts ═══════════════════

/** 创建 artifact */
export async function createSandboxV2Artifact(payload: SandboxV2ArtifactMaterializationRequest) {
  return fetchJSON<SandboxV2MaterializeArtifactResponse>(SBV2_BASE, "/artifacts", { method: "POST", body: JSON.stringify(payload) });
}

/** 列出 artifacts */
export async function listSandboxV2Artifacts(params?: { job_id?: string; record_id?: string; organization_id?: string; workspace_id?: string; limit?: number }) {
  const sp = new URLSearchParams();
  if (params?.job_id) sp.set("job_id", params.job_id);
  if (params?.record_id) sp.set("record_id", params.record_id);
  if (params?.organization_id) sp.set("organization_id", params.organization_id);
  if (params?.workspace_id) sp.set("workspace_id", params.workspace_id);
  if (params?.limit) sp.set("limit", String(params.limit));
  const qs = sp.toString();
  return fetchJSON<SandboxV2ArtifactsListResponse>(SBV2_BASE, `/artifacts${qs ? `?${qs}` : ""}`);
}

/** 获取 artifact metadata */
export async function getSandboxV2Artifact(artifactId: string) {
  return fetchJSON<SandboxV2Artifact>(SBV2_BASE, `/artifacts/${encodeURIComponent(artifactId)}`);
}

/** 获取 artifact 内容 */
export async function getSandboxV2ArtifactContent(artifactId: string) {
  return fetchJSON<SandboxV2ArtifactContentResponse>(SBV2_BASE, `/artifacts/${encodeURIComponent(artifactId)}/content`);
}

/** 标记 artifact 过期 */
export async function expireSandboxV2Artifact(artifactId: string) {
  return fetchJSON<{ artifact_id: string; status: string }>(SBV2_BASE, `/artifacts/${encodeURIComponent(artifactId)}/expire`, { method: "POST", body: "{}" });
}

/** 删除 artifact */
export async function deleteSandboxV2Artifact(artifactId: string) {
  return fetchJSON<{ artifact_id: string; deleted: boolean }>(SBV2_BASE, `/artifacts/${encodeURIComponent(artifactId)}`, { method: "DELETE" });
}

/** 创建 artifact manifest */
export async function createSandboxV2ArtifactManifest(payload: { job_id: string; record_id?: string }) {
  return fetchJSON<{ manifest: SandboxV2ArtifactManifest }>(SBV2_BASE, "/artifact-manifests", { method: "POST", body: JSON.stringify(payload) });
}

/** 获取 manifest */
export async function getSandboxV2ArtifactManifest(manifestId: string) {
  return fetchJSON<SandboxV2ArtifactManifest>(SBV2_BASE, `/artifact-manifests/${encodeURIComponent(manifestId)}`);
}

// ═══════════════════ Sandbox v2 Step 4 — Package / Supply Chain ═══════════════════

export async function createSandboxV2PackageRequest(payload: { package_name: string; [key: string]: unknown }) {
  return fetchJSON<{ package_request: SandboxV2PackageRequest; decision: SandboxV2PackagePolicyDecision; accepted: boolean }>(SBV2_BASE, "/packages/requests", { method: "POST", body: JSON.stringify(payload) });
}
export async function listSandboxV2PackageRequests(params?: { job_id?: string; organization_id?: string; workspace_id?: string; status?: string; limit?: number }) {
  const sp = new URLSearchParams();
  if (params?.job_id) sp.set("job_id", params.job_id);
  if (params?.organization_id) sp.set("organization_id", params.organization_id);
  if (params?.workspace_id) sp.set("workspace_id", params.workspace_id);
  if (params?.status) sp.set("status", params.status);
  if (params?.limit) sp.set("limit", String(params.limit));
  const qs = sp.toString();
  return fetchJSON<SandboxV2PackageRequestsListResponse>(SBV2_BASE, `/packages/requests${qs ? `?${qs}` : ""}`);
}
export async function getSandboxV2PackageRequest(packageRequestId: string) {
  return fetchJSON<SandboxV2PackageRequest>(SBV2_BASE, `/packages/requests/${encodeURIComponent(packageRequestId)}`);
}
export async function quarantineSandboxV2Package(packageRequestId: string, payload: { content_text?: string; original_filename?: string }) {
  return fetchJSON<{ quarantine_record: SandboxV2PackageQuarantineRecord; error: string }>(SBV2_BASE, `/packages/requests/${encodeURIComponent(packageRequestId)}/quarantine`, { method: "POST", body: JSON.stringify(payload) });
}
export async function listSandboxV2PackageQuarantine(params?: { package_request_id?: string; status?: string; limit?: number }) {
  const sp = new URLSearchParams();
  if (params?.package_request_id) sp.set("package_request_id", params.package_request_id);
  if (params?.status) sp.set("status", params.status);
  if (params?.limit) sp.set("limit", String(params.limit));
  const qs = sp.toString();
  return fetchJSON<SandboxV2QuarantineListResponse>(SBV2_BASE, `/packages/quarantine${qs ? `?${qs}` : ""}`);
}
export async function getSandboxV2PackageQuarantineRecord(quarantineId: string) {
  return fetchJSON<SandboxV2PackageQuarantineRecord>(SBV2_BASE, `/packages/quarantine/${encodeURIComponent(quarantineId)}`);
}
export async function reviewSandboxV2PackageQuarantine(quarantineId: string, payload: { decision: string; reviewed_by?: string; reason?: string }) {
  return fetchJSON<Record<string, unknown>>(SBV2_BASE, `/packages/quarantine/${encodeURIComponent(quarantineId)}/review`, { method: "POST", body: JSON.stringify(payload) });
}
export async function deleteSandboxV2PackageQuarantine(quarantineId: string) {
  return fetchJSON<{ quarantine_id: string; deleted: boolean }>(SBV2_BASE, `/packages/quarantine/${encodeURIComponent(quarantineId)}`, { method: "DELETE" });
}
export async function submitSandboxV2PackageSBOM(payload: { package_request_id: string; sbom_content: string; format?: string }) {
  return fetchJSON<{ sbom: Record<string, unknown>; validated: boolean }>(SBV2_BASE, "/packages/sbom", { method: "POST", body: JSON.stringify(payload) });
}
export async function listSandboxV2PackageSBOMs(params?: { package_request_id?: string; limit?: number }) {
  const sp = new URLSearchParams();
  if (params?.package_request_id) sp.set("package_request_id", params.package_request_id);
  if (params?.limit) sp.set("limit", String(params.limit));
  const qs = sp.toString();
  return fetchJSON<SandboxV2SbomListResponse>(SBV2_BASE, `/packages/sbom${qs ? `?${qs}` : ""}`);
}
export async function runSandboxV2PackageScan(packageRequestId: string, sbomId?: string) {
  const sp = new URLSearchParams(); sp.set("package_request_id", packageRequestId);
  if (sbomId) sp.set("sbom_id", sbomId);
  return fetchJSON<Record<string, unknown>>(SBV2_BASE, `/packages/scans?${sp.toString()}`, { method: "POST", body: "{}" });
}
export async function listSandboxV2PackageScans(params?: { package_request_id?: string; limit?: number }) {
  const sp = new URLSearchParams();
  if (params?.package_request_id) sp.set("package_request_id", params.package_request_id);
  if (params?.limit) sp.set("limit", String(params.limit));
  const qs = sp.toString();
  return fetchJSON<SandboxV2ScanListResponse>(SBV2_BASE, `/packages/scans${qs ? `?${qs}` : ""}`);
}

// ═══════════════════ Sandbox v2 Step 5 — Network Egress ═══════════════════

export async function createSandboxV2NetworkEgressRequest(payload: { url: string; [key: string]: unknown }) {
  return fetchJSON<Record<string, unknown>>(SBV2_BASE, "/network/egress-requests", { method: "POST", body: JSON.stringify(payload) });
}
export async function listSandboxV2NetworkEgressRequests(params?: { job_id?: string; organization_id?: string; workspace_id?: string; status?: string; limit?: number }) {
  const sp = new URLSearchParams();
  if (params?.job_id) sp.set("job_id", params.job_id);
  if (params?.organization_id) sp.set("organization_id", params.organization_id);
  if (params?.workspace_id) sp.set("workspace_id", params.workspace_id);
  if (params?.status) sp.set("status", params.status);
  if (params?.limit) sp.set("limit", String(params.limit));
  const qs = sp.toString();
  return fetchJSON<SandboxV2EgressRequestsListResponse>(SBV2_BASE, `/network/egress-requests${qs ? `?${qs}` : ""}`);
}
export async function getSandboxV2NetworkEgressRequest(egressRequestId: string) {
  return fetchJSON<SandboxV2NetworkEgressRequest>(SBV2_BASE, `/network/egress-requests/${encodeURIComponent(egressRequestId)}`);
}
export async function listSandboxV2NetworkAuditRecords(params?: { egress_request_id?: string; job_id?: string; limit?: number }) {
  const sp = new URLSearchParams();
  if (params?.egress_request_id) sp.set("egress_request_id", params.egress_request_id);
  if (params?.job_id) sp.set("job_id", params.job_id);
  if (params?.limit) sp.set("limit", String(params.limit));
  const qs = sp.toString();
  return fetchJSON<SandboxV2AuditRecordsListResponse>(SBV2_BASE, `/network/audit-records${qs ? `?${qs}` : ""}`);
}
export async function preflightSandboxV2NetworkEgress(payload: { url: string; hostname?: string; port?: number; resolved_ips?: string[]; purpose?: string }) {
  return fetchJSON<SandboxV2NetworkEgressPolicyDecision>(SBV2_BASE, "/network/preflight", { method: "POST", body: JSON.stringify(payload) });
}
export async function getSandboxV2NetworkReadiness() {
  return fetchJSON<SandboxV2NetworkReadiness>(SBV2_BASE, "/network/readiness");
}

// ═══════════════════ Sandbox v2 Step 6A — Isolation / Execution ═══════════════════

export async function getSandboxV2IsolationCapabilities() {
  return fetchJSON<SandboxV2IsolationReadiness>(SBV2_BASE, "/isolation/capabilities");
}
export async function getSandboxV2IsolationReadiness() {
  return fetchJSON<SandboxV2IsolationReadiness>(SBV2_BASE, "/isolation/readiness");
}
export async function createSandboxV2ExecutionPlan(payload: { provider?: string; mode?: string; command_ref?: string; [key: string]: unknown }) {
  return fetchJSON<{ execution_plan: SandboxV2ExecutionPlan; decision: SandboxV2IsolationDecision }>(SBV2_BASE, "/isolation/execution-plans", { method: "POST", body: JSON.stringify(payload) });
}
export async function listSandboxV2ExecutionPlans(params?: { job_id?: string; organization_id?: string; workspace_id?: string; status?: string; limit?: number }) {
  const sp = new URLSearchParams();
  if (params?.job_id) sp.set("job_id", params.job_id);
  if (params?.organization_id) sp.set("organization_id", params.organization_id);
  if (params?.workspace_id) sp.set("workspace_id", params.workspace_id);
  if (params?.status) sp.set("status", params.status);
  if (params?.limit) sp.set("limit", String(params.limit));
  const qs = sp.toString();
  return fetchJSON<SandboxV2ExecutionPlansListResponse>(SBV2_BASE, `/isolation/execution-plans${qs ? `?${qs}` : ""}`);
}
export async function getSandboxV2ExecutionPlan(executionPlanId: string) {
  return fetchJSON<SandboxV2ExecutionPlan>(SBV2_BASE, `/isolation/execution-plans/${encodeURIComponent(executionPlanId)}`);
}
export async function runSandboxV2TrustedFixture(executionPlanId: string) {
  return fetchJSON<Record<string, unknown>>(SBV2_BASE, `/isolation/execution-plans/${encodeURIComponent(executionPlanId)}/run-trusted-fixture`, { method: "POST", body: "{}" });
}
export async function cancelSandboxV2ExecutionPlan(executionPlanId: string) {
  return fetchJSON<Record<string, unknown>>(SBV2_BASE, `/isolation/execution-plans/${encodeURIComponent(executionPlanId)}/cancel`, { method: "POST", body: "{}" });
}

// ═══════════════════ Sandbox v2 Step 6B — Container Execution ═══════════════════

export async function createSandboxV2ContainerPlan(payload: { job_id?: string; provider?: string; runtime?: string; image?: string; fixture_id?: string; timeout_seconds?: number }) {
  return fetchJSON<{ container_plan: SandboxV2ContainerExecutionPlan }>(SBV2_BASE, "/isolation/container-plans", { method: "POST", body: JSON.stringify(payload) });
}
export async function listSandboxV2ContainerPlans(params?: { job_id?: string; status?: string; limit?: number }) {
  const sp = new URLSearchParams();
  if (params?.job_id) sp.set("job_id", params.job_id);
  if (params?.status) sp.set("status", params.status);
  if (params?.limit) sp.set("limit", String(params.limit));
  const qs = sp.toString();
  return fetchJSON<SandboxV2ContainerPlansListResponse>(SBV2_BASE, `/isolation/container-plans${qs ? `?${qs}` : ""}`);
}
export async function getSandboxV2ContainerPlan(containerPlanId: string) {
  return fetchJSON<SandboxV2ContainerExecutionPlan>(SBV2_BASE, `/isolation/container-plans/${encodeURIComponent(containerPlanId)}`);
}
export async function runSandboxV2ContainerTrustedFixture(containerPlanId: string) {
  return fetchJSON<Record<string, unknown>>(SBV2_BASE, `/isolation/container-plans/${encodeURIComponent(containerPlanId)}/run-trusted-fixture`, { method: "POST", body: "{}" });
}
export async function listSandboxV2ContainerResults(params?: { job_id?: string; container_plan_id?: string; limit?: number }) {
  const sp = new URLSearchParams();
  if (params?.job_id) sp.set("job_id", params.job_id);
  if (params?.container_plan_id) sp.set("container_plan_id", params.container_plan_id);
  if (params?.limit) sp.set("limit", String(params.limit));
  const qs = sp.toString();
  return fetchJSON<SandboxV2ContainerResultsListResponse>(SBV2_BASE, `/isolation/container-results${qs ? `?${qs}` : ""}`);
}
export async function getSandboxV2ContainerResult(containerResultId: string) {
  return fetchJSON<SandboxV2ContainerExecutionResult>(SBV2_BASE, `/isolation/container-results/${encodeURIComponent(containerResultId)}`);
}

// ═══════════════════ Sandbox v2 Step 7 — Kill Switch ═══════════════════

export async function killSandboxV2Job(jobId: string) {
  return fetchJSON<Record<string, unknown>>(SBV2_BASE, `/kill/job/${encodeURIComponent(jobId)}`, { method: "POST", body: "{}" });
}
export async function killSandboxV2ExecutionPlan(executionPlanId: string) {
  return fetchJSON<Record<string, unknown>>(SBV2_BASE, `/kill/execution-plan/${encodeURIComponent(executionPlanId)}`, { method: "POST", body: "{}" });
}
export async function killSandboxV2ContainerPlan(containerPlanId: string) {
  return fetchJSON<Record<string, unknown>>(SBV2_BASE, `/kill/container-plan/${encodeURIComponent(containerPlanId)}`, { method: "POST", body: "{}" });
}
export async function listSandboxV2KillRequests(params?: { job_id?: string; status?: string; limit?: number }) {
  const sp = new URLSearchParams();
  if (params?.job_id) sp.set("job_id", params.job_id);
  if (params?.status) sp.set("status", params.status);
  if (params?.limit) sp.set("limit", String(params.limit));
  const qs = sp.toString();
  return fetchJSON<{ kill_requests: SandboxV2KillRequest[]; total: number }>(SBV2_BASE, `/kill/requests${qs ? `?${qs}` : ""}`);
}
export async function listSandboxV2KillRecords(params?: { job_id?: string; kill_request_id?: string; limit?: number }) {
  const sp = new URLSearchParams();
  if (params?.job_id) sp.set("job_id", params.job_id);
  if (params?.kill_request_id) sp.set("kill_request_id", params.kill_request_id);
  if (params?.limit) sp.set("limit", String(params.limit));
  const qs = sp.toString();
  return fetchJSON<{ kill_records: SandboxV2KillRecord[]; total: number }>(SBV2_BASE, `/kill/records${qs ? `?${qs}` : ""}`);
}
export async function listSandboxV2ActiveHandles(params?: { status?: string; limit?: number }) {
  const sp = new URLSearchParams();
  if (params?.status) sp.set("status", params.status);
  if (params?.limit) sp.set("limit", String(params.limit));
  const qs = sp.toString();
  return fetchJSON<{ active_handles: SandboxV2ActiveExecutionHandle[]; total: number }>(SBV2_BASE, `/kill/active-handles${qs ? `?${qs}` : ""}`);
}
export async function requestSandboxV2HandleCancel(handleId: string, reason?: string) {
  const qs = reason ? `?reason=${encodeURIComponent(reason)}` : "";
  return fetchJSON<Record<string, unknown>>(SBV2_BASE, `/kill/handles/${encodeURIComponent(handleId)}/cancel-request${qs}`, { method: "POST", body: "{}" });
}
export async function getSandboxV2KillReadiness() {
  return fetchJSON<SandboxV2KillReadiness>(SBV2_BASE, "/kill/readiness");
}

export async function getSandboxV2PerformanceReadiness() {
  return fetchJSON<SandboxV2PerformanceReadiness>(SBV2_BASE, "/performance/readiness");
}

export async function createSandboxV2PerformanceBenchmark(payload: {
  profile: "smoke" | "small";
  targets?: string[];
  max_jobs?: number;
  max_queue_items?: number;
  max_artifacts?: number;
  max_concurrency?: number;
  timeout_seconds?: number;
  cleanup_after_run?: boolean;
}) {
  return fetchJSON<{ benchmark: SandboxV2BenchmarkConfig }>(SBV2_BASE, "/performance/benchmarks", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function runSandboxV2PerformanceBenchmark(benchmarkId: string) {
  return fetchJSON<Record<string, unknown>>(SBV2_BASE, `/performance/benchmarks/${encodeURIComponent(benchmarkId)}/run`, {
    method: "POST",
    body: "{}",
  });
}

export async function listSandboxV2PerformanceBenchmarks(params?: { limit?: number }) {
  const sp = new URLSearchParams();
  if (params?.limit) sp.set("limit", String(params.limit));
  const qs = sp.toString();
  return fetchJSON<{ benchmarks: SandboxV2BenchmarkConfig[]; total: number }>(SBV2_BASE, `/performance/benchmarks${qs ? `?${qs}` : ""}`);
}

export async function listSandboxV2PerformanceResults(params?: { benchmark_id?: string; target?: string; limit?: number }) {
  const sp = new URLSearchParams();
  if (params?.benchmark_id) sp.set("benchmark_id", params.benchmark_id);
  if (params?.target) sp.set("target", params.target);
  if (params?.limit) sp.set("limit", String(params.limit));
  const qs = sp.toString();
  return fetchJSON<{ results: SandboxV2BenchmarkResult[]; total: number }>(SBV2_BASE, `/performance/results${qs ? `?${qs}` : ""}`);
}

export async function getSandboxV2LatestCapacityEstimate() {
  return fetchJSON<{ capacity_estimate: SandboxV2CapacityEstimate | null }>(SBV2_BASE, "/performance/capacity/latest");
}

export async function getSandboxV2PerformanceReport(benchmarkId: string, format: "markdown" | "json" = "markdown") {
  return fetchJSON<{ benchmark_id: string; format: string; report: unknown }>(
    SBV2_BASE,
    `/performance/report/${encodeURIComponent(benchmarkId)}?format=${encodeURIComponent(format)}`,
  );
}

// ═══════════════════ Step 17 — IAM / SSO API ═══════════════════

export async function getSandboxV2IAMReadiness() {
  return fetchJSON<SandboxV2IAMReadiness>(SBV2_BASE, "/iam/readiness");
}

export async function createSandboxV2IAMProviderConfig(payload: {
  provider_type?: string; protocol?: string; enabled?: boolean;
  issuer?: string; client_id?: string; client_secret?: string;
  jwks_uri?: string; discovery_enabled?: boolean;
  saml_entity_id?: string; saml_metadata_ref?: string;
  jit_provisioning?: boolean; default_role?: string;
  allowed_domains?: string[]; require_verified_email?: boolean;
  external_group_mapping_enabled?: boolean;
  organization_id?: string; workspace_id?: string;
  metadata?: Record<string, unknown>;
}) {
  return fetchJSON<{ provider_config: SandboxV2IAMProviderConfig }>(
    SBV2_BASE, "/iam/provider-configs", { method: "POST", body: JSON.stringify(payload) },
  );
}

export async function listSandboxV2IAMProviderConfigs(params?: {
  organization_id?: string; workspace_id?: string; limit?: number;
}) {
  const sp = new URLSearchParams();
  if (params?.organization_id) sp.set("organization_id", params.organization_id);
  if (params?.workspace_id) sp.set("workspace_id", params.workspace_id);
  if (params?.limit) sp.set("limit", String(params.limit));
  const qs = sp.toString();
  return fetchJSON<{ provider_configs: SandboxV2IAMProviderConfig[]; total: number }>(
    SBV2_BASE, `/iam/provider-configs${qs ? `?${qs}` : ""}`,
  );
}

export async function getSandboxV2IAMProviderConfig(providerConfigId: string) {
  return fetchJSON<{ provider_config: SandboxV2IAMProviderConfig }>(
    SBV2_BASE, `/iam/provider-configs/${encodeURIComponent(providerConfigId)}`,
  );
}

export async function createSandboxV2IAMRoleMapping(payload: {
  provider_config_id?: string; external_group?: string;
  external_claim?: string; sandbox_role?: string;
  sandbox_scopes?: string[];
  organization_id?: string; workspace_id?: string;
  enabled?: boolean; metadata?: Record<string, unknown>;
}) {
  return fetchJSON<{ role_mapping: SandboxV2IAMRoleMapping }>(
    SBV2_BASE, "/iam/role-mappings", { method: "POST", body: JSON.stringify(payload) },
  );
}

export async function listSandboxV2IAMRoleMappings(params?: {
  provider_config_id?: string; organization_id?: string;
  workspace_id?: string; limit?: number;
}) {
  const sp = new URLSearchParams();
  if (params?.provider_config_id) sp.set("provider_config_id", params.provider_config_id);
  if (params?.organization_id) sp.set("organization_id", params.organization_id);
  if (params?.workspace_id) sp.set("workspace_id", params.workspace_id);
  if (params?.limit) sp.set("limit", String(params.limit));
  const qs = sp.toString();
  return fetchJSON<{ role_mappings: SandboxV2IAMRoleMapping[]; total: number }>(
    SBV2_BASE, `/iam/role-mappings${qs ? `?${qs}` : ""}`,
  );
}

export async function simulateSandboxV2SSOLogin(payload: {
  claims: Record<string, unknown>; provider_config_id: string;
  organization_id?: string; workspace_id?: string;
}) {
  return fetchJSON<{
    login_status: string; reason: string; allowed: boolean;
    claim_set: Record<string, unknown> | null;
    mapping_decision: Record<string, unknown> | null;
    security_context: Record<string, unknown> | null;
  }>(SBV2_BASE, "/iam/simulate-login", { method: "POST", body: JSON.stringify(payload) });
}

export async function listSandboxV2ExternalIdentities(params?: {
  organization_id?: string; workspace_id?: string;
  provider_config_id?: string; limit?: number;
}) {
  const sp = new URLSearchParams();
  if (params?.organization_id) sp.set("organization_id", params.organization_id);
  if (params?.workspace_id) sp.set("workspace_id", params.workspace_id);
  if (params?.provider_config_id) sp.set("provider_config_id", params.provider_config_id);
  if (params?.limit) sp.set("limit", String(params.limit));
  const qs = sp.toString();
  return fetchJSON<{ external_identities: SandboxV2ExternalIdentity[]; total: number }>(
    SBV2_BASE, `/iam/external-identities${qs ? `?${qs}` : ""}`,
  );
}

export async function listSandboxV2IAMMappingDecisions(params?: {
  organization_id?: string; workspace_id?: string; limit?: number;
}) {
  const sp = new URLSearchParams();
  if (params?.organization_id) sp.set("organization_id", params.organization_id);
  if (params?.workspace_id) sp.set("workspace_id", params.workspace_id);
  if (params?.limit) sp.set("limit", String(params.limit));
  const qs = sp.toString();
  return fetchJSON<{ mapping_decisions: SandboxV2IAMMappingDecision[]; total: number }>(
    SBV2_BASE, `/iam/mapping-decisions${qs ? `?${qs}` : ""}`,
  );
}

export async function listSandboxV2SSOSimulations(params?: {
  organization_id?: string; workspace_id?: string; limit?: number;
}) {
  const sp = new URLSearchParams();
  if (params?.organization_id) sp.set("organization_id", params.organization_id);
  if (params?.workspace_id) sp.set("workspace_id", params.workspace_id);
  if (params?.limit) sp.set("limit", String(params.limit));
  const qs = sp.toString();
  return fetchJSON<{ sso_simulations: SandboxV2SSOSimulationResult[]; total: number }>(
    SBV2_BASE, `/iam/sso-simulations${qs ? `?${qs}` : ""}`,
  );
}

// ═══════════════════ Step 18 — Observability API ═══════════════════

export async function getSandboxV2ObservabilityReadiness() {
  return fetchJSON<SandboxV2ObservabilityReadiness>(SBV2_BASE, "/observability/readiness");
}

export async function getSandboxV2PrometheusScrapeConfig(params?: {
  job_name?: string; host?: string;
}) {
  const sp = new URLSearchParams();
  if (params?.job_name) sp.set("job_name", params.job_name);
  if (params?.host) sp.set("host", params.host);
  const qs = sp.toString();
  return fetchJSON<Record<string, unknown>>(SBV2_BASE, `/observability/prometheus/scrape-config${qs ? `?${qs}` : ""}`);
}

export async function getSandboxV2PrometheusAlertRules() {
  return fetchJSON<Record<string, unknown>>(SBV2_BASE, "/observability/prometheus/alert-rules");
}

export async function getSandboxV2GrafanaDashboard(dashboardType: string = "overview") {
  return fetchJSON<{ dashboard: SandboxV2GrafanaDashboardSpec }>(
    SBV2_BASE, `/observability/grafana/dashboard?dashboard_type=${encodeURIComponent(dashboardType)}`,
  );
}

export async function generateSandboxV2GrafanaDashboard(dashboardType: string = "overview") {
  return fetchJSON<{ dashboard: SandboxV2GrafanaDashboardSpec; generated: boolean }>(
    SBV2_BASE, `/observability/grafana/dashboard/generate?dashboard_type=${encodeURIComponent(dashboardType)}`,
    { method: "POST" },
  );
}

export async function listSandboxV2TraceSpans(params?: {
  organization_id?: string; workspace_id?: string; trace_id?: string; limit?: number;
}) {
  const sp = new URLSearchParams();
  if (params?.organization_id) sp.set("organization_id", params.organization_id);
  if (params?.workspace_id) sp.set("workspace_id", params.workspace_id);
  if (params?.trace_id) sp.set("trace_id", params.trace_id);
  if (params?.limit) sp.set("limit", String(params.limit));
  const qs = sp.toString();
  return fetchJSON<{ traces: SandboxV2TraceSpan[]; total: number }>(
    SBV2_BASE, `/observability/traces${qs ? `?${qs}` : ""}`,
  );
}

export async function createSandboxV2TraceSpan(payload: {
  span_name?: string; trace_id?: string; parent_span_id?: string;
  organization_id?: string; workspace_id?: string;
  resource_type?: string; resource_id?: string;
  attributes?: Record<string, unknown>;
}) {
  return fetchJSON<{ trace_span: SandboxV2TraceSpan }>(
    SBV2_BASE, "/observability/traces", { method: "POST", body: JSON.stringify(payload) },
  );
}

export async function simulateSandboxV2OTelExport(payload: {
  signal_type?: string; items?: Record<string, unknown>[];
  organization_id?: string; workspace_id?: string;
}) {
  return fetchJSON<Record<string, unknown>>(
    SBV2_BASE, "/observability/otel/simulate-export", { method: "POST", body: JSON.stringify(payload) },
  );
}

export async function listSandboxV2TelemetryExportRecords(params?: {
  provider?: string; signal_type?: string; status?: string; limit?: number;
}) {
  const sp = new URLSearchParams();
  if (params?.provider) sp.set("provider", params.provider);
  if (params?.signal_type) sp.set("signal_type", params.signal_type);
  if (params?.status) sp.set("status", params.status);
  if (params?.limit) sp.set("limit", String(params.limit));
  const qs = sp.toString();
  return fetchJSON<{ export_records: SandboxV2TelemetryExportRecord[]; total: number }>(
    SBV2_BASE, `/observability/export-records${qs ? `?${qs}` : ""}`,
  );
}

// ═══════════════════ Step 19 — Load Testing / SLO API ═══════════════════

export async function getSandboxV2LoadTestingReadiness() {
  return fetchJSON<SandboxV2LoadTestingReadiness>(SBV2_BASE, "/load-testing/readiness");
}

export async function createSandboxV2LoadTestConfig(payload: {
  profile?: string; base_url_masked?: string; targets?: string[];
  max_users?: number; max_rps?: number; duration_seconds?: number;
  timeout_seconds?: number; allow_production?: boolean;
  require_confirmation?: boolean; organization_id?: string;
  workspace_id?: string; metadata?: Record<string, unknown>;
}) {
  return fetchJSON<{ load_test_config: SandboxV2LoadTestConfig }>(
    SBV2_BASE, "/load-testing/configs", { method: "POST", body: JSON.stringify(payload) },
  );
}

export async function listSandboxV2LoadTestConfigs(params?: { limit?: number }) {
  const sp = new URLSearchParams();
  if (params?.limit) sp.set("limit", String(params.limit));
  const qs = sp.toString();
  return fetchJSON<{ load_test_configs: SandboxV2LoadTestConfig[]; total: number }>(
    SBV2_BASE, `/load-testing/configs${qs ? `?${qs}` : ""}`,
  );
}

export async function runSandboxV2LoadTest(loadTestId: string, mode: string = "local") {
  return fetchJSON<Record<string, unknown>>(
    SBV2_BASE, `/load-testing/configs/${encodeURIComponent(loadTestId)}/run?mode=${encodeURIComponent(mode)}`,
    { method: "POST" },
  );
}

export async function listSandboxV2LoadTestResults(params?: {
  load_test_id?: string; target?: string; limit?: number;
}) {
  const sp = new URLSearchParams();
  if (params?.load_test_id) sp.set("load_test_id", params.load_test_id);
  if (params?.target) sp.set("target", params.target);
  if (params?.limit) sp.set("limit", String(params.limit));
  const qs = sp.toString();
  return fetchJSON<{ load_test_results: SandboxV2LoadTestResult[]; total: number }>(
    SBV2_BASE, `/load-testing/results${qs ? `?${qs}` : ""}`,
  );
}

export async function listSandboxV2SLODefinitions(params?: { limit?: number }) {
  const sp = new URLSearchParams();
  if (params?.limit) sp.set("limit", String(params.limit));
  const qs = sp.toString();
  return fetchJSON<{ slo_definitions: SandboxV2SLODefinition[]; total: number }>(
    SBV2_BASE, `/load-testing/slo/definitions${qs ? `?${qs}` : ""}`,
  );
}

export async function listSandboxV2SLOEvaluations(params?: {
  load_test_id?: string; slo_id?: string; limit?: number;
}) {
  const sp = new URLSearchParams();
  if (params?.load_test_id) sp.set("load_test_id", params.load_test_id);
  if (params?.slo_id) sp.set("slo_id", params.slo_id);
  if (params?.limit) sp.set("limit", String(params.limit));
  const qs = sp.toString();
  return fetchJSON<{ slo_evaluations: SandboxV2SLOEvaluation[]; total: number }>(
    SBV2_BASE, `/load-testing/slo/evaluations${qs ? `?${qs}` : ""}`,
  );
}

export async function evaluateSandboxV2LoadTestSLO(loadTestId: string) {
  return fetchJSON<Record<string, unknown>>(
    SBV2_BASE, `/load-testing/slo/evaluate/${encodeURIComponent(loadTestId)}`,
    { method: "POST" },
  );
}

export async function getSandboxV2LatestCapacityPlan() {
  return fetchJSON<{ capacity_plan: SandboxV2CapacityPlan | null }>(
    SBV2_BASE, "/load-testing/capacity/latest",
  );
}

export async function getSandboxV2LoadTestReport(loadTestId: string, format: "json" | "markdown" = "json") {
  return fetchJSON<{ load_test_id: string; format: string; report: unknown }>(
    SBV2_BASE, `/load-testing/report/${encodeURIComponent(loadTestId)}?format=${encodeURIComponent(format)}`,
  );
}
