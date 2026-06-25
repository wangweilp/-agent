import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { QueryState, EmptyState, ErrorState } from "@/components/dashboard-v2/query-state";

describe("EmptyState", () => {
  it("renders default message", () => {
    render(<EmptyState />);
    expect(screen.getByText("暂无数据")).toBeInTheDocument();
  });

  it("renders custom message", () => {
    render(<EmptyState message="无趋势数据" />);
    expect(screen.getByText("无趋势数据")).toBeInTheDocument();
  });
});

describe("ErrorState", () => {
  it("renders error message", () => {
    render(<ErrorState message="加载失败" />);
    expect(screen.getByText("加载失败")).toBeInTheDocument();
  });

  it("renders retry button and triggers handler", () => {
    const onRetry = vi.fn();
    render(<ErrorState message="err" onRetry={onRetry} />);
    const btn = screen.getByText("重试");
    fireEvent.click(btn);
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("hides retry button when no handler", () => {
    render(<ErrorState message="err" />);
    expect(screen.queryByText("重试")).not.toBeInTheDocument();
  });
});

describe("QueryState", () => {
  it("renders skeleton when loading (default)", () => {
    const { container } = render(<QueryState isLoading isError={false}><div>content</div></QueryState>);
    expect(screen.queryByText("content")).not.toBeInTheDocument();
    // 默认 CardSkeleton 渲染出骨架 div
    expect(container.querySelector(".shimmer-bg")).toBeInTheDocument();
  });

  it("renders custom skeleton when provided", () => {
    const { container } = render(
      <QueryState isLoading isError={false} skeleton={<div data-testid="sk">loading</div>}>
        <div>content</div>
      </QueryState>,
    );
    expect(screen.getByTestId("sk")).toBeInTheDocument();
    expect(container.querySelector(".shimmer-bg")).not.toBeInTheDocument();
  });

  it("renders error state with retry", () => {
    const onRetry = vi.fn();
    render(
      <QueryState isLoading={false} isError errorText="boom" onRetry={onRetry}>
        <div>content</div>
      </QueryState>,
    );
    expect(screen.getByText("boom")).toBeInTheDocument();
    fireEvent.click(screen.getByText("重试"));
    expect(onRetry).toHaveBeenCalled();
  });

  it("renders empty state when isEmpty", () => {
    render(
      <QueryState isLoading={false} isError={false} isEmpty emptyText="无内容">
        <div>content</div>
      </QueryState>,
    );
    expect(screen.getByText("无内容")).toBeInTheDocument();
    expect(screen.queryByText("content")).not.toBeInTheDocument();
  });

  it("renders children on happy path", () => {
    render(
      <QueryState isLoading={false} isError={false}>
        <div>happy</div>
      </QueryState>,
    );
    expect(screen.getByText("happy")).toBeInTheDocument();
  });
});
