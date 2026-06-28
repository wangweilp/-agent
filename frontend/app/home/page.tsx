"use client";

import { motion } from "framer-motion";
import Link from "next/link";
import {
  ArrowRight,
  BookOpen,
  Brain,
  ShieldCheck,
  Layers,
  Zap,
  Database,
  GitBranch,
  Terminal,
} from "lucide-react";

// ── 工作台门面首页 (Workspace Hub) ──
// 与 /dashboard（数据图表监控中心）物理隔离：
//   - /home       = 登录后门面首页，极客风 Hero 视觉 + 业务引导
//   - /dashboard  = 纯数据图表监控中心，无 Hero 元素
// 两个页面 UI 代码完全独立，不共享任何视觉组件。

const fadeUp = {
  initial: { opacity: 0, y: 20 },
  animate: { opacity: 1, y: 0 },
};

interface BentoFeature {
  title: string;
  desc: string;
  icon: React.ComponentType<{ className?: string }>;
  colSpan?: string;
  rowSpan?: string;
  accent: string;
}

const BENTO_FEATURES: BentoFeature[] = [
  {
    title: "多维记忆图谱",
    desc: "情景 / 语义 / 反思三层记忆架构，跨会话长期记忆引擎，让 Agent 真正「记住」每一次交互。",
    icon: Brain,
    colSpan: "md:col-span-2",
    accent: "text-os-accent",
  },
  {
    title: "沙箱安全控制面",
    desc: "Rootless 容器隔离 + MicroVM 沙箱，零信任执行面，全链路审计与 kill-switch。",
    icon: ShieldCheck,
    rowSpan: "md:row-span-2",
    accent: "text-emerald-400",
  },
  {
    title: "插件生态大厅",
    desc: "Raycast 风格的 Agent Marketplace，开发者 SDK 一键发布，版本签名校验。",
    icon: Layers,
    accent: "text-os-accent-cyan",
  },
  {
    title: "决策可观测内核",
    desc: "Waterfall Trace + Causal Graph，每一个 LLM 调用的 Latency / Tokens / Cost 全链路可视。",
    icon: GitBranch,
    accent: "text-os-accent-violet",
  },
];

// ── 语法高亮着色 Map ──
type TokenKind = "keyword" | "string" | "comment" | "number" | "func" | "plain" | "class";

interface CodeToken {
  text: string;
  kind: TokenKind;
}

const TOKEN_COLOR: Record<TokenKind, string> = {
  keyword: "text-purple-400",
  string: "text-emerald-400",
  comment: "text-os-subtle italic",
  number: "text-amber-400",
  func: "text-sky-400",
  plain: "text-os-text",
  class: "text-os-accent-cyan",
};

