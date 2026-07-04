"use client";
/* eslint-disable react/no-unescaped-entities */

import { useState, useCallback, useMemo, useEffect, useRef } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { motion, AnimatePresence } from "framer-motion";
import {
  Link,
  RefreshCw,
  CheckCircle2,
  ListOrdered,
  Plus,
  Trash2,
  Play,
  RotateCcw,
  Clock,
  Loader2,
  AlertTriangle,
  X,
  Search,
  Settings2,
  TestTube,
  MessageSquare,
  BookOpen,
  BookMarked,
  Gem,
  Network,
  Github,
  Rss,
  MessageCircle,
  HardDrive,
  Box,
  FolderOpen,
  Cloud,
  Heart,
  ChevronDown,
  ChevronUp,
  BarChart3,
  Terminal,
} from "lucide-react";
import { api } from "@/services/api";
import { PageTransition, StaggerItem } from "@/components/animations/page-transition";
import { CardSkeleton } from "@/components/animations/skeleton";
import { cn, formatNumber, formatDate } from "@/lib/utils";
import { layout } from "@/styles/layout";

// ── 本地类型（types/sync.ts 尚未建立时的 fallback） ──

interface SyncConnector {
  connector_id: string;
  name: string;
  connector_type: string;
  status: "active" | "inactive" | "error";
  last_sync_at: string | null;
  credentials?: Record<string, string>;
  created_at: string;
  updated_at?: string;
}

interface SyncJob {
  job_id: string;
  connector_config_id: string;
  name: string;
  rule_type: string;
  cron_expression: string | null;
  status: "active" | "paused" | "error" | "running";
  last_run_at: string | null;
  next_run_at: string | null;
  created_at: string;
  updated_at?: string;
  connector_name?: string;
  connector_type?: string;
}

interface SyncExecution {
  execution_id: string;
  job_id: string;
  job_name?: string;
  connector_type?: string;
  status: "running" | "completed" | "failed";
  started_at: string;
  completed_at: string | null;
  duration_ms: number | null;
  items_new: number;
  items_updated: number;
  items_deleted: number;
  error: string | null;
}

interface SyncStatsResponse {
  total_connectors: number;
  enabled_connectors: number;
  active_jobs: number;
  pending_jobs: number;
  last_hour_executions: number;
  last_hour_failures: number;
  queue_depth: number;
  connectors: SyncConnector[];
}

type TabId = "connectors" | "jobs" | "history";

// ── 常量 ──

const CONNECTOR_TYPES = [
  { value: "feishu", label: "飞书", icon: MessageSquare },
  { value: "yuque", label: "语雀", icon: BookOpen },
  { value: "notion", label: "Notion", icon: BookMarked },
  { value: "obsidian", label: "Obsidian", icon: Gem },
  { value: "logseq", label: "Logseq", icon: Network },
  { value: "github", label: "GitHub", icon: Github },
  { value: "rss", label: "RSS", icon: Rss },
  { value: "wechat_mp", label: "微信公众号", icon: MessageCircle },
  { value: "bilibili", label: "Bilibili", icon: Play },
  { value: "weixin_reader", label: "微信读书", icon: Heart },
  { value: "local_folder", label: "本地文件夹", icon: FolderOpen },
  { value: "onedrive", label: "OneDrive", icon: Cloud },
  { value: "gdrive", label: "Google Drive", icon: HardDrive },
  { value: "dropbox", label: "Dropbox", icon: Box },
] as const;

function getConnectorIcon(type: string) {
  return CONNECTOR_TYPES.find((t) => t.value === type)?.icon ?? Link;
}

function getConnectorLabel(type: string): string {
  return CONNECTOR_TYPES.find((t) => t.value === type)?.label ?? type;
}

const CONNECTOR_CREDENTIAL_FIELDS: Record<string, { key: string; label: string; type: "text" | "password"; placeholder: string }[]> = {
  feishu: [
    { key: "app_id", label: "App ID", type: "text", placeholder: "cli_..." },
    { key: "app_secret", label: "App Secret", type: "password", placeholder: "••••••••" },
  ],
  yuque: [
    { key: "token", label: "Token", type: "password", placeholder: "••••••••" },
    { key: "namespace", label: "Namespace", type: "text", placeholder: "user/repo" },
  ],
  notion: [
    { key: "api_key", label: "API Key", type: "password", placeholder: "secret_..." },
    { key: "database_id", label: "Database ID", type: "text", placeholder: "••••••••" },
  ],
  obsidian: [
    { key: "vault_path", label: "Vault Path", type: "text", placeholder: "/path/to/vault" },
  ],
  logseq: [
    { key: "graph_path", label: "Graph Path", type: "text", placeholder: "/path/to/graph" },
  ],
  github: [
    { key: "token", label: "Personal Access Token", type: "password", placeholder: "ghp_..." },
    { key: "repo", label: "Repository (owner/name)", type: "text", placeholder: "user/repo" },
  ],
  rss: [
    { key: "feed_url", label: "Feed URL", type: "text", placeholder: "https://..." },
  ],
  wechat_mp: [
    { key: "app_id", label: "App ID", type: "text", placeholder: "wx..." },
    { key: "app_secret", label: "App Secret", type: "password", placeholder: "••••••••" },
  ],
  bilibili: [
    { key: "uid", label: "User ID (UID)", type: "text", placeholder: "123456" },
  ],
  weixin_reader: [
    { key: "cookie", label: "Cookie", type: "password", placeholder: "••••••••" },
  ],
  local_folder: [
    { key: "path", label: "Folder Path", type: "text", placeholder: "D:\\notes" },
  ],
  onedrive: [
    { key: "client_id", label: "Client ID", type: "text", placeholder: "••••••••" },
    { key: "client_secret", label: "Client Secret", type: "password", placeholder: "••••••••" },
    { key: "folder_path", label: "Folder Path (可选)", type: "text", placeholder: "/Documents/Notes" },
  ],
  gdrive: [
    { key: "client_id", label: "Client ID", type: "text", placeholder: "••••••••" },
    { key: "client_secret", label: "Client Secret", type: "password", placeholder: "••••••••" },
    { key: "folder_id", label: "Folder ID (可选)", type: "text", placeholder: "••••••••" },
  ],
  dropbox: [
    { key: "access_token", label: "Access Token", type: "password", placeholder: "sl...." },
    { key: "folder_path", label: "Folder Path (可选)", type: "text", placeholder: "/Notes" },
  ],
};

function getCredentialFields(type: string) {
  return CONNECTOR_CREDENTIAL_FIELDS[type] ?? [
    { key: "api_key", label: "API Key", type: "password" as const, placeholder: "••••••••" },
  ];
}

