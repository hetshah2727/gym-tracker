"use client";

import { useState } from "react";
import { HBars } from "@/components/charts/Charts";
import { FeatureGate, Kpi, percent } from "@/components/shared/growth";
import { Card, EmptyState, ErrorNote, Loading, PageHeader, Select } from "@/components/shared/ui";
import { useApi } from "@/hooks/useApi";
import { formatCurrency } from "@/lib/utils";

interface LA {
  total_enquiries: number; new: number; contacted: number; uncontacted_now: number; overdue_follow_ups: number; qualified: number;
  trials_booked: number; joined: number; lost: number; conversion_rate: number; avg_first_response_minutes: number | null;
  by_status: Record<string, number>; by_staff: Record<string, { assigned: number; contacted: number; joined: number }>;
  by_source: Record<string, { leads: number; joined: number; revenue_collected: number; conversion_rate: number }>;
  lost_reasons: Record<string, number>;
}
const FUNNEL = ["new", "contacted", "interested", "trial_booked", "trial_attended", "negotiation", "converted", "lost"];

export default function SalesAnalyticsPage() {
  const [days, setDays] = useState("30");
  const { data: a, loading, error } = useApi<LA>("/crm/analytics", { days });
  return (
    <FeatureGate feature="lead_crm">
      <PageHeader title="Sales analytics" description="Calculated from your lead records - nothing is estimated."
        actions={<Select className="w-36" value={days} onChange={(e) => setDays(e.target.value)} options={[{ value: "7", label: "7 days" }, { value: "30", label: "30 days" }, { value: "90", label: "90 days" }, { value: "365", label: "12 months" }]} />} />
      {error && <ErrorNote message={error} />}
      {loading || !a ? <Loading /> : (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Kpi label="Total enquiries" value={a.total_enquiries} />
            <Kpi label="Uncontacted (now)" value={a.uncontacted_now} tone={a.uncontacted_now ? "warning" : undefined} href="/dashboard/leads?status=uncontacted" />
            <Kpi label="Overdue follow-ups" value={a.overdue_follow_ups} tone={a.overdue_follow_ups ? "danger" : undefined} href="/dashboard/follow-ups?due=overdue" />
            <Kpi label="Avg first response" value={a.avg_first_response_minutes != null ? `${Math.round(a.avg_first_response_minutes)} min` : "—"} />
            <Kpi label="Qualified" value={a.qualified} hint="Score ≥ 50 or interested+" />
            <Kpi label="Trials booked" value={a.trials_booked} />
            <Kpi label="Joined" value={a.joined} tone="brand" />
            <Kpi label="Conversion rate" value={percent(a.conversion_rate)} hint={`${a.lost} lost`} />
          </div>
          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            <Card title="Leads by stage (this period)">
              <div className="p-4"><HBars data={FUNNEL.map((s) => ({ label: s === "converted" ? "Joined" : s.replace(/_/g, " "), value: a.by_status[s] ?? 0 }))} valueLabel="Leads" /></div>
            </Card>
            <Card title="Lost reasons">
              <div className="p-4">{Object.keys(a.lost_reasons).length ? <HBars data={Object.entries(a.lost_reasons).map(([k, v]) => ({ label: k, value: v }))} valueLabel="Leads" /> : <EmptyState title="No lost leads with reasons" />}</div>
            </Card>
          </div>
          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            <Card title="Source conversion">
              <table className="table-base"><thead><tr><th>Source</th><th>Leads</th><th>Joined</th><th>Rate</th><th>Collected</th></tr></thead>
                <tbody>{Object.entries(a.by_source).sort((x, y) => y[1].leads - x[1].leads).map(([k, r]) => <tr key={k}><td>{k.replace(/_/g, " ")}</td><td>{r.leads}</td><td>{r.joined}</td><td>{percent(r.conversion_rate)}</td><td className="tabular-nums">{formatCurrency(r.revenue_collected)}</td></tr>)}</tbody></table>
            </Card>
            <Card title="Staff performance">
              <table className="table-base"><thead><tr><th>Staff</th><th>Assigned</th><th>Contacted</th><th>Joined</th></tr></thead>
                <tbody>{Object.entries(a.by_staff).map(([k, r]) => <tr key={k}><td>{k}</td><td>{r.assigned}</td><td>{r.contacted}</td><td>{r.joined}</td></tr>)}</tbody></table>
            </Card>
          </div>
        </>
      )}
    </FeatureGate>
  );
}
