import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { SeriesChart } from "@/components/dashboard-v2/series-chart";
import type { MetricPoint } from "@/types/dashboard-v2";

const data: MetricPoint[] = [
  { date: "2026-06-01", value: 10 },
  { date: "2026-06-02", value: 20 },
];

describe("SeriesChart", () => {
  it("renders loading skeleton when loading", () => {
    const { container } = render(
      <SeriesChart data={undefined} isLoading isError={false} />,
    );
    expect(container.querySelector(".shimmer-bg")).toBeInTheDocument();
  });

  it("renders error state when isError", () => {
    render(<SeriesChart data={undefined} isLoading={false} isError />);
    expect(screen.getByText("加载失败")).toBeInTheDocument();
  });

  it("renders empty state when data is empty array", () => {
    render(<SeriesChart data={[]} isLoading={false} isError={false} emptyText="无趋势" />);
    expect(screen.getByText("无趋势")).toBeInTheDocument();
  });

  it("renders without crashing when data is present", () => {
    const { container } = render(<SeriesChart data={data} isLoading={false} isError={false} />);
    // 数据存在时不应显示骨架/空态
    expect(container.querySelector(".shimmer-bg")).not.toBeInTheDocument();
    expect(screen.queryByText(/暂无/)).not.toBeInTheDocument();
  });
});
