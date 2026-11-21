"use client";

import { Check } from "lucide-react";
import { useState } from "react";
import { ConfirmDialog, useAction, useEntitlements } from "@/components/shared/growth";
import { Button, Card, Loading, PageHeader } from "@/components/shared/ui";
import { useApi } from "@/hooks/useApi";
import { cn, formatCurrency, formatDate, formatDateTime, humanize } from "@/lib/utils";
import { post } from "@/services/api";

interface Plan { id: string; code: string; name: string; price_monthly: number; max_members: number | null; features: Record<string, boolean> }

// What each plan is *for*, in the owner's words. Feature lists come from the server's entitlements.
const PITCH: Record<string, { promise: string; who: string }> = {
  starter: { promise: "Run my gym", who: "Replace the register: members, fees, check-in and reminders." },
  growth: { promise: "Collect & renew", who: "Stop losing fees. Renewals, late fees and enquiries followed up for you." },
  pro: { promise: "Fill my gym", who: "Get found on Google, Maps and AI apps, and turn visitors into members." },
};
const HIDDEN = new Set(["affiliate", "voice_calls"]);
const USAGE_LABEL: Record<string, string> = { ai_messages: "AI replies", seo_audits: "Website checks", content_generations: "AI-written posts" };

export default function PlanPage() {
  const { ent, reload } = useEntitlements();
  const plans = useApi<Plan[]>("/subscriptions/plans");
  const history = useApi<{ event: string; from_plan: string | null; to_plan: string | null; status: string | null; notes: string | null; at: string }[]>("/subscriptions/history");
  const [change, setChange] = useState<Plan | null>(null);
  const { busy, run } = useAction();
  if (!ent) return <Loading />;
  const keys = Object.keys(ent.catalog).filter((k) => !HIDDEN.has(k));
  const sorted = [...(plans.data ?? [])].sort((a, b) => a.price_monthly - b.price_monthly);

  return (
    <>
      <PageHeader title="Your subscription"
        description={ent.plan_name
          ? `You're on ${ent.plan_name}${ent.status === "trialing" && ent.trial_ends_at ? ` – free trial until ${formatDate(ent.trial_ends_at)}` : ent.status === "active" ? "" : ` (${humanize(ent.status)})`}.`
          : "Pick the plan that fits your gym. You can change any time."} />

      <div className="grid gap-4 lg:grid-cols-3">
        {sorted.map((p, i) => {
          const current = ent.plan_code === p.code;
          const featured = p.code === "growth";
          const prev = sorted[i - 1];
          // Show only what this plan adds over the cheaper one, so the cards stay short.
          const adds = keys.filter((k) => p.features[k] && !(prev?.features[k]));
          return (
            <div key={p.id} className={cn("card relative flex flex-col p-6", featured && "border-2 border-brand shadow-soft")}>
              {featured && <span className="absolute -top-3 left-6 rounded-full bg-brand px-3 py-0.5 text-xs font-bold text-brand-fg">Recommended</span>}
              <p className="text-sm font-semibold text-brand">{PITCH[p.code]?.promise ?? p.name}</p>
              <h2 className="font-display text-xl font-bold">{p.name}</h2>
              <p className="mt-3"><span className="num font-display text-4xl font-extrabold">{formatCurrency(p.price_monthly)}</span><span className="text-sm text-muted"> / month</span></p>
              <p className="mt-1 text-xs text-muted">{p.max_members ? `Up to ${p.max_members} members` : "Unlimited members"} · plus GST</p>
              <p className="mt-4 text-sm">{PITCH[p.code]?.who}</p>
              <ul className="mt-4 flex-1 space-y-2 text-sm">
                {prev && <li className="text-xs font-semibold text-muted">Everything in {prev.name}, plus:</li>}
                {adds.map((k) => <li key={k} className="flex gap-2"><Check className="mt-0.5 h-4 w-4 shrink-0 text-money" />{ent.catalog[k].label}</li>)}
              </ul>
              <div className="mt-6">
                {current ? (
                  <div className="rounded-xl bg-surface-2 py-2.5 text-center text-sm font-semibold">Your current plan</div>
                ) : (
                  <Button className="w-full" variant={featured ? "primary" : "secondary"} onClick={() => setChange(p)}>Switch to {p.name}</Button>
                )}
              </div>
            </div>
          );
        })}
      </div>

      <div className="mt-6 grid gap-4 lg:grid-cols-2">
        <Card title="This month's usage">
          <ul className="divide-y divide-border/60">
            {Object.entries(ent.limits).map(([k, limit]) => {
              const used = ent.usage[k] ?? 0;
              const pct = limit ? Math.min(100, (used / limit) * 100) : 0;
              return (
                <li key={k} className="px-5 py-3 text-sm">
                  <div className="flex justify-between"><span>{USAGE_LABEL[k] ?? humanize(k)}</span><span className="num text-muted">{used} / {limit ?? "unlimited"}</span></div>
                  {limit && <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-surface-2"><div className={cn("h-full rounded-full", pct > 85 ? "bg-danger" : "bg-money")} style={{ width: `${pct}%` }} /></div>}
                </li>
              );
            })}
          </ul>
        </Card>
        <Card title="History">
          {(history.data ?? []).length === 0 ? <p className="px-5 py-4 text-sm text-muted">No changes yet.</p> : (
            <ul className="divide-y divide-border/60">{(history.data ?? []).map((h, i) => (
              <li key={i} className="px-5 py-2.5 text-sm">{humanize(h.event)} {h.from_plan && `${h.from_plan} →`} {h.to_plan} <span className="text-xs text-muted">· {formatDateTime(h.at)}</span></li>
            ))}</ul>
          )}
        </Card>
      </div>

      <ConfirmDialog open={!!change} title={`Switch to ${change?.name}?`} confirmLabel="Switch plan" busy={busy === "c"}
        message={<>Your new features switch on straight away. {formatCurrency(change?.price_monthly ?? 0)}/month plus GST – we&apos;ll send the invoice separately.</>}
        onClose={() => setChange(null)} onConfirm={() => change && run("c", () => post("/subscriptions/change-plan", { plan_code: change.code }), "Plan changed").then(() => { setChange(null); reload(); history.reload(); })} />
    </>
  );
}
