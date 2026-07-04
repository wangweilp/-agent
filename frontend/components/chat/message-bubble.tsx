"use client";

import { useState, type ComponentPropsWithoutRef } from "react";
import { motion } from "framer-motion";
import { Brain, User, Copy, Check } from "lucide-react";
import ReactMarkdown from "react-markdown";
import { Highlight, themes } from "prism-react-renderer";
import { cn, formatDate } from "@/lib/utils";
import type { Message } from "@/types";

// ── 代码块（含 Copy 按钮） ──

function CodeBlock({ language, value }: { language: string; value: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(value);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="group relative my-3 overflow-hidden rounded-xl border border-os-border bg-slate-50">
      {/* Header: 语言标签 + Copy 按钮 */}
      <div className="flex items-center justify-between px-3 py-1.5 border-b border-os-border/50 bg-os-elevated/40">
        <span className="text-2xs text-os-muted font-mono">{language || "text"}</span>
        <button
          onClick={handleCopy}
          className="flex items-center gap-1 text-2xs text-os-subtle hover:text-os-text-high transition-colors"
        >
          {copied ? (
            <>
              <Check size={11} className="text-emerald-400" />
              <span className="text-emerald-400">已复制</span>
            </>
          ) : (
            <>
              <Copy size={11} />
              <span>复制</span>
            </>
          )}
        </button>
      </div>
      <Highlight
        theme={themes.github}
        code={value}
        language={(language || "text") as never}
      >
        {({ className, style, tokens, getLineProps, getTokenProps }) => (
          <pre
            className={cn(className, "m-0 bg-transparent p-3 sm:px-3.5 text-[13px] leading-[1.6] overflow-x-auto")}
            style={{ ...style, background: "transparent", fontFamily: "var(--font-mono, monospace)" }}
          >
            {tokens.map((line, i) => {
              const lineProps = getLineProps({ line });
              return (
                <div key={i} {...lineProps} className={cn(lineProps.className, "table-row")}>
                  <span className="table-cell select-none pr-3 text-right text-os-border text-xs w-8">
                    {i + 1}
                  </span>
                  <span className="table-cell">
                    {line.map((token, key) => {
                      const tokenProps = getTokenProps({ token });
                      return <span key={key} {...tokenProps} />;
                    })}
                  </span>
                </div>
              );
            })}
          </pre>
        )}
      </Highlight>
    </div>
  );
}

// ── Markdown 组件映射 ──

const markdownComponents: ComponentPropsWithoutRef<typeof ReactMarkdown>["components"] = {
  code({ className, children, ...props }) {
    const match = /language-(\w+)/.exec(className || "");
    const value = String(children).replace(/\n$/, "");
    // 有 language- class 或含换行 → 代码块；否则 → inline code
    const isBlock = !!match || value.includes("\n");
    if (isBlock) {
      return <CodeBlock language={match?.[1] || ""} value={value} />;
    }
    return (
      <code className="px-1.5 py-0.5 rounded bg-os-elevated text-os-accent text-xs font-mono" {...props}>
        {children}
      </code>
    );
  },
  p({ children }) {
    return <p className="leading-relaxed mb-3 last:mb-0">{children}</p>;
  },
  ul({ children }) {
    return <ul className="list-disc list-inside mb-3 space-y-1 last:mb-0">{children}</ul>;
  },
  ol({ children }) {
    return <ol className="list-decimal list-inside mb-3 space-y-1 last:mb-0">{children}</ol>;
  },
  li({ children }) {
    return <li className="leading-relaxed">{children}</li>;
  },
  blockquote({ children }) {
    return (
      <blockquote className="border-l-2 border-os-accent/40 pl-3 text-os-muted italic my-2">
        {children}
      </blockquote>
    );
  },
  h1({ children }) {
    return <h1 className="text-base font-semibold mb-2 mt-3 first:mt-0">{children}</h1>;
  },
  h2({ children }) {
    return <h2 className="text-sm font-semibold mb-2 mt-3 first:mt-0">{children}</h2>;
  },
  h3({ children }) {
    return <h3 className="text-sm font-medium mb-1 mt-2 first:mt-0">{children}</h3>;
  },
  a({ href, children }) {
    return (
      <a
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        className="text-os-accent hover:underline"
      >
        {children}
      </a>
    );
  },
  hr() {
    return <hr className="border-os-border/50 my-4" />;
  },
  table({ children }) {
    return (
      <div className="overflow-x-auto my-3">
        <table className="w-full text-xs border-collapse">{children}</table>
      </div>
    );
  },
  th({ children }) {
    return <th className="border border-os-border/50 px-3 py-1.5 text-left text-os-muted font-medium bg-os-elevated/30">{children}</th>;
  },
  td({ children }) {
    return <td className="border border-os-border/50 px-3 py-1.5 text-os-text">{children}</td>;
  },
};

// ── 消息气泡 ──

export function MessageBubble({
  message,
  streaming,
}: {
  message: Message;
  streaming?: boolean;
}) {
  const isUser = message.role === "user";

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className={cn("flex gap-3", isUser && "flex-row-reverse")}
    >
      {/* Avatar */}
      <div
        className={cn(
          "w-7 h-7 rounded-lg flex items-center justify-center shrink-0",
          isUser ? "bg-os-accent/10" : "bg-os-elevated border border-os-border",
        )}
      >
        {isUser ? (
          <User size={14} className="text-os-accent" />
        ) : (
          <Brain size={14} className="text-os-subtle" />
        )}
      </div>

      {/* Content */}
      <div className={cn("max-w-[80%]", isUser && "items-end")}>
        <div
          className={cn(
            "rounded-xl px-4 py-2.5 text-sm leading-relaxed",
            isUser
              ? "bg-os-accent/10 text-os-text-high border border-os-accent/10"
              : "bg-os-elevated text-os-text-high border border-os-border",
          )}
        >
          {/* 用户消息保持纯文本（防止 markdown 注入），AI 消息走 ReactMarkdown */}
          {isUser ? (
            <p className="whitespace-pre-wrap break-words">{message.content}</p>
          ) : (
            <div className="prose-chat">
              <ReactMarkdown components={markdownComponents}>
                {message.content}
              </ReactMarkdown>
            </div>
          )}
          {streaming && (
            <span className="inline-block w-1.5 h-4 bg-os-accent ml-0.5 animate-pulse align-text-bottom rounded-sm" />
          )}
        </div>
        {message.timestamp && (
          <p className="text-2xs text-os-muted mt-1 px-1">{formatDate(message.timestamp)}</p>
        )}
      </div>
    </motion.div>
  );
}
