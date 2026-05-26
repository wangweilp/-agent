import { create } from "zustand";
import type { Message, ToolCall } from "@/types";

interface ChatState {
  messages: Message[];
  streaming: boolean;
  streamingText: string;
  toolCalls: ToolCall[];
  isThinking: boolean;
  addMessage: (m: Message) => void;
  setStreaming: (v: boolean) => void;
  appendStreamToken: (t: string) => void;
  flushStream: (role: "assistant") => void;
  addToolCall: (tc: ToolCall) => void;
  updateToolCall: (id: string, partial: Partial<ToolCall>) => void;
  setThinking: (v: boolean) => void;
  clear: () => void;
}

export const useChatStore = create<ChatState>((set) => ({
  messages: [],
  streaming: false,
  streamingText: "",
  toolCalls: [],
  isThinking: false,

  addMessage: (m) =>
    set((s) => ({ messages: [...s.messages, m] })),
  setStreaming: (streaming) => set({ streaming }),
  appendStreamToken: (t) =>
    set((s) => ({ streamingText: s.streamingText + t })),
  flushStream: (role) =>
    set((s) => {
      if (!s.streamingText.trim()) return s;
      return {
        messages: [...s.messages, { role, content: s.streamingText }],
        streamingText: "",
        toolCalls: [],
      };
    }),
  addToolCall: (tc) =>
    set((s) => ({ toolCalls: [...s.toolCalls, tc] })),
  updateToolCall: (id, partial) =>
    set((s) => ({
      toolCalls: s.toolCalls.map((t) =>
        t.call_id === id ? { ...t, ...partial } : t,
      ),
    })),
  setThinking: (isThinking) => set({ isThinking }),
  clear: () =>
    set({ messages: [], streamingText: "", toolCalls: [], isThinking: false }),
}));
