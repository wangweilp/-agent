/** Open Platform — 类型定义。与后端 /developers API response 对齐。 */

// ═══════════════════════════════════════════
// Enums
// ═══════════════════════════════════════════

export type DeveloperStatus = "pending" | "active" | "suspended" | "rejected";
export type ApiKeyStatus = "active" | "revoked" | "expired";
export type SubmissionStatus = "draft" | "submitted" | "in_review" | "approved" | "rejected" | "published" | "withdrawn";
export type RuntimeType = "manifest_only" | "knowledge" | "workflow" | "http" | "external";
export type SandboxLevel = "no_execution" | "restricted" | "isolated";
export type SubmissionSourceType = "manifest" | "package_url" | "repository";
export type ReviewDecision = "approve" | "reject" | "request_changes";

// ═══════════════════════════════════════════
// Developer Account
// ═══════════════════════════════════════════

export interface DeveloperAccount {
  developer_id: string;
  user_id: string;
  tenant_id: string;
  display_name: string;
  organization_name: string | null;
  website: string | null;
  contact_email: string;
  status: DeveloperStatus;
  verified: boolean;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

// ═══════════════════════════════════════════
// API Key (no key_hash, raw_key only in create)
// ═══════════════════════════════════════════

export interface DeveloperApiKey {
  api_key_id: string;
  developer_id: string;
  key_prefix: string;
  name: string;
  scopes: string[];
  status: ApiKeyStatus;
  expires_at: string | null;
  last_used_at: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface CreateApiKeyResponse {
  api_key: DeveloperApiKey;
  raw_key: string;
}

// ═══════════════════════════════════════════
// Security Profile
// ═══════════════════════════════════════════

export interface SecurityProfile {
  requires_network: boolean;
  reads_user_data: boolean;
  writes_user_data: boolean;
  sandbox_level: SandboxLevel;
  allowed_domains: string[];
  data_access_scope: string[];
  risk_notes: string | null;
}

// ═══════════════════════════════════════════
// Agent Manifest
// ═══════════════════════════════════════════

export interface AgentManifest {
  name: string;
  display_name: string;
  description: string;
  version: string;
  capabilities: string[];
  required_permissions: string[];
  supported_workflows: string[];
  runtime_type: RuntimeType;
  entrypoint: string | null;
  config_schema: Record<string, unknown>;
  usage_limits: Record<string, unknown>;
  security_profile: SecurityProfile | null;
  metadata: Record<string, unknown>;
}

// ═══════════════════════════════════════════
// Manifest Validation
// ═══════════════════════════════════════════

export interface ManifestValidationResult {
  valid: boolean;
  errors: string[];
  warnings: string[];
}

// ═══════════════════════════════════════════
// Agent Submission
// ═══════════════════════════════════════════

export interface AgentSubmission {
  submission_id: string;
  developer_id: string;
  tenant_id: string;
  marketplace_agent_id: string | null;
  agent_manifest: AgentManifest | null;
  package_url: string | null;
  source_type: SubmissionSourceType;
  status: SubmissionStatus;
  review_notes: string | null;
  submitted_at: string | null;
  reviewed_at: string | null;
  reviewed_by: string | null;
  published_at: string | null;
  created_at: string;
  updated_at: string;
  metadata: Record<string, unknown>;
}

// ═══════════════════════════════════════════
// Review Record
// ═══════════════════════════════════════════

export interface AgentReviewRecord {
  review_id: string;
  submission_id: string;
  reviewer_id: string;
  decision: ReviewDecision;
  notes: string;
  checklist: Record<string, unknown>;
  created_at: string;
  metadata: Record<string, unknown>;
}

// ═══════════════════════════════════════════
// API Request Types
// ═══════════════════════════════════════════

export interface DeveloperRegisterRequest {
  display_name?: string;
  organization_name?: string | null;
  website?: string | null;
  contact_email?: string;
  metadata?: Record<string, unknown>;
}

export interface DeveloperUpdateRequest {
  display_name?: string;
  organization_name?: string | null;
  website?: string | null;
  contact_email?: string;
  metadata?: Record<string, unknown>;
}

export interface CreateApiKeyRequest {
  name: string;
  scopes: string[];
  expires_at?: string | null;
  metadata?: Record<string, unknown>;
}

export interface CreateSubmissionRequest {
  agent_manifest: Record<string, unknown>;
  package_url?: string | null;
  source_type?: string;
  metadata?: Record<string, unknown>;
}

export interface UpdateSubmissionRequest {
  agent_manifest?: Record<string, unknown>;
  package_url?: string | null;
  source_type?: string;
  metadata?: Record<string, unknown>;
}

// ═══════════════════════════════════════════
// API Response Types
// ═══════════════════════════════════════════

export interface DeveloperMeResponse {
  developer: DeveloperAccount;
}

export interface VerifyRequestResponse {
  success: boolean;
  message: string;
}

export interface ApiKeyListResponse {
  api_keys: DeveloperApiKey[];
  total: number;
}

export interface SubmissionListResponse {
  submissions: AgentSubmission[];
  total: number;
}

export interface SubmissionDetailResponse {
  submission: AgentSubmission;
}

export interface ValidateSubmissionResponse {
  valid: boolean;
  errors: string[];
  warnings: string[];
}

// ═══════════════════════════════════════════
// Admin Review API Types (Step 22-G)
// ═══════════════════════════════════════════

export interface AdminSubmissionListResponse {
  submissions: AgentSubmission[];
  total: number;
}

export interface AdminSubmissionDetailResponse {
  submission: AgentSubmission;
  developer: DeveloperAccount | null;
  validation: ManifestValidationResult;
  latest_review_record: AgentReviewRecord | null;
}

export interface AdminReviewListResponse {
  reviews: AgentReviewRecord[];
  total: number;
}

export interface ReviewActionRequest {
  notes: string;
  checklist: Record<string, unknown>;
}

export interface AdminSubmissionFilters {
  status?: SubmissionStatus;
  tenant_id?: string;
  developer_id?: string;
}

// ═══════════════════════════════════════════
// Publish (Step 22-H)
// ═══════════════════════════════════════════

export interface PublishSubmissionResponse {
  success: boolean;
  submission: AgentSubmission;
  marketplace_agent: Record<string, unknown>;
  message: string;
}
