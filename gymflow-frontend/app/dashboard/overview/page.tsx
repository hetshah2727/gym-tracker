"use client";

import { ArrowRight, ArrowUpRight, CheckCircle2, Circle, MessageSquareText } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { DueRow, type DueList } from "@/components/money/DueRow";
import type { Action } from "@/components/growth/Lists";
import { Card, ErrorNote, InfoTip, Input, Skeleton } from "@/components/shared/ui";
import { useApi } from "@/hooks/useApi";
import { useT } from "@/lib/i18n";
import { cn, firstName, formatCompact, formatCurrency, greeting } from "@/lib/utils";

interface Dashboard {
  gym: { name: string; currency: string; is_demo: boolean };
  owner_name: string;
  subscription: { plan_name: string | null; status: string; price_monthly: number | null };
  setup: { key: string; label: string; done: boolean; href: string }[];
  money: { due_total: number; due_count: number; buckets: DueList["buckets"] };
  checkins: number;
  business: Record<string, number>;
  recovery: { expiring_7d: number };
  actions: Action[];
}

// Money actions are shown person-by-person from the due list, so they're skipped in the generic list.
const MONEY_ACTIONS = new Set(["renewals", "payments"]);
const SUGGESTIONS = ["Who hasn't come in 2 weeks?", "How much did I collect this month?", "Which enquiries should I call today?"];

function Hero({ d }: { d: Dashboard }) {
  const { t } = useT();
  const cur = d.gym.currency;
  const recovered = d.business.recovered_revenue ?? 0;
  const price = d.subscription.price_monthly;
  const multiple = price && recovered > 0 ? recovered / price : null;
  const overdue = d.money.buckets.overdue;
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <Link href="/dashboard/money" className="card group relative overflow-hidden p-6 transition hover:shadow-soft">
        <p className="text-sm font-medium text-muted">{t("Waiting to be collected")}</p>
        <p className="num mt-2 font-display text-4xl font-extrabold sm:text-5xl">{formatCurrency(d.money.due_total, cur)}</p>
        <p className="mt-2 text-sm text-muted">
          {d.money.due_count === 0 ? t("Nobody owes you anything right now.") : <>
            {t(d.money.due_count === 1 ? "{n} person" : "{n} people", { n: d.money.due_count })}
            {overdue.count > 0 && <> · <span className="font-semibold text-danger">{t("{n} late", { n: overdue.count })}</span></>}
            {d.money.buckets.this_week.count > 0 && <> · {t("{n} ending this week", { n: d.money.buckets.this_week.count })}</>}
          </>}
        </p>
        <span className="mt-5 inline-flex items-center gap-1.5 rounded-xl bg-brand px-4 py-2.5 text-sm font-semibold text-brand-fg transition group-hover:bg-brand/90">
          {t("See who owes")} <ArrowRight className="h-4 w-4" />
        </span>
      </Link>

      <div className="card relative overflow-hidden bg-money/[0.06] p-6">
        <p className="text-sm font-medium text-muted">{t("Brought back by GymFlow this month")}</p>
        <p className="num mt-2 font-display text-4xl font-extrabold text-money sm:text-5xl">{formatCurrency(recovered, cur)}</p>
        {multiple && multiple >= 1 ? (
          <p className="mt-2 text-sm font-medium">
            {t("That's {x}× what you pay for GymFlow ({price}/month).", { x: multiple >= 10 ? Math.round(multiple) : multiple.toFixed(1), price: formatCurrency(price, cur) })}
          </p>
        ) : (
          <p className="mt-2 text-sm text-muted">
            {recovered > 0 ? "Money from renewals and late fees collected after a reminder." : "As members renew and pay late fees after a reminder, it adds up here."}
          </p>
        )}
        <div className="mt-5">
          <InfoTip>
            Counted only when a member who was due, late or whose membership had ended actually pays – each payment once.
            Estimates and unpaid amounts are never included.
          </InfoTip>
        </div>
      </div>
    </div>
  );
}

