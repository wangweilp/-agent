"use client";

import { useState, useEffect, useCallback } from "react";
import { Download, FileText, Trash2, RefreshCw, FileJson, FileSpreadsheet } from "lucide-react";
import { api } from "@/services/api";
import type { Report } from "@/types";

const TYPE_LABELS: Record<string, string> = {
  weekly: "周报",
  monthly: "月报",
  quarterly: "季报",
};

const STATUS_STYLES: Record<string, string> = {
  generating: "bg-amber-400/10 text-amber-400 border-amber-400/20",
  ready: "bg-emerald-400/10 text-emerald-400 border-emerald-400/20",
  failed: "bg-red-400/10 text-red-400 border-red-400/20",
};

const STATUS_LABELS: Record<string, string> = {
  generating: "生成中",
  ready: "就绪",
  failed: "失败",
};

export default function ReportsPage() {
  const [reports, setReports] = useState<Report[]>([]);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [reportType, setReportType] = useState("monthly");
  const [reportFormat, setReportFormat] = useState("json");

  const fetchReports = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api.reports.list(undefined, 50);
      setReports(r);
    } catch (err) {
      console.error("Failed to fetch reports:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchReports();
  }, [fetchReports]);

  const handleGenerate = async () => {
    setGenerating(true);
    try {
      await api.reports.generate({
        report_type: reportType,
        format: reportFormat,
      });
      fetchReports();
    } catch (err) {
      console.error("Failed to generate report:", err);
    } finally {
      setGenerating(false);
    }
  };

  const handleExport = async (report: Report) => {
    try {
      const blob = await api.reports.exportReport(report.id, report.format);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${report.report_type}_${report.period_start}_${report.period_end}.${report.format}`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error("Export failed:", err);
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm("确认删除此报告？")) return;
    try {
      await api.reports.delete(id);
      fetchReports();
    } catch (err) {
      console.error("Failed to delete report:", err);
    }
  };

  return (
    <div className="space-y-6 p-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">报告中心</h1>
          <p className="text-sm text-muted-foreground">
            自动生成并导出运营分析报告
          </p>
        </div>
      </div>

      {/* Generate Card */}
      <div className="rounded-xl border bg-card p-6 shadow-sm">
        <h2 className="text-sm font-semibold mb-4">生成新报告</h2>
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <label className="text-xs font-medium">报告类型</label>
            <select
              className="mt-1 rounded-lg border px-3 py-2 text-sm bg-background block"
              value={reportType}
              onChange={(e) => setReportType(e.target.value)}
            >
              <option value="weekly">周报 (周)</option>
              <option value="monthly">月报 (月)</option>
              <option value="quarterly">季报 (季)</option>
            </select>
          </div>
          <div>
            <label className="text-xs font-medium">导出格式</label>
            <select
              className="mt-1 rounded-lg border px-3 py-2 text-sm bg-background block"
              value={reportFormat}
              onChange={(e) => setReportFormat(e.target.value)}
            >
              <option value="json">JSON</option>
              <option value="csv">CSV</option>
            </select>
          </div>
          <button
            onClick={handleGenerate}
            disabled={generating}
            className="flex items-center gap-1.5 rounded-lg bg-primary px-4 py-2 text-sm text-primary-foreground hover:bg-primary/90 disabled:opacity-50 h-[38px]"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${generating ? "animate-spin" : ""}`} />
            {generating ? "生成中..." : "生成报告"}
          </button>
        </div>
      </div>

      {/* Report List */}
      <div className="rounded-xl border bg-card shadow-sm">
        <div className="border-b px-4 py-3 flex items-center justify-between">
          <h2 className="text-sm font-semibold">报告列表 ({reports.length})</h2>
        </div>
        <div className="divide-y">
          {reports.length === 0 && (
            <div className="p-8 text-center text-sm text-muted-foreground">
              暂无报告，点击「生成报告」创建
            </div>
          )}
          {reports.map((report) => (
            <div key={report.id} className="flex items-center justify-between px-4 py-3">
              <div className="flex items-center gap-3">
                <FileText className="h-5 w-5 text-muted-foreground" />
                <div>
                  <p className="text-sm font-medium">
                    {TYPE_LABELS[report.report_type] || report.report_type}
                    {" · "}
                    {report.period_start} ~ {report.period_end}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    <span
                      className={`inline-flex rounded-full border px-1.5 py-0.5 text-xs ${STATUS_STYLES[report.status]}`}
                    >
                      {STATUS_LABELS[report.status] || report.status}
                    </span>
                    <span className="ml-2">
                      {report.format.toUpperCase()} · {new Date(report.created_at).toLocaleString("zh-CN")}
                    </span>
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                {report.status === "ready" && (
                  <button
                    onClick={() => handleExport(report)}
                    className="flex items-center gap-1 rounded-lg border px-2 py-1 text-xs hover:bg-accent"
                    title={`导出 ${report.format.toUpperCase()}`}
                  >
                    {report.format === "csv" ? (
                      <FileSpreadsheet className="h-3.5 w-3.5" />
                    ) : (
                      <FileJson className="h-3.5 w-3.5" />
                    )}
                    <Download className="h-3.5 w-3.5" />
                    下载
                  </button>
                )}
                <button
                  onClick={() => handleDelete(report.id)}
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
    </div>
  );
}
