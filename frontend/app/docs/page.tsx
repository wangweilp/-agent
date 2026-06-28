import React from "react";
import Link from "next/link";
import { BookOpen, Terminal, Brain, Shield, Key, ChevronLeft } from "lucide-react";

export default function DeveloperDocsPage() {
  return (
    <div className="min-h-screen bg-os-base text-os-text selection:bg-os-accent/30 p-6 md:p-12 lg:px-24 max-w-6xl mx-auto overflow-y-auto">
      {/* 顶部导航与面包屑 */}
      <div className="flex items-center justify-between mb-12">
        <Link className="group flex items-center gap-2 text-os-subtle hover:text-os-accent transition-colors text-sm font-medium" href="/dashboard">
          <ChevronLeft className="w-4 h-4 group-hover:-translate-x-1 transition-transform"/>
          返回工作台
        </Link>
        <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-os-accent/10 border border-os-accent/20 text-os-accent text-xs font-mono">
          <span className="relative flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-os-accent opacity-75"></span>
            <span className="relative inline-flex rounded-full h-2 w-2 bg-os-accent"></span>
          </span>
          API v1.0.0 Live
        </div>
      </div>

      {/* 页面 Header */}
      <header className="mb-16">
        <div className="inline-flex items-center justify-center p-3 rounded-2xl bg-os-surface/50 border border-os-border/50 mb-6 shadow-[0_0_30px_rgba(129,140,248,0.15)]">
          <BookOpen className="w-8 h-8 text-os-accent"/>
        </div>
        <h1 className="text-4xl md:text-5xl font-extrabold mb-4 tracking-tight text-transparent bg-clip-text bg-gradient-to-r from-white to-os-muted">
          开发者文档 & API 引用
        </h1>
        <p className="text-lg text-os-subtle max-w-2xl leading-relaxed">
          欢迎来到知维 OS 开发者中心。通过我们提供的 RESTful API 和官方 SDK，您可以轻松地将“认知内核”、“长期记忆”与“沙箱控制面”集成到您的企业级 Agent 业务流中。
        </p>
      </header>

      <div className="space-y-16">
        {/* Section 1: 鉴权 */}
        <section className="grid grid-cols-1 lg:grid-cols-2 gap-8 items-start">
          <div>
            <div className="flex items-center gap-3 mb-4">
              <Key className="w-6 h-6 text-emerald-400"/>
              <h2 className="text-2xl font-bold">API 鉴权 (Authentication)</h2>
            </div>
            <p className="text-os-subtle mb-4 leading-relaxed">
              所有的 API 请求必须在 Header 中包含您的专属 API Key。您可以在开发者控制台的 <code className="text-os-text bg-os-surface px-1.5 py-0.5 rounded">API Keys</code> 页面生成并管理您的密钥。
            </p>
            <div className="bg-os-warning/10 border border-os-warning/30 rounded-xl p-4 flex gap-3 text-sm text-os-warning">
              <Shield className="w-5 h-5 shrink-0"/>
              <p>请妥善保管您的 <code className="font-mono">sk-zhiwei-***</code> 密钥，切勿将其硬编码在前端代码或公开的 GitHub 仓库中。</p>
            </div>
          </div>
          <CodeBlock
            title="cURL - 鉴权示例"
            language="bash"
            code={`curl -X GET "https://api.zhiwei.os/v1/models" \\
  -H "Authorization: Bearer sk-zhiwei-xxxxxxxxxxxxx" \\
  -H "Content-Type: application/json"`}
          />
        </section>

        <hr className="border-os-border/50" />

        {/* Section 2: 长期记忆引擎 */}
        <section className="grid grid-cols-1 lg:grid-cols-2 gap-8 items-start">
          <div>
            <div className="flex items-center gap-3 mb-4">
              <Brain className="w-6 h-6 text-purple-400"/>
              <h2 className="text-2xl font-bold">读写记忆 (Memory Engine)</h2>
            </div>
            <p className="text-os-subtle mb-4 leading-relaxed">
              知维 OS 提供分层的长期记忆管理架构。您可以使用 <code className="font-mono text-os-text">client.memory</code> 命名空间，向系统中写入情景记忆（Episodic）或语义记忆（Semantic），并支持自动的向量化检索与反思合并。
            </p>
            <ul className="space-y-2 text-os-subtle text-sm mb-6 list-disc pl-5">
              <li><strong className="text-os-text">write()</strong>: 写入原子化记忆切片。</li>
              <li><strong className="text-os-text">search()</strong>: 基于余弦相似度的语义召回。</li>
            </ul>
          </div>
          <CodeBlock
            title="python - 记忆检索"
            language="python"
            code={`from zhiwei_os import ZhiweiClient, MemoryScope

client = ZhiweiClient(api_key="sk-zhiwei-...")

# 写入长期记忆
await client.memory.write(
    content="用户偏好夜间深度工作，习惯使用深色模式。",
    scope=MemoryScope.EPISODIC,
    importance=0.92
)

# 语义检索与反思合并
results = await client.memory.search(
    query="用户的工作习惯是什么？",
    top_k=5,
    rerank=True
)

print(f"召回 {len(results)} 条相关记忆")`}
          />
        </section>

        <hr className="border-os-border/50" />

        {/* Section 3: 安全沙箱执行 */}
        <section className="grid grid-cols-1 lg:grid-cols-2 gap-8 items-start">
          <div>
            <div className="flex items-center gap-3 mb-4">
              <Terminal className="w-6 h-6 text-cyan-400"/>
              <h2 className="text-2xl font-bold">沙箱执行 (Rootless Sandbox)</h2>
            </div>
            <p className="text-os-subtle mb-4 leading-relaxed">
              所有危险代码或第三方工具调用，都必须在知维 OS 的隔离沙箱中运行。系统会实时监控并拦截越权操作。
            </p>
            <p className="text-os-subtle leading-relaxed">
              调用 <code className="font-mono text-os-text">sandbox.execute()</code> 时，系统会自动挂载监控探针，运行产生的 Trace 数据会实时同步到您的可观测性仪表盘中。
            </p>
          </div>
          <CodeBlock
            title="python - 隔离沙箱"
            language="python"
            code={`# 在隔离沙箱中安全执行不受信代码
task = await client.sandbox.execute(
    code_string="import os; print(os.environ)",
    language="python",
    timeout=5.0,
    memory_limit="256MB",
    network_access=False
)

if task.status == "INTERCEPTED":
    print(f"执行被拦截: {task.security_reason}")
else:
    print(f"输出结果: {task.stdout}")`}
          />
        </section>
      </div>
      
      {/* Footer */}
      <footer className="mt-24 pt-8 border-t border-os-border text-center text-sm text-os-muted font-mono">
        &copy; {new Date().getFullYear()} 知维 OS Kernel. All rights reserved.
      </footer>
    </div>
  );
}

