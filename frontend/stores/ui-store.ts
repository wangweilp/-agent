"use client";

import { create } from "zustand";

// ── Toast 类型 ──

export type ToastType = "success" | "warning" | "danger" | "info";

export interface ToastItem {
  id: string;
  message: string;
  type: ToastType;
  description?: string;
}

// ── UI Store ──

interface UIState {
  // Command Palette
  commandPaletteOpen: boolean;
  openCommandPalette: () => void;
  closeCommandPalette: () => void;
  toggleCommandPalette: () => void;

  // Toast 队列
  toasts: ToastItem[];
  addToast: (toast: Omit<ToastItem, "id">) => void;
  dismissToast: (id: string) => void;
}

let toastIdCounter = 0;

export const useUIStore = create<UIState>((set, get) => ({
  // ── Command Palette ──
  commandPaletteOpen: false,
  openCommandPalette: () => set({ commandPaletteOpen: true }),
  closeCommandPalette: () => set({ commandPaletteOpen: false }),
  toggleCommandPalette: () =>
    set((s) => ({ commandPaletteOpen: !s.commandPaletteOpen })),

  // ── Toast 队列 ──
  toasts: [],
  addToast: (toast) => {
    const id = `toast-${++toastIdCounter}`;
    set((s) => ({ toasts: [...s.toasts, { ...toast, id }] }));
    // 4 秒后自动移除
    setTimeout(() => {
      get().dismissToast(id);
    }, 4000);
  },
  dismissToast: (id) =>
    set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
}));

// ── 便捷 helper（非 React 组件中也可调用） ──

export const toast = {
  success: (message: string, description?: string) =>
    useUIStore.getState().addToast({ message, description, type: "success" }),
  warning: (message: string, description?: string) =>
    useUIStore.getState().addToast({ message, description, type: "warning" }),
  danger: (message: string, description?: string) =>
    useUIStore.getState().addToast({ message, description, type: "danger" }),
  info: (message: string, description?: string) =>
    useUIStore.getState().addToast({ message, description, type: "info" }),
};
