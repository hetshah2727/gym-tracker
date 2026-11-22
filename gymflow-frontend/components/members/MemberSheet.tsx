"use client";

import { CalendarCheck, MessageCircle, Pencil, Ticket } from "lucide-react";
import { Badge, Button, Loading, Sheet } from "@/components/shared/ui";
import { useApi } from "@/hooks/useApi";
import { cn, daysPhrase, formatCurrency, formatDate, whatsappLink } from "@/lib/utils";
import type { Member } from "@/types";

interface Timeline {
  member: Member;
  memberships: { id: string; plan: string | null; start_date: string; end_date: string; amount: number; status: string }[];
  payments: { id: string; amount: number; status: string; method: string | null; due_date: string | null; paid_at: string | null }[];
  visits: { last_30_days: number; recent: string[] };
}

/** Everything about one member in one place, with the three things staff do most. */
export function MemberSheet({ memberId, onClose, onEdit, onRenew }: {
  memberId: string | null; onClose: () => void; onEdit: (m: Member) => void; onRenew: (m: Member) => void;
}) {
  const { data, loading } = useApi<Timeline>(memberId ? `/members/${memberId}/timeline` : null);
  const m = data?.member;
  const days = m?.days_left;
  return (
    <Sheet open={!!memberId} onClose={onClose} title={m?.full_name ?? "Member"}>
      {loading || !data || !m ? <Loading /> : (
        <div className="space-y-5 text-sm">
          <div className="grid grid-cols-3 gap-2">
            <div className="rounded-2xl bg-surface-2 p-3">
              <p className="text-xs text-muted">Plan</p>
              <p className="font-semibold">{m.plan_name ?? "None"}</p>
              <p className={cn("text-xs", days == null ? "text-muted" : days < 0 ? "text-danger" : days <= 7 ? "text-warning" : "text-muted")}>{days != null ? daysPhrase(days) : "—"}</p>
            </div>
            <div className="rounded-2xl bg-surface-2 p-3">
              <p className="text-xs text-muted">Dues</p>
              <p className={cn("font-semibold", m.due_amount ? "text-danger" : "text-money")}>{m.due_amount ? formatCurrency(m.due_amount) : "Paid up"}</p>
            </div>
            <div className="rounded-2xl bg-surface-2 p-3">
              <p className="text-xs text-muted">Visits (30 days)</p>
              <p className="font-semibold">{data.visits.last_30_days}</p>
              <p className="text-xs text-muted">{data.visits.recent[0] ? `last ${formatDate(data.visits.recent[0], { day: "numeric", month: "short" })}` : "none yet"}</p>
            </div>
          </div>

          <div className="flex flex-wrap gap-2">
            <a href={whatsappLink(m.phone)} target="_blank" rel="noreferrer" className="inline-flex items-center gap-2 rounded-xl border border-border px-3 py-2 font-semibold hover:bg-surface-2">
              <MessageCircle className="h-4 w-4 text-money" /> WhatsApp
            </a>
            <Button variant="secondary" onClick={() => onRenew(m)}><Ticket className="h-4 w-4" /> {m.plan_name ? "Renew" : "Add plan"}</Button>
            <Button variant="ghost" onClick={() => onEdit(m)}><Pencil className="h-4 w-4" /> Edit details</Button>
          </div>

          <p className="text-xs text-muted">{m.phone}{m.email ? ` · ${m.email}` : ""} · member since {formatDate(m.joined_on)}</p>

          <section>
            <h3 className="mb-2 font-display font-semibold">Memberships</h3>
            {data.memberships.length === 0 ? <p className="text-muted">No memberships yet.</p> : (
              <ul className="space-y-1.5">
                {data.memberships.map((ms) => (
                  <li key={ms.id} className="flex items-center justify-between rounded-xl border border-border/70 px-3 py-2">
                    <span><span className="font-medium">{ms.plan ?? "Plan"}</span> <span className="text-xs text-muted">{formatDate(ms.start_date, { day: "numeric", month: "short" })} – {formatDate(ms.end_date)}</span></span>
                    <Badge value={ms.status} />
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section>
            <h3 className="mb-2 font-display font-semibold">Payments</h3>
            {data.payments.length === 0 ? <p className="text-muted">No payments yet.</p> : (
              <ul className="space-y-1.5">
                {data.payments.map((p) => (
                  <li key={p.id} className="flex items-center justify-between rounded-xl border border-border/70 px-3 py-2">
                    <span><span className="num font-semibold">{formatCurrency(p.amount)}</span> <span className="text-xs text-muted">
                      {p.paid_at ? `paid ${formatDate(p.paid_at, { day: "numeric", month: "short" })}${p.method ? ` · ${p.method.toUpperCase()}` : ""}` : p.due_date ? `due ${formatDate(p.due_date, { day: "numeric", month: "short" })}` : ""}
                    </span></span>
                    <Badge value={p.status} />
                  </li>
                ))}
              </ul>
            )}
          </section>

          {data.visits.recent.length > 0 && (
            <section>
              <h3 className="mb-2 flex items-center gap-1.5 font-display font-semibold"><CalendarCheck className="h-4 w-4" /> Recent visits</h3>
              <p className="text-muted">{data.visits.recent.map((v) => formatDate(v, { day: "numeric", month: "short" })).join(" · ")}</p>
            </section>
          )}
        </div>
      )}
    </Sheet>
  );
}
