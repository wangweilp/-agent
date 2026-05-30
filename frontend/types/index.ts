export interface Memory {
  id: string;
  content: string;
  summary: string | null;
  source: "user" | "agent" | "reflect";
  timestamp: string;
  importance: number;
  entities: string[];
  memory_type: "episodic" | "semantic" | "procedural" | "reflect";
  access_count: number;
  last_accessed: string | null;
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