// 可复用的高定代码块组件
function CodeBlock({ code, title, language }: { code: string, title: string, language: string }) {
  // 极简防弹版语法高亮：移除会误伤 HTML class 的全局数字匹配
  const highlightedCode = code
    .replace(/(import|from|await|if|else|return)/g, '<span class="text-purple-400">$1</span>')
    .replace(/("|'.*?"|')/g, '<span class="text-emerald-400">$1</span>')
    .replace(/(#.*)/g, '<span class="text-os-muted italic">$1</span>');

  return (
    <div className="bg-[#0a0a0b] rounded-2xl border border-os-border/60 shadow-xl overflow-hidden group">
      {/* macOS 风格顶部栏 */}
      <div className="flex items-center justify-between px-4 py-3 bg-os-surface/30 border-b border-os-border/50">
        <div className="flex space-x-2">
          <div className="w-3 h-3 rounded-full bg-[#ff5f57] border border-[#e0443e]"></div>
          <div className="w-3 h-3 rounded-full bg-[#febc2e] border border-[#d89e24]"></div>
          <div className="w-3 h-3 rounded-full bg-[#28c840] border border-[#1aab29]"></div>
        </div>
        <div className="text-xs font-mono text-os-muted">{title}</div>
      </div>
      {/* 代码区 */}
      <div className="p-4 overflow-x-auto scrollbar-none">
        <pre className="text-sm font-mono leading-relaxed text-os-text-high whitespace-pre">
          <code dangerouslySetInnerHTML={{ __html: highlightedCode }} />
        </pre>
      </div>
    </div>
  );
}
