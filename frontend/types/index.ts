export interface Memory {
  id: string;
  content: string;
  summary: string | null;
  source: "user" | "agent" | "reflect";
  timestamp: string;
  importance: number;
  entities: string[];
  relations?: Array<{ s: string; p: string; o: string }>;
  memory_type: "episodic" | "semantic" | "procedural" | "reflect";
  access_count: number;
  last_accessed: string | null;
  status: string;
  archived_at: string | null;
  embedding_status?: string;
}

export interface ToolCall {
  tool_name: string;
  arguments: Record<string, unknown>;
  call_id: string;
  status: "pending" | "running" | "success" | "failed";
  started_at: string | null;
  finished_at: string | null;
}

export interface ToolResult {
  tool_name: string;
  success: boolean;
  content: string;
  error: string | null;
  metadata: Record<string, unknown>;
}

export interface Message {
  role: "system" | "user" | "assistant" | "tool";
  content: string;
  timestamp?: string;
  tool_calls?: ToolCall[];
  tool_call_id?: string;
}

export interface ChatRequest {
  content: string;
}

export interface ChatResponse {
  reply: string;
}

export interface AgentStatus {
  status: "idle" | "thinking" | "acting" | "reflecting";
  short_term_size: number;
  trace_id: string;
  memory_count: number;
  tool_calls_total: number;
  uptime: number;
}

export interface DashboardMetrics {
  memory_count: number;
  memory_growth: number;
  recall_success_rate: number;
  reflection_count: number;
  tool_calls_today: number;
  avg_latency_ms: number;
  token_usage: number;
  active_sessions: number;
}

export interface ReflectionInsight {
  id: string;
  topic: string;
  finding: string;
  confidence: number;
  timestamp: string;
  related_memories: string[];
}

export interface ToolInfo {
  name: string;
  description: string;
  category: string;
  requires_confirmation: boolean;
  call_count: number;
  avg_duration_ms: number;
  success_rate: number;
  risk_level: "low" | "medium" | "high";
  enabled: boolean;
}

export interface TraceEntry {
  id: string;
  step: string;
  type: "llm_call" | "tool_call" | "reflection" | "memory_write" | "memory_read";
  status: "success" | "failed" | "running";
  duration_ms: number;
  timestamp: string;
  detail: string;
}

export interface RuntimeStats {
  worker: {
    alive: boolean;
    started_at: string;
    uptime_seconds: number;
  };
  queue: {
    pending: number;
    total_stored: number;
    total_failed: number;
  };
  dead_letter: {
    count: number;
    dir: string;
  };
  recent_tasks: Array<{
    task_id: string;
    call_id: string;
    status: string;
    content_preview: string;
    elapsed_ms: number;
    submitted_at: string;
  }>;
}

export interface UploadTask {
  task_id: string;
  memory_type: string;
  content: string;
  status: string;
  entities?: string[];
  importance?: number;
}

export interface UploadResult {
  status: string;
  files_count: number;
  total_tasks_enqueued: number;
  analysis_time_ms: number;
  total_time_ms: number;
  queue_depth: number;
  items: Array<{
    file_id: string;
    filename: string;
    size_bytes: number;
    analysis: {
      summary: string;
      scene_type: string;
      text_in_image: string;
      entities?: string[];
      structured_json?: {
        text_in_image: string;
        entities: string[];
        scene_type: string;
        object_list: string[];
      } | null;
      trigger?: {
        matched: boolean;
        reason: string;
      };
    };
    tasks: UploadTask[];
    task_count: number;
    error?: string;
  }>;
  worker: {
    alive: boolean;
    total_stored: number;
    total_failed: number;
    dlq_count: number;
  };
  alerts: Array<{
    level: string;
    type: string;
    message: string;
    threshold: number;
    current: number;
  }>;
}

export interface StreamEvent {
  event: "token" | "tool_call" | "tool_result" | "done" | "error";
  data: Record<string, unknown>;
}

// ── Dashboard 新接口 ──

