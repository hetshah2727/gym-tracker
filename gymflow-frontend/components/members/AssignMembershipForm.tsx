"use client";

import { useState, type FormEvent } from "react";
import { Button, ErrorNote, Field, Input, Select } from "@/components/shared/ui";
import { formatCurrency, todayISO } from "@/lib/utils";
import { post } from "@/services/api";
import type { Member, Membership, MembershipPlan } from "@/types";

export function AssignMembershipForm({
  members,
  plans,
  defaultMemberId,
  onSaved,
}: {
  members: Member[];
  plans: MembershipPlan[];
  defaultMemberId?: string;
  onSaved: (m: Membership) => void;
}) {
  const [memberId, setMemberId] = useState(defaultMemberId ?? "");
  const [planId, setPlanId] = useState(plans[0]?.id ?? "");
  const [startDate, setStartDate] = useState(todayISO());
  const [amount, setAmount] = useState("");
  const [paid, setPaid] = useState(true);
  const [method, setMethod] = useState("upi");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const plan = plans.find((p) => p.id === planId);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      onSaved(
        await post<Membership>("/memberships", {
          member_id: memberId,
          plan_id: planId,
          start_date: startDate,
          amount: amount ? Number(amount) : undefined,
          paid,
          payment_method: paid ? method : undefined,
        }),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not assign membership");
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="space-y-4">
      <ErrorNote message={error} />
      {!defaultMemberId && (
        <Field label="Member">
          <Select required value={memberId} onChange={(e) => setMemberId(e.target.value)} placeholder="Select member"
            options={members.map((m) => ({ value: m.id, label: `${m.full_name} · ${m.phone}` }))} />
        </Field>
      )}
      <Field label="Plan">
        <Select required value={planId} onChange={(e) => setPlanId(e.target.value)}
          options={plans.map((p) => ({ value: p.id, label: `${p.name} · ${p.duration_days} days · ${formatCurrency(p.price)}` }))} />
      </Field>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Start date"><Input type="date" required value={startDate} onChange={(e) => setStartDate(e.target.value)} /></Field>
        <Field label="Amount" hint={plan ? `Plan price ${formatCurrency(plan.price)}` : undefined}>
          <Input type="number" min={0} value={amount} placeholder={plan ? String(plan.price) : ""} onChange={(e) => setAmount(e.target.value)} />
        </Field>
      </div>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={paid} onChange={(e) => setPaid(e.target.checked)} className="h-4 w-4 accent-[rgb(var(--brand))]" />
        Fee collected now
      </label>
      {paid && (
        <Field label="Payment method">
          <Select value={method} onChange={(e) => setMethod(e.target.value)} options={["upi", "cash", "card", "bank_transfer"]} />
        </Field>
      )}
      <div className="flex justify-end">
        <Button type="submit" loading={saving} disabled={!memberId || !planId}>Assign membership</Button>
      </div>
    </form>
  );
}
