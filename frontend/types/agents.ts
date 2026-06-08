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
  node_type: "agent" | "human" | "condition" | "parallel" | "start" | "end";
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
