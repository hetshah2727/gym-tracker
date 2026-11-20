"use client";

import { AlertTriangle, CalendarCheck, IndianRupee, Inbox, UserCheck, Users, Wallet } from "lucide-react";
import Link from "next/link";
import { RevenueChart } from "@/components/dashboard/RevenueChart";
import { StatCard } from "@/components/dashboard/StatCard";
import { Badge, Card, EmptyState, ErrorNote, Loading, PageHeader } from "@/components/shared/ui";
import { useApi } from "@/hooks/useApi";
import { useMemberNames } from "@/hooks/useLookups";
import { formatCurrency, formatDate } from "@/lib/utils";
import type { Membership, Overview } from "@/types";

export default function OverviewPage() {
  const { data: o, error, loading } = useApi<Overview>("/analytics/overview");
  const { data: revenue } = useApi<{ month: string; revenue: number }[]>("/analytics/revenue", { months: 6 });
  const { data: expiring } = useApi<Membership[]>("/memberships", { expiring_within_days: 7, status: "active" });
  const { names } = useMemberNames();

  if (loading) return <Loading />;
  if (error || !o) return <ErrorNote message={error} />;

  const growth = o.revenue_last_month ? Math.round(((o.revenue_this_month - o.revenue_last_month) / o.revenue_last_month) * 100) : null;

  return (
    <>
      <PageHeader title="Overview" description="Today at a glance." />
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard label="Active members" value={o.active_members} hint={`${o.total_members} total · ${o.new_members_this_month} new this month`} icon={Users} tone="brand" />
        <StatCard
          label="Revenue this month"
          value={formatCurrency(o.revenue_this_month)}
          hint={growth === null ? "No data for last month" : `${growth >= 0 ? "+" : ""}${growth}% vs last month`}
          icon={IndianRupee}
          tone="brand"
        />
        <StatCard label="Pending fees" value={formatCurrency(o.pending_amount)} hint={`${o.pending_count} unpaid`} icon={Wallet} tone="warning" />
        <StatCard label="Expiring in 7 days" value={o.expiring_in_7_days} hint={`${o.expired_members} already expired`} icon={AlertTriangle} tone="danger" />
        <StatCard label="Check-ins today" value={o.checkins_today} icon={CalendarCheck} />
        <StatCard label="New website leads" value={o.new_leads} icon={Inbox} />
        <StatCard label="Expired members" value={o.expired_members} icon={UserCheck} />
      </div>

      <div className="mt-6 grid gap-4 lg:grid-cols-5">
        <Card title="Revenue (last 6 months)" className="lg:col-span-3">
          <div className="p-4">{revenue ? <RevenueChart data={revenue} /> : <Loading />}</div>
        </Card>
        <Card
          title="Renewals due this week"
          className="lg:col-span-2"
          actions={<Link href="/dashboard/memberships" className="text-xs text-brand">View all</Link>}
        >
          {!expiring?.length ? (
            <EmptyState title="No renewals due" description="Nobody's membership ends in the next 7 days." />
          ) : (
            <ul className="divide-y divide-border/60">
              {expiring.slice(0, 8).map((m) => (
                <li key={m.id} className="flex items-center justify-between px-4 py-3 text-sm">
                  <div>
                    <p className="font-medium">{names[m.member_id] ?? "Member"}</p>
                    <p className="text-xs text-muted">Ends {formatDate(m.end_date)}</p>
                  </div>
                  {m.days_left !== null && m.days_left < 0 ? (
                    <Badge value="overdue" />
                  ) : (
                    <span className="text-xs font-medium text-warning">{m.days_left === 0 ? "Today" : `${m.days_left}d left`}</span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </>
  );
}
