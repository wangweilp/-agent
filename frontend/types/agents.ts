/** Enterprise Agent Platform — 类型定义 */

export interface AgentSummary {
  agent_id: string;
  name: string;
  description: string;
  version: string;
  enabled: boolean;
  tags: string[];
  usage_count: number;
  success_rate: number;
  avg_duration_ms: number;
}

export interface AgentListResponse {
  total: number;
  enabled: number;
  agents: AgentSummary[];
}

export interface AgentDetail extends AgentSummary {
  status: string;
  metrics: Record<string, unknown>;
  config: Record<string, unknown>;
}

export interface AgentRunRequest {
  agent_id: string;
  title?: string;
  description?: string;
  input_data?: Record<string, unknown>;
  priority?: "low" | "medium" | "high" | "critical";
}

export interface AgentRunResponse {
  task_id: string;
  agent_id: string;
  agent_name: string;
  success: boolean;
  output: string;
  error?: string | null;
  plan: string[];
  observations: string[];
  reflections: string[];
  tool_calls_count: number;
  memory_calls_count: number;
  kg_calls_count: number;
  duration_ms: number;
}

export interface WorkflowNode {
  node_id: string;
  name: string;
  node_type: "agent" | "human" | "condition" | "parallel" | "tool" | "memory" | "knowledge_graph" | "start" | "end";
  agent_id: string;
  description: string;
  next_nodes: string[];
  human_prompt: string;
  status: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface Workflow {
  workflow_id: string;
  name: string;
  description: string;
  version: string;
  nodes: WorkflowNode[];
  start_node_id: string;
  tags: string[];
  created_at: string;
  updated_at: string;
}

export interface WorkflowExecution {
  execution_id: string;
  workflow_id: string;
  workflow_name: string;
  status: "draft" | "running" | "paused" | "completed" | "failed" | "cancelled";
  node_statuses: Record<string, string>;
  current_node_id: string;
  error?: string | null;
  duration_ms: number;
  started_at: string | null;
  finished_at: string | null;
}

export interface AgentStats {
  total_agents: number;
  enabled_agents: number;
  disabled_agents: number;
  total_usage: number;
  total_success: number;
  agents: AgentSummary[];
}

export interface WorkflowCreateNode {
  name: string;
  node_type: WorkflowNode["node_type"];
  agent_id?: string;
  description?: string;
  is_start?: boolean;
}

export interface WorkflowCreateRequest {
  name: string;
  description?: string;
  nodes: WorkflowCreateNode[];
  start_node_id?: string;
  tags?: string[];
}

export interface WorkflowExecuteRequest {
  input_data?: Record<string, unknown>;
}

// ── Scenario Types ──

export interface ScenarioDefinition {
  scenario_id: string;
  name: string;
  description: string;
  category: "automation" | "assistant";
  icon: string;
  input_schema: Record<string, string>;
  output_schema: Record<string, string>;
  required_permissions: string[];
  estimated_duration_ms: number;
}

export interface MeetingToTrainingRequest {
  meeting_title: string;
  meeting_notes: string;
  participants?: string[];
  department_id?: string;
}

export interface DepartmentAssistantRequest {
  department: string;
  question: string;
  context?: string;
}

export interface ScenarioRunResponse {
  success: boolean;
  scenario_id: string;
  execution_id: string;
  result: Record<string, unknown>;
  trace: Array<Record<string, unknown>>;
  metrics: Record<string, unknown>;
  error: string | null;
}

export interface MeetingToTrainingResult {
  scenario_id: string;
  workflow_execution_id: string | null;
  success: boolean;
  meeting_title: string;
  summary: string;
  decisions: string[];
  action_items: string[];
  knowledge_entries: Array<{ content: string }>;
  entity_suggestions: Array<{ name: string; entity_type: string }>;
  relation_suggestions: Array<{ source: string; target: string; predicate: string }>;
  training_outline: string[];
  training_qa: string[];
  execution_steps: Array<execution_step>;
  execution_trace: Array<Record<string, unknown>>;
  memory_refs: string[];
  knowledge_refs: string[];
  duration_ms: number;
  llm_available: boolean;
  fallback_mode: boolean;
  error: string | null;
}

export interface execution_step {
  step_index: number;
  node_id: string;
  node_name: string;
  node_type: string;
  status: string;
  started_at: string | null;
  finished_at: string | null;
  duration_ms: number;
  error: string | null;
  output_summary: string;
}

export interface DepartmentAssistantResult {
  scenario_id: string;
  success: boolean;
  department: string;
  question: string;
  answer: string;
  reasoning_summary: string;
  recommended_actions: string[];
  related_memories: Array<{ content: string }>;
  related_entities: Array<{ name: string; entity_type: string }>;
  confidence: number;
  confidence_reason: string;
  limitations: string[];
  execution_trace: Array<Record<string, unknown>>;
  execution_steps: execution_step[];
  memory_refs: string[];
  knowledge_refs: string[];
  related_memory_count: number;
  related_entity_count: number;
  duration_ms: number;
  llm_available: boolean;
  fallback_mode: boolean;
  workflow_execution_id: string | null;
  error: string | null;
}
