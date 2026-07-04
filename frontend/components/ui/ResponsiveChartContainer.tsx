"use client";

import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";

export function ResponsiveChartContainer({
  children,
  height = 300,
  className,
}: {
  children: React.ReactNode;
  height?: number | string;
  className?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(0);

  useEffect(() => {
    if (!ref.current) return;

    const el = ref.current;
    setWidth(el.clientWidth);

    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        setWidth(entry.contentRect.width);
      }
    });

    observer.observe(el);

    return () => observer.disconnect();
  }, []);

  return (
    <div
      ref={ref}
      className={cn("w-full overflow-hidden rounded-2xl border border-os-border bg-white shadow-os-card", className)}
      style={{ minHeight: height }}
    >
      <div style={{ width: width || "100%", height, minWidth: 0 }}>
        {children}
      </div>
    </div>
  );
}
