"use client";

import { Check, Minus } from "lucide-react";
import { useState } from "react";
import { ConfirmDialog, Kpi, Note, useAction, useEntitlements } from "@/components/shared/growth";
import { Badge, Button, Card, Loading, PageHeader } from "@/components/shared/ui";
import { useApi } from "@/hooks/useApi";
import { formatCurrency, formatDate, formatDateTime, humanize } from "@/lib/utils";
import { post } from "@/services/api";

interface Plan { id: string; code: string; name: string; price_monthly: number; max_members: number | null; features: Record<string, boolean> }

export default function PlanPage() {
  const { ent, reload } = useEntitlements();
  const plans = useApi<Plan[]>("/subscriptions/plans");
  const history = useApi<{ event: string; from_plan: string | null; to_plan: string | null; status: string | null; notes: string | null; at: string }[]>("/subscriptions/history");
  const [change, setChange] = useState<Plan | null>(null);
  const { busy, run } = useAction();
  if (!ent) return <Loading />;
  const keys = Object.keys(ent.catalog);

  return (
    <>
      <PageHeader title="Plan & usage" description="What your plan includes and how much you've used this month." />
      <Note className="mb-4">Prices shown are the platform&apos;s current list prices. Changing plan applies immediately; automated subscription billing through Razorpay is not available yet, so invoices are handled separately.</Note>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Kpi label="Current plan" value={ent.plan_name ?? "None"} hint={<>{humanize(ent.status)}{ent.trial_ends_at && ` · trial ends ${formatDate(ent.trial_ends_at)}`}</>} />
        {Object.entries(ent.limits).map(([k, limit]) => <Kpi key={k} label={humanize(k)} value={`${ent.usage[k] ?? 0} / ${limit ?? "∞"}`} hint="this month" />)}
      </div>
      <div className="mt-4 grid gap-4 md:grid-cols-3">
        {plans.data?.map((p) => (
          <Card key={p.id} title={p.name} actions={ent.plan_code === p.code ? <Badge value="active" /> : undefined}>
            <div className="space-y-3 p-4 text-sm">
              <p className="text-2xl font-semibold">{formatCurrency(p.price_monthly)}<span className="text-sm font-normal text-muted">/month</span></p>
              <p className="text-xs text-muted">{p.max_members ? `Up to ${p.max_members} members` : "Unlimited members"}</p>
              <ul className="space-y-1">{keys.map((k) => <li key={k} className="flex items-center gap-2 text-xs">{p.features[k] ? <Check className="h-3.5 w-3.5 text-brand" /> : <Minus className="h-3.5 w-3.5 text-muted" />}<span className={p.features[k] ? "" : "text-muted"}>{ent.catalog[k].label}</span></li>)}</ul>
              {ent.plan_code !== p.code && <Button className="w-full" variant="secondary" onClick={() => setChange(p)}>Switch to {p.name}</Button>}
            </div>
          </Card>))}
      </div>
      <Card title="Subscription history" className="mt-4"><ul className="divide-y divide-border/60">{(history.data ?? []).map((h, i) => <li key={i} className="px-4 py-2 text-sm">{humanize(h.event)} {h.from_plan && `${h.from_plan} →`} {h.to_plan} <span className="text-xs text-muted">· {formatDateTime(h.at)}{h.notes && ` · ${h.notes}`}</span></li>)}</ul></Card>
      <ConfirmDialog open={!!change} title={`Switch to ${change?.name}?`} confirmLabel="Switch plan" busy={busy === "c"}
        message={<>Features change immediately. Billing: {formatCurrency(change?.price_monthly ?? 0)}/month, invoiced outside GymFlow for now.</>}
        onClose={() => setChange(null)} onConfirm={() => change && run("c", () => post("/subscriptions/change-plan", { plan_code: change.code }), "Plan changed").then(() => { setChange(null); reload(); history.reload(); })} />
    </>
  );
}
