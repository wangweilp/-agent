"use client";

import type { ComponentType } from "react";
import { motion, useReducedMotion } from "framer-motion";
import Link from "next/link";
import {
  ArrowRight,
  BookOpen,
  Database,
  GitBranch,
  ShieldCheck,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { CognitiveRuntimeVisual } from "@/components/home/CognitiveRuntimeVisual";
import { SystemTrustRail } from "@/components/home/SystemTrustRail";

type PremiumHeroProps = {
  primaryHref: string;
  primaryLabel: string;
  secondaryHref?: string;
  secondaryLabel: string;
};

type Capability = {
  no: string;
  title: string;
  label: string;
  desc: string;
  status: string;
  href: string;
  icon: ComponentType<{ className?: string }>;
  line: string;
  iconShell: string;
  iconColor: string;
  arrow: string;
};

const CAPABILITIES: Capability[] = [
  {
    no: "01",
    title: "全链路",
    label: "Trace & Observability",
    desc: "端到端追踪与因果链路可视化，洞见每一次 Agent 决策。",
    status: "Full Chain",
    href: "/dashboard",
    icon: GitBranch,
    line: "bg-gradient-to-r from-os-data-cyan to-os-accent",
    iconShell: "border-os-data-cyan/20 bg-os-data-cyan-soft",
    iconColor: "text-os-data-cyan",
    arrow: "text-os-data-cyan",
  },
  {
    no: "02",
    title: "Rootless",
    label: "Isolation & Execution",
    desc: "无 Root 容器技术，构建安全可控的 Agent 执行环境。",
    status: "Sandbox",
    href: "/runtime",
    icon: ShieldCheck,
    line: "bg-gradient-to-r from-blue-500 to-os-accent",
    iconShell: "border-blue-500/20 bg-blue-500/[0.07]",
    iconColor: "text-blue-600",
    arrow: "text-blue-600",
  },
  {
    no: "03",
    title: "三层记忆",
    label: "Memory Architecture",
    desc: "感知层 / 反思层 / 语义层，构成可进化的记忆系统。",
    status: "3 Layers",
    href: "/memory-console",
    icon: Database,
    line: "bg-gradient-to-r from-os-success to-os-memory-violet",
    iconShell: "border-os-success/20 bg-os-success-soft",
    iconColor: "text-os-success",
    arrow: "text-os-memory-violet",
  },
];

function motionProps(shouldReduceMotion: boolean, delay = 0) {
  return {
    initial: shouldReduceMotion ? false : { opacity: 0, y: 10 },
    animate: { opacity: 1, y: 0 },
    transition: { duration: 0.28, delay, ease: "easeOut" },
  };
}

function CapabilityCard({
  item,
  index,
  shouldReduceMotion,
}: {
  item: Capability;
  index: number;
  shouldReduceMotion: boolean;
}) {
  const Icon = item.icon;

  return (
    <motion.div {...motionProps(shouldReduceMotion, 0.18 + index * 0.04)} className="h-full">
      <Link
        href={item.href}
        className="group block h-full rounded-[14px] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-os-accent/30 focus-visible:ring-offset-2 focus-visible:ring-offset-os-page"
      >
        <article className="relative flex min-h-[88px] h-full items-center gap-3 overflow-hidden rounded-[14px] border border-slate-900/[0.075] bg-white px-4 py-3 text-left shadow-[0_1px_2px_rgba(16,24,40,0.03)] transition-[border-color,box-shadow,transform,background-color] duration-200 hover:-translate-y-px hover:border-slate-900/[0.13] hover:bg-white hover:shadow-[0_10px_30px_rgba(16,24,40,0.06)] motion-reduce:transform-none sm:px-5 lg:min-h-[164px] lg:flex-col lg:items-start lg:justify-between lg:p-6">
          <span className={cn("absolute inset-x-0 top-0 h-px", item.line)} />

          <div className="flex min-w-0 flex-1 items-center gap-3 lg:w-full lg:items-start">
            <span className={cn("flex h-10 w-10 shrink-0 items-center justify-center rounded-[10px] border", item.iconShell)}>
              <Icon className={cn("h-[18px] w-[18px]", item.iconColor)} />
            </span>
            <div className="min-w-0 flex-1">
              <div className="flex min-w-0 items-center gap-2">
                <span className="font-mono text-[11px] font-semibold leading-4 text-os-muted">
                  {item.no}
                </span>
                <h3 className="truncate text-[17px] font-semibold leading-6 text-os-text-high">
                  {item.title}
                </h3>
              </div>
              <p className="mt-0.5 truncate text-xs font-medium leading-5 text-os-muted">
                {item.label}
              </p>
              <p className="mt-1.5 line-clamp-2 text-xs leading-5 text-os-subtle lg:mt-3 lg:line-clamp-none">
                {item.desc}
              </p>
            </div>
          </div>

          <div className="flex shrink-0 items-center gap-2 lg:w-full lg:justify-between">
            <span className="hidden rounded-full border border-slate-900/[0.07] bg-os-surface-muted px-2 py-1 text-[10px] font-medium text-os-muted lg:inline-flex">
              {item.status}
            </span>
            <ArrowRight
              className={cn(
                "h-4 w-4 shrink-0 opacity-75 transition-transform duration-200 group-hover:translate-x-0.5 motion-reduce:transform-none",
                item.arrow,
              )}
            />
          </div>
        </article>
      </Link>
    </motion.div>
  );
}

export function PremiumHero({
  primaryHref,
  primaryLabel,
  secondaryHref = "/docs",
  secondaryLabel,
}: PremiumHeroProps) {
  const shouldReduceMotion = useReducedMotion() ?? false;

  return (
    <section className="relative isolate overflow-hidden bg-os-page">
      <div className="pointer-events-none absolute inset-x-0 top-0 h-[640px] bg-[radial-gradient(circle_at_52%_24%,rgba(255,255,255,0.88),transparent_54%)]" />
      <div className="pointer-events-none absolute inset-x-0 top-0 h-[620px] bg-os-grid opacity-80 [mask-image:linear-gradient(to_bottom,black,transparent_82%)]" />
      <div className="pointer-events-none absolute left-[54%] top-10 h-[420px] w-[760px] -translate-x-1/2 bg-[radial-gradient(circle_at_center,rgba(49,130,206,0.026),transparent_66%)]" />

      <div className="relative mx-auto max-w-[1360px] px-[18px] pb-12 pt-16 sm:px-6 sm:pb-14 sm:pt-20 lg:px-12 lg:pb-16 lg:pt-24 xl:px-14">
        <div className="grid items-start gap-6 lg:grid-cols-12 lg:gap-12 xl:gap-16">
          <div className="min-w-0 text-left lg:col-span-7">
            <motion.div
              {...motionProps(shouldReduceMotion)}
              className="inline-flex h-8 max-w-full items-center gap-2 rounded-full border border-slate-900/[0.075] bg-white/82 px-3 text-[11px] text-os-subtle shadow-[0_1px_2px_rgba(16,24,40,0.035)] backdrop-blur-md"
            >
              <span className="runtime-status-pulse h-1.5 w-1.5 shrink-0 rounded-full bg-os-success" />
              <span className="font-mono text-os-text-high">Runtime Ready</span>
              <span className="text-os-muted">/</span>
              <span className="truncate">Separation Kernel</span>
            </motion.div>

            <motion.h1
              {...motionProps(shouldReduceMotion, 0.04)}
              className="mt-6 max-w-[760px] text-[42px] font-bold leading-[0.96] text-os-text-high sm:text-5xl lg:text-6xl xl:text-7xl"
            >
              <span>知维</span>{" "}
              <span className="bg-gradient-to-r from-[#4f63df] to-[#6b55d9] bg-clip-text text-transparent">
                OS
              </span>
            </motion.h1>

            <motion.p
              {...motionProps(shouldReduceMotion, 0.08)}
              className="mt-[18px] max-w-[720px] text-xl font-medium leading-tight text-[#344054] sm:text-2xl md:text-[28px]"
            >
              Enterprise cognitive infrastructure for governed agents.
            </motion.p>

            <motion.p
              {...motionProps(shouldReduceMotion, 0.12)}
              className="mt-5 max-w-[600px] text-base leading-8 text-os-subtle md:text-[17px] md:leading-8"
            >
              面向企业级 Agent 的认知操作系统。安全沙箱执行面、长期记忆引擎、
              决策可观测内核，让智能体在可治理边界内持续运行。
            </motion.p>

            <motion.div
              {...motionProps(shouldReduceMotion, 0.16)}
              className="mt-8 flex flex-col items-stretch gap-3 sm:flex-row sm:items-center"
            >
              <Link
                href={primaryHref}
                className="group inline-flex h-11 w-full items-center justify-center gap-2 whitespace-nowrap rounded-[11px] bg-[#5959d9] px-5 text-sm font-semibold text-white shadow-[0_8px_22px_rgba(89,89,217,0.18)] transition-[background-color,box-shadow,transform] duration-200 hover:-translate-y-px hover:bg-[#4f4fc8] hover:shadow-[0_10px_28px_rgba(89,89,217,0.22)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-os-accent/35 focus-visible:ring-offset-2 focus-visible:ring-offset-os-page motion-reduce:transform-none md:h-12 md:px-6 sm:w-auto"
              >
                {primaryLabel}
                <ArrowRight className="h-4 w-4 transition-transform duration-200 group-hover:translate-x-0.5 motion-reduce:transform-none" />
              </Link>
              <Link
                href={secondaryHref}
                className="inline-flex h-11 w-full items-center justify-center gap-2 whitespace-nowrap rounded-[11px] border border-slate-900/[0.09] bg-white px-5 text-sm font-semibold text-[#202632] shadow-[0_1px_2px_rgba(16,24,40,0.035)] transition-[background-color,border-color] duration-200 hover:border-slate-900/[0.14] hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-os-accent/30 focus-visible:ring-offset-2 focus-visible:ring-offset-os-page md:h-12 md:px-6 sm:w-auto"
              >
                <BookOpen className="h-4 w-4" />
                {secondaryLabel}
              </Link>
            </motion.div>
          </div>

          <div className="min-w-0 lg:col-span-5">
            <CognitiveRuntimeVisual />
          </div>
        </div>

        <SystemTrustRail className="mt-3 sm:mt-8 lg:mt-12" />

        <div className="mt-5 grid gap-3 lg:grid-cols-3 lg:gap-4">
          {CAPABILITIES.map((item, index) => (
            <CapabilityCard
              key={item.no}
              item={item}
              index={index}
              shouldReduceMotion={shouldReduceMotion}
            />
          ))}
        </div>
      </div>
    </section>
  );
}