function Setup({ steps }: { steps: Dashboard["setup"] }) {
  const { t } = useT();
  const done = steps.filter((s) => s.done).length;
  if (done === steps.length) return null;
  return (
    <Card className="mt-6">
      <div className="flex items-center justify-between gap-4 px-5 pt-4">
        <div>
          <h2 className="font-display font-bold">{t("Finish setting up your gym")}</h2>
          <p className="text-xs text-muted">{done} of {steps.length} done · <Link href="/dashboard/setup" className="font-semibold text-brand underline">open the 10-minute setup</Link></p>
        </div>
        <div className="h-2 w-28 overflow-hidden rounded-full bg-surface-2" aria-hidden>
          <div className="h-full rounded-full bg-money" style={{ width: `${(done / steps.length) * 100}%` }} />
        </div>
      </div>
      <ul className="grid gap-x-6 p-3 sm:grid-cols-2">
        {steps.map((s) => (
          <li key={s.key}>
            <Link href={s.href} className={cn("flex items-center gap-2.5 rounded-xl px-2 py-2 text-sm hover:bg-surface-2", s.done && "text-muted line-through")}>
              {s.done ? <CheckCircle2 className="h-4 w-4 text-money" /> : <Circle className="h-4 w-4 text-muted" />} {s.label}
            </Link>
          </li>
        ))}
      </ul>
    </Card>
  );
}

const TOUR = [
  { title: "Money waiting to be collected", text: "Every fee that's late and every membership ending soon, added up. Tap it to see who owes what.", href: "/dashboard/money" },
  { title: "One tap to remind, one tap when paid", text: "Remind opens WhatsApp with the message ready. Paid records the payment and the renewal together.", href: "/dashboard/money" },
  { title: "Proof it pays for itself", text: "The green card shows what GymFlow brought back this month – only money members actually paid.", href: null },
  { title: "Every enquiry in one place", text: "Google, Instagram, WhatsApp and walk-ins – with reminders so nobody is forgotten.", href: "/dashboard/leads" },
];

/** A short guided tour for people looking at the sample gym. Dismissed for good once closed. */
function DemoTour() {
  const [step, setStep] = useState<number | null>(null);
  useEffect(() => {
    try { if (localStorage.getItem("gf-demo-tour") !== "done") setStep(0); } catch { setStep(0); }
  }, []);
  if (step === null) return null;
  const s = TOUR[step];
  const close = () => { try { localStorage.setItem("gf-demo-tour", "done"); } catch { /* ignore */ } setStep(null); };
  return (
    <Card className="mt-6 border-brand/40 bg-brand/[0.04] p-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-brand">Quick tour · {step + 1} of {TOUR.length}</p>
          <p className="mt-1 font-display text-lg font-bold">{s.title}</p>
          <p className="mt-1 text-sm text-muted">{s.text}</p>
        </div>
        <button onClick={close} className="text-xs text-muted underline">Skip tour</button>
      </div>
      <div className="mt-4 flex gap-2">
        {step < TOUR.length - 1
          ? <button onClick={() => setStep(step + 1)} className="rounded-xl bg-brand px-4 py-2 text-sm font-semibold text-brand-fg">Next</button>
          : <button onClick={close} className="rounded-xl bg-brand px-4 py-2 text-sm font-semibold text-brand-fg">Got it</button>}
        {s.href && <Link href={s.href} className="rounded-xl border border-border px-4 py-2 text-sm font-semibold hover:bg-surface-2">Show me</Link>}
      </div>
    </Card>
  );
}

