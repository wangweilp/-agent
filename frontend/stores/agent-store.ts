import { create } from "zustand";
import type { AgentStatus, TraceEntry } from "@/types";

interface AgentState {
  status: AgentStatus["status"];
  traceId: string;
  traces: TraceEntry[];
  setStatus: (s: AgentStatus["status"]) => void;
  setTraces: (t: TraceEntry[]) => void;
  addTrace: (t: TraceEntry) => void;
  updateTrace: (id: string, partial: Partial<TraceEntry>) => void;
}

export const useAgentStore = create<AgentState>((set) => ({
  status: "idle",
  traceId: "",
  traces: [],

  setStatus: (status) => set({ status }),
  setTraces: (traces) => set({ traces }),
  addTrace: (trace) =>
    set((s) => ({ traces: [...s.traces.slice(-99), trace] })),
  updateTrace: (id, partial) =>
    set((s) => ({
      traces: s.traces.map((t) => (t.id === id ? { ...t, ...partial } : t)),
    })),
}));
