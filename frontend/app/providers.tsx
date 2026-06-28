"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { CommandPalette, useGlobalCommandShortcut } from "@/components/os/command-palette";
import { Toaster } from "@/components/os/toaster";

// 全局 OS 组件 — 挂载 CommandPalette + Toaster + 键盘快捷键
function GlobalOSLayer() {
  useGlobalCommandShortcut();
  return (
    <>
      <CommandPalette />
      <Toaster />
    </>
  );
}

export function Providers({ children }: { children: React.ReactNode }) {
  const [qc] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: { retry: 1, staleTime: 5000, refetchOnWindowFocus: false },
        },
      }),
  );

  return (
    <QueryClientProvider client={qc}>
      {children}
      <GlobalOSLayer />
    </QueryClientProvider>
  );
}
