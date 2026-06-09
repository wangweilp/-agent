/** Enterprise Agent Platform API client.
 *
 * Keep the backend API boundary explicit. The frontend owns `/agents` as a
 * page route, while FastAPI owns `${API_BASE}/agents` as an API route.
 */

import { getAccessToken } from "@/stores/auth-store";
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
  ScenarioDefinition,
  MeetingToTrainingRequest,
  DepartmentAssistantRequest,
  ScenarioRunResponse,
} from "@/types/agents";

const API_BASE = (process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
const AGENT_API_BASE = `${API_BASE}/agents`;

class AgentApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "AgentApiError";
  }
}

function getToken(): string | null {
  if (typeof window === "undefined") return null;

  const moduleToken = getAccessToken();
  if (moduleToken) return moduleToken;

  try {
    const raw = localStorage.getItem("agent-os-auth");
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    return parsed?.state?.token?.access_token || null;
  } catch {
    return null;
  }
}

async function fetchJSON<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init?.headers as Record<string, string> | undefined),
  };

  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  const res = await fetch(`${AGENT_API_BASE}${path}`, {
    ...init,
    headers,
  });

  const contentType = res.headers.get("content-type") || "";
  const raw = await res.text();

  if (!res.ok) {
    let message = `Agent API ${res.status}`;
    try {
      const parsed = JSON.parse(raw);
      message = parsed.detail || parsed.message || message;
    } catch {
      if (raw.trim()) message = raw.trim().slice(0, 300);
    }
    throw new AgentApiError(res.status, message);
  }

  if (!contentType.includes("application/json")) {
    throw new AgentApiError(
      res.status,
      "Agent API 返回的不是 JSON。请确认前端正在请求后端 API，而不是前端页面路由。",
    );
  }

  return JSON.parse(raw) as T;
}

// Agents

export async function listAgents(tag?: string, enabledOnly?: boolean): Promise<AgentListResponse> {
  const params = new URLSearchParams();
  if (tag) params.set("tag", tag);
  if (enabledOnly) params.set("enabled_only", "true");
  const qs = params.toString();
  return fetchJSON<AgentListResponse>(qs ? `?${qs}` : "");
}

export async function getAgent(agentId: string): Promise<AgentDetail> {
  return fetchJSON<AgentDetail>(`/${encodeURIComponent(agentId)}`);
}

export async function runAgent(req: AgentRunRequest): Promise<AgentRunResponse> {
  return fetchJSON<AgentRunResponse>("/run", {
    method: "POST",
    body: JSON.stringify(req),
  });
}

export async function enableAgent(agentId: string): Promise<void> {
  await fetchJSON(`/${encodeURIComponent(agentId)}/enable`, { method: "POST" });
}

export async function disableAgent(agentId: string): Promise<void> {
  await fetchJSON(`/${encodeURIComponent(agentId)}/disable`, { method: "POST" });
}

export async function updateAgentConfig(
  agentId: string,
  config: Record<string, unknown>,
): Promise<void> {
  await fetchJSON(`/${encodeURIComponent(agentId)}/config`, {
    method: "PUT",
    body: JSON.stringify({ config }),
  });
}

export async function getAgentStats(): Promise<AgentStats> {
  return fetchJSON<AgentStats>("/stats/overview");
}

// Workflows

export async function listWorkflows(): Promise<Workflow[]> {
  return fetchJSON<Workflow[]>("/workflows");
}

export async function getWorkflow(workflowId: string): Promise<Workflow> {
  return fetchJSON<Workflow>(`/workflows/${encodeURIComponent(workflowId)}`);
}

export async function createWorkflow(req: WorkflowCreateRequest): Promise<Workflow> {
  return fetchJSON<Workflow>("/workflows", {
    method: "POST",
    body: JSON.stringify(req),
  });
}

export async function executeWorkflow(
  workflowId: string,
  req?: WorkflowExecuteRequest,
): Promise<WorkflowExecution> {
  return fetchJSON<WorkflowExecution>(`/workflows/${encodeURIComponent(workflowId)}/execute`, {
    method: "POST",
    body: JSON.stringify(req || {}),
  });
}

export async function resumeExecution(
  executionId: string,
  humanInputs: Record<string, string>,
): Promise<WorkflowExecution> {
  return fetchJSON<WorkflowExecution>(`/executions/${encodeURIComponent(executionId)}/resume`, {
    method: "POST",
    body: JSON.stringify({ human_inputs: humanInputs }),
  });
}

// Executions

export async function listExecutions(workflowId?: string): Promise<WorkflowExecution[]> {
  const params = workflowId ? `?workflow_id=${encodeURIComponent(workflowId)}` : "";
  return fetchJSON<WorkflowExecution[]>(`/executions${params}`);
}

export async function getExecution(executionId: string): Promise<WorkflowExecution> {
  return fetchJSON<WorkflowExecution>(`/executions/${encodeURIComponent(executionId)}`);
}

// Scenarios

export async function listScenarios(): Promise<ScenarioDefinition[]> {
  return fetchJSON<ScenarioDefinition[]>("/scenarios");
}

export async function getScenario(scenarioId: string): Promise<ScenarioDefinition> {
  return fetchJSON<ScenarioDefinition>(`/scenarios/${encodeURIComponent(scenarioId)}`);
}

export async function runMeetingToTraining(
  req: MeetingToTrainingRequest,
): Promise<ScenarioRunResponse> {
  return fetchJSON<ScenarioRunResponse>("/scenarios/meeting-to-training/run", {
    method: "POST",
    body: JSON.stringify(req),
  });
}

export async function runDepartmentAssistant(
  req: DepartmentAssistantRequest,
): Promise<ScenarioRunResponse> {
  return fetchJSON<ScenarioRunResponse>("/scenarios/department-assistant/run", {
    method: "POST",
    body: JSON.stringify(req),
  });
}
