"use client";

import { Badge, Card, EmptyState, Loading, PageHeader } from "@/components/shared/ui";
import { useApi } from "@/hooks/useApi";
import { formatCurrency, formatDate, humanize } from "@/lib/utils";
import type { Membership, Payment } from "@/types";

export default function MemberMembership() {
  const memberships = useApi<Membership[]>("/me/memberships");
  const payments = useApi<Payment[]>("/me/payments");

  return (
    <>
      <PageHeader title="My membership" description="Your plans and payment history." />
      <Card title="Memberships" className="mb-6">
        {memberships.loading ? <Loading /> : !memberships.data?.length ? <EmptyState title="No memberships yet" /> : (
          <ul className="divide-y divide-border/60">
            {memberships.data.map((m) => (
              <li key={m.id} className="flex items-center justify-between px-4 py-3 text-sm">
                <div>
                  <p className="font-medium">{formatDate(m.start_date)} – {formatDate(m.end_date)}</p>
                  <p className="text-xs text-muted">{formatCurrency(m.amount)}{m.status === "active" && m.days_left !== null ? ` · ${m.days_left} days left` : ""}</p>
                </div>
                <Badge value={m.status} />
              </li>
            ))}
          </ul>
        )}
      </Card>
      <Card title="Payments">
        {payments.loading ? <Loading /> : !payments.data?.length ? <EmptyState title="No payments yet" /> : (
          <ul className="divide-y divide-border/60">
            {payments.data.map((p) => (
              <li key={p.id} className="flex items-center justify-between px-4 py-3 text-sm">
                <div>
                  <p className="font-medium tabular-nums">{formatCurrency(p.amount)}</p>
                  <p className="text-xs text-muted">{p.paid_at ? `Paid ${formatDate(p.paid_at)} · ${humanize(p.method)}` : `Due ${formatDate(p.due_date)}`}</p>
                </div>
                <Badge value={p.status} />
              </li>
            ))}
          </ul>
        )}
      </Card>
    </>
  );
}
