"use client";

import { Building2, IndianRupee, ShoppingBag, Users, Wallet } from "lucide-react";
import { StatCard } from "@/components/dashboard/StatCard";
import { Card, ErrorNote, Loading, PageHeader } from "@/components/shared/ui";
import { useApi } from "@/hooks/useApi";
import { formatCurrency, humanize } from "@/lib/utils";
import type { PlatformStats } from "@/types";

export default function AdminDashboard() {
  const { data: s, loading, error } = useApi<PlatformStats>("/platform/stats");
  if (loading) return <Loading />;
  if (error || !s) return <ErrorNote message={error} />;
  const totalSubs = Object.values(s.subscriptions_by_status).reduce((a, b) => a + b, 0) || 1;

  return (
    <>
      <PageHeader title="Platform overview" description="GymFlow AI across all gyms." />
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard label="MRR" value={formatCurrency(s.mrr)} hint="Active paid subscriptions" icon={IndianRupee} tone="brand" />
        <StatCard label="Gyms" value={s.total_gyms} hint={`${s.active_gyms} active`} icon={Building2} />
        <StatCard label="Members on platform" value={s.total_members} hint={`${s.active_members} active`} icon={Users} />
        <StatCard label="Affiliate earnings" value={formatCurrency(s.affiliate_platform_earnings)} hint="Platform share" icon={ShoppingBag} />
        <StatCard label="Fees processed this month" value={formatCurrency(s.gym_fee_volume_this_month)} icon={Wallet} />
      </div>
      <Card title="Subscriptions by status" className="mt-6">
        <ul className="space-y-3 p-4">
          {Object.entries(s.subscriptions_by_status).map(([status, count]) => (
            <li key={status}>
              <div className="mb-1 flex justify-between text-sm"><span>{humanize(status)}</span><span className="tabular-nums text-muted">{count}</span></div>
              <div className="h-2 overflow-hidden rounded-full bg-surface-2"><div className="h-full bg-brand" style={{ width: `${(count / totalSubs) * 100}%` }} /></div>
            </li>
          ))}
          {!Object.keys(s.subscriptions_by_status).length && <li className="text-sm text-muted">No subscriptions yet.</li>}
        </ul>
      </Card>
    </>
  );
}
