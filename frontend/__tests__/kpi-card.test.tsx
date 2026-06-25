import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { DollarSign } from "lucide-react";
import { KpiCard } from "@/components/dashboard-v2/kpi-card";

describe("KpiCard", () => {
  it("renders label and value", () => {
    render(<KpiCard icon={DollarSign} label="MRR" value="¥123.45" />);
    expect(screen.getByText("MRR")).toBeInTheDocument();
    expect(screen.getByText("¥123.45")).toBeInTheDocument();
  });

  it("renders sub text when provided", () => {
    render(<KpiCard icon={DollarSign} label="ARPU" value="¥10.00" sub="单用户" />);
    expect(screen.getByText("单用户")).toBeInTheDocument();
  });

  it("renders positive change with + sign", () => {
    render(<KpiCard icon={DollarSign} label="DAU" value="1.2K" change={12} />);
    expect(screen.getByText("+12%")).toBeInTheDocument();
  });

  it("renders negative change without + sign", () => {
    render(<KpiCard icon={DollarSign} label="Churn" value="5%" change={-3} />);
    expect(screen.getByText("-3%")).toBeInTheDocument();
  });

  it("does not render change block when change undefined", () => {
    render(<KpiCard icon={DollarSign} label="X" value="1" />);
    expect(screen.queryByText(/%/)).not.toBeInTheDocument();
  });
});
