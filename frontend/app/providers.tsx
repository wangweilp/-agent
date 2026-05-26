"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";

export function Providers({ children }: { children: React.ReactNode }) {
  const [qc] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: { retry: 1, staleTime: 5000, refetchOnWindowFocus: false },
        },
      }),
  );

  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}
