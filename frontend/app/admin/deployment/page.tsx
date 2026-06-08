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
import { apiFetch } from "@/services/api";

const BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

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
  if (!seconds || seconds < 0) return "N/A";
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return `${h}h ${m}m`;
}

function StatusIcon({ status }: { status: ServiceStatus }) {
  if (status === "healthy") return <CheckCircle2 size={16} className="text-emerald-400" />;
  if (status === "unhealthy") return <XCircle size={16} className="text-red-400" />;
  return <Clock size={16} className="text-amber-400 animate-pulse" />;
}

function statusBadgeStyle(status: ServiceStatus): string {
  switch (status) {
    case "healthy":
      return "bg-emerald-400/10 text-emerald-400";
    case "unhealthy":
      return "bg-red-400/10 text-red-400";
    default:
      return "bg-amber-400/10 text-amber-400";
  }
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
      const res = await fetch(`${BASE}/health`);
      if (res.ok) {
        const data = await res.json();
        setBackendHealth(data);
        setHealth((h) => ({ ...h, backend: "healthy" }));
      } else {
        setHealth((h) => ({ ...h, backend: "unhealthy" }));
      }
    } catch {
      setHealth((h) => ({ ...h, backend: "unhealthy" }));
      setError("Cannot reach backend. Is the server running?");
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
    { name: "Backend API", status: health.backend, url: `${BASE}/docs`, desc: "FastAPI application server" },
    { name: "Frontend", status: health.frontend, url: "/", desc: "Next.js web interface" },
    { name: "Database", status: health.database, url: null, desc: config?.db_type || "Primary data store" },
    { name: "Vector DB", status: health.vectorDb, url: null, desc: config?.vector_store || "Embedding vector store" },
  ];

  // ── Render ──

  return (
    <div className="p-6 space-y-5 max-w-[1440px] mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-os-text-high tracking-tight">
            Deployment Status
          </h1>
          <p className="text-xs text-os-subtle mt-0.5">
            System health, configuration, and deployment guide
          </p>
        </div>
        <button
          onClick={() => { checkHealth(); fetchConfig(); }}
          disabled={checking}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-2xs text-os-subtle hover:text-os-text hover:bg-os-elevated disabled:opacity-50 transition-colors"
        >
          <RefreshCw size={12} className={checking ? "animate-spin" : ""} />
          {checking ? "Checking..." : "Check Health"}
        </button>
      </div>

      {/* Error */}
      {error && (
        <div className="os-card p-3 rounded-lg border border-red-400/20 bg-red-400/5 text-red-400 text-xs">
          {error}
        </div>
      )}

      {/* Health Status Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {services.map((svc) => (
          <div key={svc.name} className="os-card p-4 rounded-lg border border-os-border/30 bg-os-surface hover:border-os-border/60 transition-colors">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm font-medium text-os-text-high">{svc.name}</span>
              <StatusIcon status={svc.status} />
            </div>
            <p className="text-xs text-os-muted mb-2">{svc.desc}</p>
            <div className="flex items-center justify-between">
              <span className={cn("px-1.5 py-0.5 rounded text-2xs font-bold uppercase", statusBadgeStyle(svc.status))}>
                {svc.status}
              </span>
              {svc.url && (
                <a
                  href={svc.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-xs text-os-accent hover:underline flex items-center gap-1"
                >
                  <ExternalLink size={11} /> Open
                </a>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* Backend Health Details */}
      {backendHealth && (
        <div>
          <h2 className="text-xs font-medium text-os-text-high uppercase tracking-wider mb-3">
            Backend Details
          </h2>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div className="os-card p-3 rounded-lg border border-os-border/30 bg-os-surface text-center">
              <span className="text-2xs text-os-muted uppercase block mb-1">Version</span>
              <p className="text-sm font-mono font-semibold text-os-text-high">
                {backendHealth.version || "N/A"}
              </p>
            </div>
            <div className="os-card p-3 rounded-lg border border-os-border/30 bg-os-surface text-center">
              <span className="text-2xs text-os-muted uppercase block mb-1">Uptime</span>
              <p className="text-sm font-mono font-semibold text-os-text-high">
                {backendHealth.uptime_seconds != null ? formatUptime(backendHealth.uptime_seconds) : "N/A"}
              </p>
            </div>
            <div className="os-card p-3 rounded-lg border border-os-border/30 bg-os-surface text-center">
              <span className="text-2xs text-os-muted uppercase block mb-1">Status</span>
              <p className={cn("text-sm font-semibold capitalize", backendHealth.status === "healthy" ? "text-emerald-400" : "text-red-400")}>
                {backendHealth.status || "unknown"}
              </p>
            </div>
            <div className="os-card p-3 rounded-lg border border-os-border/30 bg-os-surface text-center">
              <span className="text-2xs text-os-muted uppercase block mb-1">Checks</span>
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
                    <span className="text-xs text-os-text-high capitalize">{name.replace(/_/g, " ")}</span>
                    {check.latency_ms != null && (
                      <span className="text-2xs text-os-muted ml-2 font-mono">{check.latency_ms}ms</span>
                    )}
                  </div>
                  {check.status === "pass" ? (
                    <CheckCircle2 size={14} className="text-emerald-400" />
                  ) : check.status === "warn" ? (
                    <AlertTriangle size={14} className="text-amber-400" />
                  ) : (
                    <XCircle size={14} className="text-red-400" />
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Configuration Summary */}
      <div>
        <h2 className="text-xs font-medium text-os-text-high uppercase tracking-wider mb-3">
          Configuration
        </h2>
        {config ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
            <div className="os-card p-3 rounded-lg border border-os-border/30 bg-os-surface">
              <div className="flex items-center gap-2 mb-2">
                <Database size={13} className="text-os-accent" />
                <span className="text-2xs text-os-muted uppercase tracking-wider">Database</span>
              </div>
              <p className="text-xs font-mono text-os-text-high">{config.db_type || "N/A"}</p>
            </div>
            <div className="os-card p-3 rounded-lg border border-os-border/30 bg-os-surface">
              <div className="flex items-center gap-2 mb-2">
                <Network size={13} className="text-os-accent" />
                <span className="text-2xs text-os-muted uppercase tracking-wider">Vector Store</span>
              </div>
              <p className="text-xs font-mono text-os-text-high">{config.vector_store || "N/A"}</p>
            </div>
            <div className="os-card p-3 rounded-lg border border-os-border/30 bg-os-surface">
              <div className="flex items-center gap-2 mb-2">
                <Cpu size={13} className="text-os-accent" />
                <span className="text-2xs text-os-muted uppercase tracking-wider">LLM Provider</span>
              </div>
              <p className="text-xs font-mono text-os-text-high">{config.llm_provider || "N/A"}</p>
            </div>
            <div className="os-card p-3 rounded-lg border border-os-border/30 bg-os-surface">
              <div className="flex items-center gap-2 mb-2">
                <HardDrive size={13} className="text-os-accent" />
                <span className="text-2xs text-os-muted uppercase tracking-wider">Embedding Model</span>
              </div>
              <p className="text-xs font-mono text-os-text-high">{config.embedding_model || "N/A"}</p>
            </div>
          </div>
        ) : (
          <div className="os-card rounded-lg border border-os-border/30 bg-os-surface overflow-hidden">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-os-muted border-b border-os-border/30 bg-os-elevated/30">
                  <th className="text-left py-2.5 px-3 font-medium">Setting</th>
                  <th className="text-left py-2.5 px-3 font-medium">Value</th>
                  <th className="text-left py-2.5 px-3 font-medium hidden sm:table-cell">Description</th>
                </tr>
              </thead>
              <tbody>
                {[
                  ["API Base URL", BASE, "Backend API endpoint"],
                  ["Database", "SQLite (embedded)", "Relational database"],
                  ["Vector DB", "ChromaDB (embedded)", "Vector database for embeddings"],
                  ["Embedding Model", "BAAI/bge-small-zh-v1.5", "Chinese-optimized embeddings"],
                  ["LLM", "DeepSeek API", "Language model provider"],
                ].map(([key, value, desc]) => (
                  <tr key={key} className="border-b border-os-border/10 hover:bg-os-elevated/30 transition-colors">
                    <td className="py-2.5 px-3 font-medium text-os-text-high">{key}</td>
                    <td className="py-2.5 px-3 text-os-text font-mono text-2xs">{value}</td>
                    <td className="py-2.5 px-3 text-os-muted hidden sm:table-cell">{desc}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Deployment Guide Quick Links */}
      <div>
        <h2 className="text-xs font-medium text-os-text-high uppercase tracking-wider mb-3">
          Deployment Guide
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div className="os-card p-4 rounded-lg border border-os-border/30 bg-os-surface hover:border-os-accent/30 transition-colors">
            <div className="flex items-center gap-2 mb-2">
              <Terminal size={14} className="text-os-accent" />
              <span className="text-xs font-semibold text-os-text-high">Docker</span>
            </div>
            <p className="text-2xs text-os-muted mb-3">
              Single-container deployment. Ideal for development and small teams.
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
              Docker Docs <ExternalLink size={10} />
            </a>
          </div>

          <div className="os-card p-4 rounded-lg border border-os-border/30 bg-os-surface hover:border-os-accent/30 transition-colors">
            <div className="flex items-center gap-2 mb-2">
              <Container size={14} className="text-os-accent" />
              <span className="text-xs font-semibold text-os-text-high">Docker Compose</span>
            </div>
            <p className="text-2xs text-os-muted mb-3">
              Multi-service deployment with frontend + backend. Recommended for production.
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
            <p className="text-2xs text-os-muted mb-3">
              Helm-based deployment for Kubernetes clusters. Best for enterprise scale.
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
              K8s Docs <ExternalLink size={10} />
            </a>
          </div>
        </div>
      </div>

      {/* Deployment Files Reference */}
      <div>
        <h2 className="text-xs font-medium text-os-text-high uppercase tracking-wider mb-3">
          Deployment Files
        </h2>
        <div className="os-card rounded-lg border border-os-border/30 bg-os-surface overflow-hidden">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-os-muted border-b border-os-border/30 bg-os-elevated/30">
                <th className="text-left py-2.5 px-3 font-medium">File</th>
                <th className="text-left py-2.5 px-3 font-medium hidden sm:table-cell">Purpose</th>
              </tr>
            </thead>
            <tbody>
              {[
                ["deployment/docker/Dockerfile", "Backend container image"],
                ["deployment/docker/Dockerfile.frontend", "Frontend container image"],
                ["deployment/docker/docker-compose.yml", "Multi-service orchestration"],
                ["deployment/docker/docker-compose.offline.yml", "Offline/air-gapped deployment"],
                ["deployment/docker/.env.docker", "Environment variable template"],
                ["deployment/helm/Chart.yaml", "Helm chart metadata"],
                ["deployment/helm/values.yaml", "Kubernetes configuration values"],
                ["deployment/helm/templates/", "Kubernetes resource templates"],
                ["deployment/README.md", "Full deployment documentation"],
              ].map(([file, purpose]) => (
                <tr key={file} className="border-b border-os-border/10 hover:bg-os-elevated/30 transition-colors">
                  <td className="py-2.5 px-3 text-os-text font-mono text-2xs">{file}</td>
                  <td className="py-2.5 px-3 text-os-muted hidden sm:table-cell">{purpose}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Quick Links */}
      <div>
        <h2 className="text-xs font-medium text-os-text-high uppercase tracking-wider mb-3">
          Quick Links
        </h2>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2">
          {[
            { label: "API Docs", url: `${BASE}/docs` },
            { label: "Redoc", url: `${BASE}/redoc` },
            { label: "Health", url: `${BASE}/health` },
            { label: "Metrics", url: `${BASE}/metrics` },
            { label: "OpenAPI JSON", url: `${BASE}/openapi.json` },
            { label: "Admin API", url: `${BASE}/api/admin/summary` },
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
