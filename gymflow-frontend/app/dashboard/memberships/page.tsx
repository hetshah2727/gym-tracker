"use client";

import { Pencil, Plus, RefreshCw, XCircle } from "lucide-react";
import { useState, type FormEvent } from "react";
import { AssignMembershipForm } from "@/components/members/AssignMembershipForm";
import { Badge, Button, Card, EmptyState, ErrorNote, Field, Input, Loading, Modal, PageHeader, Tabs, Textarea } from "@/components/shared/ui";
import { useApi } from "@/hooks/useApi";
import { useMemberNames, usePlans } from "@/hooks/useLookups";
import { formatCurrency, formatDate } from "@/lib/utils";
import { patch, post } from "@/services/api";
import type { Membership, MembershipPlan } from "@/types";

type View = "expiring" | "active" | "expired" | "all";

export default function MembershipsPage() {
  const [view, setView] = useState<View>("expiring");
  const query =
    view === "expiring" ? { expiring_within_days: 14 } : view === "all" ? {} : { status: view };
  const { data, loading, error, reload } = useApi<Membership[]>("/memberships", query);
  const { members, names } = useMemberNames();
  const { plans, names: planNames, reload: reloadPlans } = usePlans(true);
  const [assigning, setAssigning] = useState(false);
  const [editingPlan, setEditingPlan] = useState<MembershipPlan | "new" | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  async function act(id: string, action: "renew" | "cancel") {
    if (action === "cancel" && !confirm("Cancel this membership?")) return;
    setBusy(id);
    try {
      await post(`/memberships/${id}/${action}`, action === "renew" ? { paid: false } : undefined);
      reload();
    } finally {
      setBusy(null);
    }
  }

  return (
    <>
      <PageHeader
        title="Memberships"
        description="Plans, renewals and expiry tracking."
        actions={<Button onClick={() => setAssigning(true)}><Plus className="h-4 w-4" /> Assign membership</Button>}
      />

      <Card title="Plans" className="mb-6" actions={<Button size="sm" variant="secondary" onClick={() => setEditingPlan("new")}><Plus className="h-3.5 w-3.5" /> New plan</Button>}>
        <div className="grid gap-3 p-4 sm:grid-cols-2 lg:grid-cols-4">
          {plans.map((p) => (
            <div key={p.id} className={`rounded-lg border border-border p-4 ${p.is_active ? "" : "opacity-50"}`}>
              <div className="flex items-start justify-between">
                <p className="font-medium">{p.name}</p>
                <button onClick={() => setEditingPlan(p)} className="text-muted hover:text-fg" aria-label={`Edit ${p.name}`}><Pencil className="h-3.5 w-3.5" /></button>
              </div>
              <p className="mt-2 text-xl font-semibold tabular-nums">{formatCurrency(p.price)}</p>
              <p className="text-xs text-muted">{p.duration_days} days{p.is_active ? "" : " · archived"}</p>
            </div>
          ))}
        </div>
      </Card>

      <Tabs<View>
        value={view}
        onChange={setView}
        tabs={[
          { value: "expiring", label: "Expiring in 14 days" },
          { value: "active", label: "Active" },
          { value: "expired", label: "Expired" },
          { value: "all", label: "All" },
        ]}
      />
      <Card>
        {error && <div className="p-4"><ErrorNote message={error} /></div>}
        {loading && !data ? (
          <Loading />
        ) : !data?.length ? (
          <EmptyState title="Nothing here" description={view === "expiring" ? "No memberships end in the next two weeks." : "No memberships match this view."} />
        ) : (
          <div className="overflow-x-auto">
            <table className="table-base">
              <thead>
                <tr><th>Member</th><th>Plan</th><th>Period</th><th>Days left</th><th>Amount</th><th>Status</th><th className="text-right">Actions</th></tr>
              </thead>
              <tbody>
                {data.map((m) => (
                  <tr key={m.id}>
                    <td className="font-medium">{names[m.member_id] ?? "—"}</td>
                    <td className="text-muted">{m.plan_id ? planNames[m.plan_id] : "—"}</td>
                    <td className="whitespace-nowrap text-muted">{formatDate(m.start_date)} – {formatDate(m.end_date)}</td>
                    <td className={`tabular-nums ${m.days_left !== null && m.days_left <= 3 ? "text-danger" : m.days_left !== null && m.days_left <= 7 ? "text-warning" : ""}`}>
                      {m.status === "active" ? m.days_left : "—"}
                    </td>
                    <td className="tabular-nums">{formatCurrency(m.amount)}</td>
                    <td><Badge value={m.status} /></td>
                    <td className="text-right">
                      <div className="flex justify-end gap-1">
                        {m.status !== "cancelled" && (
                          <Button size="sm" variant="secondary" loading={busy === m.id} onClick={() => act(m.id, "renew")}><RefreshCw className="h-3.5 w-3.5" /> Renew</Button>
                        )}
                        {m.status === "active" && (
                          <Button size="sm" variant="ghost" onClick={() => act(m.id, "cancel")} aria-label="Cancel"><XCircle className="h-3.5 w-3.5" /></Button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Modal open={assigning} onClose={() => setAssigning(false)} title="Assign membership">
        {assigning && <AssignMembershipForm members={members} plans={plans.filter((p) => p.is_active)} onSaved={() => { setAssigning(false); reload(); }} />}
      </Modal>
      <Modal open={editingPlan !== null} onClose={() => setEditingPlan(null)} title={editingPlan === "new" ? "New plan" : "Edit plan"}>
        {editingPlan !== null && <PlanForm plan={editingPlan === "new" ? undefined : editingPlan} onSaved={() => { setEditingPlan(null); reloadPlans(); }} />}
      </Modal>
    </>
  );
}

function PlanForm({ plan, onSaved }: { plan?: MembershipPlan; onSaved: () => void }) {
  const [form, setForm] = useState({
    name: plan?.name ?? "",
    duration_days: String(plan?.duration_days ?? 30),
    price: String(plan?.price ?? ""),
    description: plan?.description ?? "",
    is_active: plan?.is_active ?? true,
  });
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    const body = { ...form, duration_days: Number(form.duration_days), price: Number(form.price) };
    try {
      if (plan) await patch(`/membership-plans/${plan.id}`, body);
      else await post("/membership-plans", body);
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
      <Field label="Plan name"><Input required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Duration (days)"><Input type="number" min={1} required value={form.duration_days} onChange={(e) => setForm({ ...form, duration_days: e.target.value })} /></Field>
        <Field label="Price"><Input type="number" min={0} required value={form.price} onChange={(e) => setForm({ ...form, price: e.target.value })} /></Field>
      </div>
      <Field label="Description"><Textarea value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></Field>
      {plan && (
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={form.is_active} onChange={(e) => setForm({ ...form, is_active: e.target.checked })} /> Available for new memberships
        </label>
      )}
      <div className="flex justify-end"><Button type="submit" loading={saving}>Save plan</Button></div>
    </form>
  );
}
