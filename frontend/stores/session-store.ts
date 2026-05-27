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
  sessions: [],
  activeId: null,

  setSessions: (sessions) => set({ sessions }),
  setActive: (activeId) => set({ activeId }),
  addSession: (session) =>
    set((s) => ({
      sessions: [session, ...s.sessions],
      activeId: s.activeId || session.id,
    })),
  removeSession: (id) =>
    set((s) => {
      const remaining = s.sessions.filter((x) => x.id !== id);
      return {
        sessions: remaining,
        activeId: s.activeId === id ? (remaining[0]?.id || null) : s.activeId,
      };
    }),
}));