const SCHEDULE_PRESETS = [
  { value: "manual", label: "手动触发", cron: "" },
  { value: "hourly", label: "每小时", cron: "0 * * * *" },
  { value: "every6h", label: "每 6 小时", cron: "0 */6 * * *" },
  { value: "daily", label: "每天", cron: "0 2 * * *" },
  { value: "custom", label: "自定义 Cron", cron: "" },
] as const;

const STATUS_CONFIG: Record<string, { color: string; bg: string; label: string; dotClass: string }> = {
  active:    { color: "text-emerald-400", bg: "bg-emerald-400/10", label: "活跃",   dotClass: "bg-emerald-400 animate-status-breathe" },
  inactive:  { color: "text-zinc-500",    bg: "bg-zinc-500/10",    label: "未激活", dotClass: "bg-zinc-500" },
  error:     { color: "text-red-400",     bg: "bg-red-400/10",     label: "错误",   dotClass: "bg-red-400" },
  paused:    { color: "text-amber-400",   bg: "bg-amber-400/10",   label: "暂停",   dotClass: "bg-amber-400" },
  running:   { color: "text-blue-400",    bg: "bg-blue-400/10",    label: "运行中", dotClass: "bg-blue-400 animate-pulse" },
  completed: { color: "text-emerald-400", bg: "bg-emerald-400/10", label: "已完成", dotClass: "bg-emerald-400" },
  failed:    { color: "text-red-400",     bg: "bg-red-400/10",     label: "失败",   dotClass: "bg-red-400" },
};

function formatDuration(ms: number | null): string {
  if (ms == null) return "--";
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  const mins = Math.floor(ms / 60000);
  const secs = Math.floor((ms % 60000) / 1000);
  return `${mins}m ${secs}s`;
}

function formatCronLabel(cron: string | null): string {
  if (!cron) return "手动";
  const preset = SCHEDULE_PRESETS.find((p) => p.cron === cron);
  if (preset && preset.value !== "custom") return preset.label;
  return cron;
}

function parseJsonSafe(raw: string): string {
  try {
    return JSON.parse(raw);
  } catch {
    return raw;
  }
}

// ── 子组件 ──

function StatusBadge({ status }: { status: string }) {
  const cfg = STATUS_CONFIG[status] ?? STATUS_CONFIG.inactive;
  return (
    <span className={cn("inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-2xs font-medium", cfg.bg, cfg.color)}>
      <span className={cn("w-1.5 h-1.5 rounded-full", cfg.dotClass)} />
      {cfg.label}
    </span>
  );
}

function EmptyState({ icon: Icon, title, description }: { icon: React.ComponentType<{ size?: number; className?: string }>; title: string; description: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-20 text-os-muted">
      <Icon size={40} className="mb-3 opacity-30" />
      <p className="text-sm">{title}</p>
      <p className="text-2xs mt-1">{description}</p>
    </div>
  );
}

// ── 主页面组件 ──

