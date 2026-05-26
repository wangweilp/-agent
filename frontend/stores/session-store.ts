import { create } from "zustand";

export interface Session {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
}

interface SessionState {
  sessions: Session[];
  activeId: string | null;
  setSessions: (s: Session[]) => void;
  setActive: (id: string) => void;
  addSession: (s: Session) => void;
  removeSession: (id: string) => void;
}

export const useSessionStore = create<SessionState>((set) => ({
  sessions: [
    { id: "1", title: "今天的对话", created_at: new Date().toISOString(), updated_at: new Date().toISOString(), message_count: 0 },
  ],
  activeId: "1",

  setSessions: (sessions) => set({ sessions }),
  setActive: (activeId) => set({ activeId }),
  addSession: (session) =>
    set((s) => ({ sessions: [session, ...s.sessions] })),
  removeSession: (id) =>
    set((s) => ({
      sessions: s.sessions.filter((x) => x.id !== id),
      activeId: s.activeId === id ? s.sessions[0]?.id || null : s.activeId,
    })),
}));
