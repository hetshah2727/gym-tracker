"use client";

import { CheckCircle2, MessageCircle, SkipForward, X } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { DueRow, sendReminder, type DueItem, type DueList } from "@/components/money/DueRow";
import { FeatureGate } from "@/components/shared/growth";
import { Button, Card, EmptyState, ErrorNote, InfoTip, Skeleton } from "@/components/shared/ui";
import { useApi } from "@/hooks/useApi";
import { useT } from "@/lib/i18n";
import { formatCurrency } from "@/lib/utils";

const SECTIONS: { key: DueItem["bucket"]; title: string; hint: string; tone: string }[] = [
  { key: "overdue", title: "Late", hint: "Fees past their due date and memberships that have ended", tone: "text-danger" },
  { key: "this_week", title: "Ending this week", hint: "Remind them now so they renew before the last day", tone: "text-warning" },
  { key: "later", title: "Ending this month", hint: "An early reminder makes renewing easy", tone: "text-muted" },
];

function ReminderQueue({ items, onClose, withLink }: { items: DueItem[]; onClose: () => void; withLink: boolean }) {
  const { t } = useT();
  const [i, setI] = useState(0);
  const item = items[i];
  const next = () => setI((n) => n + 1);
  if (!item) {
    return (
      <Card className="mb-6 border-money/40 p-5">
        <div className="flex items-center gap-3">
          <CheckCircle2 className="h-6 w-6 text-money" />
          <p className="flex-1 font-semibold">Done – {items.length} reminder{items.length === 1 ? "" : "s"} sent. Mark people as paid as the money comes in.</p>
          <Button variant="ghost" size="sm" onClick={onClose}>Close</Button>
        </div>
      </Card>
    );
  }
  return (
    <Card className="mb-6 border-brand/40 p-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-brand">Reminder {i + 1} of {items.length}</p>
          <p className="mt-1 font-display text-lg font-bold">{item.name} · {formatCurrency(item.amount)}</p>
          <p className="mt-2 rounded-xl bg-surface-2 p-3 text-sm text-muted">{item.message}</p>
        </div>
        <button onClick={onClose} className="rounded-lg p-1 text-muted hover:bg-surface-2" aria-label="Stop reminding"><X className="h-4 w-4" /></button>
      </div>
      <div className="mt-4 flex gap-2">
        <Button onClick={() => { void sendReminder(item, withLink); next(); }}><MessageCircle className="h-4 w-4" /> {t("Open WhatsApp & next")}</Button>
        <Button variant="ghost" onClick={next}><SkipForward className="h-4 w-4" /> {t("Skip")}</Button>
      </div>
    </Card>
  );
}

export default function MoneyPage() {
  const { data, error, loading, reload } = useApi<DueList>("/recovery/due");
  const [queue, setQueue] = useState<DueItem[] | null>(null);
  const cur = data?.currency ?? "INR";
  const urgent = (data?.items ?? []).filter((i) => i.bucket !== "later");
  const { t } = useT();

  return (
    <FeatureGate feature="recovery_center">
      <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="font-display text-2xl font-bold tracking-tight sm:text-[1.7rem]">{t("Who owes you money")}</h1>
          {loading ? <Skeleton className="mt-2 h-10 w-56" /> : data && (
            <p className="mt-1 text-sm text-muted">
              <span className="num font-display text-3xl font-extrabold text-fg">{formatCurrency(data.total, cur)}</span>{" "}
              from {data.count} {data.count === 1 ? "person" : "people"} in the next 30 days
            </p>
          )}
        </div>
        {urgent.length > 0 && !queue && (
          <Button size="lg" onClick={() => setQueue(urgent)}><MessageCircle className="h-5 w-5" /> {t("Remind {n} on WhatsApp", { n: urgent.length })}</Button>
        )}
      </div>

      {error && <ErrorNote message={error} />}
      {queue && <ReminderQueue items={queue} withLink={!!data?.payment_links} onClose={() => { setQueue(null); reload(); }} />}
      {data && data.count > 0 && (
        <p className="mb-4 text-xs text-muted">
          {data.payment_links ? "Reminders include a Razorpay link so members can pay by UPI or card – it's marked paid automatically."
            : data.upi_payments ? "Reminders include a UPI pay page with your QR code. Mark people paid when the money arrives."
            : <>Tip: add your <Link href="/dashboard/settings" className="underline">UPI ID</Link> or <Link href="/dashboard/integrations" className="underline">connect Razorpay</Link> to add a pay-online link to every reminder.</>}
        </p>
      )}

      {loading ? (
        <div className="space-y-3"><Skeleton className="h-16" /><Skeleton className="h-16" /><Skeleton className="h-16" /></div>
      ) : data && data.count === 0 ? (
        <Card><EmptyState icon={<CheckCircle2 className="h-7 w-7 text-money" />} title={t("Nobody owes you money")} description="Every fee is paid and no membership ends in the next 30 days. GymFlow checks again every day." /></Card>
      ) : data && (
        <div className="space-y-6">
          {SECTIONS.map((s) => {
            const items = data.items.filter((i) => i.bucket === s.key);
            if (!items.length) return null;
            return (
              <section key={s.key}>
                <div className="mb-2 flex items-baseline justify-between gap-3 px-1">
                  <div>
                    <h2 className={`font-display text-lg font-bold ${s.tone}`}>{t(s.title)} <span className="text-sm font-medium text-muted">({items.length})</span></h2>
                    <p className="text-xs text-muted">{s.hint}</p>
                  </div>
                  <p className="num font-display font-bold">{formatCurrency(data.buckets[s.key].amount, cur)}</p>
                </div>
                <Card><ul className="divide-y divide-border/60">{items.map((i) => <DueRow key={i.id} item={i} currency={cur} onDone={reload} paymentLinks={!!data.payment_links} />)}</ul></Card>
              </section>
            );
          })}
        </div>
      )}

      <div className="mt-6 flex flex-wrap items-center justify-between gap-3 text-xs text-muted">
        <InfoTip>
          Late fees are payments past their due date. Renewal amounts are your current plan price – they become money
          collected only once the member pays. Marking someone paid records the payment (and the renewal) in one step.
        </InfoTip>
        <span>Someone paid a different amount? Record it under <Link href="/dashboard/payments" className="underline">Payments</Link>.</span>
      </div>
    </FeatureGate>
  );
}