export interface DashboardSummary {
  total_memories: number;
  active_memories: number;
  archived_memories: number;
  merged_memories: number;
  deleted_memories: number;
  episodic_count: number;
  semantic_count: number;
  reflect_count: number;
  weekly_growth: number;
  queue_depth: number;
  dlq_count: number;
}

export interface TopicItem {
  name: string;
  mention_count: number;
  memory_count: number;
}

export interface EntityItem {
  name: string;
  entity_type: string;
  mention_count: number;
  first_seen: string | null;
}

export interface RecentMemoryItem {
  id: string;
  content_preview: string;
  source: string;
  timestamp: string;
  importance: number;
  memory_type: string;
  status: string;
  entities: string[];
}

export interface RecentReflectionItem {
  id: string;
  topic: string;
  finding: string;
  importance: number;
  timestamp: string;
  entities: string[];
}

export interface WeeklyReportPlaceholder {
  status: string;
  message: string;
  stats: {
    week_new_memories: number;
    week_reflections: number;
    week_top_entities: string[];
  };
}

// ── Memory Management ──

export interface MemorySearchParams {
  q?: string;
  type?: string;
  status?: string;
  date_from?: string;
  date_to?: string;
  semantic?: boolean;
  limit?: number;
}

export interface MemoryUpdateRequest {
  content?: string;
  summary?: string;
  importance?: number;
  entities?: string[];
  memory_type?: string;
}

export interface MemoryMergeRequest {
  primary_id: string;
  secondary_ids: string[];
}

export interface MemoryMergeResponse {
  primary_id: string;
  merged_ids: string[];
  merged_count: number;
}

// ── Timeline ──

export type TimelineEventType =
  | "memory_created"
  | "memory_archived"
  | "memory_merged"
  | "memory_promoted"
  | "image_uploaded"
  | "reflection_generated"
  | "weekly_report_generated";

export interface TimelineEvent {
  id: string;
  type: TimelineEventType;
  content_preview: string;
  memory_type: string;
  importance: number;
  entities: string[];
  timestamp: string;
  status: string;
}

export interface TimelineDay {
  date: string;
  events: TimelineEvent[];
  count: number;
}

export interface TimelineStats {
  total_events: number;
  created_count: number;
  archived_count: number;
  merged_count: number;
  reflection_count: number;
  image_count: number;
  promoted_count: number;
  weekly_report_count: number;
}

// ── Graph ──

export interface GraphNode {
  id: string;
  label: string;
  type: "entity" | "memory" | "concept" | "image";
  importance: number;
  memory_count: number;
  group: string;
}

export interface GraphEdge {
  source: string;
  target: string;
  relation: string;
  weight: number;
}

export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
  stats: {
    node_count: number;
    edge_count: number;
    entity_nodes?: number;
    concept_nodes?: number;
    top_entities?: string[];
    top_entities_count?: number[];
    center_entity?: string;
    depth?: number;
  };
}

export interface EntityDetail {
  name: string;
  entity_type: string;
  mention_count: number;
  first_seen: string | null;
  related_memories: Array<{
    id: string;
    content_preview: string;
    source: string;
    timestamp: string;
    importance: number;
    memory_type: string;
  }>;
  related_entities: Array<{
    name: string;
    entity_type: string;
    mention_count: number;
    co_count: number;
  }>;
  recent_activity: Array<{
    id: string;
    content_preview: string;
    timestamp: string;
    memory_type: string;
    importance: number;
  }>;
}

// ── Audio ──

export interface AudioAnalysis {
  summary: string;
  topic: string;
  sentiment: string;
  key_points: string[];
  action_items: string[];
  entities: string[];
  transcription_preview: string;
  duration_seconds: number;
  importance_hint: number;
}

