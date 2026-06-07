"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { AuthUser, AuthTokens, Workspace } from "@/types";

// Module-level token reference so api.ts can read it without circular imports
let _currentToken: string | null = null;
export function getAccessToken(): string | null {
  return _currentToken;
}
export function setAccessToken(token: string | null) {
  _currentToken = token;
}

interface AuthState {
  // Data
  token: AuthTokens | null;
  user: AuthUser | null;
  currentWorkspace: Workspace | null;
  workspaces: Workspace[];

  // Actions
  setAuth: (tokens: AuthTokens, user: AuthUser, workspace: Workspace) => void;
  setWorkspaces: (list: Workspace[]) => void;
  setCurrentWorkspace: (ws: Workspace) => void;
  clearAuth: () => void;
  updateUser: (user: Partial<AuthUser>) => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      token: null,
      user: null,
      currentWorkspace: null,
      workspaces: [],

      setAuth: (tokens, user, workspace) => {
        setAccessToken(tokens.access_token);
        set({ token: tokens, user, currentWorkspace: workspace });
        // 立即持久化到 localStorage，不等 Zustand persist 异步队列
        // 避免登录后页面跳转时 API 调用读不到 token
        try {
          localStorage.setItem(
            "agent-os-auth",
            JSON.stringify({
              state: { token: tokens, user, currentWorkspace: workspace },
              version: 0,
            })
          );
        } catch { /* ignore */ }
      },

      setWorkspaces: (list) => set({ workspaces: list }),

      setCurrentWorkspace: (ws) => {
        set({ currentWorkspace: ws });
      },

      clearAuth: () => {
        setAccessToken(null);
        set({ token: null, user: null, currentWorkspace: null, workspaces: [] });
        try { localStorage.removeItem("agent-os-auth"); } catch { /* ignore */ }
      },

      updateUser: (partial) => {
        const current = get().user;
        if (current) {
          set({ user: { ...current, ...partial } });
        }
      },
    }),
    {
      name: "agent-os-auth",
      // Only persist these keys
      partialize: (state) => ({
        token: state.token,
        user: state.user,
        currentWorkspace: state.currentWorkspace,
      }),
      onRehydrateStorage: () => (state) => {
        if (state?.token?.access_token) {
          setAccessToken(state.token.access_token);
        }
      },
    }
  )
);
