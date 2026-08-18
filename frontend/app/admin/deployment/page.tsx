"use client";

import { useState, useEffect, useCallback } from "react";
import {
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Clock,
  ExternalLink,
  RefreshCw,
  Terminal,
  BookOpen,
  Cpu,
  HardDrive,
  Database,
  Network,
  Container,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { apiFetch, API_BASE_URL } from "@/services/api";
import { layout } from "@/styles/layout";

// Display-only alias for anchor hrefs to backend docs/redoc/health endpoints.
// All actual fetch calls use apiFetch() with relative paths — this constant is
// NEVER used in fetch. Sourced from the unified API_BASE_URL to avoid duplicating
// the hardcoded fallback URL across files.
const BASE = API_BASE_URL;

// ── Types ──

type ServiceStatus = "healthy" | "unhealthy" | "checking";

interface HealthStatus {
  backend: ServiceStatus;
  frontend: ServiceStatus;
  database: ServiceStatus;
  vectorDb: ServiceStatus;
}

interface BackendHealth {
  status: string;
  version?: string;
  uptime_seconds?: number;
  checks?: Record<string, { status: string; message: string; latency_ms?: number }>;
}

interface ConfigSummary {
  db_type?: string;
  vector_store?: string;
  llm_provider?: string;
  embedding_model?: string;
  auth_enabled?: boolean;
  cors_origins?: string[];
  log_level?: string;
  environment?: string;
}

// ── Helpers ──

function formatUptime(seconds: number): string {
  if (!seconds || seconds < 0) return "暂无";
  if (seconds < 60) return `${seconds} 秒`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)} 分 ${seconds % 60} 秒`;
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return `${h} 小时 ${m} 分`;
}

function StatusIcon({ status }: { status: ServiceStatus }) {
  if (status === "healthy") return <CheckCircle2 size={16} className="text-os-success" />;
  if (status === "unhealthy") return <XCircle size={16} className="text-os-danger" />;
  return <Clock size={16} className="text-os-warning animate-pulse" />;
}

function statusBadgeStyle(status: ServiceStatus): string {
  switch (status) {
    case "healthy":
      return "bg-os-success-soft text-os-success";
    case "unhealthy":
      return "bg-os-danger-soft text-os-danger";
    default:
      return "bg-os-warning-soft text-os-warning";
  }
}

const SERVICE_STATUS_LABELS: Record<ServiceStatus, string> = {
  healthy: "健康",
  unhealthy: "异常",
  checking: "检查中",
};

const BACKEND_STATUS_LABELS: Record<string, string> = {
  healthy: "健康",
  ok: "正常",
  pass: "正常",
  unhealthy: "异常",
  error: "异常",
  fail: "失败",
};

const CHECK_LABELS: Record<string, string> = {
  database: "数据库",
  vector_db: "向量数据库",
  vector_store: "向量存储",
  redis: "Redis",
  storage: "存储",
  llm: "LLM",
};

function isHealthyBackendStatus(status: string): boolean {
  return status === "healthy" || status === "ok" || status === "pass";
}

// ── Page ──

export default function DeploymentStatusPage() {
  const [health, setHealth] = useState<HealthStatus>({
    backend: "checking",
    frontend: "healthy",
    database: "checking",
    vectorDb: "checking",
  });
  const [backendHealth, setBackendHealth] = useState<BackendHealth | null>(null);
  const [config, setConfig] = useState<ConfigSummary | null>(null);
  const [checking, setChecking] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const checkHealth = useCallback(async () => {
    setChecking(true);
    setError(null);

    // Check backend
    try {
      const data = await apiFetch<BackendHealth>("/health");
      setBackendHealth(data);
      setHealth((h) => ({ ...h, backend: "healthy" }));
    } catch {
      setHealth((h) => ({ ...h, backend: "unhealthy" }));
      setError("无法连接后端服务，请确认服务器是否正在运行。");
    }

    // Check DB via dashboard endpoint
    try {
      await apiFetch("/dashboard/summary");
      setHealth((h) => ({ ...h, database: "healthy" }));
    } catch {
      setHealth((h) => ({ ...h, database: "unhealthy" }));
    }

    // Vector DB
    setHealth((h) => ({
      ...h,
      vectorDb: h.backend === "healthy" ? "healthy" : "checking",
    }));

    setChecking(false);
  }, []);

  const fetchConfig = useCallback(async () => {
    try {
      setConfig(await apiFetch<ConfigSummary>("/api/admin/config"));
    } catch {
      // config endpoint optional
    }
  }, []);

  useEffect(() => {
    checkHealth();
    fetchConfig();
  }, [checkHealth, fetchConfig]);

  const services = [
    { name: "后端 API", status: health.backend, url: `${BASE}/docs`, desc: "FastAPI 应用服务" },
    { name: "前端", status: health.frontend, url: "/", desc: "Next.js Web 界面" },
    { name: "数据库", status: health.database, url: null, desc: config?.db_type || "主数据存储" },
    { name: "向量数据库", status: health.vectorDb, url: null, desc: config?.vector_store || "向量嵌入存储" },
  ];

  // ── Render ──

  return (
    <div className="p-6 space-y-5 max-w-[1440px] mx-auto">
      {/* Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-lg font-semibold text-os-text-high tracking-tight">
            部署状态
          </h1>
          <p className="text-xs text-os-subtle mt-0.5">
            系统健康、配置与部署指南
          </p>
        </div>
        <button
          onClick={() => { checkHealth(); fetchConfig(); }}
          disabled={checking}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-2xs text-os-subtle hover:text-os-text hover:bg-os-elevated disabled:opacity-50 transition-colors"
        >
          <RefreshCw size={12} className={checking ? "animate-spin" : ""} />
          {checking ? "检查中..." : "检查健康状况"}
        </button>
      </div>

      {/* Error */}
      {error && (
        <div className="os-card rounded-lg border border-os-danger/20 bg-os-danger-soft p-3 text-xs text-os-danger">
          {error}
        </div>
      )}

      {/* Health Status Cards */}
      <div className={layout.grid.twoMd}>
        {services.map((svc) => (
          <div key={svc.name} className="os-card p-4 rounded-lg border border-os-border/30 bg-os-surface hover:border-os-border/60 transition-colors">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm font-medium text-os-text-high">{svc.name}</span>
              <StatusIcon status={svc.status} />
            </div>
            <p className="mb-2 break-words text-xs text-os-subtle">{svc.desc}</p>
            <div className="flex items-center justify-between">
              <span className={cn("px-1.5 py-0.5 rounded text-2xs font-bold", statusBadgeStyle(svc.status))}>
                {SERVICE_STATUS_LABELS[svc.status]}
              </span>
              {svc.url && (
                <a
                  href={svc.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-xs text-os-accent hover:underline flex items-center gap-1"
                >
                  <ExternalLink size={11} /> 打开
                </a>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* Backend Health Details */}
      {backendHealth && (
        <div>
          <h2 className="text-xs font-medium text-os-text-high tracking-wider mb-3">
            后端详情
          </h2>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div className="os-card p-3 rounded-lg border border-os-border/30 bg-os-surface text-center">
              <span className="text-2xs text-os-subtle block mb-1">版本</span>
              <p className="text-sm font-mono font-semibold text-os-text-high">
                {backendHealth.version || "暂无"}
              </p>
            </div>
            <div className="os-card p-3 rounded-lg border border-os-border/30 bg-os-surface text-center">
              <span className="text-2xs text-os-subtle block mb-1">运行时长</span>
              <p className="text-sm font-mono font-semibold text-os-text-high">
                {backendHealth.uptime_seconds != null ? formatUptime(backendHealth.uptime_seconds) : "暂无"}
              </p>
            </div>
            <div className="os-card p-3 rounded-lg border border-os-border/30 bg-os-surface text-center">
              <span className="text-2xs text-os-subtle block mb-1">状态</span>
              <p className={cn("text-sm font-semibold", isHealthyBackendStatus(backendHealth.status) ? "text-os-success" : "text-os-danger")}>
                {BACKEND_STATUS_LABELS[backendHealth.status] || "未知"}
              </p>
            </div>
            <div className="os-card p-3 rounded-lg border border-os-border/30 bg-os-surface text-center">
              <span className="text-2xs text-os-subtle block mb-1">检查项</span>
              <p className="text-sm font-mono font-semibold text-os-text-high">
                {backendHealth.checks ? Object.keys(backendHealth.checks).length : 0}
              </p>
            </div>
          </div>

          {/* Individual checks */}
          {backendHealth.checks && Object.keys(backendHealth.checks).length > 0 && (
            <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
              {Object.entries(backendHealth.checks).map(([name, check]) => (
                <div key={name} className="os-card p-3 rounded-lg border border-os-border/30 bg-os-surface flex items-center justify-between">
                  <div>
                    <span className="text-xs text-os-text-high">{CHECK_LABELS[name] || name.replace(/_/g, " ")}</span>
                    {check.latency_ms != null && (
                      <span className="text-2xs text-os-subtle ml-2 font-mono">{check.latency_ms} ms</span>
                    )}
                  </div>
                  {check.status === "pass" ? (
                    <CheckCircle2 size={14} className="text-os-success" />
                  ) : check.status === "warn" ? (
                    <AlertTriangle size={14} className="text-os-warning" />
                  ) : (
                    <XCircle size={14} className="text-os-danger" />
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Configuration Summary */}
      <div>
        <h2 className="text-xs font-medium text-os-text-high tracking-wider mb-3">
          配置摘要
        </h2>
        {config ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
            <div className="os-card p-3 rounded-lg border border-os-border/30 bg-os-surface">
              <div className="flex items-center gap-2 mb-2">
                <Database size={13} className="text-os-accent" />
                <span className="text-2xs text-os-subtle tracking-wider">数据库</span>
              </div>
              <p className="text-xs font-mono text-os-text-high">{config.db_type || "暂无"}</p>
            </div>
            <div className="os-card p-3 rounded-lg border border-os-border/30 bg-os-surface">
              <div className="flex items-center gap-2 mb-2">
                <Network size={13} className="text-os-accent" />
                <span className="text-2xs text-os-subtle tracking-wider">向量存储</span>
              </div>
              <p className="text-xs font-mono text-os-text-high">{config.vector_store || "暂无"}</p>
            </div>
            <div className="os-card p-3 rounded-lg border border-os-border/30 bg-os-surface">
              <div className="flex items-center gap-2 mb-2">
                <Cpu size={13} className="text-os-accent" />
                <span className="text-2xs text-os-subtle tracking-wider">LLM 提供商</span>
              </div>
              <p className="text-xs font-mono text-os-text-high">{config.llm_provider || "暂无"}</p>
            </div>
            <div className="os-card p-3 rounded-lg border border-os-border/30 bg-os-surface">
              <div className="flex items-center gap-2 mb-2">
                <HardDrive size={13} className="text-os-accent" />
                <span className="text-2xs text-os-subtle tracking-wider">向量嵌入模型</span>
              </div>
              <p className="text-xs font-mono text-os-text-high">{config.embedding_model || "暂无"}</p>
            </div>
          </div>
        ) : (
          <div className="os-card rounded-lg border border-os-border/30 bg-os-surface overflow-hidden">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-os-subtle border-b border-os-border/30 bg-os-elevated/30">
                  <th className="text-left py-2.5 px-3 font-medium">设置</th>
                  <th className="text-left py-2.5 px-3 font-medium">值</th>
                  <th className="text-left py-2.5 px-3 font-medium hidden sm:table-cell">说明</th>
                </tr>
              </thead>
              <tbody>
                {[
                  ["API 基础 URL", BASE, "后端 API 端点"],
                  ["数据库", "SQLite（嵌入式）", "关系型数据库"],
                  ["向量数据库", "ChromaDB（嵌入式）", "用于向量嵌入的数据库"],
                  ["向量嵌入模型", "BAAI/bge-small-zh-v1.5", "针对中文优化的向量嵌入"],
                  ["LLM", "DeepSeek API", "语言模型提供商"],
                ].map(([key, value, desc]) => (
                  <tr key={key} className="border-b border-os-border/10 hover:bg-os-elevated/30 transition-colors">
                    <td className="py-2.5 px-3 font-medium text-os-text-high">{key}</td>
                    <td className="py-2.5 px-3 text-os-text font-mono text-2xs">{value}</td>
                    <td className="py-2.5 px-3 text-os-subtle hidden sm:table-cell">{desc}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Deployment Guide Quick Links */}
      <div>
        <h2 className="text-xs font-medium text-os-text-high tracking-wider mb-3">
          部署指南
        </h2>
        <div className={layout.grid.threeMd}>
          <div className="os-card p-4 rounded-lg border border-os-border/30 bg-os-surface hover:border-os-accent/30 transition-colors">
            <div className="flex items-center gap-2 mb-2">
              <Terminal size={14} className="text-os-accent" />
              <span className="text-xs font-semibold text-os-text-high">Docker</span>
            </div>
            <p className="text-2xs text-os-subtle mb-3">
              单容器部署，适合开发环境与小型团队。
            </p>
            <div className="space-y-1.5">
              <code className="block p-2 bg-os-elevated rounded text-2xs text-os-text overflow-x-auto">
                docker build -t ekos .
              </code>
              <code className="block p-2 bg-os-elevated rounded text-2xs text-os-text overflow-x-auto">
                docker run -p 8000:8000 ekos
              </code>
            </div>
            <a
              href="https://docs.docker.com/"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-2xs text-os-accent hover:underline mt-3"
            >
              Docker 文档 <ExternalLink size={10} />
            </a>
          </div>

          <div className="os-card p-4 rounded-lg border border-os-border/30 bg-os-surface hover:border-os-accent/30 transition-colors">
            <div className="flex items-center gap-2 mb-2">
              <Container size={14} className="text-os-accent" />
              <span className="text-xs font-semibold text-os-text-high">Docker Compose</span>
            </div>
            <p className="text-2xs text-os-subtle mb-3">
              前后端多服务部署，推荐用于生产环境。
            </p>
            <div className="space-y-1.5">
              <code className="block p-2 bg-os-elevated rounded text-2xs text-os-text overflow-x-auto">
                git clone &lt;repo-url&gt;
              </code>
              <code className="block p-2 bg-os-elevated rounded text-2xs text-os-text overflow-x-auto">
                docker compose up -d
              </code>
              <code className="block p-2 bg-os-elevated rounded text-2xs text-os-text overflow-x-auto">
                docker compose ps
              </code>
            </div>
          </div>

          <div className="os-card p-4 rounded-lg border border-os-border/30 bg-os-surface hover:border-os-accent/30 transition-colors">
            <div className="flex items-center gap-2 mb-2">
              <BookOpen size={14} className="text-os-accent" />
              <span className="text-xs font-semibold text-os-text-high">Kubernetes</span>
            </div>
            <p className="text-2xs text-os-subtle mb-3">
              基于 Helm 部署到 Kubernetes 集群，适合企业级规模。
            </p>
            <div className="space-y-1.5">
              <code className="block p-2 bg-os-elevated rounded text-2xs text-os-text overflow-x-auto">
                helm repo add ekos https://charts.example.com
              </code>
              <code className="block p-2 bg-os-elevated rounded text-2xs text-os-text overflow-x-auto">
                helm install ekos ./deployment/helm
              </code>
              <code className="block p-2 bg-os-elevated rounded text-2xs text-os-text overflow-x-auto">
                kubectl get pods -n ekos
              </code>
            </div>
            <a
              href="https://kubernetes.io/docs/home/"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-2xs text-os-accent hover:underline mt-3"
            >
              Kubernetes 文档 <ExternalLink size={10} />
            </a>
          </div>
        </div>
      </div>

      {/* Deployment Files Reference */}
      <div>
        <h2 className="text-xs font-medium text-os-text-high tracking-wider mb-3">
          部署文件
        </h2>
        <div className="os-card rounded-lg border border-os-border/30 bg-os-surface overflow-hidden">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-os-subtle border-b border-os-border/30 bg-os-elevated/30">
                <th className="text-left py-2.5 px-3 font-medium">文件</th>
                <th className="text-left py-2.5 px-3 font-medium hidden sm:table-cell">用途</th>
              </tr>
            </thead>
            <tbody>
              {[
                ["deployment/docker/Dockerfile", "后端容器镜像"],
                ["deployment/docker/Dockerfile.frontend", "前端容器镜像"],
                ["deployment/docker/docker-compose.yml", "多服务编排"],
                ["deployment/docker/docker-compose.offline.yml", "离线 / 隔离网络部署"],
                ["deployment/docker/.env.docker", "环境变量模板"],
                ["deployment/helm/Chart.yaml", "Helm Chart 元数据"],
                ["deployment/helm/values.yaml", "Kubernetes 配置值"],
                ["deployment/helm/templates/", "Kubernetes 资源模板"],
                ["deployment/README.md", "完整部署文档"],
              ].map(([file, purpose]) => (
                <tr key={file} className="border-b border-os-border/10 hover:bg-os-elevated/30 transition-colors">
                  <td className="py-2.5 px-3 text-os-text font-mono text-2xs">{file}</td>
                  <td className="py-2.5 px-3 text-os-subtle hidden sm:table-cell">{purpose}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Quick Links */}
      <div>
        <h2 className="text-xs font-medium text-os-text-high tracking-wider mb-3">
          快捷链接
        </h2>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2">
          {[
            { label: "API 文档", url: `${BASE}/docs` },
            { label: "Redoc", url: `${BASE}/redoc` },
            { label: "健康检查", url: `${BASE}/health` },
            { label: "监控指标", url: `${BASE}/metrics` },
            { label: "OpenAPI JSON", url: `${BASE}/openapi.json` },
            { label: "管理 API", url: `${BASE}/api/admin/summary` },
          ].map((link) => (
            <a
              key={link.label}
              href={link.url}
              target="_blank"
              rel="noopener noreferrer"
              className="os-card p-3 rounded-lg border border-os-border/30 bg-os-surface hover:border-os-border/60 hover:bg-os-elevated/50 transition-all text-center group"
            >
              <p className="text-xs text-os-text group-hover:text-os-text-high transition-colors">{link.label}</p>
              <ExternalLink size={10} className="mx-auto mt-1 text-os-muted group-hover:text-os-accent transition-colors" />
            </a>
          ))}
        </div>
      </div>
    </div>
  );
}
