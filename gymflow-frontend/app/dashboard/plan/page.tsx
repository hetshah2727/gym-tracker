"use client";

import { Check, Copy, Gift, MessageCircle } from "lucide-react";
import { useState } from "react";
import { ConfirmDialog, useAction, useEntitlements, useToast } from "@/components/shared/growth";
import { Button, Card, Loading, PageHeader } from "@/components/shared/ui";
import { useApi } from "@/hooks/useApi";
import { track } from "@/lib/analytics";
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
interface Checkout { configured: boolean; subscription_id?: string; short_url?: string; key_id?: string; plan_name?: string }
type RazorpayCtor = new (opts: Record<string, unknown>) => { open: () => void };

function loadCheckout(): Promise<RazorpayCtor | null> {
  const w = window as unknown as { Razorpay?: RazorpayCtor };
  if (w.Razorpay) return Promise.resolve(w.Razorpay);
  return new Promise((resolve) => {
    const s = document.createElement("script");
    s.src = "https://checkout.razorpay.com/v1/checkout.js";
    s.onload = () => resolve((window as unknown as { Razorpay?: RazorpayCtor }).Razorpay ?? null);
    s.onerror = () => resolve(null);
    document.body.appendChild(s);
  });
}

const USAGE_LABEL: Record<string, string> = { ai_messages: "AI replies", seo_audits: "Website checks", content_generations: "AI-written posts" };

interface Referral { code: string; link: string; joined: number; paying: number; trial_days: number; reward_days: number }

/** "Give a gym friend a longer trial, get a free month when they start paying." */
function ReferralCard() {
  const { data: r } = useApi<Referral>("/subscriptions/referral");
  const toast = useToast();
  if (!r) return null;
  const text = `I use GymFlow to collect fees and renewals on WhatsApp. Try it free for ${r.trial_days} days: ${r.link}`;
  return (
    <Card className="mt-6 p-5">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center">
        <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-money/10 text-money"><Gift className="h-6 w-6" /></span>
        <div className="flex-1">
          <p className="font-display text-lg font-bold">Invite a gym owner, get a free month</p>
          <p className="text-sm text-muted">They get a {r.trial_days}-day free trial. When they start paying, you get {r.reward_days} days free.
            {r.joined > 0 && <> So far: <strong className="text-fg">{r.joined}</strong> joined, <strong className="text-fg">{r.paying}</strong> paying.</>}</p>
        </div>
        <div className="flex gap-2">
          <a href={`https://wa.me/?text=${encodeURIComponent(text)}`} target="_blank" rel="noreferrer"
            className="inline-flex items-center gap-2 rounded-xl bg-brand px-4 py-2.5 text-sm font-semibold text-brand-fg"><MessageCircle className="h-4 w-4" /> Share</a>
          <Button variant="secondary" onClick={() => { navigator.clipboard?.writeText(r.link); toast("Invite link copied"); }}><Copy className="h-4 w-4" /> Copy link</Button>
        </div>
      </div>
    </Card>
  );
}

export default function PlanPage() {
  const { ent, reload } = useEntitlements();
  const plans = useApi<Plan[]>("/subscriptions/plans");
  const history = useApi<{ event: string; from_plan: string | null; to_plan: string | null; status: string | null; notes: string | null; at: string }[]>("/subscriptions/history");
  const [change, setChange] = useState<Plan | null>(null);
  const { busy, run } = useAction();
  const toast = useToast();
  if (!ent) return <Loading />;
  const online = !!ent.billing?.gateway_subscriptions;

  // Razorpay subscription checkout (UPI autopay / card). The plan switches on when Razorpay confirms payment.
  const subscribe = (p: Plan) => run("c", () => post<Checkout>("/subscriptions/checkout", { plan_code: p.code })).then(async (c) => {
    setChange(null);
    if (!c?.configured || !c.subscription_id) return;
    track("checkout_started", { plan: p.code });
    const Razorpay = await loadCheckout();
    if (!Razorpay) { if (c.short_url) window.open(c.short_url, "_blank", "noopener"); return; }
    new Razorpay({
      key: c.key_id, subscription_id: c.subscription_id, name: "GymFlow", description: `${c.plan_name} plan – monthly`,
      theme: { color: "#D9480F" },
      handler: () => { toast("Payment received – your plan switches on in a few seconds"); setTimeout(reload, 4000); setTimeout(reload, 12000); },
    }).open();
  });
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

      <ReferralCard />

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

      <ConfirmDialog open={!!change} title={`Switch to ${change?.name}?`} confirmLabel={online ? "Continue to payment" : "Switch plan"} busy={busy === "c"}
        message={online
          ? <>{formatCurrency(change?.price_monthly ?? 0)}/month plus GST, paid by UPI autopay or card through Razorpay. Cancel any time.</>
          : <>Your new features switch on straight away. {formatCurrency(change?.price_monthly ?? 0)}/month plus GST – we&apos;ll send the invoice separately.</>}
        onClose={() => setChange(null)} onConfirm={() => change && (online ? subscribe(change)
          : run("c", () => post("/subscriptions/change-plan", { plan_code: change.code }), "Plan changed").then(() => { setChange(null); reload(); history.reload(); }))} />
    </>
  );
}
