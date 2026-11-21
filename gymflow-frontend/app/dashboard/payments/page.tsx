"use client";

import { Plus, Wallet } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { PaymentsTable } from "@/components/payments/PaymentsTable";
import { Button, Card, EmptyState, ErrorNote, Field, Input, Loading, Modal, PageHeader, Select, Tabs } from "@/components/shared/ui";
import { useApi } from "@/hooks/useApi";
import { useMemberNames } from "@/hooks/useLookups";
import { formatCurrency, todayISO } from "@/lib/utils";
import { post } from "@/services/api";
import type { Member, Page, Payment } from "@/types";

type View = "" | "pending" | "overdue" | "paid";

export default function PaymentsPage() {
  const [view, setView] = useState<View>("pending");
  const { data, loading, error, reload } = useApi<Page<Payment>>("/payments", { status: view, limit: 100 });
  const { members, names } = useMemberNames();
  const [recording, setRecording] = useState(false);
  const params = useSearchParams();
  useEffect(() => { if (params.get("new") === "1") setRecording(true); }, [params]);
  const total = data?.items.reduce((s, p) => s + Number(p.amount), 0) ?? 0;

  return (
    <>
      <PageHeader
        title="Payments"
        description="Every fee – paid, due and late."
        actions={<Button onClick={() => setRecording(true)}><Plus className="h-4 w-4" /> Take payment</Button>}
      />
      <Tabs<View>
        value={view}
        onChange={setView}
        tabs={[
          { value: "pending", label: "Due" },
          { value: "overdue", label: "Late" },
          { value: "paid", label: "Paid" },
          { value: "", label: "All" },
        ]}
      />
      <Card title={data ? `${data.total} payments · ${formatCurrency(total)}` : undefined}>
        {error && <div className="p-4"><ErrorNote message={error} /></div>}
        {loading && !data ? (
          <Loading />
        ) : !data?.items.length ? (
          <EmptyState icon={<Wallet className="h-8 w-8" />} title="No payments" description="Nothing matches this filter." />
        ) : (
          <PaymentsTable payments={data.items} names={names} onChanged={reload} />
        )}
      </Card>
      <Modal open={recording} onClose={() => setRecording(false)} title="Take a payment">
        {recording && <RecordPaymentForm members={members} onSaved={() => { setRecording(false); reload(); }} />}
      </Modal>
    </>
  );
}

function RecordPaymentForm({ members, onSaved }: { members: Member[]; onSaved: () => void }) {
  const [form, setForm] = useState({ member_id: "", amount: "", method: "cash", paid: true, due_date: todayISO(), reference: "" });
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      await post("/payments", { ...form, amount: Number(form.amount), reference: form.reference || undefined });
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save");
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="space-y-4">
      <ErrorNote message={error} />
      <Field label="Member">
        <Select required value={form.member_id} onChange={(e) => setForm({ ...form, member_id: e.target.value })} placeholder="Select member"
          options={members.map((m) => ({ value: m.id, label: `${m.full_name} · ${m.phone}` }))} />
      </Field>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Amount"><Input type="number" min={1} required value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} /></Field>
        <Field label={form.paid ? "Date" : "Due date"}><Input type="date" value={form.due_date} onChange={(e) => setForm({ ...form, due_date: e.target.value })} /></Field>
      </div>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={form.paid} onChange={(e) => setForm({ ...form, paid: e.target.checked })} /> Already paid
      </label>
      {form.paid && (
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Method"><Select value={form.method} onChange={(e) => setForm({ ...form, method: e.target.value })} options={["cash", "upi", "card", "bank_transfer"]} /></Field>
          <Field label="Reference (optional)"><Input value={form.reference} onChange={(e) => setForm({ ...form, reference: e.target.value })} placeholder="UPI txn id" /></Field>
        </div>
      )}
      <div className="flex justify-end"><Button type="submit" loading={saving}>Save</Button></div>
    </form>
  );
}
