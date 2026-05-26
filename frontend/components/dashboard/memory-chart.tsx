"use client";

import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";

const data = [
  { day: "周一", episodic: 12, semantic: 5, reflect: 2 },
  { day: "周二", episodic: 18, semantic: 8, reflect: 3 },
  { day: "周三", episodic: 22, semantic: 11, reflect: 4 },
  { day: "周四", episodic: 28, semantic: 15, reflect: 5 },
  { day: "周五", episodic: 35, semantic: 20, reflect: 7 },
  { day: "周六", episodic: 41, semantic: 24, reflect: 8 },
  { day: "周日", episodic: 48, semantic: 28, reflect: 10 },
];

export function MemoryChart() {
  return (
    <div className="h-48">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 0, right: 0, left: -20, bottom: 0 }}>
          <defs>
            <linearGradient id="episodicGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#818CF8" stopOpacity={0.2} />
              <stop offset="100%" stopColor="#818CF8" stopOpacity={0} />
            </linearGradient>
            <linearGradient id="semanticGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#34D399" stopOpacity={0.15} />
              <stop offset="100%" stopColor="#34D399" stopOpacity={0} />
            </linearGradient>
          </defs>
          <XAxis dataKey="day" tick={{ fontSize: 10, fill: "#52525B" }} axisLine={false} tickLine={false} />
          <YAxis tick={{ fontSize: 10, fill: "#52525B" }} axisLine={false} tickLine={false} />
          <Tooltip
            contentStyle={{
              background: "#18181B",
              border: "1px solid #27272A",
              borderRadius: "8px",
              fontSize: "12px",
              color: "#E4E4E7",
            }}
          />
          <Area type="monotone" dataKey="episodic" stroke="#818CF8" strokeWidth={1.5} fill="url(#episodicGrad)" />
          <Area type="monotone" dataKey="semantic" stroke="#34D399" strokeWidth={1.5} fill="url(#semanticGrad)" />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
