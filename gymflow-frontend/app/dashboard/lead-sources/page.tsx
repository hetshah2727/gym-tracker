"use client";

import { Copy } from "lucide-react";
import { useState } from "react";
import { HBars } from "@/components/charts/Charts";
import { FeatureGate, Note, percent, useAction, useToast } from "@/components/shared/growth";
import { Badge, Button, Card, EmptyState, Field, Input, Loading, Modal, PageHeader, Select } from "@/components/shared/ui";
import { useApi } from "@/hooks/useApi";
import { formatCurrency, formatDate } from "@/lib/utils";
import { get, post } from "@/services/api";

interface SourceRow { source: string; label: string; leads: number; trials: number; joined: number; revenue_collected: number; conversion_rate: number }
interface Campaign { id: string; name: string; code: string; source: string; channel: string | null; status: string; start_date: string | null; end_date: string | null; budget: number | null }
interface Stats { leads: number; joined: number; conversion_rate: number; revenue_collected_from_joined: number; tracking_link_hint: string }

export default function LeadSourcesPage() {
  const [days, setDays] = useState("90");
  const sources = useApi<SourceRow[]>("/crm/sources", { days });
  const campaigns = useApi<Campaign[]>("/crm/campaigns");
  const site = useApi<{ slug: string }[]>("/websites");
  const [stats, setStats] = useState<Record<string, Stats>>({});
  const [adding, setAdding] = useState(false);
  const [form, setForm] = useState({ name: "", code: "", source: "instagram", channel: "", status: "active", budget: "" });
  const { busy, run } = useAction();
  const toast = useToast();
  const rows = (sources.data ?? []).filter((s) => s.leads > 0).sort((a, b) => b.leads - a.leads);
  const base = typeof window !== "undefined" && site.data?.[0] ? `${window.location.origin}/sites/${site.data[0].slug}` : null;

  return (
    <FeatureGate feature="lead_crm">
      <PageHeader title="Lead sources" description="Where enquiries come from, and which channels turn into paying members."
        actions={<Select className="w-36" value={days} onChange={(e) => setDays(e.target.value)} options={[{ value: "30", label: "30 days" }, { value: "90", label: "90 days" }, { value: "365", label: "12 months" }]} />} />
      <Note className="mb-4">A lead is only credited to Google Maps, AI search or a campaign when there is evidence (a tracking link or the referrer). Everything else stays &quot;website&quot; or what staff recorded.</Note>
      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Enquiries by source">
          <div className="p-4">{sources.loading ? <Loading /> : rows.length ? <HBars data={rows.map((r) => ({ label: r.label, value: r.leads }))} valueLabel="Enquiries" /> : <EmptyState title="No enquiries in this period" />}</div>
        </Card>
        <Card title="Revenue collected from members who joined">
          <div className="p-4">{rows.some((r) => r.revenue_collected) ? <HBars money data={rows.filter((r) => r.revenue_collected).map((r) => ({ label: r.label, value: r.revenue_collected }))} valueLabel="Collected" /> : <EmptyState title="No paid conversions yet" />}</div>
        </Card>
      </div>
      <Card title="Source performance" className="mt-4">
        <div className="overflow-x-auto"><table className="table-base">
          <thead><tr><th>Source</th><th>Enquiries</th><th>Trials</th><th>Joined</th><th>Conversion</th><th>Collected</th></tr></thead>
          <tbody>{rows.map((r) => <tr key={r.source}><td>{r.label}</td><td className="tabular-nums">{r.leads}</td><td className="tabular-nums">{r.trials}</td><td className="tabular-nums">{r.joined}</td><td>{percent(r.conversion_rate)}</td><td className="tabular-nums">{formatCurrency(r.revenue_collected)}</td></tr>)}</tbody>
        </table></div>
      </Card>
      <Card title="Campaigns & tracking links" className="mt-4" actions={<Button size="sm" onClick={() => setAdding(true)}>New campaign</Button>}>
        {campaigns.loading ? <Loading /> : !campaigns.data?.length ? <EmptyState title="No campaigns" description="Create one to get a tracking link for posters, Instagram or your Google profile." /> : (
          <ul className="divide-y divide-border/60">
            {campaigns.data.map((c) => (
              <li key={c.id} className="px-4 py-3 text-sm">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div><p className="font-medium">{c.name} <Badge value={c.status === "active" ? "active" : c.status} className="ml-1" /></p>
                    <p className="text-xs text-muted">code {c.code} · {c.source.replace(/_/g, " ")}{c.start_date ? ` · from ${formatDate(c.start_date)}` : ""}{c.budget ? ` · budget ${formatCurrency(c.budget)}` : ""}</p></div>
                  <div className="flex gap-2">
                    <Button size="sm" variant="secondary" onClick={() => run(c.id, () => get<Stats>(`/crm/campaigns/${c.id}/stats`)).then((s) => s && setStats((x) => ({ ...x, [c.id]: s })))}>Results</Button>
                    {base && <Button size="sm" variant="ghost" onClick={async () => { const s = stats[c.id] ?? await get<Stats>(`/crm/campaigns/${c.id}/stats`); navigator.clipboard?.writeText(base + s.tracking_link_hint); toast("Tracking link copied"); }}><Copy className="h-3.5 w-3.5" /> Link</Button>}
                  </div>
                </div>
                {stats[c.id] && <p className="mt-1 text-xs text-muted">{stats[c.id].leads} enquiries · {stats[c.id].joined} joined ({percent(stats[c.id].conversion_rate)}) · {formatCurrency(stats[c.id].revenue_collected_from_joined)} collected from them</p>}
              </li>
            ))}
          </ul>
        )}
      </Card>
      <Modal open={adding} onClose={() => setAdding(false)} title="New campaign">
        <form className="grid gap-3" onSubmit={(e) => { e.preventDefault(); run("add", () => post("/crm/campaigns", { ...form, channel: form.channel || undefined, budget: form.budget ? Number(form.budget) : undefined }), "Campaign created").then((r) => { if (r) { setAdding(false); campaigns.reload(); } }); }}>
          <Field label="Name"><Input required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value, code: form.code || e.target.value.toLowerCase().replace(/[^a-z0-9]+/g, "_").slice(0, 40) })} /></Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Code (utm_campaign)" hint="lowercase, digits, _ or -"><Input required value={form.code} pattern="[a-z0-9_\-]+" onChange={(e) => setForm({ ...form, code: e.target.value })} /></Field>
            <Field label="Source"><Select value={form.source} onChange={(e) => setForm({ ...form, source: e.target.value })} options={["instagram", "paid_campaign", "google_business_profile", "qr_code", "referral", "corporate", "other"]} /></Field>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Channel"><Input value={form.channel} onChange={(e) => setForm({ ...form, channel: e.target.value })} placeholder="e.g. poster, reels" /></Field>
            <Field label="Budget (₹)"><Input type="number" min={0} value={form.budget} onChange={(e) => setForm({ ...form, budget: e.target.value })} /></Field>
          </div>
          <div className="flex justify-end"><Button type="submit" loading={busy === "add"}>Create</Button></div>
        </form>
      </Modal>
    </FeatureGate>
  );
}
