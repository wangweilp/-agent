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
