"use client";

import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";
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
      // 自定义 storage：防御脏数据（如 "undefined" 字符串）导致 JSON.parse 崩溃
      storage: createJSONStorage(() => {
        const safeStorage: Storage = {
          getItem: (name: string) => {
            try {
              const raw = localStorage.getItem(name);
              // 防御脏数据：非合法 JSON 直接视为不存在
              if (raw != null) JSON.parse(raw);
              return raw;
            } catch {
              // 脏数据 — 清理并返回 null，避免 hydration 崩溃
              try { localStorage.removeItem(name); } catch { /* ignore */ }
              return null;
            }
          },
          setItem: (name: string, value: string) => {
            try { localStorage.setItem(name, value); } catch { /* ignore */ }
          },
          removeItem: (name: string) => {
            try { localStorage.removeItem(name); } catch { /* ignore */ }
          },
          clear: () => {
            try { localStorage.clear(); } catch { /* ignore */ }
          },
          key: (index: number) => {
            try { return localStorage.key(index); } catch { return null; }
          },
          length: typeof window !== "undefined" ? localStorage.length : 0,
        };
        return safeStorage;
      }),
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