export interface AudioUploadResult {
  status: string;
  files_count: number;
  total_tasks_enqueued: number;
  analysis_time_ms: number;
  total_time_ms: number;
  queue_depth: number;
  items: Array<{
    file_id: string;
    filename: string;
    size_bytes: number;
    analysis: AudioAnalysis;
    tasks: Array<{ task_id: string; memory_type: string; status: string; importance: number }>;
    task_count: number;
  }>;
  worker: {
    alive: boolean;
    total_stored: number;
    total_failed: number;
    dlq_count: number;
  };
  alerts: Array<{ level: string; type: string; message: string; threshold: number; current: number }>;
}

// ── Video ──

export interface VideoAnalysis {
  summary: string;
  topic: string;
  key_points: string[];
  entities: string[];
  concepts: string[];
  ocr_text_preview: string;
  transcription_preview: string;
  duration_seconds: number;
  keyframe_count: number;
  importance_hint: number;
}

export interface VideoUploadResult {
  status: string;
  files_count: number;
  total_tasks_enqueued: number;
  analysis_time_ms: number;
  total_time_ms: number;
  queue_depth: number;
  items: Array<{
    file_id: string;
    filename: string;
    size_bytes: number;
    analysis: VideoAnalysis;
    tasks: Array<{ task_id: string; memory_type: string; status: string; importance: number }>;
    task_count: number;
  }>;
  worker: {
    alive: boolean;
    total_stored: number;
    total_failed: number;
    dlq_count: number;
  };
  alerts: Array<{ level: string; type: string; message: string; threshold: number; current: number }>;
}

// ── Auth & Workspace ──

export type WorkspaceRole = "owner" | "admin" | "member" | "viewer";

export interface AuthUser {
  id: string;
  email: string;
  name: string;
  avatar_url: string | null;
  auth_provider: string;
  created_at: string;
}

export interface AuthTokens {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export interface Workspace {
  id: string;
  name: string;
  owner_id?: string;
  members?: number;
  role?: WorkspaceRole;
  created_at?: string;
}

export interface WorkspaceMember {
  user_id: string;
  name: string;
  email: string;
  avatar_url: string | null;
  role: WorkspaceRole;
  joined_at: string;
}

export interface LoginResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  user: AuthUser;
  workspace: Workspace | null;
}

export interface RegisterResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  user: AuthUser;
  workspace: Workspace | null;
}

export interface WorkspaceDashboard {
  total_members: number;
  total_memories: number;
  total_actions: number;
  completed_actions: number;
  member_contributions: Record<string, number>;
  recent_activity: string[];
}

export interface ActivityEvent {
  id: string;
  workspace_id: string;
  user_id: string;
  user_name: string;
  event_type: string;
  message: string;
  timestamp: string;
}

export interface AuditLogEntry {
  id: string;
  user_id: string;
  action: string;
  resource_type: string;
  resource_id: string;
  detail: string;
  timestamp: string;
}

export interface ActionPlan {
  id: string;
  title: string;
  description: string;
  assigned_to: string | null;
  assigned_by: string;
  priority: "low" | "medium" | "high" | "urgent";
  status: "pending" | "in_progress" | "completed" | "cancelled";
  due_date: string | null;
  related_memory_ids: string[];
  created_at: string;
  completed_at: string | null;
}

export interface Notification {
  id: string;
  title: string;
  body: string;
  read: boolean;
  created_at: string;
  link: string;
}

// ── SaaS: Billing ──

export interface BillingAccount {
  id: string;
  tenant_id: string;
  currency: string;
  balance: number;
  billing_email: string;
  created_at: string;
}

export interface PaymentIntent {
  id: string;
  client_secret: string;
  qr_code_url: string;
  amount: number;
  currency: string;
  provider: string;
  created_at: string;
}

export interface Invoice {
  id: string;
  invoice_number: string;
  amount: number;
  currency: string;
  status: string;
  description: string;
  due_date: string | null;
  paid_at: string | null;
  period_start: string | null;
  period_end: string | null;
  created_at: string;
}

export interface Payment {
  id: string;
  amount: number;
  currency: string;
  provider: string;
  status: string;
  description: string;
  invoice_id: string | null;
  created_at: string;
}

