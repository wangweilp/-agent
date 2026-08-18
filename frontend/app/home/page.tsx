"use client";

import { motion } from "framer-motion";
import { PremiumHero } from "@/components/home/PremiumHero";
import {
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
//   - /home       = 登录后门面首页，Premium Hero 视觉 + 业务引导
//   - /dashboard  = 纯数据图表监控中心，无 Hero 元素
// 首屏展示组件共享，页面后续业务区块保持独立。

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
    accent: "text-emerald-600",
  },
  {
    title: "插件生态大厅",
    desc: "Raycast 风格的 Agent Marketplace，开发者 SDK 一键发布，版本签名校验。",
    icon: Layers,
    accent: "text-indigo-500",
  },
  {
    title: "决策可观测内核",
    desc: "Waterfall Trace + Causal Graph，每一个 LLM 调用的 Latency / Tokens / Cost 全链路可视。",
    icon: GitBranch,
    accent: "text-violet-500",
  },
];

// ── 语法高亮着色 Map ──
type TokenKind = "keyword" | "string" | "comment" | "number" | "func" | "plain" | "class";

interface CodeToken {
  text: string;
  kind: TokenKind;
}

const TOKEN_COLOR: Record<TokenKind, string> = {
  keyword: "text-violet-600",
  string: "text-emerald-600",
  comment: "text-os-subtle italic",
  number: "text-amber-600",
  func: "text-blue-600",
  plain: "text-os-text",
  class: "text-indigo-600",
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
      <PremiumHero
        primaryHref="/dashboard"
        primaryLabel="查看数据仪表盘"
        secondaryLabel="阅读开发者文档"
      />

      {/* ── Bento Box 特性网格 ── */}
      <section className="relative mx-auto max-w-6xl px-4 py-8 sm:px-6 sm:py-12 md:py-14">
        <motion.div
          {...fadeUp}
          transition={{ duration: 0.5 }}
          className="mb-10 text-center"
        >
          <h2 className="text-2xl font-semibold text-os-text-high sm:text-3xl md:text-4xl">
            一体化的 Agent 基础设施
          </h2>
          <p className="mt-3 text-sm text-os-subtle md:text-base">
            从记忆到执行，从决策到可观测——知维 OS 提供端到端的能力底座。
          </p>
        </motion.div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 md:gap-5 auto-rows-[minmax(164px,auto)]">
          {BENTO_FEATURES.map((feat, i) => {
            const Icon = feat.icon;
            return (
              <motion.div
                key={feat.title}
                {...fadeUp}
                transition={{ duration: 0.5, delay: 0.05 * i }}
                className={`group relative overflow-hidden rounded-lg border border-os-border bg-white/95 p-4 shadow-os-sm transition-all duration-150 hover:border-os-accent/20 hover:bg-white hover:shadow-os-md sm:p-5 ${feat.colSpan ?? ""} ${feat.rowSpan ?? ""}`}
              >
                <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-os-accent/0 transition-colors duration-200 group-hover:bg-os-accent/20" />

                <div className="relative flex h-full flex-col">
                  <div className={`mb-4 inline-flex w-9 h-9 items-center justify-center rounded-md border border-os-accent/10 bg-os-accent-soft ${feat.accent}`}>
                    <Icon className="h-5 w-5" />
                  </div>
                  <h3 className="text-base font-semibold text-os-text-high">{feat.title}</h3>
                  <p className="mt-2 text-sm leading-6 text-os-subtle">{feat.desc}</p>
                </div>
              </motion.div>
            );
          })}
        </div>
      </section>

      {/* ── Developer Code Showcase ── */}
      <section className="relative mx-auto max-w-5xl px-4 py-10 sm:px-6 sm:py-16 md:py-20">
        <motion.div
          {...fadeUp}
          transition={{ duration: 0.5 }}
          className="mb-8 flex items-center gap-3"
        >
          <Terminal className="h-5 w-5 text-os-accent" />
          <h2 className="text-xl font-semibold text-os-text-high sm:text-2xl md:text-3xl">
            开发者优先
          </h2>
        </motion.div>

        <motion.div
          {...fadeUp}
          transition={{ duration: 0.5, delay: 0.1 }}
          className="overflow-hidden rounded-lg border border-os-border bg-white shadow-os-md"
        >
          {/* macOS 风格顶栏 */}
          <div className="flex items-center gap-2 border-b border-os-border bg-os-elevated/80 px-4 py-2.5">
            <span className="h-2.5 w-2.5 rounded-full bg-[#ff5f57]" />
            <span className="h-2.5 w-2.5 rounded-full bg-[#febc2e]" />
            <span className="h-2.5 w-2.5 rounded-full bg-[#28c840]" />
            <span className="ml-3 text-2xs font-mono text-os-subtle">zhiwei_quickstart.py</span>
          </div>

          {/* 代码区 */}
          <div className="p-3 sm:p-4 font-mono text-xs sm:text-sm leading-relaxed overflow-x-auto [scrollbar-width:none] [-ms-overflow-style:none] [&::-webkit-scrollbar]:hidden">
            <pre className="min-w-max">
              {MOCK_CODE_LINES.map((line, i) => (
                <div key={i} className="flex">
                  <span className="select-none w-8 shrink-0 pr-3 text-right text-xs text-os-subtle">
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
            { label: "类型提示", icon: Zap },
            { label: "原生异步", icon: GitBranch },
            { label: "记忆 API", icon: Database },
            { label: "沙箱 SDK", icon: ShieldCheck },
          ].map((tag) => {
            const Icon = tag.icon;
            return (
              <span
                key={tag.label}
                className="inline-flex items-center gap-1.5 rounded-md border border-os-border bg-white/90 px-3 py-1 text-2xs font-mono text-os-subtle shadow-os-sm"
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
