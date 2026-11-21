"use client";

import { Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { ConfirmDialog, FeatureGate, Note, SourceBadge, useAction } from "@/components/shared/growth";
import { Button, Card, EmptyState, Field, Input, Loading, Modal, PageHeader } from "@/components/shared/ui";
import { useApi } from "@/hooks/useApi";
import { del, post } from "@/services/api";

interface Row { id: string; name: string; rating: number | null; review_count: number | null; reviews_last_90_days: number | null; services: string[]; categories: string[]; area: string | null; distance_km: number | null; website: string | null; source: string }
interface Report { ours: { name: string; rating: number | null; review_count: number | null; reviews_last_90_days: number; services: string[]; categories: string[]; profile_completeness: number | null; source: string }; competitors: Row[]; opportunities: string[]; note: string }
const blank = { name: "", area: "", website: "", rating: "", review_count: "", reviews_last_90_days: "", services: "", categories: "" };

export default function CompetitorsPage() {
  const report = useApi<Report>("/local/competitors/report");
  const [form, setForm] = useState(blank);
  const [adding, setAdding] = useState(false);
  const [remove, setRemove] = useState<Row | null>(null);
  const { busy, run } = useAction();
  const num = (v: string) => (v === "" ? null : Number(v));
  const list = (v: string) => v.split(",").map((x) => x.trim()).filter(Boolean);
  const r = report.data;

  return (
    <FeatureGate feature="local_seo">
      <PageHeader title="Local competitors" description="Compare what you know about nearby gyms with your own profile." actions={<Button onClick={() => setAdding(true)}><Plus className="h-4 w-4" /> Add competitor</Button>} />
      {report.loading || !r ? <Loading /> : <>
        <Note className="mb-4">{r.note}</Note>
        <Card title="Opportunities">
          {r.opportunities.length ? <ul className="list-disc space-y-1 py-3 pl-9 pr-4 text-sm">{r.opportunities.map((o) => <li key={o}>{o}</li>)}</ul> : <EmptyState title="No gaps found yet" description="Add competitors with their services and review counts." />}
        </Card>
        <Card title="Side by side" className="mt-4">
          {!r.competitors.length ? <EmptyState title="No competitors added" /> : <div className="overflow-x-auto"><table className="table-base">
            <thead><tr><th>Gym</th><th>Area</th><th>Rating</th><th>Reviews</th><th>Last 90 days</th><th>Services</th><th>Source</th><th></th></tr></thead>
            <tbody>
              <tr className="bg-brand/5"><td className="font-medium">{r.ours.name} (you)</td><td>—</td><td>{r.ours.rating ?? "—"}</td><td>{r.ours.review_count ?? "—"}</td><td>{r.ours.reviews_last_90_days}</td><td className="text-xs">{r.ours.services.join(", ")}</td><td><SourceBadge source={r.ours.source} /></td><td /></tr>
              {r.competitors.map((c) => <tr key={c.id}><td className="font-medium">{c.name}</td><td className="text-xs">{c.area ?? "—"}</td><td>{c.rating ?? "—"}</td><td>{c.review_count ?? "—"}</td><td>{c.reviews_last_90_days ?? "—"}</td><td className="text-xs">{c.services.join(", ")}</td><td><SourceBadge source={c.source} /></td>
                <td><button aria-label="Remove" onClick={() => setRemove(c)} className="text-muted hover:text-danger"><Trash2 className="h-4 w-4" /></button></td></tr>)}
            </tbody></table></div>}
        </Card>
      </>}
      <Modal open={adding} onClose={() => setAdding(false)} title="Add competitor">
        <form className="grid gap-3 sm:grid-cols-2" onSubmit={(e) => { e.preventDefault(); run("add", () => post("/local/competitors", { name: form.name, area: form.area || null, website: form.website || null, rating: num(form.rating), review_count: num(form.review_count), reviews_last_90_days: num(form.reviews_last_90_days), services: list(form.services), categories: list(form.categories) }), "Competitor added").then(() => { setAdding(false); setForm(blank); report.reload(); }); }}>
          <Field label="Name" className="sm:col-span-2"><Input required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
          <Field label="Area"><Input value={form.area} onChange={(e) => setForm({ ...form, area: e.target.value })} /></Field>
          <Field label="Website"><Input value={form.website} onChange={(e) => setForm({ ...form, website: e.target.value })} /></Field>
          <Field label="Rating (as shown on Google)"><Input type="number" step={0.1} min={1} max={5} value={form.rating} onChange={(e) => setForm({ ...form, rating: e.target.value })} /></Field>
          <Field label="Review count"><Input type="number" min={0} value={form.review_count} onChange={(e) => setForm({ ...form, review_count: e.target.value })} /></Field>
          <Field label="Reviews in last 90 days"><Input type="number" min={0} value={form.reviews_last_90_days} onChange={(e) => setForm({ ...form, reviews_last_90_days: e.target.value })} /></Field>
          <Field label="Categories (comma separated)"><Input value={form.categories} onChange={(e) => setForm({ ...form, categories: e.target.value })} /></Field>
          <Field label="Services (comma separated)" className="sm:col-span-2"><Input value={form.services} onChange={(e) => setForm({ ...form, services: e.target.value })} /></Field>
          <div className="sm:col-span-2 flex justify-end"><Button type="submit" loading={busy === "add"}>Save</Button></div>
        </form>
      </Modal>
      <ConfirmDialog open={!!remove} danger title="Remove competitor?" message={remove?.name} confirmLabel="Remove" onClose={() => setRemove(null)}
        onConfirm={() => remove && run("del", () => del(`/local/competitors/${remove.id}`), "Removed").then(() => { setRemove(null); report.reload(); })} />
    </FeatureGate>
  );
}