export default function SyncPage() {
  const queryClient = useQueryClient();

  // ── State ──
  const [activeTab, setActiveTab] = useState<TabId>("connectors");
  const [toast, setToast] = useState<{ message: string; type: "success" | "error" } | null>(null);
  const [deleteConfirm, setDeleteConfirm] = useState<{ type: "connector" | "job"; id: string } | null>(null);

  // Connector modal
  const [connectorModal, setConnectorModal] = useState(false);
  const [connectorForm, setConnectorForm] = useState({
    name: "",
    connector_type: "feishu",
    credentials: {} as Record<string, string>,
  });
  const [connectorTypeSearch, setConnectorTypeSearch] = useState("");
  const [connectorTypeOpen, setConnectorTypeOpen] = useState(false);
  const connectorDropdownRef = useRef<HTMLDivElement>(null);

  // Job modal
  const [jobModal, setJobModal] = useState(false);
  const [jobForm, setJobForm] = useState({
    name: "",
    connector_config_id: "",
    rule_type: "full_sync",
    schedule_preset: "manual" as "manual" | "hourly" | "every6h" | "daily" | "custom",
    custom_cron: "",
  });

  // Test connection result
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null);

  // ── Toast auto-dismiss ──
  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 4000);
    return () => clearTimeout(t);
  }, [toast]);

  // ── Close connector type dropdown on outside click ──
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (connectorDropdownRef.current && !connectorDropdownRef.current.contains(e.target as Node)) {
        setConnectorTypeOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  // ── Data fetching ──

  const { data: statsData, isLoading: statsLoading } = useQuery({
    queryKey: ["sync-stats"],
    queryFn: () => api.sync.getStats(),
    refetchInterval: 15000,
  });

  const { data: connectorsData, isLoading: connectorsLoading } = useQuery({
    queryKey: ["sync-connectors"],
    queryFn: () => api.sync.listConnectors(),
    enabled: activeTab === "connectors" || activeTab === "jobs",
  });

  const { data: jobsData, isLoading: jobsLoading } = useQuery({
    queryKey: ["sync-jobs"],
    queryFn: () => api.sync.listJobs(),
    enabled: activeTab === "jobs" || activeTab === "history",
  });

  const { data: historyData, isLoading: historyLoading } = useQuery({
    queryKey: ["sync-history"],
    queryFn: () => api.sync.getHistory({ limit: 50 }),
    enabled: activeTab === "history",
    refetchInterval: 30000,
  });

  const stats = statsData as SyncStatsResponse | undefined;
  const connectors = (connectorsData as { connectors: SyncConnector[] } | undefined)?.connectors ?? [];
  const jobs = (jobsData as { jobs: SyncJob[] } | undefined)?.jobs ?? [];
  const executions = (historyData as { executions: SyncExecution[] } | undefined)?.executions ?? [];

  // ── Derived ──

  const successRate = useMemo(() => {
    const total = (stats?.last_hour_executions ?? 0);
    const failures = (stats?.last_hour_failures ?? 0);
    if (total === 0) return 0;
    return Math.round(((total - failures) / total) * 100);
  }, [stats]);

  const filteredConnectorTypes = useMemo(() => {
    if (!connectorTypeSearch) return CONNECTOR_TYPES.slice();
    const q = connectorTypeSearch.toLowerCase();
    return CONNECTOR_TYPES.filter(
      (t) => t.label.toLowerCase().includes(q) || t.value.toLowerCase().includes(q),
    );
  }, [connectorTypeSearch]);

  // ── Mutations ──

  const refreshAll = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ["sync-stats"] });
    queryClient.invalidateQueries({ queryKey: ["sync-connectors"] });
    queryClient.invalidateQueries({ queryKey: ["sync-jobs"] });
    queryClient.invalidateQueries({ queryKey: ["sync-history"] });
  }, [queryClient]);

  // ── Connector mutations ──

  const createConnectorMutation = useMutation({
    mutationFn: () =>
      api.sync.createConnector({
        name: connectorForm.name,
        connector_type: connectorForm.connector_type,
        credentials: connectorForm.credentials,
      }),
    onSuccess: () => {
      setConnectorModal(false);
      resetConnectorForm();
      setToast({ message: "连接器已创建", type: "success" });
      refreshAll();
    },
    onError: (err: Error) => {
      setToast({ message: err.message || "创建失败", type: "error" });
    },
  });

  const testConnectionMutation = useMutation({
    mutationFn: (connectorId: string) => api.sync.testConnector(connectorId),
    onSuccess: (data: { connector_id: string; success: boolean; message: string }) => {
      setTestResult({ success: data.success, message: data.message });
    },
    onError: (err: Error) => {
      setTestResult({ success: false, message: err.message });
    },
  });

  const deleteConnectorMutation = useMutation({
    mutationFn: (id: string) => api.sync.deleteConnector(id),
    onSuccess: () => {
      setDeleteConfirm(null);
      setToast({ message: "连接器已删除", type: "success" });
      refreshAll();
    },
    onError: (err: Error) => {
      setToast({ message: err.message || "删除失败", type: "error" });
    },
  });

  // ── Job mutations ──

  const createJobMutation = useMutation({
    mutationFn: () =>
      api.sync.createJob({
        connector_config_id: jobForm.connector_config_id,
        name: jobForm.name,
        rule_type: jobForm.rule_type,
        cron_expression:
          jobForm.schedule_preset === "custom"
            ? jobForm.custom_cron
            : jobForm.schedule_preset !== "manual"
              ? SCHEDULE_PRESETS.find((p) => p.value === jobForm.schedule_preset)?.cron ?? ""
              : undefined,
      }),
    onSuccess: () => {
      setJobModal(false);
      resetJobForm();
      setToast({ message: "同步任务已创建", type: "success" });
      refreshAll();
    },
    onError: (err: Error) => {
      setToast({ message: err.message || "创建失败", type: "error" });
    },
  });

  const runJobMutation = useMutation({
    mutationFn: (jobId: string) => api.sync.runJob(jobId),
    onSuccess: () => {
      setToast({ message: "任务已触发", type: "success" });
      refreshAll();
    },
    onError: (err: Error) => {
      setToast({ message: err.message || "触发失败", type: "error" });
    },
  });

  const retryJobMutation = useMutation({
    mutationFn: (jobId: string) => api.sync.retryJob(jobId),
    onSuccess: () => {
      setToast({ message: "已重新提交", type: "success" });
      refreshAll();
    },
    onError: (err: Error) => {
      setToast({ message: err.message || "重试失败", type: "error" });
    },
  });

  const deleteJobMutation = useMutation({
    mutationFn: (jobId: string) => api.sync.deleteJob(jobId),
    onSuccess: () => {
      setDeleteConfirm(null);
      setToast({ message: "任务已删除", type: "success" });
      refreshAll();
    },
    onError: (err: Error) => {
      setToast({ message: err.message || "删除失败", type: "error" });
    },
  });

  // ── Form helpers ──

  function resetConnectorForm() {
    setConnectorForm({ name: "", connector_type: "feishu", credentials: {} });
    setConnectorTypeSearch("");
    setTestResult(null);
  }

  function resetJobForm() {
    setJobForm({
      name: "",
      connector_config_id: "",
      rule_type: "full_sync",
      schedule_preset: "manual",
      custom_cron: "",
    });
  }

  function handleCredentialChange(key: string, value: string) {
    setConnectorForm((prev) => ({
      ...prev,
      credentials: { ...prev.credentials, [key]: value },
    }));
  }

  function openConnectorModal() {
    resetConnectorForm();
    setConnectorModal(true);
  }

  function openJobModal() {
    resetJobForm();
    setJobModal(true);
  }

  // ── Tab config ──

  const TABS: { id: TabId; label: string }[] = [
    { id: "connectors", label: "连接器" },
    { id: "jobs", label: "同步任务" },
    { id: "history", label: "执行历史" },
  ];

  return (
    <PageTransition>
      <div className="p-6 space-y-5 max-w-[1440px] mx-auto">
        {/* ── Toast ── */}
        <AnimatePresence>
          {toast && (
            <motion.div
              initial={{ opacity: 0, y: -16, x: "-50%" }}
              animate={{ opacity: 1, y: 0, x: "-50%" }}
              exit={{ opacity: 0, y: -16, x: "-50%" }}
              className={cn(
                "fixed top-4 left-1/2 z-50 flex items-center gap-2 px-4 py-2.5 rounded-md shadow-lg text-xs",
                toast.type === "success"
                  ? "bg-emerald-600/90 text-white"
                  : "bg-red-600/90 text-white",
              )}
            >
              {toast.type === "success" ? <CheckCircle2 size={14} /> : <AlertTriangle size={14} />}
              {toast.message}
              <button
                onClick={() => setToast(null)}
                className="ml-2 opacity-70 hover:opacity-100 transition-opacity"
              >
                <X size={12} />
              </button>
            </motion.div>
          )}
        </AnimatePresence>

        {/* ── Header ── */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-lg font-semibold text-os-text-high tracking-tight">Sync Hub</h1>
            <p className="text-xs text-os-subtle mt-0.5">
              管理外部数据源连接器与自动同步任务
            </p>
          </div>
          <button
            onClick={refreshAll}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-2xs text-os-muted bg-os-elevated border border-os-border hover:text-os-subtle hover:border-os-muted transition-colors"
          >
            <RefreshCw size={12} />
            刷新
          </button>
        </div>

        {/* ── Stats Bar ── */}
        <div className={layout.grid.fourMd}>
          <StaggerItem delay={0}>
            <div className="os-card p-4">
              <div className="flex items-center gap-2 mb-2">
                <Link size={14} className="text-os-accent" />
                <span className="text-2xs text-os-muted">连接器总数</span>
              </div>
              <p className="text-lg font-semibold text-os-text-high">
                {statsLoading ? "..." : formatNumber(stats?.total_connectors ?? 0)}
              </p>
              <p className="text-2xs text-os-muted mt-0.5">
                {stats?.enabled_connectors ?? 0} 已启用
              </p>
            </div>
          </StaggerItem>
          <StaggerItem delay={0.03}>
            <div className="os-card p-4">
              <div className="flex items-center gap-2 mb-2">
                <RefreshCw size={14} className="text-os-accent" />
                <span className="text-2xs text-os-muted">活跃同步</span>
              </div>
              <p className="text-lg font-semibold text-os-text-high">
                {statsLoading ? "..." : formatNumber(stats?.active_jobs ?? 0)}
              </p>
              <p className="text-2xs text-os-muted mt-0.5">
                {stats?.pending_jobs ?? 0} 等待中
              </p>
            </div>
          </StaggerItem>
          <StaggerItem delay={0.06}>
            <div className="os-card p-4">
              <div className="flex items-center gap-2 mb-2">
                <CheckCircle2 size={14} className="text-os-accent" />
                <span className="text-2xs text-os-muted">成功率 (1h)</span>
              </div>
              <p className="text-lg font-semibold text-os-text-high">
                {statsLoading ? "..." : `${successRate}%`}
              </p>
              <p className="text-2xs text-os-muted mt-0.5">
                {(stats?.last_hour_executions ?? 0) - (stats?.last_hour_failures ?? 0)} 成功 / {stats?.last_hour_failures ?? 0} 失败
              </p>
            </div>
          </StaggerItem>
          <StaggerItem delay={0.09}>
            <div className="os-card p-4">
              <div className="flex items-center gap-2 mb-2">
                <ListOrdered size={14} className="text-os-accent" />
                <span className="text-2xs text-os-muted">队列深度</span>
              </div>
              <p className="text-lg font-semibold text-os-text-high">
                {statsLoading ? "..." : formatNumber(stats?.queue_depth ?? 0)}
              </p>
            </div>
          </StaggerItem>
        </div>

        {/* ── Tabs ── */}
        <StaggerItem delay={0.12}>
          <div className="os-card p-4">
            {/* Tab header */}
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-1">
                {TABS.map((tab) => (
                  <button
                    key={tab.id}
                    onClick={() => setActiveTab(tab.id)}
                    className={cn(
                      "px-3 py-1.5 rounded-md text-xs font-medium transition-colors",
                      activeTab === tab.id
                        ? "bg-os-accent text-white"
                        : "text-os-muted hover:text-os-subtle hover:bg-os-elevated",
                    )}
                  >
                    {tab.label}
                  </button>
                ))}
              </div>
              {activeTab === "connectors" && (
                <button
                  onClick={openConnectorModal}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium bg-os-accent text-white hover:bg-os-accent/90 transition-colors"
                >
                  <Plus size={13} />
                  添加连接器
                </button>
              )}
              {activeTab === "jobs" && (
                <button
                  onClick={openJobModal}
                  disabled={connectors.length === 0}
                  className={cn(
                    "flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors",
                    connectors.length > 0
                      ? "bg-os-accent text-white hover:bg-os-accent/90"
                      : "bg-os-elevated text-os-muted cursor-not-allowed",
                  )}
                >
                  <Plus size={13} />
                  创建任务
                </button>
              )}
            </div>

            {/* ── Connectors Tab ── */}
            {activeTab === "connectors" && (
              <>
                {connectorsLoading ? (
                  <div className={layout.grid.threeLgMd}>
                    {Array.from({ length: 6 }).map((_, i) => (
                      <CardSkeleton key={i} />
                    ))}
                  </div>
                ) : connectors.length === 0 ? (
                  <EmptyState
                    icon={Link}
                    title="暂无连接器"
                    description="点击上方按钮添加你的第一个数据源连接器"
                  />
                ) : (
                  <div className={layout.grid.threeLgMd}>
                    {connectors.map((c) => {
                      const Icon = getConnectorIcon(c.connector_type);
                      const isActive = c.status === "active";
                      return (
                        <motion.div
                          key={c.connector_id}
                          initial={{ opacity: 0, y: 6 }}
                          animate={{ opacity: 1, y: 0 }}
                          className={cn(
                            "group relative p-4 space-y-3 rounded-2xl backdrop-blur-md transition-all duration-300",
                            isActive
                              // 已连接: 边框亮起 + 插拔感
                              ? "border border-os-accent/50 bg-os-surface/40 hover:-translate-y-0.5 hover:shadow-[0_8px_30px_rgba(129,140,248,0.12)]"
                              // 未连接: 虚线 + 暗淡
                              : "border border-dashed border-os-border/50 bg-os-surface/20 hover:border-os-muted/50",
                          )}
                        >
                          {/* 存活指示灯 — 仅 active 时显示 status-breathe */}
                          {isActive && (
                            <div className="absolute top-3 right-3 flex items-center gap-1.5">
                              <div className="relative">
                                <div className="w-2 h-2 rounded-full bg-emerald-400" />
                                <div className="absolute inset-0 w-2 h-2 rounded-full bg-emerald-400 animate-status-breathe" />
                              </div>
                              <span className="text-2xs font-medium text-emerald-400">LIVE</span>
                            </div>
                          )}

                          {/* Header */}
                          <div className="flex items-start gap-2.5">
                            <div className={cn(
                              "w-9 h-9 rounded-lg flex items-center justify-center border transition-colors",
                              isActive
                                ? "bg-os-accent/10 border-os-accent/30 text-os-accent"
                                : "bg-os-elevated border-os-border text-os-muted",
                            )}>
                              <Icon size={16} />
                            </div>
                            <div className="min-w-0 flex-1">
                              <p className="text-xs font-medium text-os-text-high truncate max-w-[140px]">
                                {c.name}
                              </p>
                              <span className="text-2xs text-os-muted">
                                {getConnectorLabel(c.connector_type)}
                              </span>
                            </div>
                          </div>

                          {/* Last sync */}
                          <div className="flex items-center gap-1.5 text-2xs text-os-muted">
                            <Clock size={10} />
                            <span>
                              {c.last_sync_at ? `上次同步: ${formatDate(c.last_sync_at)}` : "尚未同步"}
                            </span>
                          </div>

                          {/* Actions */}
                          <div className="flex items-center gap-1 pt-2 border-t border-os-border/50">
                            <button
                              onClick={() => {
                                testConnectionMutation.mutate(c.connector_id);
                                setTestResult(null);
                                setTimeout(() => {
                                  const result = testConnectionMutation.data;
                                  if (result) {
                                    setToast({
                                      message: result.success ? "连接测试成功" : `连接测试失败: ${result.message}`,
                                      type: result.success ? "success" : "error",
                                    });
                                  }
                                }, 100);
                              }}
                              disabled={testConnectionMutation.isPending}
                              className="flex items-center gap-1 px-2 py-1 rounded text-2xs text-os-muted hover:text-os-accent hover:bg-os-accent/10 transition-colors disabled:opacity-50"
                            >
                              <TestTube size={11} />
                              测试
                            </button>
                            <button className="flex items-center gap-1 px-2 py-1 rounded text-2xs text-os-muted hover:text-os-subtle hover:bg-os-elevated transition-colors">
                              <Settings2 size={11} />
                              编辑
                            </button>
                            <button
                              onClick={() => setDeleteConfirm({ type: "connector", id: c.connector_id })}
                              className="flex items-center gap-1 px-2 py-1 rounded text-2xs text-os-muted hover:text-red-400 hover:bg-red-400/10 transition-colors ml-auto"
                            >
                              <Trash2 size={11} />
                              卸载
                            </button>
                          </div>
                        </motion.div>
                      );
                    })}
                  </div>
                )}
              </>
            )}

            {/* ── Jobs Tab ── */}
            {activeTab === "jobs" && (
              <>
                {jobsLoading ? (
                  <div className="space-y-2">
                    {Array.from({ length: 4 }).map((_, i) => (
                      <CardSkeleton key={i} />
                    ))}
                  </div>
                ) : jobs.length === 0 ? (
                  <EmptyState
                    icon={RefreshCw}
                    title="暂无同步任务"
                    description={connectors.length === 0 ? "请先创建一个连接器" : "创建第一个同步任务开始自动同步"}
                  />
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs" role="table">
                      <thead>
                        <tr className="border-b border-os-border">
                          <th className="text-left py-2.5 px-3 text-2xs text-os-muted font-medium uppercase tracking-wider">任务名称</th>
                          <th className="text-left py-2.5 px-3 text-2xs text-os-muted font-medium uppercase tracking-wider hidden sm:table-cell">连接器</th>
                          <th className="text-left py-2.5 px-3 text-2xs text-os-muted font-medium uppercase tracking-wider hidden md:table-cell">调度</th>
                          <th className="text-left py-2.5 px-3 text-2xs text-os-muted font-medium uppercase tracking-wider">状态</th>
                          <th className="text-left py-2.5 px-3 text-2xs text-os-muted font-medium uppercase tracking-wider hidden lg:table-cell">上次运行</th>
                          <th className="text-right py-2.5 px-3 text-2xs text-os-muted font-medium uppercase tracking-wider">操作</th>
                        </tr>
                      </thead>
                      <tbody>
                        {jobs.map((job) => {
                          const jobConnector = connectors.find((c) => c.connector_id === job.connector_config_id);
                          const ConnIcon = getConnectorIcon(jobConnector?.connector_type ?? "");
                          return (
                            <tr
                              key={job.job_id}
                              className="border-b border-os-border/50 hover:bg-os-elevated/50 transition-colors"
                            >
                              <td className="py-2.5 px-3">
                                <span className="text-os-text-high font-medium truncate max-w-[160px] block">
                                  {job.name}
                                </span>
                              </td>
                              <td className="py-2.5 px-3 hidden sm:table-cell">
                                <span className="inline-flex items-center gap-1 text-os-muted">
                                  <ConnIcon size={12} />
                                  {jobConnector?.name ?? getConnectorLabel(jobConnector?.connector_type ?? "")}
                                </span>
                              </td>
                              <td className="py-2.5 px-3 hidden md:table-cell">
                                <span className="text-os-muted font-mono text-2xs">
                                  {formatCronLabel(job.cron_expression)}
                                </span>
                              </td>
                              <td className="py-2.5 px-3">
                                <StatusBadge status={job.status} />
                              </td>
                              <td className="py-2.5 px-3 hidden lg:table-cell">
                                <span className="text-os-muted">
                                  {job.last_run_at ? formatDate(job.last_run_at) : "--"}
                                </span>
                              </td>
                              <td className="py-2.5 px-3 text-right">
                                <div className="flex items-center justify-end gap-1">
                                  <button
                                    onClick={() => runJobMutation.mutate(job.job_id)}
                                    disabled={runJobMutation.isPending}
                                    className="p-1.5 rounded hover:bg-os-elevated transition-colors text-os-muted hover:text-emerald-400"
                                    title="立即运行"
                                    aria-label={`运行 ${job.name}`}
                                  >
                                    <Play size={13} />
                                  </button>
                                  {job.status === "error" && (
                                    <button
                                      onClick={() => retryJobMutation.mutate(job.job_id)}
                                      disabled={retryJobMutation.isPending}
                                      className="p-1.5 rounded hover:bg-os-elevated transition-colors text-os-muted hover:text-amber-400"
                                      title="重试"
                                      aria-label={`重试 ${job.name}`}
                                    >
                                      <RotateCcw size={13} />
                                    </button>
                                  )}
                                  <button
                                    onClick={() => setDeleteConfirm({ type: "job", id: job.job_id })}
                                    className="p-1.5 rounded hover:bg-os-elevated transition-colors text-os-muted hover:text-red-400"
                                    title="删除"
                                    aria-label={`删除 ${job.name}`}
                                  >
                                    <Trash2 size={13} />
                                  </button>
                                </div>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                )}
              </>
            )}

            {/* ── History Tab ── */}
            {activeTab === "history" && (
              <>
                {historyLoading ? (
                  <div className="space-y-2">
                    {Array.from({ length: 5 }).map((_, i) => (
                      <CardSkeleton key={i} />
                    ))}
                  </div>
                ) : executions.length === 0 ? (
                  <EmptyState
                    icon={BarChart3}
                    title="暂无执行记录"
                    description="运行同步任务后，执行历史将显示在这里"
                  />
                ) : (
                  <div className="space-y-2">
                    {executions.map((ex) => {
                      const job = jobs.find((j) => j.job_id === ex.job_id);
                      const displayName = ex.job_name ?? job?.name ?? ex.execution_id;
                      const itemsChanged = (ex.items_new ?? 0) + (ex.items_updated ?? 0) + (ex.items_deleted ?? 0);
                      return (
                        <motion.div
                          key={ex.execution_id}
                          initial={{ opacity: 0, y: 4 }}
                          animate={{ opacity: 1, y: 0 }}
                          className="os-card p-3 space-y-2 os-card-hover"
                        >
                          <div className="flex items-center justify-between">
                            <div className="flex items-center gap-2 min-w-0">
                              <span className="text-xs font-medium text-os-text-high truncate max-w-[200px]">
                                {displayName}
                              </span>
                              <StatusBadge status={ex.status} />
                            </div>
                            <span className="text-2xs text-os-muted shrink-0">
                              {formatDuration(ex.duration_ms)}
                            </span>
                          </div>

                          <div className="flex items-center gap-4 text-2xs text-os-muted">
                            {ex.items_new != null && (
                              <span className="flex items-center gap-1">
                                <span className="text-emerald-400">+{ex.items_new}</span> 新增
                              </span>
                            )}
                            {ex.items_updated != null && (
                              <span className="flex items-center gap-1">
                                <span className="text-amber-400">~{ex.items_updated}</span> 更新
                              </span>
                            )}
                            {ex.items_deleted != null && (
                              <span className="flex items-center gap-1">
                                <span className="text-red-400">-{ex.items_deleted}</span> 删除
                              </span>
                            )}
                            {itemsChanged === 0 && (
                              <span className="text-os-muted">无变更</span>
                            )}
                            <span className="ml-auto">{formatDate(ex.started_at)}</span>
                          </div>

                          {ex.error && (
                            <div className="flex items-start gap-1.5 p-2 rounded-md bg-red-400/5 border border-red-400/10">
                              <AlertTriangle size={11} className="text-red-400 mt-0.5 shrink-0" />
                              <span className="text-2xs text-red-300 break-all">
                                {parseJsonSafe(ex.error)}
                              </span>
                            </div>
                          )}
                        </motion.div>
                      );
                    })}
                  </div>
                )}

                {/* ── 赛博管线状态指示 + 终端日志面板 ── */}
                {(stats?.active_jobs ?? 0) > 0 && (
                  <div className="mt-4 space-y-3">
                    {/* 管线状态条 */}
                    <div className="flex items-center gap-3 rounded-lg border border-os-accent-cyan/30 bg-os-accent-cyan/5 p-3">
                      <div className="relative">
                        <div className="w-2.5 h-2.5 rounded-full bg-os-accent-cyan animate-pulse" />
                        <div className="absolute inset-0 w-2.5 h-2.5 rounded-full bg-os-accent-cyan blur-[6px] animate-pulse" />
                      </div>
                      <div className="flex-1">
                        <p className="text-xs font-medium text-os-accent-cyan">
                          同步管线运行中 · {stats?.active_jobs ?? 0} 个活跃任务
                        </p>
                        <p className="text-2xs text-os-muted">
                          队列深度: {stats?.queue_depth ?? 0} · 过去 1h 执行: {stats?.last_hour_executions ?? 0} 次
                        </p>
                      </div>
                      {/* 流光连接线 */}
                      <div className="hidden sm:flex items-center gap-1">
                        {[0, 1, 2, 3, 4].map((i) => (
                          <motion.div
                            key={i}
                            className="w-1.5 h-1.5 rounded-full bg-os-accent-cyan"
                            animate={{ opacity: [0.3, 1, 0.3] }}
                            transition={{
                              duration: 1.2,
                              repeat: Infinity,
                              delay: i * 0.15,
                              ease: "easeInOut",
                            }}
                          />
                        ))}
                      </div>
                    </div>

                    {/* 终端日志面板 */}
                    <div className="rounded-xl border border-os-border/50 bg-slate-50 overflow-hidden">
                      <div className="flex items-center justify-between px-3 py-2 border-b border-os-border/30">
                        <div className="flex items-center gap-1.5">
                          <Terminal size={11} className="text-os-success" />
                          <span className="font-mono text-2xs text-os-muted">sync-pipeline.log</span>
                        </div>
                        <div className="flex items-center gap-1">
                          <div className="w-2 h-2 rounded-full bg-red-500/60" />
                          <div className="w-2 h-2 rounded-full bg-amber-500/60" />
                          <div className="w-2 h-2 rounded-full bg-emerald-500/60" />
                        </div>
                      </div>
                      <div className="h-48 overflow-y-auto p-4 font-mono text-xs text-os-success space-y-0.5">
                        {executions.slice(0, 8).map((ex, i) => {
                          const ts = new Date(ex.started_at).toLocaleTimeString("en-US", { hour12: false });
                          const job = jobs.find((j) => j.job_id === ex.job_id);
                          const name = ex.job_name ?? job?.name ?? ex.execution_id;
                          const itemsTotal = (ex.items_new ?? 0) + (ex.items_updated ?? 0) + (ex.items_deleted ?? 0);
                          return (
                            <div key={ex.execution_id} className="leading-5">
                              <span className="text-os-muted">[{ts}]</span>{" "}
                              <span className={cn(
                                ex.status === "completed" && "text-os-success",
                                ex.status === "running" && "text-os-accent-cyan",
                                ex.status === "failed" && "text-red-400",
                              )}>
                                {ex.status === "completed"
                                  ? `> [OK] "${name}" synced — +${ex.items_new ?? 0} new / ~${ex.items_updated ?? 0} upd / -${ex.items_deleted ?? 0} del (${formatDuration(ex.duration_ms)})`
                                  : ex.status === "running"
                                    ? `> [..] "${name}" fetching items... (${itemsTotal} changes so far)`
                                    : `> [ERR] "${name}" failed: ${parseJsonSafe(ex.error ?? "unknown")}`}
                              </span>
                            </div>
                          );
                        })}
                        {executions.length === 0 && (
                          <div className="leading-5 text-os-muted">
                            <span>$</span> 等待同步任务执行...
                          </div>
                        )}
                        <div className="leading-5">
                          <span className="text-os-muted">$</span>{" "}
                          <span className="inline-block w-1.5 h-3.5 bg-os-success animate-pulse align-middle" />
                        </div>
                      </div>
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        </StaggerItem>

        {/* ── Connector Modal ── */}
        <AnimatePresence>
          {connectorModal && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="fixed inset-0 z-50 flex items-start justify-center pt-[10vh] bg-slate-950/20 backdrop-blur-sm overflow-y-auto"
              onClick={() => setConnectorModal(false)}
            >
              <motion.div
                initial={{ opacity: 0, scale: 0.95, y: 10 }}
                animate={{ opacity: 1, scale: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.95, y: 10 }}
                transition={{ duration: 0.15 }}
                onClick={(e) => e.stopPropagation()}
                className="os-card p-6 max-w-lg w-full mx-4 my-8"
                role="dialog"
                aria-label="添加连接器"
              >
                <div className="flex items-center justify-between mb-5">
                  <h2 className="text-sm font-semibold text-os-text-high">添加连接器</h2>
                  <button
                    onClick={() => setConnectorModal(false)}
                    className="p-1 rounded hover:bg-os-elevated transition-colors text-os-muted hover:text-os-text-high"
                  >
                    <X size={16} />
                  </button>
                </div>

                <div className="space-y-4">
                  {/* Connector name */}
                  <div>
                    <label className="block text-2xs text-os-muted mb-1.5">连接器名称</label>
                    <input
                      value={connectorForm.name}
                      onChange={(e) => setConnectorForm((p) => ({ ...p, name: e.target.value }))}
                      placeholder="例如：我的飞书文档"
                      className="w-full h-9 px-3 bg-os-elevated border border-os-border rounded-md text-xs text-os-text-high placeholder:text-os-muted focus:outline-none focus:border-os-accent transition-colors"
                    />
                  </div>

                  {/* Connector type picker */}
                  <div ref={connectorDropdownRef}>
                    <label className="block text-2xs text-os-muted mb-1.5">连接器类型</label>
                    <div className="relative">
                      <button
                        type="button"
                        onClick={() => setConnectorTypeOpen((v) => !v)}
                        className="w-full h-9 px-3 bg-os-elevated border border-os-border rounded-md text-xs text-os-text-high flex items-center justify-between focus:outline-none focus:border-os-accent transition-colors"
                      >
                        <span className="flex items-center gap-2">
                          {(() => {
                            const sel = CONNECTOR_TYPES.find((t) => t.value === connectorForm.connector_type);
                            const Icon = sel?.icon ?? Link;
                            return <Icon size={14} className="text-os-accent" />;
                          })()}
                          {getConnectorLabel(connectorForm.connector_type)}
                        </span>
                        {connectorTypeOpen ? <ChevronUp size={14} className="text-os-muted" /> : <ChevronDown size={14} className="text-os-muted" />}
                      </button>

                      <AnimatePresence>
                        {connectorTypeOpen && (
                          <motion.div
                            initial={{ opacity: 0, y: -4 }}
                            animate={{ opacity: 1, y: 0 }}
                            exit={{ opacity: 0, y: -4 }}
                            transition={{ duration: 0.12 }}
                            className="absolute z-10 mt-1 w-full bg-os-elevated border border-os-border rounded-md shadow-os-lg overflow-hidden"
                          >
                            {/* Search */}
                            <div className="p-2 border-b border-os-border">
                              <div className="relative">
                                <Search size={12} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-os-muted" />
                                <input
                                  value={connectorTypeSearch}
                                  onChange={(e) => setConnectorTypeSearch(e.target.value)}
                                  placeholder="搜索类型..."
                                  className="w-full h-8 pl-7 pr-3 bg-os-surface border border-os-border rounded text-2xs text-os-text-high placeholder:text-os-muted focus:outline-none focus:border-os-accent"
                                  autoFocus
                                />
                              </div>
                            </div>
                            {/* List */}
                            <div className="max-h-48 overflow-y-auto p-1">
                              {filteredConnectorTypes.length === 0 ? (
                                <p className="text-2xs text-os-muted text-center py-4">无匹配结果</p>
                              ) : (
                                filteredConnectorTypes.map((t) => {
                                  const Icon = t.icon;
                                  const isSelected = connectorForm.connector_type === t.value;
                                  return (
                                    <button
                                      key={t.value}
                                      type="button"
                                      onClick={() => {
                                        setConnectorForm((p) => ({ ...p, connector_type: t.value, credentials: {} }));
                                        setConnectorTypeOpen(false);
                                        setConnectorTypeSearch("");
                                        setTestResult(null);
                                      }}
                                      className={cn(
                                        "w-full flex items-center gap-2 px-2.5 py-1.5 rounded text-xs transition-colors text-left",
                                        isSelected
                                          ? "bg-os-accent/10 text-os-accent"
                                          : "text-os-text-high hover:bg-os-surface",
                                      )}
                                    >
                                      <Icon size={14} className={isSelected ? "text-os-accent" : "text-os-muted"} />
                                      {t.label}
                                      <span className="text-2xs text-os-muted ml-auto">{t.value}</span>
                                    </button>
                                  );
                                })
                              )}
                            </div>
                          </motion.div>
                        )}
                      </AnimatePresence>
                    </div>
                  </div>

                  {/* Dynamic credential fields */}
                  <div>
                    <label className="block text-2xs text-os-muted mb-1.5">凭据信息</label>
                    <div className="space-y-2">
                      {getCredentialFields(connectorForm.connector_type).map((field) => (
                        <div key={field.key}>
                          <label className="block text-2xs text-os-muted mb-1">{field.label}</label>
                          <input
                            type={field.type}
                            value={connectorForm.credentials[field.key] ?? ""}
                            onChange={(e) => handleCredentialChange(field.key, e.target.value)}
                            placeholder={field.placeholder}
                            className="w-full h-9 px-3 bg-os-elevated border border-os-border rounded-md text-xs text-os-text-high placeholder:text-os-muted focus:outline-none focus:border-os-accent transition-colors"
                          />
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Test result */}
                  {testResult && (
                    <div
                      className={cn(
                        "flex items-start gap-2 p-3 rounded-md text-xs border",
                        testResult.success
                          ? "bg-emerald-400/5 border-emerald-400/10 text-emerald-300"
                          : "bg-red-400/5 border-red-400/10 text-red-300",
                      )}
                    >
                      {testResult.success ? <CheckCircle2 size={14} className="mt-0.5 shrink-0" /> : <AlertTriangle size={14} className="mt-0.5 shrink-0" />}
                      {testResult.message}
                    </div>
                  )}

                  {/* Actions */}
                  <div className="flex justify-end gap-2 pt-2 border-t border-os-border">
                    <button
                      onClick={() => setConnectorModal(false)}
                      className="px-4 py-2 rounded-md text-xs text-os-subtle bg-os-elevated border border-os-border hover:text-os-text-high transition-colors"
                    >
                      取消
                    </button>
                    <button
                      onClick={() => createConnectorMutation.mutate()}
                      disabled={!connectorForm.name.trim() || createConnectorMutation.isPending}
                      className="px-4 py-2 rounded-md text-xs font-medium text-white bg-os-accent hover:bg-os-accent/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center gap-1.5"
                    >
                      {createConnectorMutation.isPending ? (
                        <>
                          <Loader2 size={12} className="animate-spin" />
                          创建中...
                        </>
                      ) : (
                        <>
                          <Plus size={12} />
                          创建连接器
                        </>
                      )}
                    </button>
                  </div>
                </div>
              </motion.div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* ── Job Modal ── */}
        <AnimatePresence>
          {jobModal && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="fixed inset-0 z-50 flex items-start justify-center pt-[10vh] bg-slate-950/20 backdrop-blur-sm overflow-y-auto"
              onClick={() => setJobModal(false)}
            >
              <motion.div
                initial={{ opacity: 0, scale: 0.95, y: 10 }}
                animate={{ opacity: 1, scale: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.95, y: 10 }}
                transition={{ duration: 0.15 }}
                onClick={(e) => e.stopPropagation()}
                className="os-card p-6 max-w-lg w-full mx-4 my-8"
                role="dialog"
                aria-label="创建同步任务"
              >
                <div className="flex items-center justify-between mb-5">
                  <h2 className="text-sm font-semibold text-os-text-high">创建同步任务</h2>
                  <button
                    onClick={() => setJobModal(false)}
                    className="p-1 rounded hover:bg-os-elevated transition-colors text-os-muted hover:text-os-text-high"
                  >
                    <X size={16} />
                  </button>
                </div>

                <div className="space-y-4">
                  {/* Job name */}
                  <div>
                    <label className="block text-2xs text-os-muted mb-1.5">任务名称</label>
                    <input
                      value={jobForm.name}
                      onChange={(e) => setJobForm((p) => ({ ...p, name: e.target.value }))}
                      placeholder="例如：每日飞书同步"
                      className="w-full h-9 px-3 bg-os-elevated border border-os-border rounded-md text-xs text-os-text-high placeholder:text-os-muted focus:outline-none focus:border-os-accent transition-colors"
                    />
                  </div>

                  {/* Connector selection */}
                  <div>
                    <label className="block text-2xs text-os-muted mb-1.5">关联连接器</label>
                    <select
                      value={jobForm.connector_config_id}
                      onChange={(e) => setJobForm((p) => ({ ...p, connector_config_id: e.target.value }))}
                      className="w-full h-9 px-3 bg-os-elevated border border-os-border rounded-md text-xs text-os-text-high focus:outline-none focus:border-os-accent transition-colors appearance-none"
                    >
                      <option value="" disabled>选择连接器...</option>
                      {connectors.map((c) => {
                        const Icon = getConnectorIcon(c.connector_type);
                        return (
                          <option key={c.connector_id} value={c.connector_id}>
                            {c.name} ({getConnectorLabel(c.connector_type)})
                          </option>
                        );
                      })}
                    </select>
                  </div>

                  {/* Rule type */}
                  <div>
                    <label className="block text-2xs text-os-muted mb-1.5">同步规则</label>
                    <select
                      value={jobForm.rule_type}
                      onChange={(e) => setJobForm((p) => ({ ...p, rule_type: e.target.value }))}
                      className="w-full h-9 px-3 bg-os-elevated border border-os-border rounded-md text-xs text-os-text-high focus:outline-none focus:border-os-accent transition-colors appearance-none"
                    >
                      <option value="full_sync">全量同步</option>
                      <option value="incremental">增量同步</option>
                      <option value="changes_only">仅变更</option>
                    </select>
                  </div>

                  {/* Schedule picker */}
                  <div>
                    <label className="block text-2xs text-os-muted mb-1.5">调度策略</label>
                    <div className="grid grid-cols-2 gap-2 mb-2">
                      {SCHEDULE_PRESETS.map((preset) => (
                        <button
                          key={preset.value}
                          type="button"
                          onClick={() => setJobForm((p) => ({ ...p, schedule_preset: preset.value as typeof jobForm.schedule_preset }))}
                          className={cn(
                            "px-3 py-2 rounded-md text-xs text-left border transition-colors",
                            jobForm.schedule_preset === preset.value
                              ? "border-os-accent bg-os-accent/10 text-os-accent"
                              : "border-os-border bg-os-elevated text-os-muted hover:text-os-subtle hover:border-os-muted",
                          )}
                        >
                          {preset.label}
                        </button>
                      ))}
                    </div>

                    {/* Custom cron input */}
                    {jobForm.schedule_preset === "custom" && (
                      <motion.div
                        initial={{ opacity: 0, height: 0 }}
                        animate={{ opacity: 1, height: "auto" }}
                        exit={{ opacity: 0, height: 0 }}
                      >
                        <label className="block text-2xs text-os-muted mb-1">Cron 表达式</label>
                        <input
                          value={jobForm.custom_cron}
                          onChange={(e) => setJobForm((p) => ({ ...p, custom_cron: e.target.value }))}
                          placeholder="0 2 * * *"
                          className="w-full h-9 px-3 bg-os-elevated border border-os-border rounded-md text-xs font-mono text-os-text-high placeholder:text-os-muted focus:outline-none focus:border-os-accent transition-colors"
                        />
                        <p className="text-2xs text-os-muted mt-1">
                          格式: 分 时 日 月 周 (例如 "0 2 * * *" = 每天凌晨 2 点)
                        </p>
                      </motion.div>
                    )}
                  </div>

                  {/* Actions */}
                  <div className="flex justify-end gap-2 pt-2 border-t border-os-border">
                    <button
                      onClick={() => setJobModal(false)}
                      className="px-4 py-2 rounded-md text-xs text-os-subtle bg-os-elevated border border-os-border hover:text-os-text-high transition-colors"
                    >
                      取消
                    </button>
                    <button
                      onClick={() => createJobMutation.mutate()}
                      disabled={
                        !jobForm.name.trim() ||
                        !jobForm.connector_config_id ||
                        (jobForm.schedule_preset === "custom" && !jobForm.custom_cron.trim()) ||
                        createJobMutation.isPending
                      }
                      className="px-4 py-2 rounded-md text-xs font-medium text-white bg-os-accent hover:bg-os-accent/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center gap-1.5"
                    >
                      {createJobMutation.isPending ? (
                        <>
                          <Loader2 size={12} className="animate-spin" />
                          创建中...
                        </>
                      ) : (
                        <>
                          <Plus size={12} />
                          创建任务
                        </>
                      )}
                    </button>
                  </div>
                </div>
              </motion.div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* ── Delete Confirmation Modal ── */}
        <AnimatePresence>
          {deleteConfirm && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/20 backdrop-blur-sm"
              onClick={() => setDeleteConfirm(null)}
            >
              <motion.div
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.95 }}
                transition={{ duration: 0.15 }}
                onClick={(e) => e.stopPropagation()}
                className="os-card p-6 max-w-sm w-full mx-4"
                role="alertdialog"
                aria-label="确认删除"
              >
                <div className="flex items-center gap-3 mb-4">
                  <div className="w-9 h-9 rounded-full bg-red-400/10 flex items-center justify-center">
                    <AlertTriangle size={18} className="text-red-400" />
                  </div>
                  <div>
                    <h3 className="text-sm font-semibold text-os-text-high">确认删除</h3>
                    <p className="text-2xs text-os-muted mt-0.5">
                      此操作不可撤销，确定要删除这个{deleteConfirm.type === "connector" ? "连接器" : "同步任务"}吗？
                    </p>
                  </div>
                </div>
                <div className="flex justify-end gap-2">
                  <button
                    onClick={() => setDeleteConfirm(null)}
                    className="px-4 py-2 rounded-md text-xs text-os-subtle bg-os-elevated border border-os-border hover:text-os-text-high transition-colors"
                  >
                    取消
                  </button>
                  <button
                    onClick={() => {
                      if (deleteConfirm.type === "connector") {
                        deleteConnectorMutation.mutate(deleteConfirm.id);
                      } else {
                        deleteJobMutation.mutate(deleteConfirm.id);
                      }
                    }}
                    disabled={deleteConnectorMutation.isPending || deleteJobMutation.isPending}
                    className="px-4 py-2 rounded-md text-xs font-medium text-white bg-red-500 hover:bg-red-600 disabled:opacity-50 transition-colors flex items-center gap-1.5"
                  >
                    {(deleteConnectorMutation.isPending || deleteJobMutation.isPending) ? (
                      <>
                        <Loader2 size={12} className="animate-spin" />
                        删除中...
                      </>
                    ) : (
                      <>
                        <Trash2 size={12} />
                        删除
                      </>
                    )}
                  </button>
                </div>
              </motion.div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </PageTransition>
  );
}
