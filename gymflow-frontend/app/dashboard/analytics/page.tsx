"use client";

import { Printer } from "lucide-react";
import { useState } from "react";
import { RevenueChart } from "@/components/dashboard/RevenueChart";
import { Button, Card, ErrorNote, Input, Loading, PageHeader, Select, Tabs } from "@/components/shared/ui";
import { useApi } from "@/hooks/useApi";
import { formatCurrency, formatDate, todayISO } from "@/lib/utils";
import type { PeriodReport } from "@/types";

type View = "daily" | "monthly";

const ROWS: { key: keyof PeriodReport; label: string; money?: boolean }[] = [
  { key: "revenue_collected", label: "Revenue collected", money: true },
  { key: "payments_collected", label: "Payments collected" },
  { key: "pending_amount", label: "Pending fees (all time)", money: true },
  { key: "pending_count", label: "Unpaid fee records" },
  { key: "new_members", label: "New members" },
  { key: "active_members", label: "Active members (now)" },
  { key: "memberships_expired", label: "Memberships expired" },
  { key: "memberships_expiring_next_7_days", label: "Expiring in the following 7 days" },
  { key: "checkins", label: "Check-ins" },
  { key: "new_leads", label: "Website leads" },
];

export default function AnalyticsPage() {
  const [view, setView] = useState<View>("monthly");
  const [day, setDay] = useState(todayISO());
  const [month, setMonth] = useState(todayISO().slice(0, 7));
  const [months, setMonths] = useState("12");
  const [year, mon] = month.split("-").map(Number);
  const report = useApi<PeriodReport>(
    view === "daily" ? "/analytics/reports/daily" : "/analytics/reports/monthly",
    view === "daily" ? { on: day } : { year, month: mon },
  );
  const revenue = useApi<{ month: string; revenue: number }[]>("/analytics/revenue", { months });

  return (
    <>
      <PageHeader title="Reports" description="Daily and monthly business reports." actions={<Button variant="secondary" onClick={() => window.print()}><Printer className="h-4 w-4" /> Print</Button>} />

      <Card title="Revenue trend" className="mb-6" actions={<Select className="w-auto py-1" value={months} onChange={(e) => setMonths(e.target.value)} options={[{ value: "6", label: "6 months" }, { value: "12", label: "12 months" }, { value: "24", label: "24 months" }]} />}>
        <div className="p-4">{revenue.data ? <RevenueChart data={revenue.data} height={260} /> : <Loading />}</div>
      </Card>

      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <Tabs<View> value={view} onChange={setView} tabs={[{ value: "daily", label: "Daily report" }, { value: "monthly", label: "Monthly report" }]} />
        {view === "daily" ? (
          <Input type="date" className="sm:w-44" value={day} onChange={(e) => setDay(e.target.value)} />
        ) : (
          <Input type="month" className="sm:w-44" value={month} onChange={(e) => setMonth(e.target.value)} />
        )}
      </div>

      <Card title={report.data ? `${formatDate(report.data.period_start)}${report.data.period_end !== report.data.period_start ? ` – ${formatDate(report.data.period_end)}` : ""}` : "Report"}>
        {report.error && <div className="p-4"><ErrorNote message={report.error} /></div>}
        {!report.data ? (
          <Loading />
        ) : (
          <dl className="grid divide-y divide-border/60 sm:grid-cols-2 sm:divide-y-0">
            {ROWS.map((r) => (
              <div key={r.key} className="flex items-center justify-between border-border/60 px-4 py-3 sm:border-b">
                <dt className="text-sm text-muted">{r.label}</dt>
                <dd className="font-semibold tabular-nums">{r.money ? formatCurrency(Number(report.data![r.key])) : String(report.data![r.key])}</dd>
              </div>
            ))}
          </dl>
        )}
      </Card>
    </>
  );
}
