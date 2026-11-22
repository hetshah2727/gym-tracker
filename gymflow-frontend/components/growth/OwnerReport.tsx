"use client";

import { Mail, MessageCircle, Printer } from "lucide-react";
import { useMemo, useState } from "react";
import { useAction, useToast } from "@/components/shared/growth";
import { Button, Card, Select, Skeleton } from "@/components/shared/ui";
import { useApi } from "@/hooks/useApi";
import { formatCurrency } from "@/lib/utils";
import { post } from "@/services/api";

interface Report {
  label: string; month: string; collected: number; payments: number; recovered: number; outstanding: number;
  active_members: number; new_memberships: number; checkins: number; enquiries: number; joined: number;
  plan_price: number | null; roi_multiple: number | null; text: string;
}

function lastMonths(n: number) {
  const out: { value: string; label: string }[] = [];
  const d = new Date();
  d.setDate(1);
  for (let i = 0; i < n; i++) {
    d.setMonth(d.getMonth() - 1);
    out.push({ value: `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`,
      label: d.toLocaleDateString("en-IN", { month: "long", year: "numeric" }) });
  }
  return out;
}

/** Last month on one card – share it on WhatsApp, print it as a PDF or email it. */
export function OwnerReport() {
  const months = useMemo(() => lastMonths(12), []);
  const [month, setMonth] = useState(months[0].value);
  const { data: r, loading } = useApi<Report>("/growth/owner-report", { month });
  const { busy, run } = useAction();
  const toast = useToast();

  return (
    <Card className="mb-6" title="Monthly report"
      actions={<Select className="w-44 py-1.5" value={month} onChange={(e) => setMonth(e.target.value)} options={months} aria-label="Month" />}>
      {loading || !r ? <div className="space-y-2 p-5"><Skeleton className="h-16" /><Skeleton className="h-10" /></div> : (
        <div className="p-5">
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            {[
              { label: "Collected", value: formatCurrency(r.collected), hint: `${r.payments} payments`, money: true },
              { label: "Brought back by GymFlow", value: formatCurrency(r.recovered), hint: r.roi_multiple && r.roi_multiple >= 1 ? `${r.roi_multiple}× your plan` : "after reminders", money: true },
              { label: "Still unpaid", value: formatCurrency(r.outstanding), hint: "as of today" },
              { label: "Active members", value: r.active_members, hint: `${r.new_memberships} joined or renewed` },
            ].map((s) => (
              <div key={s.label}>
                <p className="text-xs text-muted">{s.label}</p>
                <p className={`num font-display text-xl font-bold ${s.money ? "text-money" : ""}`}>{s.value}</p>
                <p className="text-xs text-muted">{s.hint}</p>
              </div>
            ))}
          </div>
          <p className="mt-4 text-sm text-muted">{r.checkins} check-ins · {r.enquiries} enquiries · {r.joined} of them joined</p>
          <div className="no-print mt-5 flex flex-wrap gap-2">
            <a href={`https://wa.me/?text=${encodeURIComponent(r.text)}`} target="_blank" rel="noreferrer"
              className="inline-flex items-center gap-2 rounded-xl bg-brand px-4 py-2.5 text-sm font-semibold text-brand-fg">
              <MessageCircle className="h-4 w-4" /> Share on WhatsApp
            </a>
            <Button variant="secondary" onClick={() => window.print()}><Printer className="h-4 w-4" /> Print / save PDF</Button>
            <Button variant="ghost" loading={busy === "mail"} onClick={() => run("mail", () => post<{ sent: number; detail?: string }>("/growth/owner-report/email", undefined, { month }))
              .then((x) => x && toast(x.sent ? "Report emailed to you" : x.detail ?? "Couldn't send the email", x.sent ? "success" : "error"))}>
              <Mail className="h-4 w-4" /> Email it to me
            </Button>
          </div>
          <p className="no-print mt-3 text-xs text-muted">This report is also emailed to you on the 1st of every month.</p>
        </div>
      )}
    </Card>
  );
}
