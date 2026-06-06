// ── Sync Hub Type Definitions ──

// ── Connector ──

export interface SyncConnector {
  id: string;
  name: string;
  connector_type: string;
  enabled: boolean;
  last_sync_time: string | null;
  last_sync_status: string; // "never" | "success" | "failed"
  created_at: string;
  updated_at: string;
}

// ── Job ──

export interface SyncJob {
  id: string;
  connector_config_id: string;
  name: string;
  status: string; // "pending" | "running" | "completed" | "failed" | "cancelled"
  enabled: boolean;
  rule_type: string; // "manual" | "cron" | "realtime"
  cron_expression: string;
  created_at: string;
}

// ── Execution ──

export interface SyncExecution {
  id: string;
  job_id: string;
  status: string; // "pending" | "running" | "completed" | "failed" | "partial"
  started_at: string | null;
  completed_at: string | null;
  items_new: number;
  items_updated: number;
  items_deleted: number;
  items_renamed: number;
  memories_created: number;
  errors_count: number;
  error: string | null;
  elapsed_ms: number;
}

// ── Stats ──

export interface ConnectorSummary {
  id: string;
  name: string;
  connector_type: string;
  enabled: boolean;
  last_sync_time: string | null;
  last_sync_status: string;
  job_count: number;
  last_execution_status: string | null;
}

export interface SyncStats {
  total_connectors: number;
  enabled_connectors: number;
  active_jobs: number;
  pending_jobs: number;
  last_hour_executions: number;
  last_hour_failures: number;
  queue_depth: number;
  connectors: ConnectorSummary[];
}

// ── Connector Type Labels ──

export interface ConnectorTypeLabel {
  label: string;
  icon: string;
  description: string;
}

export const CONNECTOR_TYPE_LABELS: Record<string, ConnectorTypeLabel> = {
  notion: {
    label: "Notion",
    icon: "book-open",
    description: "Sync Notion pages and databases into your knowledge base.",
  },
  obsidian: {
    label: "Obsidian",
    icon: "gem",
    description: "Sync Obsidian vault markdown notes bidirectionally.",
  },
  logseq: {
    label: "Logseq",
    icon: "git-branch",
    description: "Sync Logseq graph pages and journal entries.",
  },
  feishu: {
    label: "Feishu / Lark",
    icon: "message-square",
    description: "Sync Feishu documents, sheets, and Bitable records.",
  },
  yuque: {
    label: "Yuque",
    icon: "book",
    description: "Sync Yuque (语雀) documents and knowledge base articles.",
  },
  github: {
    label: "GitHub",
    icon: "github",
    description: "Sync GitHub repositories, README files, and wikis.",
  },
  gdrive: {
    label: "Google Drive",
    icon: "hard-drive",
    description: "Sync Google Drive documents, sheets, and slides.",
  },
  dropbox: {
    label: "Dropbox",
    icon: "cloud",
    description: "Sync files and folders from your Dropbox account.",
  },
  onedrive: {
    label: "OneDrive",
    icon: "cloud-sun",
    description: "Sync files and folders from Microsoft OneDrive.",
  },
  local_folder: {
    label: "Local Folder",
    icon: "folder",
    description: "Watch a local folder and sync files as they change.",
  },
  rss: {
    label: "RSS / Atom",
    icon: "rss",
    description: "Subscribe to RSS/Atom feeds and ingest articles automatically.",
  },
  wechat_mp: {
    label: "WeChat MP",
    icon: "message-circle",
    description: "Sync articles from subscribed WeChat Official Accounts (公众号).",
  },
  weixin_reader: {
    label: "Weixin Reader",
    icon: "bookmark",
    description: "Sync highlights, notes, and reading list from Weixin Reader (微信读书).",
  },
  bilibili: {
    label: "Bilibili",
    icon: "play-circle",
    description: "Sync video metadata, transcripts, and favorites from Bilibili.",
  },
  custom: {
    label: "Custom",
    icon: "puzzle",
    description: "Bring your own connector via plugin or custom API adapter.",
  },
};

// ── Cron Presets ──

export interface CronPreset {
  label: string;
  expression: string;
}

export const CRON_PRESETS: CronPreset[] = [
  { label: "Every 5 minutes", expression: "*/5 * * * *" },
  { label: "Every 15 minutes", expression: "*/15 * * * *" },
  { label: "Every 30 minutes", expression: "*/30 * * * *" },
  { label: "Every hour", expression: "0 * * * *" },
  { label: "Every 2 hours", expression: "0 */2 * * *" },
  { label: "Every 6 hours", expression: "0 */6 * * *" },
  { label: "Every 12 hours", expression: "0 */12 * * *" },
  { label: "Daily at midnight", expression: "0 0 * * *" },
  { label: "Daily at 6 AM", expression: "0 6 * * *" },
  { label: "Daily at 9 AM", expression: "0 9 * * *" },
  { label: "Weekdays at 8 AM", expression: "0 8 * * 1-5" },
  { label: "Weekends at 10 AM", expression: "0 10 * * 6,7" },
  { label: "Every Monday at 7 AM", expression: "0 7 * * 1" },
  { label: "Every 1st of month at midnight", expression: "0 0 1 * *" },
  { label: "Manual only", expression: "" },
];
