import { create } from "zustand";
import type { AgentStatus, DashboardMetrics, TraceEntry } from "@/types";

interface AgentState {
  status: AgentStatus["status"];
  traceId: string;
  metrics: DashboardMetrics | null;
  traces: TraceEntry[];
  setStatus: (s: AgentStatus["status"]) => void;
  setMetrics: (m: DashboardMetrics) => void;
  setTraces: (t: TraceEntry[]) => void;
  addTrace: (t: TraceEntry) => void;
  updateTrace: (id: string, partial: Partial<TraceEntry>) => void;
}

export const useAgentStore = create<AgentState>((set) => ({
  status: "idle",
  traceId: "",
  metrics: null,
  traces: [],

  setStatus: (status) => set({ status }),
  setMetrics: (metrics) => set({ metrics }),
  setTraces: (traces) => set({ traces }),
  addTrace: (trace) =>
    set((s) => ({ traces: [...s.traces.slice(-99), trace] })),
  updateTrace: (id, partial) =>
    set((s) => ({
      traces: s.traces.map((t) => (t.id === id ? { ...t, ...partial } : t)),
    })),
}));
