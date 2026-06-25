import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import DashboardV2Page from "@/app/dashboard-v2/page";

// ── Mock API ──
vi.mock("@/services/api", () => ({
  api: {
    dashboardV2: {
      overview: vi.fn().mockResolvedValue({
        mrr_cents: 10000,
        arr_cents: 120000,
        arpu_cents: 500,
        gross_margin_pct: 80,
        dau: 100,
        wau: 500,
        mau: 2000,
        retention_d1: 40,
        retention_d7: 25,
        agent_success_rate: 95,
        p95_latency_ms: 320,
        token_cost_today_cents: 1234,
        total_memories: 5000,
        memory_hit_rate: 88,
        net_growth_today: 12,
      }),
      growth: vi.fn().mockResolvedValue({
        dau_series: [{ date: "2026-06-01", value: 10 }],
        wau_series: [],
        mau_series: [],
        retention_cohort: [],
        funnel: [],
        activation_rate: 60,
      }),
      agentPerformance: vi.fn().mockResolvedValue({
        call_volume_series: [],
        success_rate: 95,
        failure_rate: 5,
        latency: { p50_ms: 100, p95_ms: 320, p99_ms: 800 },
        token_usage_series: [],
        token_cost_cents: 5000,
      }),
      memoryHealth: vi.fn().mockResolvedValue({
        growth_series: [],
        hit_rate: 88,
        total_memories: 5000,
        active_memories: 4000,
        net_growth: 12,
        type_distribution: [],
      }),
    },
    alerts: {
      listRules: vi.fn().mockResolvedValue([]),
      listEvents: vi.fn().mockResolvedValue([]),
    },
  },
}));

function renderWithQuery(ui: React.ReactElement) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0, gcTime: 0 } },
  });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

describe("DashboardV2Page", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders the page header", () => {
    renderWithQuery(<DashboardV2Page />);
    expect(screen.getByText("Observability Console")).toBeInTheDocument();
  });

  it("renders all 6 tab buttons", () => {
    renderWithQuery(<DashboardV2Page />);
    const labels = ["Overview", "Growth", "Agent Performance", "Memory Health", "Cost Analytics", "Alerts"];
    for (const label of labels) {
      expect(screen.getByRole("button", { name: label })).toBeInTheDocument();
    }
  });

  it("defaults to Overview tab and loads overview KPIs", async () => {
    renderWithQuery(<DashboardV2Page />);
    // Overview 加载完成后出现 KPI 分组标题
    expect(await screen.findByText("商业指标")).toBeInTheDocument();
    expect(screen.getByText("MRR")).toBeInTheDocument();
  });

  it("switches to Growth tab on click and shows growth content", async () => {
    renderWithQuery(<DashboardV2Page />);
    fireEvent.click(screen.getByRole("button", { name: "Growth" }));
    expect(await screen.findByText("激活率")).toBeInTheDocument();
  });

  it("lazy-mounts Alerts tab only after click", async () => {
    renderWithQuery(<DashboardV2Page />);
    // 初始未访问 Alerts，不应渲染其内容
    expect(screen.queryByText("告警规则 (0)")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Alerts" }));
    expect(await screen.findByText(/告警规则/)).toBeInTheDocument();
  });

  it("preserves Overview state after switching tabs (hidden, not unmounted)", async () => {
    renderWithQuery(<DashboardV2Page />);
    expect(await screen.findByText("商业指标")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Growth" }));
    // Overview 内容仍存在于 DOM（仅 hidden）
    expect(screen.getByText("商业指标")).toBeInTheDocument();
  });
});
