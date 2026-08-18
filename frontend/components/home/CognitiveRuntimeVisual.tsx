"use client";

import type { ComponentType } from "react";
import { motion, useReducedMotion } from "framer-motion";
import {
  Activity,
  BrainCircuit,
  Database,
  Eye,
  GitBranch,
  ShieldCheck,
  Workflow,
} from "lucide-react";
import { cn } from "@/lib/utils";

type NodeTone = "causal" | "memory" | "observe" | "runtime";

type RuntimeNode = {
  title: string;
  eyebrow: string;
  detail: string;
  icon: ComponentType<{ className?: string }>;
  tone: NodeTone;
  className: string;
};

const toneStyles: Record<NodeTone, { shell: string; icon: string; dot: string }> = {
  causal: {
    shell: "border-os-data-cyan/20 bg-os-data-cyan-soft text-[#245E91]",
    icon: "border-os-data-cyan/20 bg-white text-os-data-cyan",
    dot: "bg-os-data-cyan",
  },
  memory: {
    shell: "border-os-memory-violet/20 bg-os-memory-violet-soft text-[#4F3EB4]",
    icon: "border-os-memory-violet/20 bg-white text-os-memory-violet",
    dot: "bg-os-memory-violet",
  },
  observe: {
    shell: "border-os-success/20 bg-os-success-soft text-[#11755A]",
    icon: "border-os-success/20 bg-white text-emerald-700",
    dot: "bg-os-success",
  },
  runtime: {
    shell: "border-os-accent/[0.18] bg-white text-os-text-high",
    icon: "border-os-accent/[0.16] bg-os-accent-soft text-os-accent",
    dot: "bg-os-success",
  },
};

const nodes: RuntimeNode[] = [
  {
    title: "因果内核",
    eyebrow: "推理",
    detail: "决策链路",
    icon: GitBranch,
    tone: "causal",
    className: "left-0 top-6 sm:left-8 sm:top-10 lg:left-2 lg:top-16",
  },
  {
    title: "记忆引擎",
    eyebrow: "长期记忆",
    detail: "语义 + 情景",
    icon: Database,
    tone: "memory",
    className: "right-0 top-8 sm:right-8 sm:top-12 lg:right-1 lg:top-14",
  },
  {
    title: "可观测性",
    eyebrow: "时间线",
    detail: "审计 + 运行时",
    icon: Eye,
    tone: "observe",
    className: "bottom-5 left-1/2 -translate-x-1/2 sm:bottom-8 lg:bottom-14",
  },
];

const eventRows = [
  { label: "trace.create", tone: "bg-os-data-cyan", width: "w-24" },
  { label: "memory.recall", tone: "bg-os-memory-violet", width: "w-20" },
  { label: "kernel.verify", tone: "bg-os-success", width: "w-28" },
];

function ArchitectureNode({ node }: { node: RuntimeNode }) {
  const Icon = node.icon;
  const tone = toneStyles[node.tone];

  return (
    <div
      className={cn(
        "absolute z-10 w-[136px] rounded-[12px] border px-3 py-2.5 shadow-[0_1px_2px_rgba(16,24,40,0.035)] sm:w-[168px] lg:w-[178px]",
        tone.shell,
        node.className,
      )}
    >
      <div className="flex min-w-0 items-start gap-2.5">
        <span className={cn("flex h-8 w-8 shrink-0 items-center justify-center rounded-[8px] border", tone.icon)}>
          <Icon className="h-4 w-4" />
        </span>
        <span className="min-w-0">
          <span className="block truncate text-[11px] font-semibold leading-4 text-os-text-high sm:text-xs">
            {node.title}
          </span>
          <span className="block truncate text-[10px] leading-4 text-os-subtle sm:text-[11px]">
            {node.eyebrow}
          </span>
          <span className="mt-1 hidden items-center gap-1.5 text-[10px] leading-3 text-os-subtle sm:flex">
            <span className={cn("h-1.5 w-1.5 rounded-full", tone.dot)} />
            {node.detail}
          </span>
        </span>
      </div>
    </div>
  );
}

