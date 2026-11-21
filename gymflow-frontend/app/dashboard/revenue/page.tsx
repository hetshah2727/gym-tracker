"use client";

import { useState } from "react";
import { HBars, RevenueBars } from "@/components/charts/Charts";
import { FeatureGate, Kpi, Note, percent } from "@/components/shared/growth";
import { Card, EmptyState, Loading, PageHeader, Select } from "@/components/shared/ui";
import { useApi } from "@/hooks/useApi";
import { formatCurrency, humanize } from "@/lib/utils";

interface Rev {
  summary: { collected: number; payments_collected: number; recovered: number; outstanding: number; overdue: number; potential: number; potential_by_type: Record<string, number>; forecast_next_30_days: number; forecast_basis: { unpaid_due_next_30_days: number; open_renewal_value: number; historical_renewal_rate: { rate: number | null; note: string } }; definitions: Record<string, string> };
  series: { month: string; collected: number; recovered: number }[];
  by_lead_source: Record<string, number>;
}

export default function RevenuePage() {
  const [days, setDays] = useState("");
  const { data, loading } = useApi<Rev>("/growth/revenue", { days, months: 12 });
  return (
    <FeatureGate feature="basic_reports">
      <PageHeader title="Reports" description="Money collected, brought back by reminders, still unpaid – and what's likely next month."
        actions={<Select className="w-40" value={days} onChange={(e) => setDays(e.target.value)} options={[{ value: "", label: "This month" }, { value: "30", label: "Last 30 days" }, { value: "90", label: "Last 90 days" }, { value: "365", label: "Last 12 months" }]} />} />
      {loading || !data ? <Loading /> : (() => {
        const s = data.summary;
        return <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
            <Kpi label="Collected" value={formatCurrency(s.collected)} hint={`${s.payments_collected} paid payments`} tone="brand" />
            <Kpi label="Brought back by GymFlow" value={formatCurrency(s.recovered)} hint="Included in collected" />
            <Kpi label="Unpaid fees" value={formatCurrency(s.outstanding)} hint={`${formatCurrency(s.overdue)} late`} tone={s.outstanding ? "danger" : undefined} />
            <Kpi label="Could still collect" value={formatCurrency(s.potential)} hint="If everyone renews and pays" />
            <Kpi label="Likely next 30 days" value={formatCurrency(s.forecast_next_30_days)} hint={`Renewal rate ${percent(s.forecast_basis.historical_renewal_rate.rate)}`} />
          </div>
          <Card title="Monthly revenue (12 months)" className="mt-4"><div className="p-4"><RevenueBars data={data.series} height={300} /></div></Card>
          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            <Card title="Money from members, by where they first heard of you"><div className="p-4">{Object.keys(data.by_lead_source).length ? <HBars money data={Object.entries(data.by_lead_source).filter(([, v]) => v > 0).map(([k, v]) => ({ label: humanize(k), value: v }))} valueLabel="Collected" /> : <EmptyState title="No paying members from enquiries yet" />}</div></Card>
            <Card title="Still to collect, by type"><div className="p-4">{Object.keys(s.potential_by_type).length ? <HBars money data={Object.entries(s.potential_by_type).map(([k, v]) => ({ label: humanize(k), value: v }))} valueLabel="Potential" /> : <EmptyState title="Nothing left to collect" />}</div></Card>
          </div>
          <Note className="mt-4 text-xs">{Object.entries(s.definitions).map(([k, v]) => <span key={k} className="block"><strong className="text-fg">{humanize(k)}:</strong> {v}</span>)}<span className="block">Forecast basis: {formatCurrency(s.forecast_basis.unpaid_due_next_30_days)} unpaid due + {formatCurrency(s.forecast_basis.open_renewal_value)} open renewals × {percent(s.forecast_basis.historical_renewal_rate.rate)} ({s.forecast_basis.historical_renewal_rate.note}).</span></Note>
        </>;
      })()}
    </FeatureGate>
  );
}
