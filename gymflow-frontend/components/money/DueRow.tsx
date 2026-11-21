"use client";

import { Check, MessageCircle } from "lucide-react";
import { useState } from "react";
import { useAction } from "@/components/shared/growth";
import { Button } from "@/components/shared/ui";
import { cn, daysPhrase, formatCurrency, initials, whatsappLink } from "@/lib/utils";
import { post } from "@/services/api";

export interface DueItem {
  id: string;
  kind: "renewal" | "unpaid" | "failed";
  bucket: "overdue" | "this_week" | "later";
  member_id: string;
  name: string;
  phone: string;
  plan: string | null;
  amount: number;
  days: number;
  message: string | null;
  contact_count: number;
  last_contacted_at: string | null;
  can_pay_online?: boolean;
}

export interface DueList {
  currency: string;
  total: number;
  count: number;
  buckets: Record<DueItem["bucket"], { count: number; amount: number }>;
  items: DueItem[];
  /** Razorpay is connected, so reminders can carry a pay-online link. */
  payment_links?: boolean;
}

/**
 * Opens WhatsApp with the reminder ready. With Razorpay connected, a payment link is created first and added
 * to the message. The tab is opened straight away (before the network call) so pop-up blockers allow it.
 */
export async function sendReminder(item: DueItem, withLink: boolean): Promise<void> {
  const tab = window.open("", "_blank");
  let text = item.message ?? "";
  if (withLink && item.can_pay_online) {
    try {
      const r = await post<{ url: string | null }>(`/recovery/opportunities/${item.id}/payment-link`);
      if (r.url) text += `\n\nPay online (UPI / card): ${r.url}`;
    } catch { /* send the reminder without a link */ }
  }
  const url = whatsappLink(item.phone, text);
  if (tab) tab.location.href = url; else window.location.href = url;
  post(`/recovery/opportunities/${item.id}/contact`, { note: withLink ? "WhatsApp reminder with payment link" : "WhatsApp reminder sent" }).catch(() => {});
}

const METHODS = [{ value: "cash", label: "Cash" }, { value: "upi", label: "UPI" }, { value: "card", label: "Card" }];

function when(item: DueItem) {
  if (item.kind === "failed") return "online payment failed";
  if (item.kind === "unpaid") return item.days < 0 ? `fee ${daysPhrase(item.days, "due")}` : "fee due";
  return `membership ${daysPhrase(item.days, "ends")}`;
}

/** One person who owes money, with the two things the owner actually does: message them, or mark paid. */
export function DueRow({ item, currency = "INR", onDone, paymentLinks = false }: { item: DueItem; currency?: string; onDone: () => void; paymentLinks?: boolean }) {
  const [paying, setPaying] = useState(false);
  const [gone, setGone] = useState(false);
  const { busy, run } = useAction();
  const late = item.bucket === "overdue";

  const remind = () => { void sendReminder(item, paymentLinks); };
  const markPaid = (method: string) =>
    run("pay", () => post(`/recovery/opportunities/${item.id}/mark-paid`, { method }),
      `${item.name.split(" ")[0]} paid ${formatCurrency(item.amount, currency)}. Added to this month's collection.`)
      .then((r) => { if (r) { setGone(true); setTimeout(onDone, 250); } });

  return (
    <li className={cn("flex flex-col gap-3 px-4 py-3.5 transition-all duration-300 sm:flex-row sm:items-center sm:px-5", gone && "pointer-events-none -translate-x-2 opacity-0")}>
      <div className="flex min-w-0 flex-1 items-center gap-3">
        <span className={cn("flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-xs font-bold",
          late ? "bg-danger/10 text-danger" : "bg-warning/10 text-warning")}>{initials(item.name)}</span>
        <div className="min-w-0">
          <p className="truncate font-semibold">{item.name}</p>
          <p className="truncate text-xs text-muted">
            <span className={late ? "font-medium text-danger" : "font-medium text-warning"}>{when(item)}</span>
            {item.plan && <> · {item.plan}</>}
            {item.contact_count > 0 && <> · reminded {item.contact_count}×</>}
          </p>
        </div>
      </div>
      <div className="flex items-center gap-2 pl-[3.25rem] sm:pl-0">
        <span className="num mr-auto font-display text-base font-bold sm:mr-2">{formatCurrency(item.amount, currency)}</span>
        {paying ? (
          <div className="flex animate-rise gap-1" role="group" aria-label="How did they pay?">
            {METHODS.map((m) => (
              <Button key={m.value} size="sm" variant="secondary" loading={busy === "pay"} onClick={() => markPaid(m.value)}>{m.label}</Button>
            ))}
            <Button size="sm" variant="ghost" onClick={() => setPaying(false)}>Cancel</Button>
          </div>
        ) : (
          <>
            <Button size="sm" variant="secondary" onClick={remind} aria-label={`Send ${item.name} a WhatsApp reminder`}>
              <MessageCircle className="h-4 w-4 text-money" /> Remind
            </Button>
            <Button size="sm" variant="secondary" onClick={() => setPaying(true)}>
              <Check className="h-4 w-4" /> Paid
            </Button>
          </>
        )}
      </div>
    </li>
  );
}