export default function TodayPage() {
  const { data: d, error, loading } = useApi<Dashboard>("/growth/dashboard");
  const due = useApi<DueList>("/recovery/due");
  const router = useRouter();
  const { t } = useT();
  const [ask, setAsk] = useState("");
  const go = (q: string) => router.push(`/dashboard/assistant?q=${encodeURIComponent(q)}`);

  if (error) return <ErrorNote message={error} />;
  const cur = d?.gym.currency ?? "INR";
  const people = (due.data?.items ?? []).filter((i) => i.bucket !== "later").slice(0, 5);
  const otherActions = (d?.actions ?? []).filter((a) => !MONEY_ACTIONS.has(a.key) || due.error);
  const remaining = people.length + otherActions.length;
  const b = d?.business ?? {};

  return (
    <>
      <div className="mb-6 flex flex-wrap items-end justify-between gap-2">
        <div>
          <p className="text-sm text-muted">{new Date().toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "long" })}</p>
          <h1 className="font-display text-2xl font-bold tracking-tight sm:text-3xl">
            {t(greeting())}{d?.owner_name ? `, ${firstName(d.owner_name)}` : ""}
          </h1>
        </div>
        {d?.gym.is_demo && <span className="rounded-full bg-warning/10 px-3 py-1 text-xs font-semibold text-warning">{t("Sample gym · demo data")}</span>}
      </div>

      {loading || !d ? (
        <div className="grid gap-4 md:grid-cols-2"><Skeleton className="h-52" /><Skeleton className="h-52" /></div>
      ) : <Hero d={d} />}

      {d && !d.gym.is_demo && <Setup steps={d.setup} />}
      {d?.gym.is_demo && <DemoTour />}

      <Card className="mt-6">
        <div className="flex items-center justify-between px-5 pb-1 pt-4">
          <h2 className="font-display text-lg font-bold">{t("Do these today")}</h2>
          {!loading && <span className="text-xs text-muted">{remaining ? t("{n} to do", { n: remaining }) : ""}</span>}
        </div>
        {loading || due.loading ? (
          <div className="space-y-2 p-4"><Skeleton className="h-14" /><Skeleton className="h-14" /><Skeleton className="h-14" /></div>
        ) : remaining === 0 ? (
          <div className="flex flex-col items-center gap-2 px-6 py-12 text-center">
            <CheckCircle2 className="h-10 w-10 text-money" />
            <p className="font-display font-semibold">{t("All done for today")}</p>
            <p className="text-sm text-muted">{t("Nobody is late and every enquiry has a reply. Nice work.")}</p>
          </div>
        ) : (
          <ul className="divide-y divide-border/60">
            {people.map((item) => <DueRow key={item.id} item={item} currency={cur} onDone={due.reload} paymentLinks={!!due.data?.payment_links} />)}
            {otherActions.map((a) => (
              <li key={a.key}>
                <Link href={a.href} className="flex items-center gap-3 px-4 py-3.5 hover:bg-surface-2 sm:px-5">
                  <span className={cn("h-2.5 w-2.5 shrink-0 rounded-full", a.priority === "high" ? "bg-danger" : a.priority === "medium" ? "bg-warning" : "bg-muted/50")} aria-hidden />
                  <div className="min-w-0 flex-1">
                    <p className="font-semibold">{a.title}</p>
                    <p className="truncate text-xs text-muted">{a.detail}</p>
                  </div>
                  <ArrowRight className="h-4 w-4 shrink-0 text-muted" />
                </Link>
              </li>
            ))}
          </ul>
        )}
        {(due.data?.count ?? 0) > people.length && (
          <Link href="/dashboard/money" className="block border-t border-border/60 px-5 py-3 text-sm font-semibold text-brand hover:bg-surface-2">
            {t("See all {n} people who owe money →", { n: due.data?.count ?? 0 })}
          </Link>
        )}
      </Card>

      {d && (
        <section aria-label="This month" className="mt-6 grid grid-cols-2 gap-3 lg:grid-cols-4">
          {[
            { label: t("Active members"), value: b.active_members, href: "/dashboard/members?status=active" },
            { label: t("New joins this month"), value: b.new_memberships, href: "/dashboard/members" },
            { label: t("Collected this month"), value: formatCompact(b.membership_revenue, cur), href: "/dashboard/revenue", money: true },
            { label: t("Check-ins this month"), value: d.checkins, href: "/dashboard/attendance" },
          ].map((s) => (
            <Link key={s.label} href={s.href} className="card group p-4 transition hover:shadow-soft">
              <p className="flex items-center justify-between text-xs text-muted">{s.label}<ArrowUpRight className="h-3.5 w-3.5 opacity-0 transition group-hover:opacity-100" /></p>
              <p className={cn("num mt-1 font-display text-2xl font-bold", s.money && "text-money")}>{s.value ?? "—"}</p>
            </Link>
          ))}
        </section>
      )}

      <Card className="mt-6 p-5">
        <form onSubmit={(e) => { e.preventDefault(); if (ask.trim()) go(ask); }} className="flex items-center gap-3">
          <MessageSquareText className="hidden h-5 w-5 shrink-0 text-brand sm:block" />
          <Input value={ask} onChange={(e) => setAsk(e.target.value)} placeholder={t("Ask anything about your gym…")} aria-label="Ask GymFlow" className="flex-1" />
          <button type="submit" className="rounded-xl bg-fg px-4 py-2.5 text-sm font-semibold text-bg">{t("Ask")}</button>
        </form>
        <p className="mt-3 text-xs text-muted">
          Try:{" "}
          {SUGGESTIONS.map((q, i) => (
            <span key={q}>
              <button onClick={() => go(q)} className="underline decoration-dotted underline-offset-2 hover:text-fg">{q}</button>
              {i < SUGGESTIONS.length - 1 && " · "}
            </span>
          ))}
        </p>
      </Card>
    </>
  );
}