function tokenizeLine(line: string): CodeToken[] {
  const tokens: CodeToken[] = [];
  const commentIdx = line.indexOf("#");
  let codePart = line;
  let commentPart = "";
  if (commentIdx >= 0) {
    codePart = line.slice(0, commentIdx);
    commentPart = line.slice(commentIdx);
  }

  const regex = /("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')|([A-Za-z_]\w*)|(\d+)|(\s+)|([^\sA-Za-z0-9_"'])/g;
  const keywords = new Set([
    "import", "from", "as", "def", "class", "return", "if", "else", "elif",
    "for", "while", "try", "except", "with", "async", "await", "True", "False",
    "None", "in", "not", "and", "or", "is", "lambda", "yield", "raise", "pass",
  ]);

  let match: RegExpExecArray | null;
  while ((match = regex.exec(codePart)) !== null) {
    const [full, str, ident, num, ws, punct] = match;
    if (str) {
      tokens.push({ text: str, kind: "string" });
    } else if (ident) {
      if (keywords.has(ident)) {
        tokens.push({ text: ident, kind: "keyword" });
      } else if (/^[A-Z]/.test(ident)) {
        tokens.push({ text: ident, kind: "class" });
      } else {
        const after = codePart.slice(regex.lastIndex);
        if (after.startsWith("(")) {
          tokens.push({ text: ident, kind: "func" });
        } else {
          tokens.push({ text: ident, kind: "plain" });
        }
      }
    } else if (num) {
      tokens.push({ text: num, kind: "number" });
    } else if (ws) {
      tokens.push({ text: ws, kind: "plain" });
    } else if (punct) {
      tokens.push({ text: punct, kind: "plain" });
    } else {
      tokens.push({ text: full, kind: "plain" });
    }
  }
  if (commentPart) {
    tokens.push({ text: commentPart, kind: "comment" });
  }
  return tokens;
}

const MOCK_CODE_LINES = [
  'from zhiwei_os import ZhiweiClient, MemoryScope',
  "",
  "# 初始化客户端，连接到本地沙箱",
  'client = ZhiweiClient(base_url="https://api.zhiwei.os")',
  "",
  "# 写入长期记忆（情景层）",
  'await client.memory.write(',
  '    content="用户偏好夜间深度工作",',
  "    scope=MemoryScope.EPISODIC,",
  "    importance=0.92,",
  ")",
  "",
  "# 语义检索 + 反思合并",
  'results = await client.memory.search(',
  '    query="用户工作习惯",',
  "    top_k=5,",
  "    rerank=True,",
  ")",
  "",
  'print(f"召回 {len(results)} 条相关记忆")',
];

export default function WorkspaceHomePage() {
  return (
    <main className="min-h-screen bg-os-base text-os-text-high overflow-x-hidden">
      {/* ── Hero Section ── */}
      <section className="relative overflow-hidden">
        <div className="pointer-events-none absolute inset-0 bg-os-grid bg-os-grid opacity-[0.15]" />
        <div className="pointer-events-none absolute left-1/2 top-0 h-[500px] w-[700px] -translate-x-1/2 -translate-y-1/3 rounded-full bg-os-accent/10 blur-3xl" />

        <div className="relative mx-auto max-w-5xl px-4 pt-24 pb-20 sm:px-6 sm:pt-32 sm:pb-24 lg:pt-40 lg:pb-32 text-center">
          {/* 小徽章 */}
          <motion.div
            {...fadeUp}
            transition={{ duration: 0.5 }}
            className="mb-6 inline-flex items-center gap-2 rounded-full border border-os-border/60 bg-os-surface/50 px-3 py-1 text-2xs font-mono text-os-subtle backdrop-blur-sm"
          >
            <span className="relative flex h-1.5 w-1.5">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
              <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-emerald-400" />
            </span>
            v6.2 · Separation Kernel 已冻结
          </motion.div>

          {/* 巨大渐变发光标题 */}
          <motion.h1
            {...fadeUp}
            transition={{ duration: 0.6, delay: 0.05 }}
            className="text-3xl md:text-5xl lg:text-7xl font-bold tracking-tight bg-clip-text text-transparent bg-gradient-to-b from-white to-os-muted"
          >
            知维 OS
          </motion.h1>
          <motion.p
            {...fadeUp}
            transition={{ duration: 0.6, delay: 0.1 }}
            className="mt-3 text-xl md:text-2xl lg:text-3xl font-semibold bg-clip-text text-transparent bg-gradient-to-b from-os-text-high to-os-subtle"
          >
            The Cognitive OS for Enterprise Agents
          </motion.p>

          {/* 副标题 */}
          <motion.p
            {...fadeUp}
            transition={{ duration: 0.6, delay: 0.15 }}
            className="mx-auto mt-6 text-os-subtle text-lg md:text-xl max-w-2xl text-center"
          >
            面向企业级 Agent 的认知操作系统。安全沙箱执行面、长期记忆引擎、
            决策可观测内核——让每一个智能体都拥有可治理的「大脑」。
          </motion.p>

          {/* CTA 按钮 — 内部业务引导（区别于落地页的"进入工作台"） */}
          <motion.div
            {...fadeUp}
            transition={{ duration: 0.6, delay: 0.2 }}
            className="mt-10 flex items-center justify-center gap-4"
          >
            <Link
              href="/dashboard"
              className="group inline-flex items-center gap-2 rounded-xl bg-os-accent px-6 py-3 text-sm font-semibold text-white shadow-[0_0_30px_rgba(129,140,248,0.35)] transition-all hover:bg-os-accent/85 hover:shadow-[0_0_40px_rgba(129,140,248,0.5)]"
            >
              查看数据仪表盘
              <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
            </Link>
            <Link
              href="/docs"
              className="inline-flex items-center gap-2 rounded-xl border border-os-border bg-os-surface/30 px-6 py-3 text-sm font-semibold text-os-text-high backdrop-blur-sm transition-all hover:border-os-accent/50 hover:bg-os-surface/60"
            >
              <BookOpen className="h-4 w-4" />
              阅读开发者文档
            </Link>
          </motion.div>

          {/* 关键指标条 */}
          <motion.div
            {...fadeUp}
            transition={{ duration: 0.6, delay: 0.3 }}
            className="mt-16 grid grid-cols-1 md:grid-cols-3 gap-4 max-w-2xl mx-auto"
          >
            {[
              { label: "Trace 链路", value: "全链路" },
              { label: "沙箱隔离", value: "Rootless" },
              { label: "记忆架构", value: "3 层" },
            ].map((item) => (
              <div
                key={item.label}
                className="rounded-xl border border-os-border/50 bg-os-surface/30 p-3 backdrop-blur-sm"
              >
                <p className="text-xl font-bold text-os-text-high font-mono">{item.value}</p>
                <p className="text-2xs text-os-subtle mt-0.5">{item.label}</p>
              </div>
            ))}
          </motion.div>
        </div>
      </section>

      {/* ── Bento Box 特性网格 ── */}
      <section className="relative mx-auto max-w-6xl px-4 py-16 sm:px-6 sm:py-20">
        <motion.div
          {...fadeUp}
          transition={{ duration: 0.5 }}
          className="mb-10 text-center"
        >
          <h2 className="text-2xl sm:text-3xl md:text-4xl font-bold text-os-text-high">
            一体化的 Agent 基础设施
          </h2>
          <p className="mt-3 text-os-subtle text-sm md:text-base">
            从记忆到执行，从决策到可观测——知维 OS 提供端到端的能力底座。
          </p>
        </motion.div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 md:gap-6 auto-rows-[minmax(180px,auto)]">
          {BENTO_FEATURES.map((feat, i) => {
            const Icon = feat.icon;
            return (
              <motion.div
                key={feat.title}
                {...fadeUp}
                transition={{ duration: 0.5, delay: 0.05 * i }}
                className={`group relative overflow-hidden rounded-3xl border border-os-border/50 bg-os-surface/40 backdrop-blur-md p-4 sm:p-5 md:p-6 transition-colors hover:border-os-accent/50 ${feat.colSpan ?? ""} ${feat.rowSpan ?? ""}`}
              >
                <div className="pointer-events-none absolute -right-10 -top-10 h-32 w-32 rounded-full bg-os-accent/5 opacity-0 blur-2xl transition-opacity duration-500 group-hover:opacity-100" />

                <div className="relative flex h-full flex-col">
                  <div className={`mb-4 inline-flex w-10 h-10 items-center justify-center rounded-xl bg-os-elevated/60 border border-os-border/50 ${feat.accent}`}>
                    <Icon className="h-5 w-5" />
                  </div>
                  <h3 className="text-lg font-semibold text-os-text-high">{feat.title}</h3>
                  <p className="mt-2 text-sm text-os-subtle leading-relaxed">{feat.desc}</p>
                </div>
              </motion.div>
            );
          })}
        </div>
      </section>

      {/* ── Developer Code Showcase ── */}
      <section className="relative mx-auto max-w-5xl px-4 py-16 sm:px-6 sm:py-20">
        <motion.div
          {...fadeUp}
          transition={{ duration: 0.5 }}
          className="mb-8 flex items-center gap-3"
        >
          <Terminal className="h-5 w-5 text-os-accent" />
          <h2 className="text-xl sm:text-2xl md:text-3xl font-bold text-os-text-high">
            开发者优先
          </h2>
        </motion.div>

        <motion.div
          {...fadeUp}
          transition={{ duration: 0.5, delay: 0.1 }}
          className="overflow-hidden rounded-2xl border border-os-border bg-[#0a0a0b] shadow-os-lg"
        >
          {/* macOS 风格顶栏 */}
          <div className="flex items-center gap-2 border-b border-os-border/60 bg-os-elevated/40 px-4 py-3">
            <span className="h-3 w-3 rounded-full bg-[#ff5f57]" />
            <span className="h-3 w-3 rounded-full bg-[#febc2e]" />
            <span className="h-3 w-3 rounded-full bg-[#28c840]" />
            <span className="ml-3 text-2xs font-mono text-os-subtle">zhiwei_quickstart.py</span>
          </div>

          {/* 代码区 */}
          <div className="p-3 sm:p-4 font-mono text-xs sm:text-sm leading-relaxed overflow-x-auto [scrollbar-width:none] [-ms-overflow-style:none] [&::-webkit-scrollbar]:hidden">
            <pre className="min-w-max">
              {MOCK_CODE_LINES.map((line, i) => (
                <div key={i} className="flex">
                  <span className="select-none w-8 shrink-0 pr-3 text-right text-os-border text-xs">
                    {i + 1}
                  </span>
                  <code className="whitespace-pre">
                    {line === "" ? (
                      <span>&nbsp;</span>
                    ) : (
                      tokenizeLine(line).map((tok, j) => (
                        <span key={j} className={TOKEN_COLOR[tok.kind]}>
                          {tok.text}
                        </span>
                      ))
                    )}
                  </code>
                </div>
              ))}
            </pre>
          </div>
        </motion.div>

        {/* 底部特性标签 */}
        <motion.div
          {...fadeUp}
          transition={{ duration: 0.5, delay: 0.2 }}
          className="mt-8 flex flex-wrap items-center justify-center gap-3"
        >
          {[
            { label: "Type Hints", icon: Zap },
            { label: "Async Native", icon: GitBranch },
            { label: "Memory API", icon: Database },
            { label: "Sandbox SDK", icon: ShieldCheck },
          ].map((tag) => {
            const Icon = tag.icon;
            return (
              <span
                key={tag.label}
                className="inline-flex items-center gap-1.5 rounded-full border border-os-border/50 bg-os-surface/40 px-3 py-1 text-2xs font-mono text-os-subtle backdrop-blur-sm"
              >
                <Icon className="h-3 w-3 text-os-accent" />
                {tag.label}
              </span>
            );
          })}
        </motion.div>
      </section>
    </main>
  );
}
