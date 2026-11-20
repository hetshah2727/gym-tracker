"use client";

import { CheckCircle2, Link2 } from "lucide-react";
import { useState } from "react";
import { Badge, Button } from "@/components/shared/ui";
import { formatCurrency, formatDate, humanize } from "@/lib/utils";
import { post } from "@/services/api";
import type { Payment } from "@/types";

export function PaymentsTable({ payments, names, onChanged }: { payments: Payment[]; names: Record<string, string>; onChanged: () => void }) {
  const [busy, setBusy] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  async function markPaid(p: Payment) {
    setBusy(p.id);
    try {
      await post(`/payments/${p.id}/mark-paid`, { method: "cash" });
      onChanged();
    } finally {
      setBusy(null);
    }
  }

  async function checkout(p: Payment) {
    setBusy(p.id);
    try {
      const order = await post<{ order_id: string }>(`/payments/${p.id}/checkout`);
      setNote(`Razorpay order ${order.order_id} created. Share the payment link with the member.`);
    } catch (e) {
      setNote(e instanceof Error ? e.message : "Could not create order");
    } finally {
      setBusy(null);
    }
  }

  return (
    <>
      {note && <p className="border-b border-border px-4 py-2 text-xs text-muted">{note}</p>}
      <div className="overflow-x-auto">
        <table className="table-base">
          <thead>
            <tr>
              <th>Member</th>
              <th>Amount</th>
              <th>Status</th>
              <th>Due</th>
              <th>Paid</th>
              <th>Method</th>
              <th className="text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {payments.map((p) => (
              <tr key={p.id}>
                <td className="font-medium">{names[p.member_id] ?? "—"}</td>
                <td className="tabular-nums">{formatCurrency(p.amount)}</td>
                <td><Badge value={p.status} /></td>
                <td className="text-muted">{formatDate(p.due_date)}</td>
                <td className="text-muted">{formatDate(p.paid_at)}</td>
                <td className="text-muted">{humanize(p.method)}</td>
                <td className="text-right">
                  {p.status !== "paid" && (
                    <div className="flex justify-end gap-1">
                      <Button size="sm" variant="ghost" onClick={() => checkout(p)} disabled={busy === p.id} title="Create online payment order">
                        <Link2 className="h-3.5 w-3.5" /> Pay link
                      </Button>
                      <Button size="sm" variant="secondary" onClick={() => markPaid(p)} loading={busy === p.id}>
                        <CheckCircle2 className="h-3.5 w-3.5" /> Mark paid
                      </Button>
                    </div>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
