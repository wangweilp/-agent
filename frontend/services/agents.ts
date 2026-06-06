/** Enterprise Agent Platform — API 服务 */

import type {
  AgentListResponse,
  AgentDetail,
  AgentRunRequest,
  AgentRunResponse,
  AgentStats,
  Workflow,
  WorkflowCreateRequest,
  WorkflowExecution,
  WorkflowExecuteRequest,
} from "@/types/agents";

const BASE = "/agents";

async function fetchJSON<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(body || `${res.status} ${res.statusText}`);
  }
  return res.json();
}

// ── Agents ──

export async function listAgents(tag?: string, enabledOnly?: boolean): Promise<AgentListResponse> {
  const params = new URLSearchParams();
  if (tag) params.set("tag", tag);
  if (enabledOnly) params.set("enabled_only", "true");
  const qs = params.toString();
  return fetchJSON<AgentListResponse>(`${BASE}${qs ? `?${qs}` : ""}`);
}

export async function getAgent(agentId: string): Promise<AgentDetail> {
  return fetchJSON<AgentDetail>(`${BASE}/${agentId}`);
}

export async function runAgent(req: AgentRunRequest): Promise<AgentRunResponse> {
  return fetchJSON<AgentRunResponse>(`${BASE}/run`, {
    method: "POST",
    body: JSON.stringify(req),
  });
}

export async function enableAgent(agentId: string): Promise<void> {
  await fetchJSON(`${BASE}/${agentId}/enable`, { method: "POST" });
}

export async function disableAgent(agentId: string): Promise<void> {
  await fetchJSON(`${BASE}/${agentId}/disable`, { method: "POST" });
}

export async function updateAgentConfig(agentId: string, config: Record<string, unknown>): Promise<void> {
  await fetchJSON(`${BASE}/${agentId}/config`, {
    method: "PUT",
    body: JSON.stringify({ config }),
  });
}

export async function getAgentStats(): Promise<AgentStats> {
  return fetchJSON<AgentStats>(`${BASE}/stats/overview`);
}

// ── Workflows ──

export async function listWorkflows(): Promise<Workflow[]> {
  return fetchJSON<Workflow[]>(`${BASE}/workflows`);
}

export async function getWorkflow(workflowId: string): Promise<Workflow> {
  return fetchJSON<Workflow>(`${BASE}/workflows/${workflowId}`);
}

export async function createWorkflow(req: WorkflowCreateRequest): Promise<Workflow> {
  return fetchJSON<Workflow>(`${BASE}/workflows`, {
    method: "POST",
    body: JSON.stringify(req),
  });
}

export async function executeWorkflow(
  workflowId: string,
  req?: WorkflowExecuteRequest,
): Promise<WorkflowExecution> {
  return fetchJSON<WorkflowExecution>(`${BASE}/workflows/${workflowId}/execute`, {
    method: "POST",
    body: JSON.stringify(req || {}),
  });
}

export async function resumeExecution(
  executionId: string,
  humanInputs: Record<string, string>,
): Promise<WorkflowExecution> {
  return fetchJSON<WorkflowExecution>(`${BASE}/executions/${executionId}/resume`, {
    method: "POST",
    body: JSON.stringify({ human_inputs: humanInputs }),
  });
}

// ── Executions ──

export async function listExecutions(workflowId?: string): Promise<WorkflowExecution[]> {
  const params = workflowId ? `?workflow_id=${encodeURIComponent(workflowId)}` : "";
  return fetchJSON<WorkflowExecution[]>(`${BASE}/executions${params}`);
}

export async function getExecution(executionId: string): Promise<WorkflowExecution> {
  return fetchJSON<WorkflowExecution>(`${BASE}/executions/${executionId}`);
}
