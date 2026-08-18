import Link from "next/link";
import { BookOpen, Terminal, Brain, Shield, Key, ChevronLeft } from "lucide-react";

export default function DeveloperDocsPage() {
  return (
    <div className="mx-auto min-h-screen w-full min-w-0 max-w-6xl overflow-x-hidden bg-os-base p-6 text-os-text selection:bg-os-accent/30 md:p-12 lg:px-24">
      {/* 顶部导航与面包屑 */}
      <div className="mb-12 flex items-center justify-between gap-4">
        <Link className="group flex items-center gap-2 text-os-subtle hover:text-os-accent transition-colors text-sm font-medium" href="/dashboard">
          <ChevronLeft className="w-4 h-4 group-hover:-translate-x-1 transition-transform"/>
          返回工作台
        </Link>
        <div className="flex shrink-0 items-center gap-2 rounded-full border border-indigo-200 bg-indigo-50 px-3 py-1.5 text-xs font-medium text-indigo-700">
          <span className="relative flex h-2 w-2">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-indigo-600 opacity-75"></span>
            <span className="relative inline-flex h-2 w-2 rounded-full bg-indigo-600"></span>
          </span>
          API v1.0.0 · 服务正常
        </div>
      </div>

      {/* 页面 Header */}
      <header className="mb-16">
        <div className="mb-6 inline-flex items-center justify-center rounded-2xl border border-os-border bg-os-surface p-3 shadow-os-card">
          <BookOpen className="w-8 h-8 text-os-accent"/>
        </div>
        <h1 className="mb-4 text-4xl font-bold tracking-tight text-os-text-high md:text-5xl">
          开发者文档与 API 参考
        </h1>
        <p className="max-w-2xl text-lg leading-7 text-os-text">
          欢迎来到知维 OS 开发者中心。通过我们提供的 RESTful API 和官方 SDK，您可以轻松地将“认知内核”、“长期记忆”与“沙箱控制面”集成到您的企业级智能体（Agent）业务流中。
        </p>
      </header>

      <div className="space-y-16">
        {/* Section 1: 鉴权 */}
        <section className="grid min-w-0 grid-cols-1 items-start gap-8 lg:grid-cols-2">
          <div className="min-w-0">
            <div className="flex items-center gap-3 mb-4">
              <Key className="h-6 w-6 text-emerald-700"/>
              <h2 className="text-2xl font-bold text-os-text-high">API 鉴权</h2>
            </div>
            <p className="text-os-subtle mb-4 leading-relaxed">
              所有 API 请求都必须在请求头（Header）中携带您的专属 API Key。您可以在开发者控制台的 <code className="rounded bg-os-surface px-1.5 py-0.5 text-os-text-high">API Keys</code> 页面生成并管理密钥。
            </p>
            <div className="flex gap-3 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm leading-6 text-amber-900">
              <Shield className="mt-0.5 h-5 w-5 shrink-0 text-amber-700"/>
              <p className="min-w-0">请妥善保管您的 <code className="font-mono font-medium text-amber-950">sk-zhiwei-***</code> 密钥，切勿将其硬编码在前端代码或公开的 GitHub 仓库中。</p>
            </div>
          </div>
          <CodeBlock
            title="cURL · 鉴权示例"
            language="bash"
            code={`curl -X GET "https://api.zhiwei.os/v1/models" \\
  -H "Authorization: Bearer sk-zhiwei-xxxxxxxxxxxxx" \\
  -H "Content-Type: application/json"`}
          />
        </section>

        <hr className="border-os-border" />

        {/* Section 2: 长期记忆引擎 */}
        <section className="grid min-w-0 grid-cols-1 items-start gap-8 lg:grid-cols-2">
          <div className="min-w-0">
            <div className="flex items-center gap-3 mb-4">
              <Brain className="h-6 w-6 text-os-memory-violet"/>
              <h2 className="text-2xl font-bold text-os-text-high">记忆引擎</h2>
            </div>
            <p className="text-os-subtle mb-4 leading-relaxed">
              知维 OS 提供分层的长期记忆管理架构。您可以使用 <code className="font-mono text-os-text">client.memory</code> 命名空间，向系统中写入情景记忆（Episodic）或语义记忆（Semantic），并支持自动的向量化检索与反思合并。
            </p>
            <ul className="space-y-2 text-os-subtle text-sm mb-6 list-disc pl-5">
              <li><strong className="text-os-text">write()</strong>：写入原子化记忆切片。</li>
              <li><strong className="text-os-text">search()</strong>：基于余弦相似度的语义召回。</li>
            </ul>
          </div>
          <CodeBlock
            title="Python · 记忆检索"
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

        <hr className="border-os-border" />

        {/* Section 3: 安全沙箱执行 */}
        <section className="grid min-w-0 grid-cols-1 items-start gap-8 lg:grid-cols-2">
          <div className="min-w-0">
            <div className="flex items-center gap-3 mb-4">
              <Terminal className="h-6 w-6 text-os-info"/>
              <h2 className="text-2xl font-bold text-os-text-high">Rootless 沙箱执行</h2>
            </div>
            <p className="text-os-subtle mb-4 leading-relaxed">
              所有危险代码或第三方工具调用，都必须在知维 OS 的隔离沙箱中运行。系统会实时监控并拦截越权操作。
            </p>
            <p className="text-os-subtle leading-relaxed">
              调用 <code className="font-mono text-os-text">sandbox.execute()</code> 时，系统会自动挂载监控探针，运行产生的追踪（Trace）数据会实时同步到您的可观测性仪表盘中。
            </p>
          </div>
          <CodeBlock
            title="Python · 隔离沙箱"
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
      <footer className="mt-24 border-t border-os-border pt-8 text-center text-sm text-os-subtle">
        &copy; {new Date().getFullYear()} 知维 OS 内核。保留所有权利。
      </footer>
    </div>
  );
}

// 可复用的高定代码块组件
function CodeBlock({ code, title, language }: { code: string, title: string, language: string }) {
  return (
    <div className="group min-w-0 max-w-full overflow-hidden rounded-2xl border border-os-border bg-os-surface shadow-os-card" data-language={language}>
      {/* macOS 风格顶部栏 */}
      <div className="flex items-center justify-between border-b border-os-border bg-os-surface-muted px-4 py-3">
        <div className="flex space-x-2">
          <div className="w-3 h-3 rounded-full bg-[#ff5f57] border border-[#e0443e]"></div>
          <div className="w-3 h-3 rounded-full bg-[#febc2e] border border-[#d89e24]"></div>
          <div className="w-3 h-3 rounded-full bg-[#28c840] border border-[#1aab29]"></div>
        </div>
        <div className="text-xs font-mono text-os-subtle">{title}</div>
      </div>
      {/* 代码区 */}
      <div className="max-w-full overflow-x-auto p-4">
        <pre className="min-w-max overflow-visible whitespace-pre font-mono text-sm leading-relaxed text-os-text-high">
          <code className="overflow-visible">{code}</code>
        </pre>
      </div>
    </div>
  );
}