export function CognitiveRuntimeVisual({ className }: { className?: string }) {
  const shouldReduceMotion = useReducedMotion() ?? false;

  return (
    <motion.div
      initial={shouldReduceMotion ? false : { opacity: 0, y: 10 }}
      animate={shouldReduceMotion ? { opacity: 1 } : { opacity: 1, y: 0 }}
      transition={{ duration: 0.28, ease: "easeOut" }}
      aria-hidden="true"
      className={cn(
        "pointer-events-none relative h-[224px] overflow-hidden sm:h-[300px] lg:h-[430px]",
        className,
      )}
    >
      <div className="absolute inset-0 bg-os-grid-fine opacity-70 [mask-image:radial-gradient(circle_at_50%_48%,black,transparent_72%)]" />
      <div className="absolute left-1/2 top-1/2 h-[230px] w-[360px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-[radial-gradient(circle_at_center,rgba(255,255,255,0.92),rgba(91,92,226,0.055)_48%,transparent_72%)] lg:h-[360px] lg:w-[560px]" />

      <svg
        className="absolute inset-0 h-full w-full"
        viewBox="0 0 640 430"
        preserveAspectRatio="none"
        focusable="false"
      >
        <path d="M320 220 C245 184 160 132 82 102" stroke="rgba(17,19,24,0.14)" strokeWidth="1" fill="none" />
        <path d="M320 220 C405 176 492 126 572 102" stroke="rgba(17,19,24,0.14)" strokeWidth="1" fill="none" />
        <path d="M320 220 C320 280 320 328 320 386" stroke="rgba(17,19,24,0.14)" strokeWidth="1" fill="none" />
        <path className="runtime-flow" d="M320 220 C245 184 160 132 82 102" stroke="rgba(49,130,206,0.48)" strokeWidth="1.2" fill="none" />
        <path className="runtime-flow-slow" d="M320 220 C405 176 492 126 572 102" stroke="rgba(116,88,232,0.42)" strokeWidth="1.2" fill="none" />
        <path className="runtime-flow" d="M320 220 C320 280 320 328 320 386" stroke="rgba(24,167,123,0.42)" strokeWidth="1.2" fill="none" />
      </svg>

      <div className="absolute left-1/2 top-1/2 z-20 w-[170px] -translate-x-1/2 -translate-y-1/2 rounded-[14px] border border-os-accent/20 bg-white px-4 py-3 shadow-[0_2px_6px_rgba(16,24,40,0.04),0_16px_42px_rgba(16,24,40,0.065)] sm:w-[210px] sm:px-5 sm:py-4">
        <div className="flex items-center justify-between gap-3">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[10px] border border-os-accent/[0.14] bg-os-accent-soft text-os-accent">
            <BrainCircuit className="h-5 w-5" />
          </span>
          <span className="inline-flex items-center gap-1.5 rounded-full border border-os-success/20 bg-os-success-soft px-2 py-1 text-[10px] font-medium text-[#11755A]">
            <span className="runtime-status-pulse h-1.5 w-1.5 rounded-full bg-os-success" />
            就绪
          </span>
        </div>
        <div className="mt-3">
          <p className="text-[13px] font-semibold leading-5 text-os-text-high sm:text-sm">认知运行时</p>
          <p className="text-[11px] leading-5 text-os-subtle">分离内核</p>
        </div>
        <div className="mt-3 grid grid-cols-3 gap-1.5">
          {["链路", "记忆", "审计"].map((item) => (
            <span
              key={item}
              className="rounded-[7px] border border-slate-900/[0.06] bg-os-surface-muted px-1.5 py-1 text-center text-[9px] font-medium text-os-subtle sm:text-[10px]"
            >
              {item}
            </span>
          ))}
        </div>
      </div>

      {nodes.map((node) => (
        <ArchitectureNode key={node.title} node={node} />
      ))}

      <div className="absolute bottom-6 right-3 hidden w-[190px] rounded-[12px] border border-slate-900/[0.065] bg-white/86 p-3 shadow-[0_1px_2px_rgba(16,24,40,0.035)] backdrop-blur-sm md:block lg:bottom-20 lg:right-14">
        <div className="mb-2 flex items-center justify-between text-[10px] font-medium text-os-subtle">
          <span>事件流</span>
          <Activity className="h-3 w-3 text-emerald-700" />
        </div>
        <div className="space-y-2">
          {eventRows.map((row) => (
            <div key={row.label} className="flex items-center gap-2">
              <span className={cn("h-1.5 w-1.5 rounded-full", row.tone)} />
              <span className="w-20 text-[10px] text-os-subtle">{row.label}</span>
              <span className={cn("h-1 rounded-full bg-slate-900/[0.08]", row.width)} />
            </div>
          ))}
        </div>
      </div>

      <div className="absolute left-4 bottom-14 hidden items-center gap-2 rounded-full border border-slate-900/[0.065] bg-white/80 px-3 py-1.5 text-[10px] text-os-subtle shadow-[0_1px_2px_rgba(16,24,40,0.035)] md:flex lg:left-16 lg:bottom-24">
        <Workflow className="h-3 w-3 text-os-data-cyan" />
        有向因果链路
      </div>

      <div className="absolute right-4 top-24 hidden h-8 w-8 items-center justify-center rounded-[9px] border border-os-success/20 bg-os-success-soft text-emerald-700 sm:flex lg:right-20 lg:top-32">
        <ShieldCheck className="h-4 w-4" />
      </div>
    </motion.div>
  );
}
