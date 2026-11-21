"use client";

import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { formatCurrency } from "@/lib/utils";

const axis = { fill: "rgb(var(--muted))", fontSize: 12 };
const tooltipStyle = { background: "rgb(var(--surface))", border: "1px solid rgb(var(--border))", borderRadius: 8, fontSize: 12, color: "rgb(var(--fg))" };

function monthLabel(key: string) {
  const [y, m] = key.split("-").map(Number);
  return new Date(y, m - 1, 1).toLocaleDateString("en-IN", { month: "short" });
}

const short = (v: number) => (v >= 100000 ? `${(v / 100000).toFixed(1)}L` : v >= 1000 ? `${Math.round(v / 1000)}k` : String(v));

/** Collected vs recovered revenue per month (recovered is part of collected). */
export function RevenueBars({ data, height = 260 }: { data: { month: string; collected: number; recovered: number }[]; height?: number }) {
  return (
    <div style={{ height }} className="w-full" role="img" aria-label="Monthly collected and recovered revenue">
      <ResponsiveContainer>
        <BarChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }} barGap={2}>
          <CartesianGrid vertical={false} stroke="rgb(var(--border))" strokeDasharray="3 3" />
          <XAxis dataKey="month" tickFormatter={monthLabel} tick={axis} axisLine={false} tickLine={false} />
          <YAxis tickFormatter={short} tick={axis} axisLine={false} tickLine={false} width={44} />
          <Tooltip cursor={{ fill: "rgb(var(--surface-2))" }} contentStyle={tooltipStyle} labelFormatter={(l) => monthLabel(String(l))}
            formatter={(v: number, name: string) => [formatCurrency(v), name === "collected" ? "Collected" : "Recovered (part of collected)"]} />
          <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 12, color: "rgb(var(--muted))" }}
            formatter={(v) => (v === "collected" ? "Collected" : "Recovered")} />
          <Bar dataKey="collected" fill="rgb(var(--chart-1))" radius={[4, 4, 0, 0]} maxBarSize={28} />
          <Bar dataKey="recovered" fill="rgb(var(--chart-2))" radius={[4, 4, 0, 0]} maxBarSize={28} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

/** Single-series horizontal bars (sources, stages). The title names the series, so no legend. */
export function HBars({ data, height, valueLabel = "Count", money }: { data: { label: string; value: number }[]; height?: number; valueLabel?: string; money?: boolean }) {
  const h = height ?? Math.max(120, data.length * 34 + 24);
  return (
    <div style={{ height: h }} className="w-full" role="img" aria-label={valueLabel}>
      <ResponsiveContainer>
        <BarChart data={data} layout="vertical" margin={{ top: 4, right: 24, left: 8, bottom: 4 }}>
          <CartesianGrid horizontal={false} stroke="rgb(var(--border))" strokeDasharray="3 3" />
          <XAxis type="number" tick={axis} axisLine={false} tickLine={false} allowDecimals={false} tickFormatter={money ? short : undefined} />
          <YAxis type="category" dataKey="label" tick={axis} axisLine={false} tickLine={false} width={130} />
          <Tooltip cursor={{ fill: "rgb(var(--surface-2))" }} contentStyle={tooltipStyle}
            formatter={(v: number) => [money ? formatCurrency(v) : v, valueLabel]} />
          <Bar dataKey="value" fill="rgb(var(--chart-1))" radius={[0, 4, 4, 0]} maxBarSize={18} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
