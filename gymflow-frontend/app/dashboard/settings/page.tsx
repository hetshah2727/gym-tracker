"use client";

import { Check, LifeBuoy } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { Badge, Button, Card, ErrorNote, Field, Input, Loading, PageHeader, Select, Tabs, Textarea } from "@/components/shared/ui";
import { useApi } from "@/hooks/useApi";
import { formatCurrency, formatDate, formatDateTime, humanize } from "@/lib/utils";
import { patch, post } from "@/services/api";
import type { Gym, GymSubscription, SubscriptionPlan } from "@/types";

type View = "profile" | "billing" | "support";

export default function SettingsPage() {
  const [view, setView] = useState<View>("profile");
  return (
    <>
      <PageHeader title="Settings" />
      <Tabs<View> value={view} onChange={setView} tabs={[{ value: "profile", label: "Gym profile" }, { value: "billing", label: "Subscription" }, { value: "support", label: "Support" }]} />
      {view === "profile" && <ProfileForm />}
      {view === "billing" && <Billing />}
      {view === "support" && <Support />}
    </>
  );
}

function ProfileForm() {
  const { data: gym, reload } = useApi<Gym>("/gym");
  const [form, setForm] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (gym) setForm({ name: gym.name, phone: gym.phone ?? "", email: gym.email ?? "", address: gym.address ?? "", city: gym.city ?? "", logo_url: gym.logo_url ?? "", timezone: gym.timezone, currency: gym.currency });
  }, [gym]);

  if (!gym) return <Loading />;
  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => { setForm({ ...form, [k]: e.target.value }); setSaved(false); };

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      await patch("/gym", Object.fromEntries(Object.entries(form).map(([k, v]) => [k, v || null])));
      setSaved(true);
      reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card>
      <form onSubmit={onSubmit} className="space-y-4 p-5">
        <ErrorNote message={error} />
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Gym name"><Input required value={form.name ?? ""} onChange={set("name")} /></Field>
          <Field label="Phone (shown to members)"><Input value={form.phone ?? ""} onChange={set("phone")} /></Field>
          <Field label="Email"><Input type="email" value={form.email ?? ""} onChange={set("email")} /></Field>
          <Field label="City"><Input value={form.city ?? ""} onChange={set("city")} /></Field>
        </div>
        <Field label="Address"><Textarea value={form.address ?? ""} onChange={set("address")} /></Field>
        <div className="grid gap-4 sm:grid-cols-3">
          <Field label="Logo URL"><Input value={form.logo_url ?? ""} onChange={set("logo_url")} /></Field>
          <Field label="Currency"><Select value={form.currency ?? "INR"} onChange={set("currency")} options={["INR", "USD", "AED", "GBP"].map((c) => ({ value: c, label: c }))} /></Field>
          <Field label="Timezone"><Input value={form.timezone ?? ""} onChange={set("timezone")} /></Field>
        </div>
        <div className="flex items-center justify-end gap-3">
          {saved && <span className="flex items-center gap-1 text-sm text-brand"><Check className="h-4 w-4" /> Saved</span>}
          <Button type="submit" loading={saving}>Save</Button>
        </div>
      </form>
    </Card>
  );
}

function Billing() {
  const current = useApi<GymSubscription | null>("/subscriptions/current");
  const plans = useApi<SubscriptionPlan[]>("/subscriptions/plans");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function change(code: string) {
    setBusy(code);
    setError(null);
    try {
      await post("/subscriptions/change-plan", { plan_code: code });
      current.reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not change plan");
    } finally {
      setBusy(null);
    }
  }

  if (current.loading || plans.loading) return <Loading />;
  const sub = current.data;
  return (
    <div className="space-y-4">
      <ErrorNote message={error} />
      {sub && (
        <Card className="p-5">
          <p className="text-sm text-muted">Current plan</p>
          <div className="mt-1 flex items-center gap-2">
            <p className="text-lg font-semibold">{sub.plan?.name}</p>
            <Badge value={sub.status} />
          </div>
          <p className="mt-1 text-sm text-muted">{sub.status === "trialing" ? "Trial ends" : "Renews"} {formatDate(sub.current_period_end)}</p>
        </Card>
      )}
      <div className="grid gap-3 md:grid-cols-3">
        {plans.data?.map((p) => {
          const isCurrent = sub?.plan_id === p.id;
          return (
            <div key={p.id} className={`card flex flex-col p-5 ${isCurrent ? "border-brand" : ""}`}>
              <p className="font-semibold">{p.name}</p>
              <p className="mt-2 text-2xl font-semibold">{formatCurrency(p.price_monthly)}<span className="text-sm font-normal text-muted">/mo</span></p>
              <p className="mt-1 text-xs text-muted">{p.max_members ? `Up to ${p.max_members} members` : "Unlimited members"}</p>
              <ul className="mt-4 flex-1 space-y-1.5 text-sm">
                {Object.entries(p.features).map(([k, on]) => (
                  <li key={k} className={on ? "" : "text-muted line-through"}>{humanize(k)}</li>
                ))}
              </ul>
              <Button className="mt-4" variant={isCurrent ? "secondary" : "primary"} disabled={isCurrent} loading={busy === p.code} onClick={() => change(p.code)}>
                {isCurrent ? "Current plan" : "Switch"}
              </Button>
            </div>
          );
        })}
      </div>
    </div>
  );
}

interface Ticket { id: string; subject: string; status: string; priority: string; created_at: string }

function Support() {
  const tickets = useApi<Ticket[]>("/support/tickets");
  const [form, setForm] = useState({ subject: "", description: "", priority: "medium" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card title="Contact GymFlow support">
        <form
          className="space-y-4 p-4"
          onSubmit={async (e) => {
            e.preventDefault();
            setBusy(true);
            setError(null);
            try {
              await post("/support/tickets", form);
              setForm({ subject: "", description: "", priority: "medium" });
              tickets.reload();
            } catch (err) {
              setError(err instanceof Error ? err.message : "Could not submit");
            } finally {
              setBusy(false);
            }
          }}
        >
          <ErrorNote message={error} />
          <Field label="Subject"><Input required minLength={3} value={form.subject} onChange={(e) => setForm({ ...form, subject: e.target.value })} /></Field>
          <Field label="Describe the issue"><Textarea rows={5} required value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></Field>
          <Field label="Priority"><Select value={form.priority} onChange={(e) => setForm({ ...form, priority: e.target.value })} options={["low", "medium", "high"]} /></Field>
          <div className="flex justify-end"><Button type="submit" loading={busy}><LifeBuoy className="h-4 w-4" /> Submit ticket</Button></div>
        </form>
      </Card>
      <Card title="Your tickets">
        <ul className="divide-y divide-border/60">
          {tickets.data?.length ? tickets.data.map((t) => (
            <li key={t.id} className="flex items-center justify-between px-4 py-3 text-sm">
              <div><p className="font-medium">{t.subject}</p><p className="text-xs text-muted">{formatDateTime(t.created_at)} · {humanize(t.priority)}</p></div>
              <Badge value={t.status} />
            </li>
          )) : <li className="px-4 py-6 text-center text-sm text-muted">No tickets.</li>}
        </ul>
      </Card>
    </div>
  );
}