export interface Refund {
  id: string;
  payment_id: string;
  amount: number;
  status: string;
  reason: string;
  created_at: string;
}

// ── SaaS: Subscription ──

export interface PlanPreview {
  tier: string;
  monthly_price: number;
  yearly_price: number;
  current: boolean;
  limits: PlanLimit;
}

export interface PlanLimit {
  tier: string;
  memory_count: number;
  search_count: number;
  storage_mb: number;
  import_per_day: number;
  sync_connectors: number;
  knowledge_graph: boolean;
  ai_coach: boolean;
  team_members: number;
  api_access: boolean;
  priority_support: boolean;
  llm_calls_per_day: number;
  embedding_calls_per_day: number;
}

export interface Subscription {
  id: string;
  tenant_id: string;
  plan_tier: string;
  status: string;
  billing_cycle: string;
  current_period_start: string;
  current_period_end: string | null;
  trial_start: string | null;
  trial_end: string | null;
  canceled_at: string | null;
  auto_renew: boolean;
  coupon_code: string | null;
  days_remaining: number;
  created_at: string;
}

export interface LimitCheckResult {
  resource: string;
  allowed: boolean;
  used: number;
  limit: number;
  remaining: number;
}

// ── SaaS: Usage ──

export interface UsageStats {
  tenant_id: string;
  period_start: string;
  period_end: string;
  total_events: number;
  by_resource: Record<string, number>;
  total_cost_cents: number;
  by_resource_cost: Record<string, number>;
}

export interface DailyUsage {
  date: string;
  count: number;
  cost: number;
}

export interface UserProfile {
  tenant_id: string;
  user_id: string;
  total_memories: number;
  total_searches: number;
  total_imports: number;
  coach_sessions: number;
  active_days: number;
  last_active: string | null;
  preferred_features: string[];
  engagement_score: number;
  is_power_user: boolean;
}

export interface PlatformStats {
  mrr_cents: number;
  arr_cents: number;
  total_tenants: number;
  active_tenants: number;
  trial_tenants: number;
  paying_tenants: number;
  conversion_rate: number;
  churn_rate: number;
  retention_rate: number;
  avg_revenue_per_user: number;
  total_revenue_cents: number;
}

// ── SaaS: Tenant ──

export interface Tenant {
  id: string;
  name: string;
  email: string;
  slug: string;
  status: string;
  owner_user_id: string;
  org_size: string;
  industry: string;
  website: string;
  created_at: string;
}

export interface TenantMember {
  id: string;
  tenant_id: string;
  user_id: string;
  role: string;
  org_id: string | null;
  joined_at: string;
}

export interface Organization {
  id: string;
  tenant_id: string;
  name: string;
  parent_org_id: string | null;
  description: string;
  created_at: string;
}

// ── SaaS: Growth ──

export interface Invite {
  id: string;
  invite_code: string;
  invitee_email: string;
  status: string;
  expires_at: string;
  created_at: string;
}

export interface Referral {
  id: string;
  referral_code: string;
  status: string;
  reward_granted: boolean;
  reward_amount_cents: number;
  created_at: string;
}

export interface ReferralStats {
  total_referrals: number;
  completed_referrals: number;
  total_rewards_cents: number;
}

export interface Coupon {
  id: string;
  code: string;
  coupon_type: string;
  value: number;
  status: string;
  usage_count: number;
  usage_limit: number;
  valid_until: string;
}

export interface RedeemedCoupon {
  id: string;
  code: string;
  discount_cents: number;
  redeemed_at: string;
}

export interface TrialRecord {
  id: string;
  tenant_id: string;
  plan_tier: string;
  status: string;
  trial_days: number;
  started_at: string;
  ends_at: string;
  converted_at: string | null;
  converted_to_plan: string;
  extended_count: number;
}

export interface TrialConversionStats {
  total_trials: number;
  converted_trials: number;
  conversion_rate: number;
  avg_days_to_convert: number;
}

// ── Growth & Analytics Center ──

