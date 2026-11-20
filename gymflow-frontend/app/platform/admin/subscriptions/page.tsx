"use client";

import { Pencil, Plus } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Badge, Button, ErrorNote, Field, Input, Loading, Modal, PageHeader } from "@/components/shared/ui";
import { useApi } from "@/hooks/useApi";
import { formatCurrency, humanize } from "@/lib/utils";
import { patch, post } from "@/services/api";
import type { SubscriptionPlan } from "@/types";

const FEATURES = ["automation", "ai_diet", "affiliate", "website_builder", "voice_calls"];

export default function AdminSubscriptions() {
  const { data, loading, reload } = useApi<SubscriptionPlan[]>("/subscriptions/plans");
  const [editing, setEditing] = useState<SubscriptionPlan | "new" | null>(null);

  return (
    <>
      <PageHeader title="SaaS plans" description="What gyms pay for GymFlow AI." actions={<Button onClick={() => setEditing("new")}><Plus className="h-4 w-4" /> New plan</Button>} />
      {loading ? <Loading /> : (
        <div className="grid gap-3 md:grid-cols-3">
          {data?.map((p) => (
            <div key={p.id} className="card p-5">
              <div className="flex items-start justify-between">
                <div><p className="font-semibold">{p.name}</p><p className="text-xs text-muted">{p.code}</p></div>
                <button onClick={() => setEditing(p)} className="text-muted hover:text-fg" aria-label="Edit"><Pencil className="h-4 w-4" /></button>
              </div>
              <p className="mt-3 text-2xl font-semibold">{formatCurrency(p.price_monthly)}<span className="text-sm font-normal text-muted">/mo</span></p>
              <p className="text-xs text-muted">{p.max_members ? `Up to ${p.max_members} members` : "Unlimited members"}</p>
              <div className="mt-3 flex flex-wrap gap-1">
                {FEATURES.filter((f) => p.features[f]).map((f) => <Badge key={f} value={f} className="bg-surface-2 text-fg" />)}
              </div>
            </div>
          ))}
        </div>
      )}
      <Modal open={editing !== null} onClose={() => setEditing(null)} title={editing === "new" ? "New plan" : "Edit plan"}>
        {editing !== null && <PlanForm plan={editing === "new" ? undefined : editing} onSaved={() => { setEditing(null); reload(); }} />}
      </Modal>
    </>
  );
}

function PlanForm({ plan, onSaved }: { plan?: SubscriptionPlan; onSaved: () => void }) {
  const [form, setForm] = useState({ code: plan?.code ?? "", name: plan?.name ?? "", price_monthly: String(plan?.price_monthly ?? ""), max_members: String(plan?.max_members ?? "") });
  const [features, setFeatures] = useState<Record<string, boolean>>(plan?.features ?? Object.fromEntries(FEATURES.map((f) => [f, true])));
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    const body = { name: form.name, price_monthly: Number(form.price_monthly), max_members: form.max_members ? Number(form.max_members) : null, features };
    try {
      if (plan) await patch(`/subscriptions/plans/${plan.id}`, body);
      else await post("/subscriptions/plans", { ...body, code: form.code });
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
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Code"><Input required disabled={!!plan} value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} /></Field>
        <Field label="Name"><Input required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
        <Field label="Price / month"><Input type="number" required min={0} value={form.price_monthly} onChange={(e) => setForm({ ...form, price_monthly: e.target.value })} /></Field>
        <Field label="Max members" hint="Empty = unlimited"><Input type="number" min={1} value={form.max_members} onChange={(e) => setForm({ ...form, max_members: e.target.value })} /></Field>
      </div>
      <div className="grid grid-cols-2 gap-2">
        {FEATURES.map((f) => (
          <label key={f} className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={!!features[f]} onChange={(e) => setFeatures({ ...features, [f]: e.target.checked })} /> {humanize(f)}
          </label>
        ))}
      </div>
      <div className="flex justify-end"><Button type="submit" loading={saving}>Save</Button></div>
    </form>
  );
}
