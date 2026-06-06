"use client";

import { useState, useEffect, useCallback } from "react";
import {
  Plus,
  Trash2,
  Bell,
  BellOff,
  Play,
  CheckCircle,
  AlertTriangle,
  Info,
  XCircle,
} from "lucide-react";
import { api } from "@/services/api";
import type { AlertRule, AlertEvent } from "@/types";

const METRIC_LABELS: Record<string, string> = {
  memory_usage_pct: "内存使用率",
  queue_depth: "队列深度",
  dlq_backlog: "DLQ 积压",
  api_latency: "API 延迟",
  cost_spike: "成本异常",
  anomaly_calls: "异常调用",
  hourly_event_count: "小时事件数",
  daily_cost_cents: "日成本",
};

const SEVERITY_STYLES: Record<string, string> = {
  info: "bg-blue-400/10 text-blue-400 border-blue-400/20",
  warning: "bg-amber-400/10 text-amber-400 border-amber-400/20",
  critical: "bg-red-400/10 text-red-400 border-red-400/20",
};

const SEVERITY_ICONS: Record<string, React.ReactNode> = {
  info: <Info className="h-4 w-4" />,
  warning: <AlertTriangle className="h-4 w-4" />,
  critical: <XCircle className="h-4 w-4" />,
};

export default function AlertsPage() {
  const [rules, setRules] = useState<AlertRule[]>([]);
  const [events, setEvents] = useState<AlertEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({
    name: "",
    metric: "queue_depth",
    threshold: 100,
    severity: "warning",
    channel: "system",
    cooldown_minutes: 60,
  });

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [r, e] = await Promise.all([
        api.alerts.listRules(),
        api.alerts.listEvents({ limit: 50 }),
      ]);
      setRules(r);
      setEvents(e);
    } catch (err) {
      console.error("Failed to fetch alerts:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleCreate = async () => {
    try {
      await api.alerts.createRule(form);
      setShowCreate(false);
      setForm({ name: "", metric: "queue_depth", threshold: 100, severity: "warning", channel: "system", cooldown_minutes: 60 });
      fetchData();
    } catch (err) {
      console.error("Failed to create rule:", err);
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm("确认删除此告警规则？")) return;
    try {
      await api.alerts.deleteRule(id);
      fetchData();
    } catch (err) {
      console.error("Failed to delete rule:", err);
    }
  };

  const handleToggle = async (rule: AlertRule) => {
    try {
      await api.alerts.updateRule(rule.id, { enabled: !rule.enabled });
      fetchData();
    } catch (err) {
      console.error("Failed to toggle rule:", err);
    }
  };

  const handleAcknowledge = async (eventId: string) => {
    try {
      await api.alerts.acknowledgeEvent(eventId);
      fetchData();
    } catch (err) {
      console.error("Failed to acknowledge:", err);
    }
  };

  const handleTest = async (channel: string) => {
    try {
      await api.alerts.testAlert(channel);
      fetchData();
    } catch (err) {
      console.error("Test alert failed:", err);
    }
  };

  return (
    <div className="space-y-6 p-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">告警管理</h1>
          <p className="text-sm text-muted-foreground">
            配置阈值告警规则，监控系统健康状态
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => api.alerts.seedPresets().then(fetchData)}
            className="rounded-lg border px-3 py-1.5 text-sm hover:bg-accent"
          >
            初始化预设规则
          </button>
          <button
            onClick={() => setShowCreate(true)}
            className="flex items-center gap-1.5 rounded-lg bg-primary px-3 py-1.5 text-sm text-primary-foreground hover:bg-primary/90"
          >
            <Plus className="h-3.5 w-3.5" />
            创建规则
          </button>
        </div>
      </div>

      {/* Alert Rules */}
      <div className="rounded-xl border bg-card shadow-sm">
        <div className="border-b px-4 py-3">
          <h2 className="text-sm font-semibold">告警规则 ({rules.length})</h2>
        </div>
        <div className="divide-y">
          {rules.length === 0 && (
            <div className="p-8 text-center text-sm text-muted-foreground">
              暂无告警规则，点击「初始化预设规则」快速创建
            </div>
          )}
          {rules.map((rule) => (
            <div key={rule.id} className="flex items-center justify-between px-4 py-3">
              <div className="flex items-center gap-3">
                <span
                  className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium ${SEVERITY_STYLES[rule.severity]}`}
                >
                  {SEVERITY_ICONS[rule.severity]}
                  {rule.severity.toUpperCase()}
                </span>
                <div>
                  <p className="text-sm font-medium">{rule.name}</p>
                  <p className="text-xs text-muted-foreground">
                    {METRIC_LABELS[rule.metric] || rule.metric} {rule.condition} {rule.threshold}
                    {" · "}冷却 {rule.cooldown_minutes} 分钟
                    {" · "}通知: {rule.channel}
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => handleTest(rule.channel)}
                  className="rounded p-1 text-muted-foreground hover:bg-accent hover:text-foreground"
                  title="测试告警"
                >
                  <Play className="h-3.5 w-3.5" />
                </button>
                <button
                  onClick={() => handleToggle(rule)}
                  className={`rounded p-1 hover:bg-accent ${rule.enabled ? "text-green-500" : "text-muted-foreground"}`}
                  title={rule.enabled ? "禁用" : "启用"}
                >
                  {rule.enabled ? <Bell className="h-3.5 w-3.5" /> : <BellOff className="h-3.5 w-3.5" />}
                </button>
                <button
                  onClick={() => handleDelete(rule.id)}
                  className="rounded p-1 text-muted-foreground hover:bg-red-500/10 hover:text-red-500"
                  title="删除"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Alert History */}
      <div className="rounded-xl border bg-card shadow-sm">
        <div className="border-b px-4 py-3">
          <h2 className="text-sm font-semibold">告警历史 ({events.length})</h2>
        </div>
        <div className="divide-y">
          {events.length === 0 && (
            <div className="p-8 text-center text-sm text-muted-foreground">
              暂无告警历史
            </div>
          )}
          {events.map((event) => (
            <div key={event.id} className="flex items-center justify-between px-4 py-3">
              <div className="flex items-center gap-3">
                <span
                  className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium ${SEVERITY_STYLES[event.severity]}`}
                >
                  {SEVERITY_ICONS[event.severity]}
                </span>
                <div>
                  <p className="text-sm">{event.message}</p>
                  <p className="text-xs text-muted-foreground">
                    {event.rule_name} · {event.metric} · {new Date(event.triggered_at).toLocaleString("zh-CN")}
                    {event.acknowledged && <span className="ml-2 text-green-500">✓ 已确认</span>}
                  </p>
                </div>
              </div>
              {!event.acknowledged && (
                <button
                  onClick={() => handleAcknowledge(event.id)}
                  className="flex items-center gap-1 rounded-lg border px-2 py-1 text-xs text-green-500 hover:bg-green-500/10"
                >
                  <CheckCircle className="h-3 w-3" />
                  确认
                </button>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Create Rule Modal */}
      {showCreate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="w-full max-w-md rounded-xl bg-background p-6 shadow-xl border">
            <h3 className="text-lg font-bold mb-4">创建告警规则</h3>
            <div className="space-y-3">
              <div>
                <label className="text-xs font-medium">规则名称</label>
                <input
                  className="mt-1 w-full rounded-lg border px-3 py-2 text-sm bg-background"
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  placeholder="如: memory-limit"
                />
              </div>
              <div>
                <label className="text-xs font-medium">监控指标</label>
                <select
                  className="mt-1 w-full rounded-lg border px-3 py-2 text-sm bg-background"
                  value={form.metric}
                  onChange={(e) => setForm({ ...form, metric: e.target.value })}
                >
                  {Object.entries(METRIC_LABELS).map(([k, v]) => (
                    <option key={k} value={k}>{v}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="text-xs font-medium">阈值</label>
                <input
                  type="number"
                  className="mt-1 w-full rounded-lg border px-3 py-2 text-sm bg-background"
                  value={form.threshold}
                  onChange={(e) => setForm({ ...form, threshold: Number(e.target.value) })}
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs font-medium">严重度</label>
                  <select
                    className="mt-1 w-full rounded-lg border px-3 py-2 text-sm bg-background"
                    value={form.severity}
                    onChange={(e) => setForm({ ...form, severity: e.target.value })}
                  >
                    <option value="info">Info</option>
                    <option value="warning">Warning</option>
                    <option value="critical">Critical</option>
                  </select>
                </div>
                <div>
                  <label className="text-xs font-medium">通知渠道</label>
                  <select
                    className="mt-1 w-full rounded-lg border px-3 py-2 text-sm bg-background"
                    value={form.channel}
                    onChange={(e) => setForm({ ...form, channel: e.target.value })}
                  >
                    <option value="system">系统通知</option>
                    <option value="email">邮件</option>
                    <option value="both">两者</option>
                  </select>
                </div>
              </div>
              <div>
                <label className="text-xs font-medium">冷却时间 (分钟)</label>
                <input
                  type="number"
                  className="mt-1 w-full rounded-lg border px-3 py-2 text-sm bg-background"
                  value={form.cooldown_minutes}
                  onChange={(e) => setForm({ ...form, cooldown_minutes: Number(e.target.value) })}
                />
              </div>
            </div>
            <div className="mt-6 flex justify-end gap-2">
              <button
                onClick={() => setShowCreate(false)}
                className="rounded-lg border px-4 py-2 text-sm hover:bg-accent"
              >
                取消
              </button>
              <button
                onClick={handleCreate}
                disabled={!form.name}
                className="rounded-lg bg-primary px-4 py-2 text-sm text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
              >
                创建
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