export interface AnalyticsMetrics {
  mrr_cents: number;
  arr_cents: number;
  total_tenants: number;
  active_tenants: number;
  paying_tenants: number;
  trial_tenants: number;
  conversion_rate: number;
  churn_rate: number;
  retention_rate: number;
  avg_revenue_per_user: number;
  total_revenue_cents: number;
}

export interface MemoryTrend {
  tenant_id: string;
  period: string;
  trend: Array<{ date: string; count: number; cost: number }>;
}

export interface ResourceUsageTrend {
  tenant_id: string;
  resource: string;
  days: number;
  trend: Array<{ date: string; count: number; cost: number }>;
}

export interface ImportChannelBreakdown {
  tenant_id: string;
  channels: Record<string, number>;
  total_imports: number;
}

export interface RetentionCohort {
  tenant_id: string;
  months: number;
  cohort: Array<{
    month: string;
    new_tenants: number;
    retained: number;
    retention_rate: number;
  }>;
}

export interface RealtimeMetrics {
  tenant_id: string;
  today_events: number;
  today_cost_cents: number;
  active_users_today: number;
  max_hourly_events: number;
  hourly_breakdown: Record<string, number>;
}

// ── Alerts ──

export interface AlertRule {
  id: string;
  tenant_id: string;
  name: string;
  metric: string;
  condition: string;
  threshold: number;
  severity: "info" | "warning" | "critical";
  channel: "email" | "system" | "both";
  enabled: boolean;
  cooldown_minutes: number;
  last_triggered_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface AlertEvent {
  id: string;
  tenant_id: string;
  rule_id: string;
  rule_name: string;
  metric: string;
  current_value: number;
  threshold: number;
  severity: string;
  channel: string;
  message: string;
  acknowledged: boolean;
  triggered_at: string;
}

export interface TestAlertResult {
  success: boolean;
  message: string;
  channel: string;
}

// ── Reports ──

export interface ReportData {
  report_type: string;
  period_start: string;
  period_end: string;
  mrr_cents: number;
  arr_cents: number;
  total_tenants: number;
  active_tenants: number;
  paying_tenants: number;
  trial_tenants: number;
  conversion_rate: number;
  churn_rate: number;
  retention_rate: number;
  total_memories_created: number;
  total_llm_calls: number;
  total_embedding_calls: number;
  total_searches: number;
  total_imports: number;
  total_syncs: number;
  total_coach_sessions: number;
  total_cost_cents: number;
  total_revenue_cents: number;
  net_revenue_cents: number;
  margin_percent: number;
  active_users: number;
  new_users: number;
  top_entities: Array<Record<string, unknown>>;
  top_contributors: Array<Record<string, unknown>>;
  import_channels: Record<string, number>;
  daily_usage_trend: Array<Record<string, unknown>>;
  memory_growth_trend: Array<Record<string, unknown>>;
}

export interface Report {
  id: string;
  tenant_id: string;
  report_type: "weekly" | "monthly" | "quarterly";
  period_start: string;
  period_end: string;
  format: "json" | "csv" | "pdf";
  status: "generating" | "ready" | "failed";
  data: ReportData | null;
  file_path: string | null;
  created_at: string;
}

// ── RBAC ──

export interface RbacUser {
  id: string;
  name: string;
  email: string;
  roles: string[];
  org_id: string | null;
  org_name: string | null;
  department: string | null;
  created_at?: string;
}

export interface RbacRole {
  id: string;
  name: string;
  permissions: string[];
  is_system?: boolean;
  description?: string;
}

// ── Admin ──

export interface AdminSummary {
  total_orgs: number;
  total_users: number;
  total_memories: number;
  growth_rate_weekly: number;
  audit_events_30d: number;
  risk_events: number;
}

export interface GrowthDataPoint {
  week: string;
  count: number;
}

export interface AdminConfig {
  db_type: string;
  vector_store: string;
  llm_provider: string;
  embedding_model: string;
  auth_enabled: boolean;
  cors_origins: string[];
  log_level: string;
  environment: string;
}
